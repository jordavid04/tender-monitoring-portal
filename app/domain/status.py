"""Máquina de estados do Portal Licitações (engenharia reversa do Guia de Uso, págs. 6-7, 15-21).

Módulo puro (sem banco, sem FastAPI) para ser testável e reutilizável pelo time de RPA.
A regra de `situacao_licitacao` também existe em SQL (view vw_licitacoes_resumo): mantenha as duas em sincronia.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Iterable, Optional


class ItemStatus(str, Enum):
    EMP_RECEBIDO = "EMP_RECEBIDO"
    AG_ESTOQUE = "AG_ESTOQUE"
    TROCA_MARCA = "TROCA_MARCA"
    LANCADO_SISTEMA = "LANCADO_SISTEMA"
    FATURADO = "FATURADO"
    CARTA_CORRECAO = "CARTA_CORRECAO"
    ENTREGUE = "ENTREGUE"
    EMP_CANCELADO = "EMP_CANCELADO"


ROTULOS = {
    "EMP_RECEBIDO": "Emp. recebido",
    "AG_ESTOQUE": "Ag. estoque",
    "TROCA_MARCA": "Troca de marca",
    "LANCADO_SISTEMA": "Lançado no sistema",
    "FATURADO": "Faturado",
    "CARTA_CORRECAO": "Carta de correção",
    "ENTREGUE": "Entregue",
    "EMP_CANCELADO": "Emp. cancelado",
}

S = ItemStatus
TERMINAIS = frozenset({S.ENTREGUE, S.EMP_CANCELADO})
# Itens que ainda "pedem ação" (licitação fica EM ANDAMENTO enquanto houver algum)
PENDENTES = frozenset({S.EMP_RECEBIDO, S.AG_ESTOQUE, S.TROCA_MARCA, S.LANCADO_SISTEMA, S.CARTA_CORRECAO})
ANTES_DO_LANCAMENTO = frozenset({S.EMP_RECEBIDO, S.AG_ESTOQUE, S.TROCA_MARCA})
JA_LANCADOS = frozenset({S.LANCADO_SISTEMA, S.FATURADO, S.CARTA_CORRECAO, S.ENTREGUE})
JA_FATURADOS = frozenset({S.FATURADO, S.CARTA_CORRECAO, S.ENTREGUE})

MOTIVOS_CANCELAMENTO = [  # lista assumida (o guia só cita "escolha o motivo; em Outro, descreva")
    "Órgão desistiu",
    "Troca de marca não aceita",
    "Sem estoque",
    "Empenho cancelado pelo órgão",
    "Outro",
]


class RegraNegocioErro(ValueError):
    """Violação de regra de negócio (a API converte em HTTP 422/409)."""


@dataclass(frozen=True)
class Acao:
    nome: str
    origens: frozenset
    destino: Optional[ItemStatus]


ACOES = {
    # Tem a marca empenhada? sim -> lança; não -> troca de marca ou sem estoque
    "aguardar_estoque": Acao("aguardar_estoque", frozenset({S.EMP_RECEBIDO, S.TROCA_MARCA, S.LANCADO_SISTEMA}), S.AG_ESTOQUE),
    "propor_troca": Acao("propor_troca", frozenset({S.EMP_RECEBIDO, S.AG_ESTOQUE}), S.TROCA_MARCA),
    "lancar": Acao("lancar", ANTES_DO_LANCAMENTO, S.LANCADO_SISTEMA),
    # faturar acontece pelo registro da NF; CARTA_CORRECAO volta a FATURADO quando a nota corrigida sai
    "faturar": Acao("faturar", frozenset({S.LANCADO_SISTEMA, S.CARTA_CORRECAO}), S.FATURADO),
    "carta_correcao": Acao("carta_correcao", frozenset({S.FATURADO}), S.CARTA_CORRECAO),
    "entregar": Acao("entregar", frozenset({S.FATURADO, S.CARTA_CORRECAO}), S.ENTREGUE),
    "cancelar": Acao("cancelar", frozenset(PENDENTES | {S.FATURADO}), S.EMP_CANCELADO),  # "sim, em qualquer etapa"
    "reabrir": Acao("reabrir", TERMINAIS, None),  # destino = status_anterior (administração)
}

EDITAVEL_ANTES_DE_LANCAR = ANTES_DO_LANCAMENTO  # "Corrigir dados do item: só enquanto não foi lançado"


def _st(v) -> ItemStatus:
    return v if isinstance(v, ItemStatus) else ItemStatus(v)


def validar_transicao(acao: str, origem) -> Optional[ItemStatus]:
    """Valida e devolve o destino (None para 'reabrir', que depende do status anterior)."""
    if acao not in ACOES:
        raise RegraNegocioErro(f"Ação desconhecida: {acao}")
    a, o = ACOES[acao], _st(origem)
    if o not in a.origens:
        raise RegraNegocioErro(
            f"A ação '{acao}' não é permitida para item com status '{ROTULOS[o.value]}'."
        )
    return a.destino


def exigir_campos(acao: str, origem, **campos) -> None:
    """Campos obrigatórios por ação (Guia de Uso, pág. 7: 'O que o portal pede')."""
    o = _st(origem)
    falta = []

    def vazio(k):
        v = campos.get(k)
        return v is None or (isinstance(v, str) and not v.strip())

    if acao == "lancar":
        if vazio("op_numero"):
            falta.append("OP")
        if o == S.TROCA_MARCA and vazio("codigo_produto_enviado"):
            falta.append("código do produto enviado (obrigatório quando veio de Troca de marca)")
    elif acao == "aguardar_estoque" and o == S.LANCADO_SISTEMA and vazio("motivo"):
        falta.append("motivo da OP perdida")
    elif acao == "propor_troca" and vazio("proposta_troca"):
        falta.append("descrição da proposta de troca de marca")
    elif acao == "carta_correcao" and vazio("carta_correcao_texto"):
        falta.append("o que precisa ser corrigido na nota")
    elif acao == "cancelar":
        if vazio("motivo"):
            falta.append("motivo do cancelamento")
        elif campos["motivo"].strip() == "Outro" and vazio("motivo_detalhe"):
            falta.append("descrição do motivo (motivo 'Outro')")
    elif acao == "entregar" and vazio("data_entrega"):
        falta.append("data da entrega")
    elif acao == "reabrir" and vazio("motivo"):
        falta.append("motivo da reabertura")
    if falta:
        raise RegraNegocioErro("Campo(s) obrigatório(s): " + "; ".join(falta) + ".")


def validar_data_entrega(data_entrega: date, hoje: date) -> None:
    if data_entrega > hoje:
        raise RegraNegocioErro("A data da entrega não pode ser uma data futura.")


def validar_prazo(recebimento: date, prazo: Optional[date]) -> None:
    if prazo is not None and prazo < recebimento:
        raise RegraNegocioErro("O prazo de entrega não pode ser anterior ao recebimento.")


def destino_reabertura(status_anterior: Optional[str], status_atual) -> ItemStatus:
    """Reabrir: volta ao status anterior ao encerramento; ENTREGUE sem anterior -> FATURADO; CANCELADO -> EMP_RECEBIDO."""
    atual = _st(status_atual)
    if atual not in TERMINAIS:
        raise RegraNegocioErro("Só é possível reabrir item entregue ou cancelado.")
    if status_anterior and ItemStatus(status_anterior) not in TERMINAIS:
        return ItemStatus(status_anterior)
    return S.FATURADO if atual == S.ENTREGUE else S.EMP_RECEBIDO


# ---------------------------------------------------------------------------------------------
# Situação da licitação (calculada a partir dos itens)
# ---------------------------------------------------------------------------------------------
def situacao_licitacao(statuses: Iterable, prazo_entrega: Optional[date] = None, hoje: Optional[date] = None):
    """Retorna (situacao, prazo_vencido). Situações: ANDAMENTO, FATURADA, CONCLUIDA, CANCELADA."""
    sts = [_st(s) for s in statuses]
    if not sts:
        situacao = "ANDAMENTO"
    elif all(s == S.EMP_CANCELADO for s in sts):
        situacao = "CANCELADA"
    elif any(s in PENDENTES for s in sts):
        situacao = "ANDAMENTO"
    elif any(s == S.FATURADO for s in sts):
        situacao = "FATURADA"  # nada pendente, falta registrar a entrega
    else:
        situacao = "CONCLUIDA"  # todos os itens ativos entregues
    vencido = bool(situacao == "ANDAMENTO" and prazo_entrega and hoje and prazo_entrega < hoje)
    return situacao, vencido


# ---------------------------------------------------------------------------------------------
# Barra de etapas e próximo passo (Guia, págs. 13-14)
# ---------------------------------------------------------------------------------------------
ETAPAS = ["Empenho recebido", "Confirmação", "Lançamento (OP)", "Nota fiscal", "E-mail ao órgão", "Entrega"]


def etapas(recebimento: date, tem_confirmacao: bool, statuses: Iterable, emails_nf: Iterable[str]):
    sts = [_st(s) for s in statuses if _st(s) != S.EMP_CANCELADO]
    total = len(sts)
    n_lanc = sum(s in JA_LANCADOS for s in sts)
    n_fat = sum(s in JA_FATURADOS for s in sts)
    n_ent = sum(s == S.ENTREGUE for s in sts)
    emails = list(emails_nf)

    def frac(n):
        return f"{n} de {total} item(ns)"

    if not emails:
        det_email, ok_email = "Sai junto com a NF", False
    elif all(e == "ENVIADO" for e in emails):
        det_email, ok_email = "Enviado", True
    elif any(e == "NAO_ENVIADO" for e in emails):
        det_email, ok_email = "Não enviado", False
    else:
        det_email, ok_email = "Pendente", False

    ok = [
        True,
        tem_confirmacao,
        total > 0 and n_lanc == total,
        total > 0 and n_fat == total,
        ok_email,
        total > 0 and n_ent == total,
    ]
    det = [
        recebimento.strftime("%d/%m/%Y"),
        "Anexada" if tem_confirmacao else "Falta anexar",
        frac(n_lanc), frac(n_fat), det_email, frac(n_ent),
    ]
    atual = next((i for i, v in enumerate(ok) if not v), None)
    return [
        {"numero": i + 1, "nome": ETAPAS[i], "detalhe": det[i],
         "estado": "concluida" if ok[i] else ("atual" if i == atual else "pendente")}
        for i in range(6)
    ]


def proximo_passo(tem_confirmacao: bool, statuses: Iterable, emails_nf: Iterable[str]) -> dict:
    sts = [_st(s) for s in statuses]
    emails = list(emails_nf)
    ha = lambda grupo: any(s in grupo for s in sts)  # noqa: E731

    if not tem_confirmacao and ha(PENDENTES | {S.FATURADO}):
        return {"codigo": "ANEXAR_CONFIRMACAO", "titulo": "Anexe a confirmação do empenho",
                "descricao": "O arquivo que chegou com a licitação fica guardado aqui, para ver e baixar quando precisar.",
                "botao": "Anexar confirmação"}
    if "NAO_ENVIADO" in emails:
        return {"codigo": "REENVIAR_EMAIL", "titulo": "Reenvie o e-mail da nota fiscal",
                "descricao": "O aviso ao órgão não saiu. Confira os endereços em Editar dados e tente de novo.",
                "botao": "Revisar e enviar e-mail"}
    if ha({S.LANCADO_SISTEMA, S.CARTA_CORRECAO}):
        return {"codigo": "REGISTRAR_NF", "titulo": "Registre a nota fiscal",
                "descricao": "Há itens lançados no sistema prontos para faturar (ou nota a corrigir).",
                "botao": "Registrar nota fiscal"}
    if ha({S.EMP_RECEBIDO}):
        return {"codigo": "VERIFICAR_ESTOQUE", "titulo": "Verifique o estoque",
                "descricao": "Tem estoque do item empenhado? Lance no sistema, marque sem estoque ou proponha troca de marca.",
                "botao": "Tem estoque — lançar no sistema"}
    if ha({S.AG_ESTOQUE}):
        return {"codigo": "AGUARDAR_ESTOQUE", "titulo": "Aguardando estoque",
                "descricao": "Quando o produto chegar, lance a OP.", "botao": "Lançar (OP)"}
    if ha({S.TROCA_MARCA}):
        return {"codigo": "AGUARDAR_TROCA", "titulo": "Aguardando resposta do órgão sobre a troca de marca",
                "descricao": "Se o órgão aceitar, lance a OP informando o código do produto enviado.",
                "botao": "Lançar (OP)"}
    if ha({S.FATURADO}):
        return {"codigo": "REGISTRAR_ENTREGA", "titulo": "Registre a entrega",
                "descricao": "Quando o órgão receber, marque os itens como entregues.", "botao": "Registrar entrega"}
    return {"codigo": "NENHUM", "titulo": "Nada pendente", "descricao": "", "botao": None}
