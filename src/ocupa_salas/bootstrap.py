"""
Bootstrap de sessão + captura/scrub de fixtures — rodado por um humano, uma vez.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues

O login SSO+MFA é **semi-manual**: este script abre um browser, o humano autentica, e o
cookie de sessão resultante é gravado no campo ``Extra`` da Airflow Connection
``reservaspace_{ambiente}`` — nunca em arquivo. Com a sessão de pé, o modo ``capture``
baixa respostas reais para ``.captures/`` (gitignored) e o modo ``scrub`` as converte em
fixtures versionáveis sem PII (``tests/fixtures/``).

Contra o ``mock_server/`` não há login: use ``OCUPA_SALAS_COOKIE=RSSESSID=demo``.

Requer o extra opcional: ``pip install 'ocupa-salas[bootstrap]'`` (playwright).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ocupa_salas.http_client import Connection, ReservaSpaceClient
from ocupa_salas.parser import extract_events, extract_locais
from ocupa_salas.scrub import scrub_events, scrub_locais

CAPTURE_DIR = Path(".captures")
FIXTURE_DIR = Path("tests/fixtures")
DEFAULT_BASE_URL = "https://demo.reservaspace.io"

_FIXTURE_TEMPLATE = """<!doctype html>
<html><head>
<meta name="csrf-param" content="{csrf_param}">
<meta name="csrf-token" content="{csrf_token}">
</head><body>
<div id="calendarioReservas"></div>
<script>
jQuery('#calendarioReservas').fullCalendar({{
  "editable": false,
  "events": {events}
}});
</script>
</body></html>
"""

_LOCAL_FIXTURE_TEMPLATE = """<!doctype html>
<html><head>
<meta name="csrf-param" content="{csrf_param}">
<meta name="csrf-token" content="{csrf_token}">
</head><body>
<script>
var locais = {locais};
</script>
</body></html>
"""


def capture_session_cookie(
    base_url: str = DEFAULT_BASE_URL, *, browser_args: list[str] | None = None
) -> str:
    """Abre um browser para login manual e devolve o cookie de sessão (``name=value; ...``).

    Só disponível com o extra ``bootstrap`` instalado. Nada é gravado em disco aqui.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - caminho opcional
        raise RuntimeError(
            "playwright não instalado — rode: pip install 'ocupa-salas[bootstrap]'"
        ) from exc

    with sync_playwright() as pw:  # pragma: no cover - exige interação humana
        browser = pw.chromium.launch(headless=False, args=browser_args or [])
        page = browser.new_page()
        page.goto(base_url)
        input("Faça o login SSO+MFA na janela do browser e tecle ENTER aqui... ")
        cookies = page.context.cookies()
        browser.close()
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def store_cookie_in_connection(
    conn_id: str, cookie: str, *, base_url: str = DEFAULT_BASE_URL, id_local: str | None = None
) -> None:
    """Grava/atualiza o cookie no campo ``Extra`` (JSON) da Airflow Connection ``conn_id``."""
    try:  # pragma: no cover - depende do ambiente Airflow
        from airflow.models import Connection as AirflowConnection
        from airflow.utils.session import create_session
    except ImportError as exc:  # pragma: no cover
        # NUNCA ecoar o cookie para stdout/log. Só o esqueleto do Extra, sem o segredo.
        skeleton = json.dumps(
            {
                "base_url": base_url,
                "cookie": "<cole o cookie da sessão aqui>",
                "id_local": id_local or "<preencher>",
            },
            indent=2,
            ensure_ascii=False,
        )
        raise RuntimeError(
            f"Airflow indisponível. Rode 'airflow connections add {conn_id}' com este "
            f"Extra (o cookie foi capturado e está em memória neste processo):\n{skeleton}"
        ) from exc

    with create_session() as session:  # pragma: no cover
        conn = (
            session.query(AirflowConnection)
            .filter(AirflowConnection.conn_id == conn_id)
            .one_or_none()
        )
        if conn is None:
            conn = AirflowConnection(conn_id=conn_id, conn_type="http")
            session.add(conn)
        extra = json.loads(conn.extra or "{}")
        extra.update({"base_url": base_url, "cookie": cookie})
        if id_local:
            extra["id_local"] = id_local
        conn.extra = json.dumps(extra, ensure_ascii=False)
        session.commit()


def capture_raw(
    conn: Connection, out_dir: Path = CAPTURE_DIR, *, http: object | None = None
) -> list[Path]:
    """Baixa ``GET /`` + ``get-salas`` e grava os corpos crus em ``out_dir``.

    ``out_dir`` é gitignored (`.captures/`) — o conteúdo tem PII real. Devolve os
    caminhos escritos. ``http`` é injetável para teste.
    """
    kwargs = {"http": http} if http is not None else {}
    raw = ReservaSpaceClient(conn, **kwargs).fetch_raw()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, text in raw.items():
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def build_fixture_html(
    raw_html: str, *, csrf_param: str = "reservaspace_csrf", csrf_token: str = "fixture-csrf-token"
) -> str:
    """Extrai ``events`` do HTML cru, aplica o scrub e devolve um HTML de fixture enxuto."""
    scrubbed = scrub_events(extract_events(raw_html))
    return _FIXTURE_TEMPLATE.format(
        csrf_param=csrf_param,
        csrf_token=csrf_token,
        events=json.dumps(scrubbed, ensure_ascii=False, indent=2),
    )


def build_local_fixture_html(
    raw_html: str, *, csrf_param: str = "reservaspace_csrf", csrf_token: str = "fixture-csrf-token"
) -> str:
    """Idem para a captura crua de ``/painel-config/local``: scrub do global ``locais``."""
    scrubbed = scrub_locais(extract_locais(raw_html))
    return _LOCAL_FIXTURE_TEMPLATE.format(
        csrf_param=csrf_param,
        csrf_token=csrf_token,
        locais=json.dumps(scrubbed, ensure_ascii=False, indent=2),
    )


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    cookie = capture_session_cookie(args.base_url)
    store_cookie_in_connection(args.conn_id, cookie, base_url=args.base_url, id_local=args.id_local)
    print(f"cookie gravado na Connection {args.conn_id!r}")
    return 0


def _cmd_capture(args: argparse.Namespace) -> int:
    conn = Connection(
        base_url=args.base_url.rstrip("/"), cookie=args.cookie, id_local=args.id_local
    )
    written = capture_raw(conn, Path(args.out_dir))
    for path in written:
        print(f"capturado: {path}")
    return 0


_FIXTURE_BUILDERS = {"calendar": build_fixture_html, "local": build_local_fixture_html}


def _cmd_scrub(args: argparse.Namespace) -> int:
    raw = Path(args.raw).read_text(encoding="utf-8")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_FIXTURE_BUILDERS[args.kind](raw), encoding="utf-8")
    print(f"fixture escrita em {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ocupa-salas-bootstrap", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bootstrap", help="login manual + grava cookie na Connection")
    b.add_argument("--conn-id", default="reservaspace_dev")
    b.add_argument("--base-url", default=DEFAULT_BASE_URL)
    b.add_argument("--id-local", default=None)
    b.set_defaults(func=_cmd_bootstrap)

    c = sub.add_parser("capture", help="baixa GET / + get-salas crus para .captures/")
    c.add_argument("--base-url", default=DEFAULT_BASE_URL)
    c.add_argument("--cookie", required=True, help="cookie de sessão do bootstrap")
    c.add_argument("--id-local", required=True)
    c.add_argument("--out-dir", default=str(CAPTURE_DIR))
    c.set_defaults(func=_cmd_capture)

    s = sub.add_parser("scrub", help="captura crua → fixture versionável sem PII")
    s.add_argument("--raw", required=True, help="HTML cru de .captures/ (GET / ou local)")
    s.add_argument("--out", required=True, help="destino em tests/fixtures/")
    s.add_argument(
        "--kind",
        choices=sorted(_FIXTURE_BUILDERS),
        default="calendar",
        help="calendar = tela de calendário (events); local = /painel-config/local",
    )
    s.set_defaults(func=_cmd_scrub)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "build_fixture_html",
    "build_local_fixture_html",
    "capture_raw",
    "capture_session_cookie",
    "main",
    "store_cookie_in_connection",
]
