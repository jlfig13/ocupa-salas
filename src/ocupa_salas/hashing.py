"""
``hash_linha`` — impressão digital estável da reserva stripada, base do versionamento.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues

O hash é calculado sobre o conteúdo pós-strip (ADR-0001 D3): mesmo conteúdo → mesmo
hash (re-executar a janela de coleta é idempotente); qualquer campo escalar que muda →
hash novo → linha nova na staging.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def hash_linha(payload: dict[str, Any]) -> str:
    """SHA-256 hex da serialização canônica (chaves ordenadas) de ``payload``.

    Determinístico e independente da ordem de inserção das chaves.
    """
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
