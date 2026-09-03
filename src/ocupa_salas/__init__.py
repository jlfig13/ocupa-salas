"""
Coletor de ocupação de salas — pacote raiz.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues
"""

from ocupa_salas.canary import CanaryResult, bucket_do_status, check_bloco_integrity
from ocupa_salas.config import connection_from_env
from ocupa_salas.errors import (
    EmptyBodyError,
    OcupaSalasError,
    PIILeakError,
    SchemaError,
    SessionExpiredError,
    UpstreamError,
)
from ocupa_salas.hashing import hash_linha
from ocupa_salas.http_client import (
    CollectResult,
    Connection,
    ReservaSpaceClient,
    check_session,
    collect,
)
from ocupa_salas.parser import Bloco, ParsedPage, ReservaRecord, extract_faixa_ids, parse_page
from ocupa_salas.pipeline import RunResult, StateStore, run_collection, write_jsonl
from ocupa_salas.scrub import scrub_events, scrub_get_salas, scrub_locais, scrub_reserva
from ocupa_salas.strip import assert_no_pii, find_forbidden_keys, strip_reserva

__all__ = [
    "Bloco",
    "CanaryResult",
    "CollectResult",
    "Connection",
    "EmptyBodyError",
    "OcupaSalasError",
    "PIILeakError",
    "ParsedPage",
    "ReservaRecord",
    "ReservaSpaceClient",
    "RunResult",
    "SchemaError",
    "SessionExpiredError",
    "StateStore",
    "UpstreamError",
    "assert_no_pii",
    "bucket_do_status",
    "check_bloco_integrity",
    "check_session",
    "collect",
    "connection_from_env",
    "extract_faixa_ids",
    "find_forbidden_keys",
    "hash_linha",
    "parse_page",
    "run_collection",
    "scrub_events",
    "scrub_get_salas",
    "scrub_locais",
    "scrub_reserva",
    "strip_reserva",
    "write_jsonl",
]
