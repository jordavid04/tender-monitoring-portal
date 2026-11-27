from __future__ import annotations

import json
from typing import Any, Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from .config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"options": f"-c search_path={settings.pg_search_path}"},
)


def get_conn() -> Iterator[Connection]:
    """Dependência FastAPI: uma transação por requisição (commit ao final, rollback em erro)."""
    with engine.begin() as conn:
        yield conn


def q_all(conn: Connection, sql: str, **p) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), p).mappings().all()]


def q_one(conn: Connection, sql: str, **p) -> Optional[dict]:
    r = conn.execute(text(sql), p).mappings().first()
    return dict(r) if r else None


def q_exec(conn: Connection, sql: str, **p) -> Any:
    return conn.execute(text(sql), p)


def auditar(conn: Connection, entidade: str, entidade_id: Any, acao: str, usuario: str, detalhe: Optional[dict] = None) -> None:
    """Trilha de auditoria das abas novas (tabela pregao_auditoria)."""
    conn.execute(
        text("INSERT INTO pregao_atas.pregao_auditoria (entidade, entidade_id, acao, usuario, detalhe) "
             "VALUES (:e, :i, :a, :u, CAST(:d AS JSONB))"),
        {"e": entidade, "i": str(entidade_id), "a": acao, "u": usuario,
         "d": json.dumps(detalhe or {}, default=str, ensure_ascii=False)},
    )
