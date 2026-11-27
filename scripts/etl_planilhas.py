#!/usr/bin/env python3
"""ETL — higienização e carga inicial das 3 planilhas nas tabelas das novas abas (schema pregao_atas).

Origem: "Script 3" do Gemini, com correções:
  * CNPJ ALFANUMÉRICO aceito (o original descartava qualquer CNPJ que não fosse 14 dígitos numéricos);
  * IDEMPOTENTE (pode rodar de novo): pregões por UNIQUE (data, número, órgão); itens por ON CONFLICT;
    consumo legado é recarregado com --recarregar-consumo;
  * status de entrega DESCONHECIDO não vira 'FATURADO' em silêncio (o original fazia isso): vai para o log de rejeitados;
  * --dry-run lê e valida tudo SEM tocar no banco; gera CSVs de inconsistências;
  * --data-corte: pedidos recebidos a partir da data NÃO entram (passam a vir do Portal Licitações, evitando contar 2x).

Uso:
  python scripts/etl_planilhas.py --concorrentes Concorrentes-db.xlsx \
      --registros "RELATÓRIO DE REGISTROS 1.0 NOVA.xlsx" --entregas "CONTROLE DE ENTREGA 2025 - 2026.xlsx" --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.domain.validators import cnpj_valido, limpar_cnpj  # noqa: E402

STATUS_MAP = {
    "FATURADO": "FATURADO", "ENTREGUE": "ENTREGUE", "EMP. CANCELADO": "EMP_CANCELADO",
    "CARTA DE CORREÇÃO": "CARTA_DE_CORRECAO", "AG. ESTOQUE": "AG_ESTOQUE",
    "FATURADO DUPLICADO": "FATURADO_DUPLICADO", "LANÇADO NO SISTEMA": "LANCADO_NO_SISTEMA",
    "TROCA DE MARCA": "TROCA_DE_MARCA", "EMP. RECEBIDO": "CHEGADA",
}


# ------------------------------------------------------------------ normalizações (puras)
def normalizar_empresa(valor) -> str:
    if pd.isna(valor):
        return "Empresa/SC"
    txt = str(valor).strip().upper()
    return "Empresa/SC" if txt in {"EMPRESA DEMO SC", "EMPRESADEMOSC", "EMPRESA DEMO", "EMPRESA DEMO/SC"} else txt


def normalizar_vendedor(valor) -> str:
    if pd.isna(valor):
        return "NÃO INFORMADO"
    txt = str(valor).strip().upper().replace("*", "")
    return {"GULHERME": "GUILHERME"}.get(txt, txt)  # ajuste conforme os erros de digitação reais da planilha


def normalizar_status_entrega(valor):
    """Retorna o status interno ou None (desconhecido -> rejeitado, nunca assume FATURADO)."""
    return STATUS_MAP.get(str(valor).strip().upper())


def _data(valor):
    d = pd.to_datetime(valor, errors="coerce")
    return None if pd.isna(d) else d.date()


def _txt(valor):
    return None if pd.isna(valor) else str(valor).strip()


# ------------------------------------------------------------------ preparação (pura, testável)
def preparar_concorrentes(df: pd.DataFrame):
    df = df.copy()
    df["cnpj_clean"] = df["CNPJ"].apply(limpar_cnpj)
    invalidos = df[df["cnpj_clean"].isna()].copy()
    cnpj_dv_ruim = df[df["cnpj_clean"].notna() & ~df["cnpj_clean"].apply(cnpj_valido)].copy()
    validos = df.dropna(subset=["cnpj_clean"]).drop_duplicates(subset=["cnpj_clean"], keep="first").copy()
    return validos, invalidos, cnpj_dv_ruim


def preparar_catalogo(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["CÓDIGO"].astype(str).str.strip() != "-"].copy()
    df["sku"] = df["CÓDIGO"].astype(str).str.strip()
    return df.drop_duplicates(subset=["sku"], keep="first")


def preparar_registros(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Pregao_clean"] = df["Pregão"].fillna("SEM_NUMERO").astype(str).str.strip()
    df["CNPJ_clean"] = df["CNPJ"].apply(limpar_cnpj)
    df["Empresa_clean"] = df["Empresa"].apply(normalizar_empresa)
    df["Vendedor_clean"] = df["Representante"].apply(normalizar_vendedor)
    df["SKU_clean"] = df["Código"].astype(str).str.strip()
    return df


def preparar_entregas(df: pd.DataFrame, data_corte=None):
    """Retorna (aceitas, rejeitadas). Rejeita status desconhecido, quantidade/valor inválidos e, se informado, pedidos >= data_corte."""
    df = df.dropna(subset=["STATUS", "QUANTIDADE", "EMPENHO/PEDIDO/AF"]).copy()
    df["status_interno"] = df["STATUS"].apply(normalizar_status_entrega)
    df["qtde"] = pd.to_numeric(df["QUANTIDADE"], errors="coerce")
    df["vunit"] = pd.to_numeric(df["VALOR UNITÁRIO"], errors="coerce")
    df["recebimento_d"] = df["RECEBIMENTO"].apply(_data)
    motivo = pd.Series("", index=df.index)
    motivo[df["status_interno"].isna()] = "status desconhecido"
    motivo[(df["qtde"].isna()) | (df["qtde"] <= 0)] = "quantidade inválida"
    motivo[df["vunit"].isna()] = "valor unitário inválido"
    if data_corte is not None:
        motivo[(motivo == "") & df["recebimento_d"].apply(lambda d: d is not None and d >= data_corte)] = "após data de corte (vem do Portal)"
    df["motivo_rejeicao"] = motivo
    return df[motivo == ""].copy(), df[motivo != ""].copy()


def _sku_base(valor):
    return None if pd.isna(valor) else str(valor).split(".")[0].strip()


# ------------------------------------------------------------------ carga (SQL)
def carregar(engine, args, dados) -> None:
    from sqlalchemy import text
    import uuid  # noqa: F401

    with engine.begin() as conn:
        conn.execute(text("SET search_path = pregao_atas, public, extensions"))

        for _, r in dados["concorrentes"].iterrows():
            conn.execute(text("""INSERT INTO concorrentes (nome_abreviado, razao_social, cnpj_clean, municipio, uf, data_chegada)
                                 VALUES (:a, :s, :c, :m, :u, COALESCE(:ch, NOW())) ON CONFLICT (cnpj_clean) DO NOTHING"""),
                         {"a": str(r["Abreviado"]).strip().upper(), "s": str(r["Social"]).strip().upper(), "c": r["cnpj_clean"],
                          "m": _txt(r["Município"]), "u": str(r["UF"]).strip().upper()[:2],
                          "ch": None if pd.isna(r["CHEGADA"]) else pd.to_datetime(r["CHEGADA"]).to_pydatetime()})

        for _, r in dados["catalogo"].iterrows():
            conn.execute(text("""INSERT INTO produtos_catalogo (sku, marca, modelo, medida, descricao_origem, categoria)
                                 VALUES (:sku, :ma, :mo, :me, :d, :c)
                                 ON CONFLICT (sku) DO UPDATE SET marca = EXCLUDED.marca, modelo = EXCLUDED.modelo,
                                   medida = EXCLUDED.medida, descricao_origem = EXCLUDED.descricao_origem, categoria = EXCLUDED.categoria"""),
                         {"sku": r["sku"], "ma": str(r["MARCA"]).strip().upper(), "mo": str(r["MODELO"]).strip().upper(),
                          "me": _txt(r["MEDIDA"]), "d": str(r["DESCRIÇÃO DEMO"]).strip(), "c": str(r["CATEGORIA"]).strip().upper()})

        for nome in dados["orgaos"]:
            conn.execute(text("INSERT INTO orgaos_publicos (nome) VALUES (:n) ON CONFLICT DO NOTHING"), {"n": nome})

        mapa = {}
        reg = dados["registros"]
        for (num, orgao, data_lic), grp in reg.groupby(["Pregao_clean", "Órgão" if "Órgão" in reg else "Orgão", "Data Licitação"], dropna=False):
            p = grp.iloc[0]
            uf = (_txt(p["Estado"]) or "XX").upper()[:2]
            pid = conn.execute(text("""
                INSERT INTO pregoes (data_licitacao, hora_licitacao, numero_pregao, modalidade, empresa, portal, orgao_nome, orgao_cnpj,
                                     uf, porte, situacao, total_itens_edital, itens_disputados, vendedor, observacoes)
                VALUES (:d, '09:00', :n, :mod, :emp, 'IMPORTADO_PLANILHA', :o, :c, :uf, 'AMPLA PARTICIPAÇÃO', 'VITÓRIA PARCIAL',
                        :t, :t, :v, 'Importado da planilha RELATÓRIO DE REGISTROS (hora/portal/porte/situação são valores padrão).')
                ON CONFLICT (data_licitacao, numero_pregao, orgao_nome) DO UPDATE SET updated_at = NOW() RETURNING id"""),
                {"d": _data(data_lic), "n": num, "mod": (_txt(p["Modalidade"]) or "ELETRÔNICO").upper(), "emp": p["Empresa_clean"],
                 "o": str(orgao).strip(), "c": p["CNPJ_clean"], "uf": uf, "t": len(grp), "v": p["Vendedor_clean"]}).scalar()
            contratos = {}
            for _, it in grp.iterrows():
                sku, nitem = it["SKU_clean"], str(it["Item"]).strip()
                conn.execute(text("""INSERT INTO produtos_catalogo (sku, marca, modelo, descricao_origem, categoria)
                                     VALUES (:s, 'LEGADO', 'LEGADO', :d, :c) ON CONFLICT (sku) DO NOTHING"""),
                             {"s": sku, "d": str(it["Descrição"]).strip(), "c": str(it["Categoria"]).strip().upper()})
                vunit = float(it["Valor Unit"])
                cid = conn.execute(text("""
                    INSERT INTO cotacao_itens (pregao_id, numero_item, sku, descricao, categoria, quantidade, valor_unit_minimo,
                                               valor_unit_vencedor, vencedor_tipo, status_item)
                    VALUES (:p, :n, :s, :d, :c, :q, :v, :v, 'PROPRIA', 'REGISTRADO')
                    ON CONFLICT (pregao_id, numero_item) DO UPDATE SET updated_at = NOW() RETURNING id"""),
                    {"p": pid, "n": nitem, "s": sku, "d": str(it["Descrição"]).strip(), "c": str(it["Categoria"]).strip().upper(),
                     "q": int(it["Qtde"]), "v": vunit}).scalar()
                dct = _data(it["Data contrato"]) or _data(data_lic)
                nome_ct = _txt(it["CONTRATO"]) or "SEM_NUMERO"
                chave = (nome_ct, dct)
                if chave not in contratos:
                    obs = (_txt(it["OBS"]) or "")
                    vig = "6_MESES" if "6 MESES" in obs.upper() else "12_MESES"  # padrão do script original; revisar caso a caso
                    ct = conn.execute(text("SELECT id FROM contratos_atas WHERE pregao_id = :p AND nome_contrato = :n AND data_contrato = :d"),
                                      {"p": pid, "n": nome_ct, "d": dct}).scalar()
                    if not ct:
                        ct = conn.execute(text("""INSERT INTO contratos_atas (pregao_id, nome_contrato, data_contrato, tipo_vigencia, observacoes)
                                                  VALUES (:p, :n, :d, :v, :o) RETURNING id"""),
                                          {"p": pid, "n": nome_ct, "d": dct, "v": vig, "o": obs or None}).scalar()
                    contratos[chave] = ct
                aid = conn.execute(text("""INSERT INTO ata_itens (contrato_ata_id, cotacao_item_id, numero_item, sku, descricao, categoria,
                                                                  qtde_registrada, valor_unit_registrado)
                                           VALUES (:c, :ci, :n, :s, :d, :cat, :q, :v)
                                           ON CONFLICT (cotacao_item_id) DO UPDATE SET numero_item = EXCLUDED.numero_item RETURNING id"""),
                                   {"c": contratos[chave], "ci": cid, "n": nitem, "s": sku, "d": str(it["Descrição"]).strip(),
                                    "cat": str(it["Categoria"]).strip().upper(), "q": int(it["Qtde"]), "v": vunit}).scalar()
                mapa[(num, sku, p["CNPJ_clean"])] = aid
                mapa.setdefault((num, sku, None), aid)

        if args.recarregar_consumo:
            conn.execute(text("DELETE FROM consumo_entregas"))
        pareados = 0
        for _, r in dados["entregas"].iterrows():
            preg = _txt(r["PREGÃO/PROCESSO"]) or ""
            sku_p, sku_e = _sku_base(r["ID PEDIDO"]) or "", _sku_base(r["ID ENVIADO"])
            cnpj = limpar_cnpj(r["CNPJ"])
            aid = mapa.get((preg, sku_p, cnpj)) or mapa.get((preg, sku_p, None))
            pareados += bool(aid)
            conn.execute(text("""INSERT INTO consumo_entregas (ata_item_id, pregao_ref, empenho_pedido_af, status_entrega, data_recebimento,
                                    prazo_entrega, sku_pedido, sku_enviado, quantidade, valor_unitario, op_numero, ordem_remessa,
                                    nf_numero, data_faturamento, observacoes)
                                 VALUES (:a, :pr, :e, :st, :rec, :pz, :sp, :se, :q, :v, :op, :od, :nf, :df, :ob)"""),
                         {"a": aid, "pr": preg, "e": str(r["EMPENHO/PEDIDO/AF"]).strip(), "st": r["status_interno"],
                          "rec": r["recebimento_d"], "pz": _data(r["PRAZO DE ENTREGA"]), "sp": sku_p, "se": sku_e,
                          "q": int(r["qtde"]), "v": float(r["vunit"]), "op": _txt(r["OP"]), "od": _txt(r["ORDEM/REMESSA"]),
                          "nf": _txt(r["NF"]), "df": _data(r["DATA DE FATURAMENTO"]), "ob": _txt(r["OBS"])})
        print(f"[OK] consumo carregado: {len(dados['entregas'])} linhas, {pareados} pareadas automaticamente a itens de ata.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--concorrentes", required=True)
    ap.add_argument("--registros", required=True)
    ap.add_argument("--entregas", required=True)
    ap.add_argument("--data-corte", help="AAAA-MM-DD: recebimentos a partir desta data não entram (vêm do Portal)")
    ap.add_argument("--recarregar-consumo", action="store_true", help="apaga e recarrega consumo_entregas (legado)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--saida-logs", default="./etl_logs")
    args = ap.parse_args()
    corte = pd.to_datetime(args.data_corte).date() if args.data_corte else None
    logs = Path(args.saida_logs)
    logs.mkdir(parents=True, exist_ok=True)

    conc, inval, dv_ruim = preparar_concorrentes(pd.read_excel(args.concorrentes))
    inval.to_csv(logs / "concorrentes_cnpj_formato_invalido.csv", index=False)
    dv_ruim.to_csv(logs / "concorrentes_cnpj_digito_verificador_suspeito.csv", index=False)
    cat = preparar_catalogo(pd.read_excel(args.registros, sheet_name="PNEUS"))
    orgaos = pd.read_excel(args.registros, sheet_name="dados").dropna()["Órgão"].astype(str).str.strip().unique().tolist()
    reg = preparar_registros(pd.read_excel(args.registros, sheet_name="Registrados - Ativos"))
    ent_ok, ent_rej = preparar_entregas(pd.read_excel(args.entregas, sheet_name="Controle de Entrega 2025"), corte)
    ent_rej.to_csv(logs / "entregas_rejeitadas.csv", index=False)

    print(f"Concorrentes: {len(conc)} válidos | {len(inval)} com CNPJ fora do formato | {len(dv_ruim)} com DV suspeito (carregados mesmo assim)")
    print(f"Catálogo: {len(cat)} SKUs | Órgãos: {len(orgaos)} | Registros (itens de ata): {len(reg)}")
    print(f"Entregas: {len(ent_ok)} aceitas | {len(ent_rej)} rejeitadas (ver {logs}/entregas_rejeitadas.csv)")
    if args.dry_run:
        print("[DRY-RUN] nada foi gravado.")
        return 0
    from sqlalchemy import create_engine
    engine = create_engine(os.environ["DATABASE_URL"])
    carregar(engine, args, {"concorrentes": conc, "catalogo": cat, "orgaos": orgaos, "registros": reg, "entregas": ent_ok})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
