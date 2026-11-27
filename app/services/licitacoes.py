"""Regras do Portal Licitações (módulo existente, reconstruído a partir do Guia de Uso).

Cada função recebe uma `conn` (transação aberta). Regras puras ficam em app/domain.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from ..config import settings
from ..db import q_all, q_exec, q_one
from ..domain import emailing, status as st, validators as v
from ..errors import Conflito, LimiteTentativas, NaoEncontrado
from . import mailer
from .storage import storage

MSG_CONCORRENCIA = "Outra pessoa alterou esta licitação. Aperte F5 para recarregar a página e refaça a sua alteração."


# --------------------------------------------------------------------------- utilitários
def hist(conn, lic_id: int, acao: str, descricao: str, usuario: str, item_id: Optional[int] = None) -> None:
    q_exec(conn, "INSERT INTO historico (licitacao_id, item_id, acao, descricao, usuario) "
                 "VALUES (:l, :i, :a, :d, :u)", l=lic_id, i=item_id, a=acao, d=descricao, u=usuario)


def _bump(conn, lic_id: int) -> None:
    q_exec(conn, "UPDATE licitacoes SET version = version + 1 WHERE id = :id", id=lic_id)


def _lic_ou_404(conn, lic_id: int, lock: bool = False) -> dict:
    r = q_one(conn, "SELECT * FROM licitacoes WHERE id = :id" + (" FOR UPDATE" if lock else ""), id=lic_id)
    if not r:
        raise NaoEncontrado("Licitação não encontrada.")
    return r


def _validar_cnpj(valor: str) -> str:
    limpo = v.limpar_cnpj(valor)
    if not limpo:
        raise st.RegraNegocioErro("CNPJ inválido: informe 14 caracteres (12 letras/números + 2 dígitos verificadores).")
    if settings.cnpj_validar_dv and not v.cnpj_valido(limpo):
        raise st.RegraNegocioErro("CNPJ inválido: os dígitos verificadores não conferem.")
    return limpo


def _salvar_documento(conn, lic: dict, tipo: str, nome: str, conteudo: bytes, usuario: str, permitidos) -> str:
    mime = v.validar_arquivo(nome, conteudo, permitidos, settings.max_upload_mb * v.MB)
    doc_id = str(uuid.uuid4())
    caminho = f"licitacoes/{lic['created_at'].year}/{lic['codigo']}/{tipo}/{doc_id}_{v.nome_seguro(nome)}"
    storage.salvar(caminho, conteudo)
    q_exec(conn, "INSERT INTO licitacao_documentos (id, licitacao_id, tipo, nome_arquivo, mime_type, tamanho_bytes, "
                 "storage_path, enviado_por) VALUES (:id, :l, :t, :n, :m, :s, :p, :u)",
           id=doc_id, l=lic["id"], t=tipo, n=v.nome_seguro(nome), m=mime, s=len(conteudo), p=caminho, u=usuario)
    return doc_id


# --------------------------------------------------------------------------- consulta
def autopreencher_por_cnpj(conn, cnpj: str) -> Optional[dict]:
    """Guia pág. 11: se o órgão já foi atendido, nome, UF, vendedor e e-mails vêm do último empenho."""
    limpo = v.limpar_cnpj(cnpj)
    if not limpo:
        return None
    return q_one(conn, "SELECT orgao, uf, vendedor, emails_responsaveis FROM licitacoes WHERE cnpj = :c "
                       "ORDER BY created_at DESC LIMIT 1", c=limpo)


def listar(conn, q=None, situacao=None, status_item=None, vendedor=None, de=None, ate=None,
           so_vencidos=False, pagina=1, tamanho=25) -> dict:
    where, p = ["1=1"], {}
    if q and q.strip():
        p["like"] = f"%{q.strip()}%"
        alnum = v.limpar_cnpj(q) or "".join(c for c in q.upper() if c.isalnum())
        p["like_cnpj"] = f"%{alnum}%" if len(alnum) >= 4 else "__sem_cnpj__"
        where.append(
            "(r.orgao ILIKE :like OR r.cnpj ILIKE :like_cnpj OR r.empenho ILIKE :like OR r.pregao ILIKE :like "
            "OR r.codigo ILIKE :like "
            "OR EXISTS (SELECT 1 FROM licitacao_itens i WHERE i.licitacao_id = r.id "
            "           AND (i.op_numero ILIKE :like OR i.anotacao ILIKE :like)) "
            "OR EXISTS (SELECT 1 FROM notas_fiscais n WHERE n.licitacao_id = r.id AND n.numero ILIKE :like))"
        )
    if situacao:
        where.append("r.situacao = :situacao")
        p["situacao"] = situacao
    if status_item:
        where.append(":status_item = ANY(r.status_itens)")
        p["status_item"] = status_item
    if vendedor:
        where.append("r.vendedor ILIKE :vendedor")
        p["vendedor"] = vendedor
    if de:
        where.append("r.recebimento >= :de")
        p["de"] = de
    if ate:
        where.append("r.recebimento <= :ate")
        p["ate"] = ate
    if so_vencidos:
        where.append("r.situacao = 'ANDAMENTO' AND r.prazo_entrega < CURRENT_DATE")
    w = " AND ".join(where)
    total = q_one(conn, f"SELECT COUNT(*) AS n FROM vw_licitacoes_resumo r WHERE {w}", **p)["n"]
    p.update(lim=tamanho, off=(max(pagina, 1) - 1) * tamanho)
    itens = q_all(
        conn,
        f"SELECT r.*, (r.situacao = 'ANDAMENTO' AND r.prazo_entrega < CURRENT_DATE) AS prazo_vencido "
        f"FROM vw_licitacoes_resumo r WHERE {w} ORDER BY r.recebimento DESC, r.id DESC LIMIT :lim OFFSET :off", **p)
    return {"itens": itens, "total": total, "pagina": pagina, "tamanho": tamanho}


def painel(conn) -> dict:
    ind = q_one(conn, """
        SELECT COUNT(*) FILTER (WHERE situacao = 'ANDAMENTO')                                   AS em_andamento,
               COUNT(*) FILTER (WHERE situacao = 'ANDAMENTO' AND prazo_entrega < CURRENT_DATE)  AS prazo_vencido
          FROM vw_licitacoes_resumo""")
    fat = q_one(conn, """
        SELECT COALESCE(SUM(valor), 0) AS faturado_mes, COUNT(*) AS notas_mes FROM notas_fiscais
         WHERE date_trunc('month', data_faturamento) = date_trunc('month', CURRENT_DATE)""")
    nao_env = q_one(conn, "SELECT COUNT(*) AS n FROM notas_fiscais WHERE email_status = 'NAO_ENVIADO'")["n"]
    itens = q_all(conn, """
        SELECT status, COUNT(*) AS qtd, COALESCE(SUM(valor_total), 0) AS valor FROM licitacao_itens
         WHERE status IN ('EMP_RECEBIDO','AG_ESTOQUE','TROCA_MARCA','LANCADO_SISTEMA','CARTA_CORRECAO')
         GROUP BY status ORDER BY qtd DESC""")
    prazos = q_all(conn, """
        SELECT id, codigo, orgao, uf, empenho, prazo_entrega, situacao,
               (prazo_entrega < CURRENT_DATE) AS prazo_vencido
          FROM vw_licitacoes_resumo WHERE situacao = 'ANDAMENTO' AND prazo_entrega IS NOT NULL
         ORDER BY prazo_entrega ASC LIMIT 10""")
    return {"indicadores": {**ind, **fat, "emails_nao_enviados": nao_env}, "itens_que_pedem_acao": itens,
            "proximos_prazos": prazos}


def obter(conn, lic_id: int, hoje: Optional[date] = None) -> dict:
    hoje = hoje or date.today()
    lic = _lic_ou_404(conn, lic_id)
    itens = q_all(conn, "SELECT * FROM licitacao_itens WHERE licitacao_id = :l ORDER BY id", l=lic_id)
    docs = q_all(conn, "SELECT id, tipo, nome_arquivo, mime_type, tamanho_bytes, enviado_por, enviado_em "
                       "FROM licitacao_documentos WHERE licitacao_id = :l AND ativo ORDER BY enviado_em DESC", l=lic_id)
    notas = q_all(conn, """
        SELECT n.*, d.nome_arquivo, d.tamanho_bytes, d.enviado_por AS arquivo_enviado_por, d.enviado_em AS arquivo_enviado_em,
               COALESCE((SELECT ARRAY_AGG(ni.item_id) FROM nota_itens ni WHERE ni.nota_id = n.id), '{}') AS item_ids
          FROM notas_fiscais n LEFT JOIN licitacao_documentos d ON d.id = n.documento_id
         WHERE n.licitacao_id = :l ORDER BY n.created_at DESC""", l=lic_id)
    historico = q_all(conn, "SELECT * FROM historico WHERE licitacao_id = :l ORDER BY created_at DESC, id DESC", l=lic_id)

    statuses = [i["status"] for i in itens]
    confirmacao = next((d for d in docs if d["tipo"] == "CONFIRMACAO"), None)
    emails_nf = [n["email_status"] for n in notas]
    situacao, vencido = st.situacao_licitacao(statuses, lic["prazo_entrega"], hoje)

    pendencias = []
    if not lic["emails_responsaveis"]:
        pendencias.append({"codigo": "CADASTRAR_EMAILS", "descricao": "Cadastre os e-mails dos responsáveis do órgão"})
    ids_estoque = [i["id"] for i in itens if i["status"] == "EMP_RECEBIDO"]
    if ids_estoque:
        pendencias.append({"codigo": "ESTOQUE", "descricao": "Tem estoque do item empenhado?",
                           "item_ids": ids_estoque, "acoes": ["lancar", "aguardar_estoque", "propor_troca"]})
    ids_op = [i["id"] for i in itens if i["status"] == "LANCADO_SISTEMA"]
    if ids_op:
        pendencias.append({"codigo": "OP_PERDIDA", "descricao": "OP perdida — voltar a aguardar estoque",
                           "item_ids": ids_op, "acoes": ["aguardar_estoque"]})

    return {
        "licitacao": {**lic, "situacao": situacao, "prazo_vencido": vencido,
                      "valor": sum(float(i["valor_total"]) for i in itens if i["status"] != "EMP_CANCELADO")},
        "etapas": st.etapas(lic["recebimento"], confirmacao is not None, statuses, emails_nf),
        "proximo_passo": st.proximo_passo(confirmacao is not None, statuses, emails_nf),
        "pendencias": pendencias,
        "confirmacao": confirmacao,
        "itens": itens,
        "notas_fiscais": notas,
        "historico": historico,
    }


# --------------------------------------------------------------------------- escrita: licitação
def criar(conn, dados, usuario: str, arquivo: Optional[tuple[str, bytes]] = None) -> dict:
    cnpj = _validar_cnpj(dados.cnpj)
    st.validar_prazo(dados.recebimento, dados.prazo_entrega)
    emails = v.parse_emails(dados.emails_responsaveis)
    lic = q_one(conn, """
        INSERT INTO licitacoes (cnpj, orgao, uf, situacao_financeira, pregao, empenho, vendedor, recebimento,
                                prazo_entrega, emails_responsaveis, dados_nota, observacoes, criado_por)
        VALUES (:cnpj, :orgao, :uf, :sf, :pregao, :empenho, :vend, :rec, :prazo, :emails, :dn, :obs, :u)
        RETURNING *""", cnpj=cnpj, orgao=dados.orgao.strip(), uf=dados.uf.upper(), sf=dados.situacao_financeira,
                 pregao=dados.pregao.strip(), empenho=dados.empenho.strip(), vend=dados.vendedor.strip(),
                 rec=dados.recebimento, prazo=dados.prazo_entrega, emails=emails, dn=dados.dados_nota,
                 obs=dados.observacoes, u=usuario)
    for it in dados.itens:
        q_exec(conn, "INSERT INTO licitacao_itens (licitacao_id, codigo_pedido, descricao, quantidade, valor_unitario) "
                     "VALUES (:l, :c, :d, :q, :v)", l=lic["id"], c=it.codigo_pedido.strip(), d=it.descricao.strip(),
               q=it.quantidade, v=it.valor_unitario)
    hist(conn, lic["id"], "CADASTRO", f"Licitação {lic['codigo']} cadastrada com {len(dados.itens)} item(ns).", usuario)
    if arquivo:
        _salvar_documento(conn, lic, "CONFIRMACAO", arquivo[0], arquivo[1], usuario, v.CONFIRMACAO_TIPOS)
        hist(conn, lic["id"], "CONFIRMACAO", f"Confirmação do empenho anexada: {v.nome_seguro(arquivo[0])}.", usuario)
    return {"id": lic["id"], "codigo": lic["codigo"]}


def editar(conn, lic_id: int, dados, usuario: str) -> dict:
    atual = _lic_ou_404(conn, lic_id, lock=True)
    if atual["version"] != dados.version:
        raise Conflito(MSG_CONCORRENCIA)
    campos = {k: val for k, val in dados.model_dump(exclude={"version"}).items() if val is not None}
    if "cnpj" in campos:
        campos["cnpj"] = _validar_cnpj(campos["cnpj"])
    if "uf" in campos:
        campos["uf"] = campos["uf"].upper()
    if "emails_responsaveis" in campos:
        campos["emails_responsaveis"] = v.parse_emails(campos["emails_responsaveis"])
    st.validar_prazo(campos.get("recebimento", atual["recebimento"]), campos.get("prazo_entrega", atual["prazo_entrega"]))
    alterados = [k for k, val in campos.items() if atual[k] != val]
    if alterados:
        sets = ", ".join(f"{k} = :{k}" for k in alterados)
        q_exec(conn, f"UPDATE licitacoes SET {sets}, version = version + 1 WHERE id = :id",
               id=lic_id, **{k: campos[k] for k in alterados})
        hist(conn, lic_id, "EDICAO", "Dados editados: " + ", ".join(alterados) + ".", usuario)
    return {"version": atual["version"] + (1 if alterados else 0)}


def anexar_confirmacao(conn, lic_id: int, nome: str, conteudo: bytes, usuario: str) -> dict:
    lic = _lic_ou_404(conn, lic_id, lock=True)
    substituindo = q_one(conn, "SELECT 1 AS x FROM licitacao_documentos WHERE licitacao_id = :l AND tipo = 'CONFIRMACAO' AND ativo",
                         l=lic_id) is not None
    q_exec(conn, "UPDATE licitacao_documentos SET ativo = FALSE WHERE licitacao_id = :l AND tipo = 'CONFIRMACAO'", l=lic_id)
    doc_id = _salvar_documento(conn, lic, "CONFIRMACAO", nome, conteudo, usuario, v.CONFIRMACAO_TIPOS)
    hist(conn, lic_id, "CONFIRMACAO", f"Confirmação do empenho {'substituída' if substituindo else 'anexada'}: "
                                      f"{v.nome_seguro(nome)}.", usuario)
    _bump(conn, lic_id)
    return {"documento_id": doc_id}


def adicionar_item(conn, lic_id: int, it, usuario: str) -> dict:
    _lic_ou_404(conn, lic_id, lock=True)
    r = q_one(conn, "INSERT INTO licitacao_itens (licitacao_id, codigo_pedido, descricao, quantidade, valor_unitario) "
                    "VALUES (:l, :c, :d, :q, :v) RETURNING id", l=lic_id, c=it.codigo_pedido.strip(),
              d=it.descricao.strip(), q=it.quantidade, v=it.valor_unitario)
    hist(conn, lic_id, "ITEM_ADD", f"Item adicionado: {it.descricao.strip()}.", usuario, r["id"])
    _bump(conn, lic_id)
    return r


def corrigir_item(conn, item_id: int, dados, usuario: str) -> None:
    item = q_one(conn, "SELECT * FROM licitacao_itens WHERE id = :id FOR UPDATE", id=item_id)
    if not item:
        raise NaoEncontrado("Item não encontrado.")
    if item["status"] not in {s.value for s in st.EDITAVEL_ANTES_DE_LANCAR}:
        raise st.RegraNegocioErro("Só é possível corrigir os dados do item enquanto ele não foi lançado.")
    campos = {k: val for k, val in dados.model_dump().items() if val is not None}
    if not campos:
        return
    sets = ", ".join(f"{k} = :{k}" for k in campos)
    q_exec(conn, f"UPDATE licitacao_itens SET {sets} WHERE id = :id", id=item_id, **campos)
    hist(conn, item["licitacao_id"], "ITEM_EDICAO", f"Dados do item corrigidos ({', '.join(campos)}): {item['descricao']}.",
         usuario, item_id)
    _bump(conn, item["licitacao_id"])


def anotar(conn, item_id: int, texto: str, usuario: str) -> None:
    item = q_one(conn, "SELECT * FROM licitacao_itens WHERE id = :id FOR UPDATE", id=item_id)
    if not item:
        raise NaoEncontrado("Item não encontrado.")
    q_exec(conn, "UPDATE licitacao_itens SET anotacao = :a WHERE id = :id", a=texto.strip(), id=item_id)  # não muda o status
    hist(conn, item["licitacao_id"], "ANOTACAO", f"Anotação em {item['descricao']}: {texto.strip()}", usuario, item_id)
    _bump(conn, item["licitacao_id"])


# --------------------------------------------------------------------------- transições de item
def executar_acao(conn, lic_id: int, item_ids: list[int], acao: str, usuario: str, hoje: Optional[date] = None, **campos) -> int:
    """Aplica uma ação (lancar, entregar, cancelar, ...) a um ou mais itens, validando a máquina de estados."""
    hoje = hoje or date.today()
    _lic_ou_404(conn, lic_id, lock=True)
    itens = q_all(conn, "SELECT * FROM licitacao_itens WHERE licitacao_id = :l AND id = ANY(:ids) ORDER BY id FOR UPDATE",
                  l=lic_id, ids=list(item_ids))
    if len(itens) != len(set(item_ids)):
        raise NaoEncontrado("Algum item informado não pertence a esta licitação.")
    if acao == "entregar":
        st.validar_data_entrega(campos["data_entrega"], hoje)

    for it in itens:
        origem = it["status"]
        try:
            destino = st.validar_transicao(acao, origem)
        except st.RegraNegocioErro as exc:
            raise Conflito(f"{exc} {MSG_CONCORRENCIA}") if origem in {"ENTREGUE", "EMP_CANCELADO"} else exc
        st.exigir_campos(acao, origem, **campos)
        up: dict = {"status_anterior": origem}
        desc = ""
        if acao == "lancar":
            destino = st.ItemStatus.LANCADO_SISTEMA
            up.update(op_numero=campos["op_numero"].strip(), ordem_remessa=campos.get("ordem_remessa"),
                      codigo_produto_enviado=(campos.get("codigo_produto_enviado") or None), motivo=None)
            desc = f"Lançado no sistema: OP {up['op_numero']}" + (
                f", produto enviado {up['codigo_produto_enviado']}" if up["codigo_produto_enviado"] else "")
            if campos.get("observacao"):
                desc += f" — {campos['observacao']}"
        elif acao == "aguardar_estoque":
            if origem == "LANCADO_SISTEMA":  # OP perdida: a OP antiga fica registrada no histórico
                desc = f"OP perdida ({it['op_numero']}): voltou a aguardar estoque. Motivo: {campos['motivo'].strip()}"
                up.update(op_numero=None, ordem_remessa=None, codigo_produto_enviado=None, motivo=campos["motivo"].strip())
            else:
                desc = "Aguardando estoque" + (f": {campos['motivo']}" if campos.get("motivo") else "")
                up.update(motivo=campos.get("motivo"))
        elif acao == "propor_troca":
            up.update(proposta_troca=campos["proposta_troca"].strip())
            desc = f"Troca de marca proposta ao órgão: {up['proposta_troca']}"
        elif acao == "carta_correcao":
            up.update(carta_correcao_texto=campos["carta_correcao_texto"].strip())
            desc = f"Carta de correção solicitada: {up['carta_correcao_texto']}"
        elif acao == "entregar":
            up.update(data_entrega=campos["data_entrega"])
            desc = f"Entrega registrada em {campos['data_entrega'].strftime('%d/%m/%Y')}" + (
                f" — {campos['observacao']}" if campos.get("observacao") else "")
        elif acao == "cancelar":
            motivo = campos["motivo"].strip()
            if motivo == "Outro":
                motivo = f"Outro: {campos['motivo_detalhe'].strip()}"
            up.update(motivo=motivo)
            desc = f"Item cancelado. Motivo: {motivo}"
        elif acao == "reabrir":
            destino = st.destino_reabertura(it["status_anterior"], origem)
            up.update(motivo=campos["motivo"].strip(), data_entrega=None)
            desc = f"Item reaberto ({st.ROTULOS[origem]} → {st.ROTULOS[destino.value]}). Motivo: {campos['motivo'].strip()}"
        else:
            raise st.RegraNegocioErro(f"Ação não suportada aqui: {acao}")
        up["status"] = destino.value
        sets = ", ".join(f"{k} = :{k}" for k in up)
        q_exec(conn, f"UPDATE licitacao_itens SET {sets} WHERE id = :id", id=it["id"], **up)
        hist(conn, lic_id, acao.upper(), f"{it['descricao']}: {desc}", usuario, it["id"])
    _bump(conn, lic_id)
    return len(itens)


# --------------------------------------------------------------------------- nota fiscal + e-mail
def _itens_para_nota(conn, lic_id: int, item_ids: list[int]) -> list[dict]:
    itens = q_all(conn, "SELECT * FROM licitacao_itens WHERE licitacao_id = :l AND id = ANY(:ids) ORDER BY id FOR UPDATE",
                  l=lic_id, ids=list(item_ids))
    if len(itens) != len(set(item_ids)):
        raise NaoEncontrado("Algum item informado não pertence a esta licitação.")
    invalidos = [i for i in itens if i["status"] not in {"LANCADO_SISTEMA", "CARTA_CORRECAO"}]
    if invalidos:
        raise st.RegraNegocioErro("Só itens lançados no sistema podem ser faturados: "
                                  + "; ".join(f"{i['descricao']} ({st.ROTULOS[i['status']]})" for i in invalidos))
    return itens


def preview_email(conn, lic_id: int, numero: str, data_faturamento: date, item_ids: list[int]) -> dict:
    lic = _lic_ou_404(conn, lic_id)
    itens = _itens_para_nota(conn, lic_id, item_ids)
    assunto = emailing.assunto_padrao(numero, lic["empenho"], lic["orgao"])
    mensagem = emailing.mensagem_padrao(numero, lic["empenho"])
    dados = {"Nota fiscal": numero, "Emissão": data_faturamento.strftime("%d/%m/%Y"), "Órgão": lic["orgao"],
             "CNPJ": v.formatar_cnpj(lic["cnpj"]), "Pregão/Processo": lic["pregao"], "Empenho": lic["empenho"]}
    return {"para": lic["emails_responsaveis"], "assunto": assunto, "mensagem": mensagem,
            "html": emailing.montar_html(mensagem, dados, itens)}


def registrar_nf(conn, lic_id: int, numero: str, data_faturamento: date, previsao_entrega: Optional[date],
                 item_ids: list[int], nome_arquivo: str, conteudo: bytes, usuario: str,
                 email_para: list[str], assunto: Optional[str], mensagem: Optional[str]) -> dict:
    """Etapa 1 (grava a nota e fatura os itens). O envio do e-mail é a etapa 2 (outra transação)."""
    lic = _lic_ou_404(conn, lic_id, lock=True)
    numero = numero.strip()
    if not numero:
        raise st.RegraNegocioErro("Informe o número da NF.")
    if q_one(conn, "SELECT 1 AS x FROM notas_fiscais WHERE licitacao_id = :l AND numero = :n", l=lic_id, n=numero):
        raise Conflito(f"A NF {numero} já foi registrada nesta licitação.")
    itens = _itens_para_nota(conn, lic_id, item_ids)
    para = v.parse_emails(email_para)
    doc_id = _salvar_documento(conn, lic, "NF", nome_arquivo, conteudo, usuario, v.NOTA_FISCAL_TIPOS)
    valor = round(sum(float(i["valor_total"]) for i in itens), 2)
    nf = q_one(conn, """
        INSERT INTO notas_fiscais (licitacao_id, numero, data_faturamento, previsao_entrega, valor, documento_id,
                                   email_para, email_assunto, email_mensagem, registrada_por)
        VALUES (:l, :n, :d, :p, :v, :doc, :para, :ass, :msg, :u) RETURNING id""",
               l=lic_id, n=numero, d=data_faturamento, p=previsao_entrega, v=valor, doc=doc_id, para=para,
               ass=assunto or emailing.assunto_padrao(numero, lic["empenho"], lic["orgao"]),
               msg=mensagem or emailing.mensagem_padrao(numero, lic["empenho"]), u=usuario)
    for i in itens:
        q_exec(conn, "INSERT INTO nota_itens (nota_id, item_id) VALUES (:n, :i)", n=nf["id"], i=i["id"])
        q_exec(conn, "UPDATE licitacao_itens SET status_anterior = status, status = 'FATURADO', carta_correcao_texto = NULL "
                     "WHERE id = :id", id=i["id"])
        hist(conn, lic_id, "FATURAR", f"{i['descricao']}: faturado na NF {numero}.", usuario, i["id"])
    hist(conn, lic_id, "NF", f"NF {numero} registrada: {len(itens)} itens, {emailing.brl(valor)}.", usuario)
    if previsao_entrega and not lic["prazo_entrega"]:
        pass  # a previsão fica na NF; o prazo do órgão continua sendo o do empenho
    _bump(conn, lic_id)
    return {"nota_id": nf["id"], "valor": valor}


def enviar_email_nf(conn, nota_id: int, usuario: str, para: Optional[list[str]] = None,
                    assunto: Optional[str] = None, mensagem: Optional[str] = None) -> dict:
    nf = q_one(conn, "SELECT * FROM notas_fiscais WHERE id = :id FOR UPDATE", id=nota_id)
    if not nf:
        raise NaoEncontrado("Nota fiscal não encontrada.")
    ult = nf["email_ultima_tentativa"]
    if ult and datetime.now(timezone.utc) - ult < timedelta(seconds=settings.email_reenvio_espera_s):
        raise LimiteTentativas("Espere um minuto entre uma tentativa e outra.")
    lic = _lic_ou_404(conn, nf["licitacao_id"])
    destinatarios = v.parse_emails(para) if para is not None else (nf["email_para"] or lic["emails_responsaveis"])
    if not destinatarios:
        raise st.RegraNegocioErro("Sem e-mail de responsável: cadastre em Editar dados.")
    assunto = assunto or nf["email_assunto"] or emailing.assunto_padrao(nf["numero"], lic["empenho"], lic["orgao"])
    mensagem = mensagem or nf["email_mensagem"] or emailing.mensagem_padrao(nf["numero"], lic["empenho"])
    itens = q_all(conn, "SELECT i.* FROM licitacao_itens i JOIN nota_itens ni ON ni.item_id = i.id WHERE ni.nota_id = :n ORDER BY i.id",
                  n=nota_id)
    dados = {"Nota fiscal": nf["numero"], "Emissão": nf["data_faturamento"].strftime("%d/%m/%Y"), "Órgão": lic["orgao"],
             "CNPJ": v.formatar_cnpj(lic["cnpj"]), "Pregão/Processo": lic["pregao"], "Empenho": lic["empenho"]}
    html = emailing.montar_html(mensagem, dados, itens)
    anexo = None
    doc = q_one(conn, "SELECT * FROM licitacao_documentos WHERE id = :id", id=nf["documento_id"]) if nf["documento_id"] else None
    if doc:
        anexo = (doc["nome_arquivo"], storage.ler(doc["storage_path"]), doc["mime_type"])
    ok, erro = mailer.enviar(destinatarios, assunto, mensagem, html, anexo)
    q_exec(conn, """UPDATE notas_fiscais SET email_status = :s, email_erro = :e, email_para = :p, email_assunto = :a,
                    email_mensagem = :m, email_ultima_tentativa = NOW(),
                    email_enviado_em = CASE WHEN :ok THEN NOW() ELSE email_enviado_em END WHERE id = :id""",
           s="ENVIADO" if ok else "NAO_ENVIADO", e=erro, p=destinatarios, a=assunto, m=mensagem, ok=ok, id=nota_id)
    hist(conn, lic["id"], "EMAIL",
         (f'E-mail da NF {nf["numero"]} enviado para {", ".join(destinatarios)} — assunto "{assunto}".' if ok
          else f'Falha ao enviar o e-mail da NF {nf["numero"]}: {erro}'), usuario)
    _bump(conn, lic["id"])
    return {"enviado": ok, "erro": erro}


def sem_enviar(conn, nota_id: int) -> None:
    """'Registrar sem enviar': a nota fica com e-mail PENDENTE para envio posterior pelo cartão da nota."""
    q_exec(conn, "UPDATE notas_fiscais SET email_status = 'PENDENTE' WHERE id = :id", id=nota_id)


# --------------------------------------------------------------------------- documentos
def documento(conn, doc_id: str) -> tuple[dict, bytes]:
    d = q_one(conn, "SELECT * FROM licitacao_documentos WHERE id = CAST(:id AS UUID)", id=doc_id)
    if not d:
        raise NaoEncontrado("Documento não encontrado.")
    return d, storage.ler(d["storage_path"])
