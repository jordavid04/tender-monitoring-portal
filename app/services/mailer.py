from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Optional, Sequence, Tuple

from ..config import settings

log = logging.getLogger("mailer")


def enviar(para: Sequence[str], assunto: str, texto: str, html: str,
           anexo: Optional[Tuple[str, bytes, str]] = None) -> Tuple[bool, Optional[str]]:
    """Retorna (ok, erro). Nunca lança: a falha vira status NAO_ENVIADO com o motivo no cartão da nota."""
    try:
        if settings.mail_backend == "console":
            log.warning("[MAIL console] para=%s assunto=%s anexo=%s", list(para), assunto, anexo[0] if anexo else None)
            return True, None
        if not settings.smtp_host:
            return False, "SMTP não configurado (SMTP_HOST)."
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = settings.mail_from, ", ".join(para), assunto
        msg.set_content(texto)
        msg.add_alternative(html, subtype="html")
        if anexo:
            nome, dados, mime = anexo
            tipo, _, sub = mime.partition("/")
            msg.add_attachment(dados, maintype=tipo, subtype=sub or "octet-stream", filename=nome)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            if settings.smtp_starttls:
                s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True, None
    except Exception as exc:  # noqa: BLE001
        log.exception("Falha ao enviar e-mail")
        return False, str(exc)[:500]
