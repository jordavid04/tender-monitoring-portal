"""ABA 1 — Controle de Pregões Diários (+ Cotação, Documentos, Concorrentes, Catálogo). Prefixo /api."""
from __future__ import annotations

import uuid
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.engine import Connection

from .. import schemas as sc
from ..auth import User, exigir
from ..config import settings
from ..db import auditar, get_conn, q_all, q_exec, q_one
from ..domain import validators as v
from ..domain.status import RegraNegocioErro
from ..errors import Conflito, NaoEncontrado
from ..services import exportar
from ..services.storage import storage

router = APIRouter(prefix="/api/v1", tags=["Aba 1 — Pregões"])
CONSULTA, OPERACAO, ADMIN = exigir("CONSULTA"), exigir("OPERACAO"), exigir("ADMIN")

CATEGORIAS_DOC = ["EDITAL", "TERMO_REFERENCIA", "PROPOSTA_INICIAL", "PROPOSTA_AJUSTADA", "HABILITACAO",
                  "ATA_SESSAO", "RECURSO_IMPUGNACAO", "OUTROS"]


def _cnpj_opcional(valor: Optional[str]) -> Optional[str]:
    if not valor or not valor.strip():
        return None
    limpo = v.limpar_cnpj(valor)
    if not limpo or (settings.cnpj_validar_dv and not v.cnpj_valido(limpo)):
        raise RegraNegocioErro("CNPJ do órgão inválido.")
    return limpo


def _pregao_ou_404(conn, pregao_id: UUID) -> dict:
    r = q_one(conn, "SELECT * FROM pregoes WHERE id = :id", id=str(pregao_id))
    if not r:
        raise NaoEncontrado("Pregão não encontrado.")
    return r


# ====================================================================== PREGÕES
@router.get("/pregoes")
def listar(q: Optional[str] = None, uf: Optional[str] = None, situacao: Optional[str] = None,
           vendedor: Optional[str] = None, porte: Optional[str] = None, de: Optional[date] = None,
           ate: Optional[date] = None, pagina: int = 1, tamanho: int = Query(25, le=200),
           conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    where, p = ["1=1"], {}
    if q and q.strip():
        p["like"] = f"%{q.strip()}%"
        where.append("(numero_pregao ILIKE :like OR orgao_nome ILIKE :like OR portal ILIKE :like)")
    for campo, val in (("uf", uf and uf.upper()), ("situacao", situacao), ("vendedor", vendedor), ("porte", porte)):
        if val:
            where.append(f"{campo} = :{campo}")
            p[campo] = val
    if de:
        where.append("data_licitacao >= :de"); p["de"] = de
    if ate:
        where.append("data_licitacao <= :ate"); p["ate"] = ate
    w = " AND ".join(where)
    total = q_one(conn, f"SELECT COUNT(*) AS n FROM vw_pregoes_metricas WHERE {w}", **p)["n"]
    p.update(lim=tamanho, off=(max(pagina, 1) - 1) * tamanho)
    itens = q_all(conn, f"SELECT * FROM vw_pregoes_metricas WHERE {w} "
                        f"ORDER BY data_licitacao DESC, hora_licitacao DESC LIMIT :lim OFFSET :off", **p)
    return {"itens": itens, "total": total, "pagina": pagina, "tamanho": tamanho}


@router.get("/pregoes/insights")
def insights(de: Optional[date] = None, ate: Optional[date] = None, conn: Connection = Depends(get_conn),
             _: User = Depends(CONSULTA)):
    """Métricas da Aba 1: % de disputa sobre o edital e % de vitória sobre os itens disputados."""
    p, w = {}, "1=1"
    if de:
        w += " AND data_licitacao >= :de"; p["de"] = de
    if ate:
        w += " AND data_licitacao <= :ate"; p["ate"] = ate
    agg = """COUNT(*) AS pregoes, SUM(total_itens_edital) AS itens_edital, SUM(itens_disputados_efetivos) AS itens_disputados,
             SUM(itens_registrados) AS itens_registrados, SUM(itens_ganhos) AS itens_ganhos, SUM(itens_perdidos) AS itens_perdidos,
             COALESCE(SUM(valor_ganho), 0) AS valor_ganho,
             ROUND(SUM(itens_disputados_efetivos)::NUMERIC / NULLIF(SUM(total_itens_edital), 0) * 100, 2) AS pct_disputa,
             ROUND(SUM(itens_ganhos)::NUMERIC / NULLIF(SUM(itens_disputados_efetivos), 0) * 100, 2) AS pct_vitoria"""
    return {
        "geral": q_one(conn, f"SELECT {agg} FROM vw_pregoes_metricas WHERE {w}", **p),
        "por_vendedor": q_all(conn, f"SELECT vendedor AS chave, {agg} FROM vw_pregoes_metricas WHERE {w} GROUP BY vendedor ORDER BY pregoes DESC", **p),
        "por_uf": q_all(conn, f"SELECT uf AS chave, {agg} FROM vw_pregoes_metricas WHERE {w} GROUP BY uf ORDER BY pregoes DESC", **p),
        "por_situacao": q_all(conn, f"SELECT situacao AS chave, COUNT(*) AS pregoes FROM vw_pregoes_metricas WHERE {w} GROUP BY situacao ORDER BY pregoes DESC", **p),
        "por_porte": q_all(conn, f"SELECT porte AS chave, {agg} FROM vw_pregoes_metricas WHERE {w} GROUP BY porte ORDER BY pregoes DESC", **p),
    }


FORMATO = Query("xlsx", pattern="^(xlsx|csv)$", description="xlsx (Excel) ou csv")


@router.get("/pregoes/exportar")
def exportar_pregoes(q: Optional[str] = None, uf: Optional[str] = None, situacao: Optional[str] = None,
                     vendedor: Optional[str] = None, porte: Optional[str] = None, de: Optional[date] = None,
                     ate: Optional[date] = None, formato: str = FORMATO,
                     conn: Connection = Depends(get_conn), user: User = Depends(CONSULTA)):
    """Planilha da lista de pregões, respeitando os MESMOS filtros da tela (sem paginação)."""
    linhas = listar(q, uf, situacao, vendedor, porte, de, ate, 1, 100000, conn, user)["itens"]
    cab = ["Data", "Hora", "Nº do pregão", "Portal", "Órgão", "CNPJ do órgão", "UF", "Porte", "Situação", "Vendedor",
           "Itens no edital", "Itens disputados", "% disputa", "Itens ganhos", "Itens perdidos", "% vitória",
           "Valor ganho (R$)", "Atas/contratos"]
    dados = [[r["data_licitacao"], r["hora_licitacao"], r["numero_pregao"], r["portal"], r["orgao_nome"],
              v.formatar_cnpj(r["orgao_cnpj"] or ""), r["uf"], r["porte"], r["situacao"], r["vendedor"],
              r["total_itens_edital"], r["itens_disputados_efetivos"], r["pct_disputa_edital"], r["itens_ganhos"],
              r["itens_perdidos"], r["pct_vitoria_sobre_disputados"], r["valor_ganho"], r["qtd_atas_contratos"]] for r in linhas]
    return exportar.resposta("Pregoes", cab, dados, formato)


@router.post("/pregoes", status_code=201)
def criar(d: sc.PregaoIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    if d.itens_disputados > d.total_itens_edital:
        raise RegraNegocioErro("Itens disputados não pode ser maior que o total de itens do edital.")
    cnpj = _cnpj_opcional(d.orgao_cnpj)
    orgao_id = None
    if cnpj:
        orgao_id = q_one(conn, """
            INSERT INTO orgaos_publicos (nome, cnpj_clean, uf) VALUES (:n, :c, :uf)
            ON CONFLICT (cnpj_clean) DO UPDATE SET nome = EXCLUDED.nome RETURNING id""",
                         n=d.orgao_nome.strip(), c=cnpj, uf=d.uf.upper())["id"]
    if q_one(conn, "SELECT 1 AS x FROM pregoes WHERE data_licitacao = :d AND numero_pregao = :n AND orgao_nome = :o",
             d=d.data_licitacao, n=d.numero_pregao.strip(), o=d.orgao_nome.strip()):
        raise Conflito("Este pregão já está cadastrado (mesma data, número e órgão).")
    r = q_one(conn, """
        INSERT INTO pregoes (data_licitacao, hora_licitacao, numero_pregao, modalidade, empresa, portal, orgao_id, orgao_nome,
                             orgao_cnpj, uf, porte, situacao, total_itens_edital, itens_disputados, vendedor, observacoes, criado_por)
        VALUES (:d, :h, :n, :mod, :emp, :por, :oid, :on, :oc, :uf, :pt, :sit, :tot, :disp, :vend, :obs, :u) RETURNING id""",
              d=d.data_licitacao, h=d.hora_licitacao, n=d.numero_pregao.strip(), mod=d.modalidade.upper(), emp=d.empresa,
              por=d.portal.strip(), oid=orgao_id, on=d.orgao_nome.strip(), oc=cnpj, uf=d.uf.upper(), pt=d.porte,
              sit=d.situacao, tot=d.total_itens_edital, disp=d.itens_disputados, vend=d.vendedor.strip().upper(),
              obs=d.observacoes, u=user.nome)
    auditar(conn, "PREGAO", r["id"], "CRIAR", user.nome, {"numero": d.numero_pregao})
    return {"id": r["id"]}


@router.get("/pregoes/{pregao_id}")
def obter(pregao_id: UUID, conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    _pregao_ou_404(conn, pregao_id)
    pid = str(pregao_id)
    return {
        "pregao": q_one(conn, "SELECT * FROM vw_pregoes_metricas WHERE pregao_id = :id", id=pid),
        "dados": q_one(conn, "SELECT observacoes, orgao_id, criado_por, created_at, updated_at FROM pregoes WHERE id = :id", id=pid),
        "documentos": q_all(conn, "SELECT id, categoria, nome_arquivo, mime_type, tamanho_bytes, uploaded_by, uploaded_at "
                                  "FROM pregao_documentos WHERE pregao_id = :id ORDER BY uploaded_at DESC", id=pid),
        "cotacao": q_all(conn, """
            SELECT ci.*, c.nome_abreviado AS vencedor_nome, c.cnpj_clean AS vencedor_cnpj,
                   EXISTS (SELECT 1 FROM ata_itens ai WHERE ai.cotacao_item_id = ci.id) AS em_ata
              FROM cotacao_itens ci LEFT JOIN concorrentes c ON c.id = ci.vencedor_concorrente_id
             WHERE ci.pregao_id = :id ORDER BY ci.numero_item""", id=pid),
        "atas": q_all(conn, "SELECT id, nome_contrato, tipo_instrumento, data_contrato, tipo_vigencia, data_fim_vigencia "
                            "FROM contratos_atas WHERE pregao_id = :id ORDER BY data_contrato", id=pid),
    }


@router.get("/pregoes/{pregao_id}/exportar")
def exportar_cotacao(pregao_id: UUID, formato: str = FORMATO, conn: Connection = Depends(get_conn), user: User = Depends(CONSULTA)):
    """Planilha da cotação de itens de UM pregão."""
    det = obter(pregao_id, conn, user)
    cab = ["Item", "SKU", "Medida", "Marca", "Modelo", "Categoria", "Descrição", "Quantidade", "Valor mínimo da empresa (unit.)",
           "Total mínimo da empresa", "Status", "Vencedor", "Valor unit. vencedor", "Total vencedor", "Em ata"]
    dados = [[i["numero_item"], i["sku"], i["medida"], i["marca"], i["modelo"], i["categoria"], i["descricao"], i["quantidade"],
              i["valor_unit_minimo"], i["valor_total_minimo"], i["status_item"],
              "Empresa" if i["vencedor_tipo"] == "PROPRIA" else i.get("vencedor_nome"),
              i["valor_unit_vencedor"], i["valor_total_vencedor"], "Sim" if i["em_ata"] else "Não"] for i in det["cotacao"]]
    return exportar.resposta(f"Cotacao_{det['pregao']['numero_pregao']}", cab, dados, formato)


@router.patch("/pregoes/{pregao_id}")
def editar(pregao_id: UUID, d: sc.PregaoUpdate, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    atual = _pregao_ou_404(conn, pregao_id)
    campos = {k: val for k, val in d.model_dump().items() if val is not None}
    if "orgao_cnpj" in campos:
        campos["orgao_cnpj"] = _cnpj_opcional(campos["orgao_cnpj"])
    for k in ("uf",):
        if k in campos:
            campos[k] = campos[k].upper()
    if "vendedor" in campos:
        campos["vendedor"] = campos["vendedor"].strip().upper()
    tot = campos.get("total_itens_edital", atual["total_itens_edital"])
    if campos.get("itens_disputados", atual["itens_disputados"]) > tot:
        raise RegraNegocioErro("Itens disputados não pode ser maior que o total de itens do edital.")
    if campos.get("status_item") == "REGISTRADO" and not (atual["vencedor_tipo"] == "PROPRIA" and atual["valor_unit_vencedor"]):
        raise RegraNegocioErro("Para registrar o item como ganho, defina o resultado: vencedor a empresa e valor unitário vencedor.")
    if not campos:
        return {"ok": True}
    sets = ", ".join(f"{k} = :{k}" for k in campos)
    q_exec(conn, f"UPDATE pregoes SET {sets}, atualizado_por = :_u WHERE id = :_id", _id=str(pregao_id), _u=user.nome, **campos)
    auditar(conn, "PREGAO", pregao_id, "EDITAR", user.nome, {"campos": list(campos)})
    return {"ok": True}


@router.delete("/pregoes/{pregao_id}", status_code=204)
def excluir(pregao_id: UUID, conn: Connection = Depends(get_conn), user: User = Depends(ADMIN)):
    p = _pregao_ou_404(conn, pregao_id)
    if q_one(conn, "SELECT 1 AS x FROM contratos_atas WHERE pregao_id = :id", id=str(pregao_id)):
        raise Conflito("Este pregão possui Ata/Contrato. Remova-a antes de excluir o pregão.")
    q_exec(conn, "DELETE FROM pregoes WHERE id = :id", id=str(pregao_id))
    auditar(conn, "PREGAO", pregao_id, "EXCLUIR", user.nome, {"numero": p["numero_pregao"], "orgao": p["orgao_nome"]})
    return Response(status_code=204)


# ====================================================================== DOCUMENTOS DO PREGÃO
@router.post("/pregoes/{pregao_id}/documentos", status_code=201)
async def anexar(pregao_id: UUID, categoria: str = Form(...), arquivos: List[UploadFile] = File(...),
                 conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    """Upload múltiplo (elimina as pastas manuais no Drive)."""
    if categoria not in CATEGORIAS_DOC:
        raise RegraNegocioErro(f"Categoria inválida. Use: {', '.join(CATEGORIAS_DOC)}.")
    p = _pregao_ou_404(conn, pregao_id)
    salvos = []
    for arq in arquivos:
        dados = await arq.read()
        nome = v.nome_seguro(arq.filename or "arquivo")
        mime = v.validar_arquivo(nome, dados, v.DOC_PREGAO_TIPOS, settings.max_pregao_upload_mb * v.MB)
        caminho = f"pregoes/{p['data_licitacao'].year}/{p['uf']}/{pregao_id}/{categoria}/{uuid.uuid4()}_{nome}"
        storage.salvar(caminho, dados)
        r = q_one(conn, "INSERT INTO pregao_documentos (pregao_id, categoria, nome_arquivo, storage_path, mime_type, "
                        "tamanho_bytes, uploaded_by) VALUES (:p, :c, :n, :s, :m, :t, :u) RETURNING id",
                  p=str(pregao_id), c=categoria, n=nome, s=caminho, m=mime, t=len(dados), u=user.nome)
        salvos.append({"id": r["id"], "nome_arquivo": nome})
    auditar(conn, "DOCUMENTO", pregao_id, "ANEXAR", user.nome, {"categoria": categoria, "arquivos": [s["nome_arquivo"] for s in salvos]})
    return {"arquivos_salvos": salvos}


@router.get("/pregoes/documentos/{doc_id}")
def baixar_doc(doc_id: UUID, download: bool = False, conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    d = q_one(conn, "SELECT * FROM pregao_documentos WHERE id = :id", id=str(doc_id))
    if not d:
        raise NaoEncontrado("Documento não encontrado.")
    disp = "attachment" if download else "inline"
    return Response(storage.ler(d["storage_path"]), media_type=d["mime_type"] or "application/octet-stream",
                    headers={"Content-Disposition": f'{disp}; filename="{d["nome_arquivo"]}"'})


@router.delete("/pregoes/documentos/{doc_id}", status_code=204)
def remover_doc(doc_id: UUID, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    d = q_one(conn, "DELETE FROM pregao_documentos WHERE id = :id RETURNING nome_arquivo, pregao_id", id=str(doc_id))
    if not d:
        raise NaoEncontrado("Documento não encontrado.")
    auditar(conn, "DOCUMENTO", d["pregao_id"], "REMOVER", user.nome, {"arquivo": d["nome_arquivo"]})  # arquivo físico é mantido (retenção)
    return Response(status_code=204)


# ====================================================================== SEÇÃO 1.1 — COTAÇÃO
def _completar_pelo_catalogo(conn, it: dict) -> dict:
    """Se o SKU existe no catálogo, preenche marca/modelo/medida/descrição/categoria que vierem vazios."""
    if it.get("sku"):
        cat = q_one(conn, "SELECT * FROM produtos_catalogo WHERE sku = :s", s=it["sku"].strip())
        if not cat:
            raise RegraNegocioErro(f"SKU {it['sku']} não existe no catálogo de produtos.")
        it["sku"] = cat["sku"]
        for k_it, k_cat in (("marca", "marca"), ("modelo", "modelo"), ("medida", "medida"),
                            ("descricao", "descricao_origem"), ("categoria", "categoria")):
            if not it.get(k_it):
                it[k_it] = cat[k_cat]
    if not it.get("descricao"):
        raise RegraNegocioErro(f"Item {it['numero_item']}: informe a descrição ou um SKU do catálogo.")
    return it


@router.post("/pregoes/{pregao_id}/itens", status_code=201)
def adicionar_itens(pregao_id: UUID, d: sc.CotacaoLoteIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    p = _pregao_ou_404(conn, pregao_id)
    existentes = q_one(conn, "SELECT COUNT(*) AS n FROM cotacao_itens WHERE pregao_id = :id", id=str(pregao_id))["n"]
    if existentes + len(d.itens) > p["total_itens_edital"]:
        raise RegraNegocioErro(f"O pregão tem {p['total_itens_edital']} itens no edital; a cotação teria {existentes + len(d.itens)}.")
    ids = []
    for item in d.itens:
        if item.status_item == "REGISTRADO":
            raise RegraNegocioErro("Para marcar o item como ganho (REGISTRADO), defina o resultado: vencedor a empresa e valor unitário vencedor.")
        it = _completar_pelo_catalogo(conn, item.model_dump())
        r = q_one(conn, """
            INSERT INTO cotacao_itens (pregao_id, numero_item, sku, marca, modelo, medida, descricao, categoria, quantidade,
                                       valor_unit_minimo, status_item, observacoes)
            VALUES (:p, :ni, :sku, :ma, :mo, :me, :de, :ca, :q, :vm, :st, :ob) RETURNING id""",
                  p=str(pregao_id), ni=it["numero_item"].strip(), sku=it["sku"], ma=it["marca"], mo=it["modelo"], me=it["medida"],
                  de=it["descricao"], ca=it["categoria"], q=it["quantidade"], vm=it["valor_unit_minimo"],
                  st=it["status_item"], ob=it["observacoes"])
        ids.append(r["id"])
    q_exec(conn, "UPDATE pregoes SET itens_disputados = LEAST(total_itens_edital, GREATEST(itens_disputados, :n)) WHERE id = :id",
           n=existentes + len(d.itens), id=str(pregao_id))
    auditar(conn, "COTACAO_ITEM", pregao_id, "ADICIONAR", user.nome, {"qtd": len(ids)})
    return {"ids": ids}


@router.patch("/pregoes/itens/{item_id}")
def editar_item(item_id: UUID, d: sc.CotacaoItemUpdate, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    atual = q_one(conn, "SELECT * FROM cotacao_itens WHERE id = :id FOR UPDATE", id=str(item_id))
    if not atual:
        raise NaoEncontrado("Item não encontrado.")
    campos = {k: val for k, val in d.model_dump().items() if val is not None}
    if campos.get("status_item") == "REGISTRADO" and atual["vencedor_tipo"] == "CONCORRENTE":
        raise RegraNegocioErro("Item REGISTRADO não pode ter concorrente como vencedor. Ajuste o vencedor primeiro.")
    if not campos:
        return {"ok": True}
    sets = ", ".join(f"{k} = :{k}" for k in campos)
    q_exec(conn, f"UPDATE cotacao_itens SET {sets} WHERE id = :_id", _id=str(item_id), **campos)  # trigger bloqueia 'desregistrar'
    auditar(conn, "COTACAO_ITEM", item_id, "EDITAR", user.nome, campos)
    return {"ok": True}


@router.put("/pregoes/itens/{item_id}/vencedor")
def definir_vencedor(item_id: UUID, d: sc.VencedorIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    """Vencedor: Empresa (PROPRIA), concorrente (escolhido na lista ou cadastrado na hora) ou sem vencedor."""
    item = q_one(conn, "SELECT * FROM cotacao_itens WHERE id = :id FOR UPDATE", id=str(item_id))
    if not item:
        raise NaoEncontrado("Item não encontrado.")
    conc = d.vencedor_concorrente_id
    valor = d.valor_unit_vencedor
    if d.vencedor_tipo == "CONCORRENTE":
        if not conc:
            raise RegraNegocioErro("Selecione ou cadastre o concorrente vencedor.")
        if not q_one(conn, "SELECT 1 AS x FROM concorrentes WHERE id = :id", id=str(conc)):
            raise NaoEncontrado("Concorrente não encontrado.")
        if item["status_item"] == "REGISTRADO":
            raise RegraNegocioErro("Item REGISTRADO é da empresa; altere o status do item antes de apontar um concorrente.")
    else:
        conc = None
        if d.vencedor_tipo == "SEM_VENCEDOR":
            valor = None
        elif not valor:
            raise RegraNegocioErro("Informe o valor unitário vencedor da empresa.")
    q_exec(conn, "UPDATE cotacao_itens SET vencedor_tipo = :t, vencedor_concorrente_id = :c, valor_unit_vencedor = :v WHERE id = :id",
           t=d.vencedor_tipo, c=str(conc) if conc else None, v=valor, id=str(item_id))
    auditar(conn, "COTACAO_ITEM", item_id, "VENCEDOR", user.nome, d.model_dump(mode="json"))
    return {"ok": True}


@router.delete("/pregoes/itens/{item_id}", status_code=204)
def remover_item(item_id: UUID, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    if q_one(conn, "SELECT 1 AS x FROM ata_itens WHERE cotacao_item_id = :id", id=str(item_id)):
        raise Conflito("Este item compõe uma Ata/Contrato. Remova-o da ata primeiro.")
    r = q_one(conn, "DELETE FROM cotacao_itens WHERE id = :id RETURNING pregao_id, numero_item", id=str(item_id))
    if not r:
        raise NaoEncontrado("Item não encontrado.")
    auditar(conn, "COTACAO_ITEM", r["pregao_id"], "REMOVER", user.nome, {"numero_item": r["numero_item"]})
    return Response(status_code=204)


# ====================================================================== CONCORRENTES e CATÁLOGO
@router.get("/concorrentes")
def listar_concorrentes(conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    """Lista completa (ordem alfabética) para o seletor 'Quem venceu?'. Para bases grandes use /concorrentes/buscar."""
    return {"itens": q_all(conn, "SELECT id, nome_abreviado, razao_social, cnpj_clean AS cnpj, municipio, uf "
                                 "FROM concorrentes ORDER BY nome_abreviado")}


@router.get("/concorrentes/buscar")
def buscar_concorrentes(q: str = Query(..., min_length=2), conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    """Barra buscável: nome, razão social ou CNPJ (numérico ou alfanumérico)."""
    return {"resultados": q_all(conn, "SELECT * FROM buscar_concorrentes(:q)", q=q)}


@router.post("/concorrentes/cadastro-rapido", status_code=201)
def cadastro_rapido(d: sc.ConcorrenteRapidoIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    """Vencedor não encontrado na busca: cadastra com CNPJ, município e UF; data/hora de chegada automáticas."""
    cnpj = v.limpar_cnpj(d.cnpj)
    if not cnpj or not v.cnpj_valido(cnpj):
        raise RegraNegocioErro("CNPJ inválido (formato ou dígitos verificadores).")
    r = q_one(conn, "SELECT * FROM cadastrar_concorrente_rapido(:a, :s, :c, :m, :u)",
              a=d.nome_abreviado, s=d.razao_social, c=cnpj, m=d.municipio, u=d.uf)
    auditar(conn, "CONCORRENTE", r["id"], "CADASTRO_RAPIDO", user.nome, {"cnpj": cnpj})
    return {"concorrente": r}


@router.get("/catalogo/produtos")
def catalogo(q: Optional[str] = None, categoria: Optional[str] = None, limit: int = Query(30, le=100),
             conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    where, p = ["ativo"], {"lim": limit}
    if q and q.strip():
        p["like"] = f"%{q.strip()}%"
        where.append("(sku ILIKE :like OR marca ILIKE :like OR modelo ILIKE :like OR medida ILIKE :like OR descricao_origem ILIKE :like)")
    if categoria:
        where.append("categoria = :cat"); p["cat"] = categoria.upper()
    return {"resultados": q_all(conn, f"SELECT * FROM produtos_catalogo WHERE {' AND '.join(where)} ORDER BY sku LIMIT :lim", **p)}
