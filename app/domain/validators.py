"""Validações compartilhadas: CNPJ (numérico e ALFANUMÉRICO), e-mails e arquivos (magic bytes)."""
from __future__ import annotations

import re
from typing import Iterable, Optional

# --- CNPJ -------------------------------------------------------------------------------------
# Desde jul/2026 o CNPJ pode ser alfanumérico (12 posições [0-9A-Z] + 2 DV numéricos).
# Os scripts originais assumiam 14 dígitos numéricos (regexp '\D') e descartariam esses CNPJs.
CNPJ_RE = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")
_PESOS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def limpar_cnpj(valor) -> Optional[str]:
    """Remove pontuação, coloca em maiúsculas e devolve None se não tiver o formato de CNPJ."""
    if valor is None:
        return None
    s = re.sub(r"[^0-9A-Za-z]", "", str(valor)).upper()
    return s if CNPJ_RE.match(s) else None


def _dv(base: str) -> int:
    soma = sum((ord(c) - 48) * p for c, p in zip(base, _PESOS[-len(base):]))
    r = soma % 11
    return 0 if r < 2 else 11 - r


def cnpj_valido(valor) -> bool:
    """Valida formato + dígitos verificadores (módulo 11 sobre ord(caractere)-48)."""
    s = limpar_cnpj(valor)
    if not s or len(set(s)) == 1:
        return False
    return int(s[12]) == _dv(s[:12]) and int(s[13]) == _dv(s[:13])


def formatar_cnpj(s: str) -> str:
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}" if s and len(s) == 14 else (s or "")


# --- E-mails ----------------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[^@\s;,]+@[^@\s;,]+\.[^@\s;,]+$")


def parse_emails(texto) -> list[str]:
    """Aceita lista ou string separada por ';' (ou ','). Normaliza, remove duplicados e valida."""
    if texto is None:
        return []
    partes = texto if isinstance(texto, (list, tuple)) else re.split(r"[;,\n]", str(texto))
    vistos, saida = set(), []
    for p in partes:
        e = p.strip().lower()
        if not e:
            continue
        if not _EMAIL_RE.match(e):
            raise ValueError(f"E-mail inválido: {e}")
        if e not in vistos:
            vistos.add(e)
            saida.append(e)
    return saida


# --- Arquivos ---------------------------------------------------------------------------------
MB = 1024 * 1024
TIPOS = {  # nome -> (mime, extensões)
    "pdf": ("application/pdf", {".pdf"}),
    "png": ("image/png", {".png"}),
    "jpeg": ("image/jpeg", {".jpg", ".jpeg"}),
    "xml": ("application/xml", {".xml"}),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", {".docx"}),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", {".xlsx"}),
    "zip": ("application/zip", {".zip"}),
}
CONFIRMACAO_TIPOS = ("pdf", "png", "jpeg")          # Guia pág. 14: PDF, PNG ou JPEG, até 8 MB
NOTA_FISCAL_TIPOS = ("pdf", "xml")                   # Guia pág. 17: DANFE (PDF) ou XML, até 8 MB
DOC_PREGAO_TIPOS = ("pdf", "png", "jpeg", "docx", "xlsx", "zip")


class ArquivoInvalido(ValueError):
    pass


def detectar_tipo(conteudo: bytes) -> Optional[str]:
    """Detecta o tipo REAL pelo conteúdo (o portal recusa arquivo que 'só termina em .pdf')."""
    head = conteudo[:2048]
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"PK\x03\x04"):
        return "zip_like"
    txt = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if txt.startswith(b"<?xml") or txt.startswith(b"<nfeProc") or txt.startswith(b"<NFe"):
        return "xml"
    return None


def validar_arquivo(nome: str, conteudo: bytes, permitidos: Iterable[str], max_bytes: int = 8 * MB) -> str:
    """Valida tamanho, tipo real e extensão coerente. Retorna o MIME. Lança ArquivoInvalido."""
    if not conteudo:
        raise ArquivoInvalido("Arquivo vazio.")
    if len(conteudo) > max_bytes:
        raise ArquivoInvalido(f"Arquivo maior que {max_bytes // MB} MB.")
    permitidos = list(permitidos)
    ext = ("." + nome.rsplit(".", 1)[-1].lower()) if "." in nome else ""
    real = detectar_tipo(conteudo)
    if real == "zip_like":  # docx/xlsx/zip compartilham a assinatura PK
        real = next((t for t in ("docx", "xlsx", "zip") if t in permitidos and ext in TIPOS[t][1]), None)
    if real is None or real not in permitidos:
        nomes = ", ".join(t.upper() for t in permitidos)
        raise ArquivoInvalido(f"Arquivo não aceito. Envie: {nomes}. (O conteúdo precisa ser do tipo real, não só o nome.)")
    if ext not in TIPOS[real][1]:
        raise ArquivoInvalido(f"A extensão '{ext}' não corresponde ao conteúdo do arquivo ({real.upper()}).")
    return TIPOS[real][0]


def nome_seguro(nome: str) -> str:
    base = nome.replace("\\", "/").split("/")[-1]
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .") or "arquivo"
    return base[:200]
