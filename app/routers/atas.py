"""ABA 2 — Gestão de Atas e Contratos (itens REGISTRADOS, vigência, consumo, insights). Prefixo /api."""
from __future__ import annotations

import uuid
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.engine import Connection

from .. import schemas as sc
from ..auth import User, exigir
from ..config import settings
from ..db import auditar, get_conn, q_all, q_exec, q_one
from ..domain import validators as v, vigencia
from ..domain.status import RegraNegocioErro
from ..errors import Conflito, NaoEncontrado
from ..services import exportar
from ..services.storage import storage

router = APIRouter(prefix="/api/v1", tags=["Aba 2 — Atas e Contratos"])
CONSULTA, OPERACAO, ADMIN = exigir("CONSULTA"), exigir("OPERACAO"), exigir("ADMIN")

CATEGORIAS_DOC_ATA = ["CONTRATO_ATA", "ADITIVO_PRAZO", "ADITIVO_QUANTIDADE", "REEQUILIBRIO", "EMPENHO", "OUTROS"]
FILTROS_INSIGHTS = {"uf": "uf", "vendedor": "vendedor", "status_vigencia": "status_vigencia"}


def _ata_ou_404(conn, ata_id: UUID) -> dict:
    r = q_one(conn, "SELECT * FROM contratos_atas WHERE id = :id", id=str(ata_id))
    if not r:
        raise NaoEncontrado("Ata/Contrato não encontrado.")
    return r


# ====================================================================== CRIAR ATA (somente itens REGISTRADO)
@router.post("/pregoes/{pregao_id}/contratos-atas", status_code=201)
def criar_ata(pregao_id: UUID, d: sc.ContratoAtaIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    if not q_one(conn, "SELECT 1 AS x FROM pregoes WHERE id = :id", id=str(pregao_id)):
        raise NaoEncontrado("Pregão não encontrado.")
    fim = vigencia.calcular_fim(d.data_contrato, d.tipo_vigencia, d.data_fim_vigencia)  # valida PERSONALIZADO
    ids = [str(i) for i in d.cotacao_item_ids]
    itens = q_all(conn, """
        SELECT id, numero_item, sku, descricao, categoria, quantidade, status_item,
               valor_unit_vencedor AS valor_unit
          FROM cotacao_itens WHERE pregao_id = :pid AND id = ANY(CAST(:ids AS UUID[]))""", pid=str(pregao_id), ids=ids)
    if len(itens) != len(set(ids)):
        raise RegraNegocioErro("Há itens que não pertencem a este pregão.")
    nao_reg = [i["numero_item"] for i in itens if i["status_item"] != "REGISTRADO"]
    if nao_reg:
        raise RegraNegocioErro(f"Apenas itens com status REGISTRADO podem compor a Ata/Contrato. Itens bloqueados: {', '.join(nao_reg)}.")
    sem_valor = [i["numero_item"] for i in itens if not i["valor_unit"]]
    if sem_valor:
        raise RegraNegocioErro("Itens sem valor unitário vencedor (defina o vencedor a empresa e o valor): " + ", ".join(sem_valor) + ".")
    ja = q_all(conn, "SELECT numero_item FROM ata_itens WHERE cotacao_item_id = ANY(CAST(:ids AS UUID[]))", ids=ids)
    if ja:
        raise Conflito("Itens já vinculados a outra Ata/Contrato: " + ", ".join(r["numero_item"] for r in ja))

    ata = q_one(conn, """
        INSERT INTO contratos_atas (pregao_id, nome_contrato, tipo_instrumento, data_contrato, tipo_vigencia,
                                    data_fim_vigencia, observacoes, criado_por)
        VALUES (:p, :n, :t, :d, :v, :f, :o, :u) RETURNING id, data_fim_vigencia""",
                 p=str(pregao_id), n=d.nome_contrato.strip(), t=d.tipo_instrumento, d=d.data_contrato, v=d.tipo_vigencia,
                 f=fim, o=d.observacoes, u=user.nome)  # trigger recalcula/valida data_fim_vigencia
    for i in itens:
        q_exec(conn, """INSERT INTO ata_itens (contrato_ata_id, cotacao_item_id, numero_item, sku, descricao, categoria,
                                               qtde_registrada, valor_unit_registrado)
                        VALUES (:c, :ci, :n, :s, :d, :cat, :q, :v)""",
               c=ata["id"], ci=i["id"], n=i["numero_item"], s=i["sku"], d=i["descricao"], cat=i["categoria"],
               q=i["quantidade"], v=i["valor_unit"])
    auditar(conn, "ATA", ata["id"], "CRIAR", user.nome, {"itens": len(itens), "vigencia": d.tipo_vigencia})
    return {"contrato_ata_id": ata["id"], "data_fim_vigencia": ata["data_fim_vigencia"], "itens_vinculados": len(itens)}


@router.patch("/atas/{ata_id}")
def editar_ata(ata_id: UUID, d: sc.ContratoAtaUpdate, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    atual = _ata_ou_404(conn, ata_id)
    campos = {k: val for k, val in d.model_dump().items() if val is not None}
    if {"tipo_vigencia", "data_contrato", "data_fim_vigencia"} & campos.keys():
        tipo = campos.get("tipo_vigencia", atual["tipo_vigencia"])
        vigencia.calcular_fim(campos.get("data_contrato", atual["data_contrato"]), tipo,
                              campos.get("data_fim_vigencia", atual["data_fim_vigencia"]))
    if not campos:
        return {"ok": True}
    sets = ", ".join(f"{k} = :{k}" for k in campos)
    q_exec(conn, f"UPDATE contratos_atas SET {sets} WHERE id = :_id", _id=str(ata_id), **campos)
    auditar(conn, "ATA", ata_id, "EDITAR", user.nome, {k: str(x) for k, x in campos.items()})
    return {"ok": True}


@router.delete("/atas/{ata_id}", status_code=204)
def excluir_ata(ata_id: UUID, conn: Connection = Depends(get_conn), user: User = Depends(ADMIN)):
    ata = _ata_ou_404(conn, ata_id)
    if q_one(conn, "SELECT 1 AS x FROM vinculo_ata_licitacao_item v JOIN ata_itens ai ON ai.id = v.ata_item_id "
                   "WHERE ai.contrato_ata_id = :id", id=str(ata_id)):
        raise Conflito("A ata possui pedidos do Portal Licitações vinculados. Desfaça os vínculos primeiro.")
    q_exec(conn, "DELETE FROM contratos_atas WHERE id = :id", id=str(ata_id))
    auditar(conn, "ATA", ata_id, "EXCLUIR", user.nome, {"nome": ata["nome_contrato"]})
    return Response(status_code=204)


# ====================================================================== LISTAGEM / DETALHE / INSIGHTS
@router.get("/atas")
def listar_atas(q: Optional[str] = None, uf: Optional[str] = None, vendedor: Optional[str] = None,
                status_vigencia: Optional[str] = Query(None, pattern="^(ATIVO|VENCE_30_DIAS|ENCERRADO|IMEDIATO)$"),
                pagina: int = 1, tamanho: int = Query(25, le=200), conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    where, p = ["1=1"], {}
    if q and q.strip():
        p["like"] = f"%{q.strip()}%"
        where.append("(nome_contrato ILIKE :like OR numero_pregao ILIKE :like OR orgao_nome ILIKE :like)")
    if uf:
        where.append("uf = :uf"); p["uf"] = uf.upper()
    if vendedor:
        where.append("vendedor = :vendedor"); p["vendedor"] = vendedor.upper()
    if status_vigencia:
        where.append("status_vigencia = :sv"); p["sv"] = status_vigencia
    w = " AND ".join(where)
    base = f"""SELECT contrato_ata_id, nome_contrato, tipo_instrumento, data_contrato, tipo_vigencia, data_fim_vigencia,
                      dias_para_fim, status_vigencia, pregao_id, numero_pregao, orgao_nome, uf, vendedor,
                      COUNT(ata_item_id) AS itens, SUM(qtde_registrada) AS qtde_registrada,
                      SUM(valor_total_contratado) AS valor_total_contratado, SUM(valor_consumido) AS valor_consumido,
                      SUM(saldo_valor_remanescente) AS saldo_valor_remanescente,
                      ROUND(SUM(qtde_consumida)::NUMERIC / NULLIF(SUM(qtde_registrada), 0) * 100, 2) AS pct_consumo
                 FROM vw_ata_itens_consumo WHERE {w}
                GROUP BY contrato_ata_id, nome_contrato, tipo_instrumento, data_contrato, tipo_vigencia, data_fim_vigencia,
                         dias_para_fim, status_vigencia, pregao_id, numero_pregao, orgao_nome, uf, vendedor"""
    total = q_one(conn, f"SELECT COUNT(*) AS n FROM ({base}) t", **p)["n"]
    p.update(lim=tamanho, off=(max(pagina, 1) - 1) * tamanho)
    itens = q_all(conn, base + " ORDER BY dias_para_fim ASC NULLS LAST LIMIT :lim OFFSET :off", **p)
    return {"itens": itens, "total": total, "pagina": pagina, "tamanho": tamanho}


@router.get("/atas/exportar")
def exportar_atas(q: Optional[str] = None, uf: Optional[str] = None, vendedor: Optional[str] = None,
                  status_vigencia: Optional[str] = Query(None, pattern="^(ATIVO|VENCE_30_DIAS|ENCERRADO|IMEDIATO)$"),
                  formato: str = Query("xlsx", pattern="^(xlsx|csv)$"),
                  conn: Connection = Depends(get_conn), user: User = Depends(CONSULTA)):
    """Planilha da lista de Atas/Contratos com os MESMOS filtros da tela."""
    rows = listar_atas(q, uf, vendedor, status_vigencia, 1, 100000, conn, user)["itens"]
    cab = ["Instrumento", "Tipo", "Pregão", "Órgão", "UF", "Vendedor", "Data do contrato", "Vigência", "Fim da vigência",
           "Dias p/ fim", "Situação", "Itens", "Contratado (R$)", "Consumido (R$)", "Saldo (R$)", "% consumo"]
    dados = [[r["nome_contrato"], r["tipo_instrumento"], r["numero_pregao"], r["orgao_nome"], r["uf"], r["vendedor"],
              r["data_contrato"], r["tipo_vigencia"], r["data_fim_vigencia"], r["dias_para_fim"], r["status_vigencia"], r["itens"],
              r["valor_total_contratado"], r["valor_consumido"], r["saldo_valor_remanescente"], r["pct_consumo"]] for r in rows]
    return exportar.resposta("Atas_e_Contratos", cab, dados, formato)


@router.get("/atas/insights")
def insights_atas(uf: Optional[str] = None, vendedor: Optional[str] = None,
                  status_vigencia: Optional[str] = Query(None, pattern="^(ATIVO|VENCE_30_DIAS|ENCERRADO|IMEDIATO)$"),
                  conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    """Cards de KPIs + itens com saldo/consumo. Filtros em lista fechada (sem SQL dinâmico a partir da entrada)."""
    where, p = ["1=1"], {}
    for nome, valor in (("uf", uf and uf.upper()), ("vendedor", vendedor and vendedor.upper()), ("status_vigencia", status_vigencia)):
        if valor:
            where.append(f"{FILTROS_INSIGHTS[nome]} = :{nome}"); p[nome] = valor
    return {
        "kpis": q_one(conn, "SELECT * FROM vw_dashboard_atas_kpis") or {},
        "atas_itens": q_all(conn, f"SELECT * FROM vw_ata_itens_consumo WHERE {' AND '.join(where)} "
                                  f"ORDER BY dias_para_fim ASC NULLS LAST", **p),
    }


@router.get("/atas/{ata_id}/exportar")
def exportar_ata(ata_id: UUID, formato: str = Query("xlsx", pattern="^(xlsx|csv)$"),
                 conn: Connection = Depends(get_conn), user: User = Depends(CONSULTA)):
    """Planilha dos itens de UMA ata: registrado, consumido, em processo e saldo."""
    det = obter_ata(ata_id, conn, user)
    cab = ["Item", "SKU", "Descrição", "Qtde registrada", "Qtde consumida", "Qtde em processo", "Saldo (un.)",
           "Valor unit. vigente", "Contratado (R$)", "Consumido (R$)", "Saldo (R$)", "% consumo", "Reequilíbrio"]
    dados = [[l["numero_item"], l["sku"], l["descricao"], l["qtde_registrada"], l["qtde_consumida"], l["qtde_em_processo"],
              l["saldo_qtde_remanescente"], l["valor_unit_vigente"], l["valor_total_contratado"], l["valor_consumido"],
              l["saldo_valor_remanescente"], l["pct_consumo"], l["status_reequilibrio"] or ""] for l in det["itens"]]
    return exportar.resposta(f"Ata_{det['ata']['nome_contrato']}", cab, dados, formato)


@router.get("/atas/{ata_id}")
def obter_ata(ata_id: UUID, conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    ata = _ata_ou_404(conn, ata_id)
    itens = q_all(conn, "SELECT * FROM vw_ata_itens_consumo WHERE contrato_ata_id = :id ORDER BY numero_item", id=str(ata_id))
    ids = [str(i["ata_item_id"]) for i in itens]
    consumo = q_all(conn, "SELECT * FROM vw_consumo_unificado WHERE ata_item_id = ANY(CAST(:ids AS UUID[])) ORDER BY origem, ref",
                    ids=ids) if ids else []
    return {
        "ata": ata,
        "itens": itens,
        "consumo": consumo,
        "documentos": q_all(conn, "SELECT id, categoria, nome_arquivo, mime_type, tamanho_bytes, uploaded_by, uploaded_at "
                                  "FROM contrato_documentos WHERE contrato_ata_id = :id ORDER BY uploaded_at DESC", id=str(ata_id)),
    }


@router.patch("/atas/itens/{ata_item_id}")
def editar_ata_item(ata_item_id: UUID, d: sc.AtaItemUpdate, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    """Quantidade/valor registrados e reequilíbrio (enviado, deferido, indeferido, desistência)."""
    campos = {k: val for k, val in d.model_dump().items() if val is not None}
    if campos.get("status_reequilibrio") == "DEFERIDO" and not (campos.get("valor_reequilibrio") or
            (q_one(conn, "SELECT valor_reequilibrio FROM ata_itens WHERE id = :id", id=str(ata_item_id)) or {}).get("valor_reequilibrio")):
        raise RegraNegocioErro("Para reequilíbrio DEFERIDO informe o valor reequilibrado.")
    if not campos:
        return {"ok": True}
    sets = ", ".join(f"{k} = :{k}" for k in campos)
    r = q_one(conn, f"UPDATE ata_itens SET {sets} WHERE id = :_id RETURNING id", _id=str(ata_item_id), **campos)
    if not r:
        raise NaoEncontrado("Item da ata não encontrado.")
    auditar(conn, "ATA_ITEM", ata_item_id, "EDITAR", user.nome, {k: str(x) for k, x in campos.items()})
    return {"ok": True}


# ====================================================================== DOCUMENTOS DA ATA
@router.post("/atas/{ata_id}/documentos", status_code=201)
async def anexar_doc_ata(ata_id: UUID, categoria: str = Form("CONTRATO_ATA"), arquivos: List[UploadFile] = File(...),
                         conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    if categoria not in CATEGORIAS_DOC_ATA:
        raise RegraNegocioErro(f"Categoria inválida. Use: {', '.join(CATEGORIAS_DOC_ATA)}.")
    ata = _ata_ou_404(conn, ata_id)
    salvos = []
    for arq in arquivos:
        dados = await arq.read()
        nome = v.nome_seguro(arq.filename or "arquivo")
        mime = v.validar_arquivo(nome, dados, v.DOC_PREGAO_TIPOS, settings.max_pregao_upload_mb * v.MB)
        caminho = f"contratos/{ata['data_contrato'].year}/{ata_id}/{categoria}/{uuid.uuid4()}_{nome}"
        storage.salvar(caminho, dados)
        r = q_one(conn, "INSERT INTO contrato_documentos (contrato_ata_id, categoria, nome_arquivo, storage_path, mime_type, "
                        "tamanho_bytes, uploaded_by) VALUES (:c, :cat, :n, :s, :m, :t, :u) RETURNING id",
                  c=str(ata_id), cat=categoria, n=nome, s=caminho, m=mime, t=len(dados), u=user.nome)
        salvos.append({"id": r["id"], "nome_arquivo": nome})
    auditar(conn, "DOCUMENTO", ata_id, "ANEXAR_ATA", user.nome, {"categoria": categoria, "arquivos": [s["nome_arquivo"] for s in salvos]})
    return {"contrato_ata_id": str(ata_id), "arquivos_salvos": salvos}


@router.get("/atas/documentos/{doc_id}")
def baixar_doc_ata(doc_id: UUID, download: bool = False, conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    d = q_one(conn, "SELECT * FROM contrato_documentos WHERE id = :id", id=str(doc_id))
    if not d:
        raise NaoEncontrado("Documento não encontrado.")
    disp = "attachment" if download else "inline"
    return Response(storage.ler(d["storage_path"]), media_type=d["mime_type"] or "application/octet-stream",
                    headers={"Content-Disposition": f'{disp}; filename="{d["nome_arquivo"]}"'})


# ====================================================================== VÍNCULO com o Portal Licitações (consumo automático)
@router.get("/atas/vinculos/sugestoes")
def sugestoes(licitacao_id: int, conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    """Sugere o item de ata para cada item da licitação: mesmo pregão (número) + SKU = código do pedido."""
    return {"sugestoes": q_all(conn, """
        SELECT li.id AS licitacao_item_id, li.descricao AS licitacao_item, li.quantidade, ai.id AS ata_item_id,
               ca.nome_contrato, ai.numero_item, ai.sku
          FROM public.licitacoes l
          JOIN public.licitacao_itens li ON li.licitacao_id = l.id
          JOIN pregoes p ON UPPER(TRIM(p.numero_pregao)) = UPPER(TRIM(l.pregao))
                        AND (p.orgao_cnpj IS NULL OR p.orgao_cnpj = l.cnpj)
          JOIN contratos_atas ca ON ca.pregao_id = p.id
          JOIN ata_itens ai ON ai.contrato_ata_id = ca.id AND ai.sku = li.codigo_pedido
         WHERE l.id = :l AND NOT EXISTS (SELECT 1 FROM vinculo_ata_licitacao_item v WHERE v.licitacao_item_id = li.id)
         ORDER BY li.id""", l=licitacao_id)}


@router.post("/atas/itens/{ata_item_id}/vinculos", status_code=201)
def vincular(ata_item_id: UUID, d: sc.VinculoIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    if not q_one(conn, "SELECT 1 AS x FROM ata_itens WHERE id = :id", id=str(ata_item_id)):
        raise NaoEncontrado("Item da ata não encontrado.")
    for li in d.licitacao_item_ids:
        if not q_one(conn, "SELECT 1 AS x FROM public.licitacao_itens WHERE id = :i", i=li):
            raise NaoEncontrado(f"Item {li} do Portal Licitações não encontrado.")
        if q_one(conn, "SELECT 1 AS x FROM vinculo_ata_licitacao_item WHERE licitacao_item_id = :i", i=li):
            raise Conflito(f"O item {li} já está vinculado a uma ata.")
        q_exec(conn, "INSERT INTO vinculo_ata_licitacao_item (licitacao_item_id, ata_item_id, vinculado_por) VALUES (:i, :a, :u)",
               i=li, a=str(ata_item_id), u=user.nome)
    auditar(conn, "VINCULO", ata_item_id, "VINCULAR", user.nome, {"licitacao_item_ids": d.licitacao_item_ids})
    return {"vinculados": len(d.licitacao_item_ids)}


@router.delete("/atas/vinculos/{licitacao_item_id}", status_code=204)
def desvincular(licitacao_item_id: int, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    r = q_one(conn, "DELETE FROM vinculo_ata_licitacao_item WHERE licitacao_item_id = :i RETURNING ata_item_id", i=licitacao_item_id)
    if not r:
        raise NaoEncontrado("Vínculo não encontrado.")
    auditar(conn, "VINCULO", r["ata_item_id"], "DESVINCULAR", user.nome, {"licitacao_item_id": licitacao_item_id})
    return Response(status_code=204)
