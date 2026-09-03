"""
Montagem da :class:`~ocupa_salas.http_client.Connection` a partir do ambiente.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues

Credencial nunca é hardcoded (ADR-0001 D2). Em produção vem da Airflow Connection; em
linha de comando / CI, das variáveis ``OCUPA_SALAS_*``. Contra o ``mock_server`` basta
``OCUPA_SALAS_BASE_URL=http://localhost:8000`` + ``OCUPA_SALAS_COOKIE=RSSESSID=demo`` +
``OCUPA_SALAS_ID_LOCAL=1``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from ocupa_salas.http_client import Connection

ENV_PREFIX = "OCUPA_SALAS_"


def connection_from_env(env: Mapping[str, str] | None = None) -> Connection:
    """Lê ``OCUPA_SALAS_{BASE_URL,COOKIE,ID_LOCAL,ID_EMPRESA,TIMEOUT}`` do ambiente.

    ``BASE_URL``, ``COOKIE`` e ``ID_LOCAL`` são obrigatórios; os demais têm default.
    """
    src = os.environ if env is None else env

    def need(key: str) -> str:
        val = src.get(ENV_PREFIX + key)
        if not val:
            raise KeyError(f"variável de ambiente obrigatória ausente: {ENV_PREFIX}{key}")
        return val

    return Connection(
        base_url=need("BASE_URL").rstrip("/"),
        cookie=need("COOKIE"),
        id_local=need("ID_LOCAL"),
        id_empresa=src.get(ENV_PREFIX + "ID_EMPRESA", "") or "",
        timeout=float(src.get(ENV_PREFIX + "TIMEOUT", "30") or "30"),
    )
