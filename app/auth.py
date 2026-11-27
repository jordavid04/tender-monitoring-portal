"""Perfis do Portal Licitações: CONSULTA < OPERACAO < ADMIN (Guia, pág. 4).

PONTO DE INTEGRAÇÃO COM O PORTAL RPA: o login é do Portal RPA. Aqui há dois adaptadores:
  * AUTH_MODE=header -> o gateway/reverse-proxy do Portal RPA injeta X-User e X-Role (NUNCA exponha
                        esta API direto na internet neste modo);
  * AUTH_MODE=jwt    -> valida Authorization: Bearer <jwt> (HS256) e lê as claims configuradas.
Se o RPA usa outro mecanismo (sessão/cookie, SSO), troque apenas `get_user`.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from .config import settings

NIVEL = {"CONSULTA": 1, "OPERACAO": 2, "ADMIN": 3}
_ALIAS = {"CONSULTA": "CONSULTA", "OPERACAO": "OPERACAO", "OPERAÇÃO": "OPERACAO",
          "ADMIN": "ADMIN", "ADMINISTRACAO": "ADMIN", "ADMINISTRAÇÃO": "ADMIN",
          # [ASSUMIDO] papéis do hub — confirmar com o time RPA
          "CONSULTOR": "CONSULTA", "LEITOR": "CONSULTA", "OPERADOR": "OPERACAO", "EDITOR": "OPERACAO", "ADMINISTRADOR": "ADMIN"}


@dataclass(frozen=True)
class User:
    nome: str
    perfil: str

    def pode(self, minimo: str) -> bool:
        return NIVEL[self.perfil] >= NIVEL[minimo]


def _perfil(v: str) -> str:
    p = _ALIAS.get((v or "").strip().upper())
    if not p:
        raise HTTPException(403, "Perfil de acesso não reconhecido.")
    return p


def get_user(request: Request) -> User:
    if settings.auth_mode == "jwt":
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(401, "Token ausente.")
        try:
            import jwt  # PyJWT
            claims = jwt.decode(auth[7:], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(401, f"Token inválido: {exc}") from exc
        return User(str(claims.get(settings.jwt_claim_user, "desconhecido")), _perfil(str(claims.get(settings.jwt_claim_role, ""))))
    nome, role = request.headers.get("x-user"), request.headers.get("x-role")
    if not nome or not role:
        raise HTTPException(401, "Usuário não identificado (cabeçalhos X-User/X-Role).")
    return User(nome, _perfil(role))


def exigir(minimo: str):
    """Uso: user: User = Depends(exigir('OPERACAO'))."""
    def dep(user: User = Depends(get_user)) -> User:
        if not user.pode(minimo):
            raise HTTPException(403, "Seu perfil não permite esta ação (perfil de consulta não altera nada).")
        return user
    return dep
