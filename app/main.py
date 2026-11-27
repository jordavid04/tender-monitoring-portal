"""Portal Licitações + novas abas (Pregões e Atas/Contratos). Execução: uvicorn app.main:app"""
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from .config import settings
from .domain.status import RegraNegocioErro
from .domain.validators import ArquivoInvalido
from .auth import NIVEL, User, get_user
from .errors import Conflito, LimiteTentativas, NaoEncontrado
from .routers import atas, licitacoes, pregoes

app = FastAPI(title="Portal Licitações — Pregões e Atas", version="1.0.0")
if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

app.include_router(licitacoes.router)
app.include_router(pregoes.router)
app.include_router(atas.router)


def _json(status: int, msg: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": msg})


@app.exception_handler(RegraNegocioErro)
async def _regra(_: Request, e: RegraNegocioErro): return _json(422, str(e))
@app.exception_handler(ArquivoInvalido)
async def _arq(_: Request, e: ArquivoInvalido): return _json(422, str(e))
@app.exception_handler(ValueError)
async def _val(_: Request, e: ValueError): return _json(422, str(e))
@app.exception_handler(Conflito)
async def _conf(_: Request, e: Conflito): return _json(409, str(e))
@app.exception_handler(NaoEncontrado)
async def _nf(_: Request, e: NaoEncontrado): return _json(404, str(e))
@app.exception_handler(LimiteTentativas)
async def _lim(_: Request, e: LimiteTentativas): return _json(429, str(e))


@app.exception_handler(IntegrityError)
async def _integridade(_: Request, e: IntegrityError):
    """Traduz violações de UNIQUE/CHECK/trigger do banco em mensagens úteis."""
    msg = str(getattr(e, "orig", e))
    if "duplicate key" in msg or "unique" in msg.lower():
        return _json(409, "Registro duplicado: " + msg.splitlines()[0])
    return _json(422, "Dado inválido: " + msg.splitlines()[0])


@app.exception_handler(Exception)
async def _generico(_: Request, e: Exception):
    # Exceções RAISE EXCEPTION das triggers (psycopg2 InternalError/RaiseException) chegam aqui:
    nome = type(e).__name__
    if nome in {"InternalError", "RaiseException", "DataError", "ProgrammingError"} or "DBAPIError" in nome:
        return _json(422, str(getattr(e, "orig", e)).splitlines()[0])
    return _json(500, "Erro interno.")


@app.get("/health")
def health():
    return {"status": "ok"}


# ----------------------------------------------------------------------------------------------
# SOMENTE DEV/STAGING (DEV_UI=1): serve a interface de ../ui e uma /sessao mínima.
# Em produção NÃO ative: o hub (Next.js) já fornece /api/v1/sessao e hospeda a interface.
# ----------------------------------------------------------------------------------------------
if os.getenv("DEV_UI") == "1":
    from fastapi.staticfiles import StaticFiles

    @app.get("/api/v1/sessao")
    def sessao_dev(user: User = Depends(get_user)):
        rot = {"CONSULTA": "Consulta", "OPERACAO": "Operação", "ADMIN": "Administração"}[user.perfil]
        return {"nome": user.nome, "papel": user.perfil, "papelRotulo": rot,
                "podeEditar": NIVEL[user.perfil] >= 2, "podeAdministrar": NIVEL[user.perfil] >= 3}

    _ui = Path(os.getenv("UI_DIR", Path(__file__).resolve().parent.parent / "ui"))
    if _ui.is_dir():
        app.mount("/", StaticFiles(directory=_ui, html=True), name="ui")
