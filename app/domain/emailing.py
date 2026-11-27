"""Texto padrão e prévia do e-mail ao órgão (Guia, pág. 18)."""
from __future__ import annotations

from html import escape
from typing import Iterable


def brl(v) -> str:
    s = f"{float(v):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def assunto_padrao(numero_nf: str, empenho: str, orgao: str) -> str:
    return f"Nota fiscal {numero_nf} — Empenho {empenho} — {orgao}"


def mensagem_padrao(numero_nf: str, empenho: str) -> str:
    return (
        "Prezados,\n\n"
        f"Informamos que a nota fiscal {numero_nf}, referente ao empenho {empenho}, foi emitida e segue em anexo.\n\n"
        "Em caso de dúvida, basta responder a este e-mail.\n\n"
        "Atenciosamente,\nEquipe de Licitações — Demo"
    )


def montar_html(mensagem: str, dados_nf: dict, itens: Iterable[dict]) -> str:
    """Mensagem editável + bloco fixo (dados da nota e tabela de itens) que 'não mudam'."""
    e = lambda x: escape(str(x if x is not None else ""))  # noqa: E731
    corpo = "<br>".join(e(l) for l in mensagem.split("\n"))
    linhas = "".join(
        f"<tr><td>{e(i['codigo_pedido'])}</td><td>{e(i['descricao'])}</td>"
        f"<td align='right'>{e(i['quantidade'])}</td><td align='right'>{brl(i['valor_unitario'])}</td>"
        f"<td align='right'>{brl(float(i['valor_unitario']) * int(i['quantidade']))}</td></tr>"
        for i in itens
    )
    dados = "".join(f"<tr><td><b>{e(k)}</b></td><td>{e(v)}</td></tr>" for k, v in dados_nf.items())
    return (
        f"<div style='font-family:Arial,sans-serif;font-size:14px'><p>{corpo}</p>"
        f"<h4 style='color:#4B0082'>DADOS DA NOTA FISCAL</h4><table cellpadding='4'>{dados}</table>"
        f"<h4 style='color:#4B0082'>ITENS</h4>"
        f"<table cellpadding='4' border='1' style='border-collapse:collapse'>"
        f"<tr><th>Código</th><th>Descrição</th><th>Qtd</th><th>Unit.</th><th>Total</th></tr>{linhas}</table></div>"
    )
