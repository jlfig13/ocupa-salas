"""
CLI do coletor: ``python -m ocupa_salas {check-session,collect}``.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues

``--mock`` sobe a fonte fictícia (``mock_server``) em processo e roda o coletor contra
ela — sem rede, sem credencial. Sem ``--mock``, a conexão vem de ``OCUPA_SALAS_*``
(ver :mod:`ocupa_salas.config`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ocupa_salas.config import connection_from_env
from ocupa_salas.http_client import Connection, check_session
from ocupa_salas.pipeline import StateStore, run_collection, write_jsonl


def _mock_http_and_conn() -> tuple[object, Connection]:
    """Cliente de teste sobre o ``mock_server`` FastAPI + Connection que aponta pra ele."""
    try:
        from mock_server.app import create_app
        from starlette.testclient import TestClient
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "modo --mock exige o extra 'mock': pip install 'ocupa-salas[mock]'"
        ) from exc

    http = TestClient(create_app(), raise_server_exceptions=True)
    conn = Connection(base_url="http://testserver", cookie="RSSESSID=demo", id_local="1")
    return http, conn


def _cmd_check_session(args: argparse.Namespace) -> int:
    if args.mock:
        http, conn = _mock_http_and_conn()
    else:
        http, conn = None, connection_from_env()
    ok = check_session(conn, http=http, raise_on_invalid=False)
    print("sessão OK" if ok else "sessão inválida — refazer bootstrap")
    return 0 if ok else 1


def _cmd_collect(args: argparse.Namespace) -> int:
    if args.mock:
        http, conn = _mock_http_and_conn()
    else:
        http, conn = None, connection_from_env()

    out = Path(args.out)
    state = StateStore(args.state or (out / "state.json"))
    run = run_collection(conn, state=state, data_particao=args.particao, http=http)

    write_jsonl(run.linhas_novas, out / "reservas.jsonl")
    write_jsonl(run.capacidade, out / "capacidade.jsonl")
    state.save()
    print(run.resumo)
    print(f"escrito em {out}/reservas.jsonl e {out}/capacidade.jsonl")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ocupa_salas", description=__doc__)
    parser.add_argument("--mock", action="store_true", help="usar a fonte fictícia em processo")
    sub = parser.add_subparsers(dest="cmd", required=True)

    cs = sub.add_parser("check-session", help="health check do cookie")
    cs.set_defaults(func=_cmd_check_session)

    co = sub.add_parser("collect", help="roda um ciclo e grava JSONL versionado")
    co.add_argument("--out", default="data", help="diretório de saída (default: data/)")
    co.add_argument("--state", default=None, help="arquivo de estado dos hashes")
    co.add_argument("--particao", default=None, help="data_particao YYYY-MM-DD (default: hoje)")
    co.set_defaults(func=_cmd_collect)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
