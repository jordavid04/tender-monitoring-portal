"""Armazenamento de arquivos. Padrão: disco local (STORAGE_DIR). Troque por S3/Supabase Storage
implementando a mesma interface (salvar/ler)."""
from __future__ import annotations

import os
from pathlib import Path

from ..config import settings


class StorageLocal:
    def __init__(self, raiz: str):
        self.raiz = Path(raiz).resolve()

    def _abs(self, caminho: str) -> Path:
        p = (self.raiz / caminho).resolve()
        if self.raiz not in p.parents and p != self.raiz:  # bloqueia path traversal
            raise ValueError("Caminho de armazenamento inválido.")
        return p

    def salvar(self, caminho: str, conteudo: bytes) -> None:
        p = self._abs(caminho)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(conteudo)
        os.replace(tmp, p)

    def ler(self, caminho: str) -> bytes:
        return self._abs(caminho).read_bytes()


storage = StorageLocal(settings.storage_dir)
