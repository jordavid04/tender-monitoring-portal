"""Espelho em Python da regra de vigência de atas (trigger fn_calcular_vigencia_ata) para testes/validação."""
from __future__ import annotations

import calendar
from datetime import date
from typing import Optional

TIPOS_VIGENCIA = ("6_MESES", "12_MESES", "IMEDIATO", "PERSONALIZADO")


def somar_meses(d: date, meses: int) -> date:
    """Igual ao PostgreSQL: date + interval 'N months' (ajusta para o último dia do mês quando preciso)."""
    m = d.month - 1 + meses
    ano, mes = d.year + m // 12, m % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def calcular_fim(data_contrato: date, tipo: str, data_fim: Optional[date] = None) -> Optional[date]:
    if tipo == "6_MESES":
        return somar_meses(data_contrato, 6)
    if tipo == "12_MESES":
        return somar_meses(data_contrato, 12)
    if tipo == "IMEDIATO":
        return None
    if tipo == "PERSONALIZADO":
        if data_fim is None:
            raise ValueError("Para vigência PERSONALIZADO/ADITIVO é obrigatório informar data_fim_vigencia.")
        if data_fim < data_contrato:
            raise ValueError("O fim da vigência não pode ser anterior à data do contrato.")
        return data_fim
    raise ValueError(f"Tipo de vigência inválido: {tipo}")


def status_vigencia(tipo: str, data_fim: Optional[date], hoje: date) -> str:
    if tipo == "IMEDIATO":
        return "IMEDIATO"
    if data_fim is None:
        raise ValueError("data_fim ausente")
    if data_fim < hoje:
        return "ENCERRADO"
    if (data_fim - hoje).days <= 30:
        return "VENCE_30_DIAS"
    return "ATIVO"
