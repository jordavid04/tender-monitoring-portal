"""Rotas do Portal Licitações (módulo existente, reconstruído). Prefixo /api."""
from __future__ import annotations

import json
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.engine import Connection

from .. import schemas as sc
from ..auth import User, exigir
from ..db import engine, get_conn
from ..domain import validators as v
from ..services import licitacoes as svc

router = APIRouter(prefix="/api/v1", tags=["Portal Licitações"])
CONSULTA, OPERACAO, ADMIN = exigir("CONSULTA"), exigir("OPERACAO"), exigir("ADMIN")


async def _ler(arq: UploadFile) -> bytes:
    return await arq.read()


@router.get("/painel")
def painel(conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    return svc.painel(conn)


@router.get("/orgaos/por-cnpj/{cnpj}")
def por_cnpj(cnpj: str, conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    return svc.autopreencher_por_cnpj(conn, cnpj) or {}


@router.get("/licitacoes")
def listar(q: Optional[str] = None, situacao: Optional[str] = Query(None, pattern="^(ANDAMENTO|FATURADA|CONCLUIDA|CANCELADA)$"),
           status_item: Optional[str] = None, vendedor: Optional[str] = None, de: Optional[date] = None,
           ate: Optional[date] = None, so_vencidos: bool = False, pagina: int = 1, tamanho: int = Query(25, le=200),
           conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    return svc.listar(conn, q, situacao, status_item, vendedor, de, ate, so_vencidos, pagina, tamanho)


@router.post("/licitacoes", status_code=201)
async def criar(dados: str = Form(..., description="JSON de LicitacaoCreate"),
                confirmacao: Optional[UploadFile] = File(None),
                conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    payload = sc.LicitacaoCreate.model_validate_json(dados)
    arq = (confirmacao.filename, await _ler(confirmacao)) if confirmacao and confirmacao.filename else None
    return svc.criar(conn, payload, user.nome, arq)


@router.get("/licitacoes/{lic_id}")
def obter(lic_id: int, conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    return svc.obter(conn, lic_id)


@router.patch("/licitacoes/{lic_id}")
def editar(lic_id: int, dados: sc.LicitacaoUpdate, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    return svc.editar(conn, lic_id, dados, user.nome)


@router.post("/licitacoes/{lic_id}/confirmacao")
async def confirmacao(lic_id: int, arquivo: UploadFile = File(...), conn: Connection = Depends(get_conn),
                      user: User = Depends(OPERACAO)):
    return svc.anexar_confirmacao(conn, lic_id, arquivo.filename or "arquivo", await _ler(arquivo), user.nome)


@router.get("/documentos/{doc_id}")
def baixar(doc_id: str, download: bool = False, conn: Connection = Depends(get_conn), _: User = Depends(CONSULTA)):
    d, dados = svc.documento(conn, doc_id)
    disp = "attachment" if download else "inline"
    return Response(dados, media_type=d["mime_type"],
                    headers={"Content-Disposition": f'{disp}; filename="{d["nome_arquivo"]}"'})


# ------------------------------------------------------------------ itens
@router.post("/licitacoes/{lic_id}/itens", status_code=201)
def add_item(lic_id: int, item: sc.ItemIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    return svc.adicionar_item(conn, lic_id, item, user.nome)


@router.patch("/itens/{item_id}")
def corrigir_item(item_id: int, dados: sc.ItemUpdate, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    svc.corrigir_item(conn, item_id, dados, user.nome)
    return {"ok": True}


def _lic_do_item(conn, item_id: int) -> int:
    from ..db import q_one
    from ..errors import NaoEncontrado
    r = q_one(conn, "SELECT licitacao_id FROM licitacao_itens WHERE id = :i", i=item_id)
    if not r:
        raise NaoEncontrado("Item não encontrado.")
    return r["licitacao_id"]


@router.post("/licitacoes/{lic_id}/itens/lancar")
def lancar(lic_id: int, d: sc.LancarIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    n = svc.executar_acao(conn, lic_id, d.item_ids, "lancar", user.nome, op_numero=d.op_numero,
                          ordem_remessa=d.ordem_remessa, codigo_produto_enviado=d.codigo_produto_enviado, observacao=d.observacao)
    return {"itens": n}


@router.post("/licitacoes/{lic_id}/itens/entregar")
def entregar(lic_id: int, d: sc.EntregarIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    n = svc.executar_acao(conn, lic_id, d.item_ids, "entregar", user.nome, data_entrega=d.data_entrega, observacao=d.observacao)
    return {"itens": n}


@router.post("/itens/{item_id}/aguardar-estoque")
def aguardar(item_id: int, d: sc.AguardarEstoqueIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    svc.executar_acao(conn, _lic_do_item(conn, item_id), [item_id], "aguardar_estoque", user.nome, motivo=d.motivo)
    return {"ok": True}


@router.post("/itens/{item_id}/propor-troca")
def troca(item_id: int, d: sc.TrocaMarcaIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    svc.executar_acao(conn, _lic_do_item(conn, item_id), [item_id], "propor_troca", user.nome, proposta_troca=d.proposta_troca)
    return {"ok": True}


@router.post("/itens/{item_id}/cancelar")
def cancelar(item_id: int, d: sc.CancelarIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    svc.executar_acao(conn, _lic_do_item(conn, item_id), [item_id], "cancelar", user.nome, motivo=d.motivo, motivo_detalhe=d.motivo_detalhe)
    return {"ok": True}


@router.post("/itens/{item_id}/carta-correcao")
def carta(item_id: int, d: sc.CartaCorrecaoIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    svc.executar_acao(conn, _lic_do_item(conn, item_id), [item_id], "carta_correcao", user.nome,
                      carta_correcao_texto=d.carta_correcao_texto)
    return {"ok": True}


@router.post("/itens/{item_id}/anotar")
def anotar(item_id: int, d: sc.AnotarIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    svc.anotar(conn, item_id, d.anotacao, user.nome)
    return {"ok": True}


@router.post("/itens/{item_id}/reabrir")
def reabrir(item_id: int, d: sc.ReabrirIn, conn: Connection = Depends(get_conn), user: User = Depends(ADMIN)):
    svc.executar_acao(conn, _lic_do_item(conn, item_id), [item_id], "reabrir", user.nome, motivo=d.motivo)
    return {"ok": True}


# ------------------------------------------------------------------ nota fiscal e e-mail
@router.post("/licitacoes/{lic_id}/notas-fiscais/preview-email")
def preview(lic_id: int, d: sc.NfPreviewIn, conn: Connection = Depends(get_conn), _: User = Depends(OPERACAO)):
    return svc.preview_email(conn, lic_id, d.numero, d.data_faturamento, d.item_ids)


@router.post("/licitacoes/{lic_id}/notas-fiscais", status_code=201)
async def registrar_nf(lic_id: int, numero: str = Form(...), data_faturamento: date = Form(...),
                       previsao_entrega: Optional[date] = Form(None), item_ids: str = Form(..., description='JSON: [1,2]'),
                       enviar_email: bool = Form(...), email_para: Optional[str] = Form(None),
                       assunto: Optional[str] = Form(None), mensagem: Optional[str] = Form(None),
                       arquivo: UploadFile = File(...), user: User = Depends(OPERACAO)):
    """Registrar sem enviar (enviar_email=false) ou registrar e enviar (true).
    Duas transações: a nota é gravada primeiro; falha de e-mail NÃO desfaz a nota (vira 'não enviado')."""
    ids = [int(x) for x in json.loads(item_ids)]
    conteudo = await _ler(arquivo)
    para = v.parse_emails(email_para) if email_para else []
    with engine.begin() as conn:
        res = svc.registrar_nf(conn, lic_id, numero, data_faturamento, previsao_entrega, ids,
                               arquivo.filename or "nf", conteudo, user.nome, para, assunto, mensagem)
        if not enviar_email:
            svc.sem_enviar(conn, res["nota_id"])
    envio = None
    if enviar_email:
        with engine.begin() as conn:
            envio = svc.enviar_email_nf(conn, res["nota_id"], user.nome, para or None, assunto, mensagem)
    return {**res, "email": envio}


@router.post("/notas-fiscais/{nota_id}/reenviar-email")
def reenviar(nota_id: int, d: sc.ReenvioIn, conn: Connection = Depends(get_conn), user: User = Depends(OPERACAO)):
    return svc.enviar_email_nf(conn, nota_id, user.nome, d.para, d.assunto, d.mensagem)
