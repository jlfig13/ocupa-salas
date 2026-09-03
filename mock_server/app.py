"""
App FastAPI da fonte fictícia — encadeamento e manias de docs/mapeamento_fonte.md.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Dados   : 100% fictícios.

Cookies aceitos em ``RSSESSID``:
  * ``demo``  → conta multi-local: ``GET /`` cai em ``/escolher-contexto`` (ADR-0001 D7)
  * ``solo``  → conta de local único: ``GET /`` entrega o calendário direto
  * ausente / ``expired`` → ``401`` (pede re-bootstrap)

Manias reproduzidas: POST sem ``X-Requested-With`` → ``200`` com corpo vazio; CSRF
obrigatório nos POST; contexto fixado server-side sem ``Set-Cookie``.
"""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from mock_server.data import EMPRESAS, LOCAIS, calendar_events, salas_por_faixa
from mock_server.templates import CSRF_PARAM, calendar_page, escolher_contexto_page, local_page

CSRF_TOKEN = "MOCK-CSRF-TOKEN-abc123"


def _token(request: Request) -> str:
    tok = request.cookies.get("RSSESSID", "")
    if not tok or tok == "expired":
        raise HTTPException(status_code=401, detail="sessão inválida — refazer bootstrap")
    return tok


def create_app() -> FastAPI:
    app = FastAPI(title="ReservaSpace (mock)", docs_url="/_docs")
    app.state.context = {"solo": {"local": "1"}}  # 'demo' começa sem contexto

    def ctx(tok: str) -> dict[str, str]:
        return app.state.context.setdefault(tok, {})

    def _require_xhr(request: Request) -> bool:
        return request.headers.get("x-requested-with") == "XMLHttpRequest"

    def _require_csrf(request: Request, form: dict) -> None:
        if not (request.headers.get("x-csrf-token") or form.get(CSRF_PARAM)):
            raise HTTPException(status_code=403, detail="token CSRF ausente")

    @app.get("/health")
    def health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    @app.post("/_mock/reset")
    def reset() -> PlainTextResponse:
        app.state.context = {"solo": {"local": "1"}}
        return PlainTextResponse("reset")

    @app.get("/", response_class=HTMLResponse)
    def calendar(request: Request) -> HTMLResponse:
        tok = _token(request)
        if "local" not in ctx(tok):
            return HTMLResponse(escolher_contexto_page(LOCAIS, EMPRESAS, CSRF_TOKEN))
        return HTMLResponse(calendar_page(calendar_events(), CSRF_TOKEN))

    @app.get("/escolher-contexto", response_class=HTMLResponse)
    def escolher(request: Request) -> HTMLResponse:
        _token(request)
        return HTMLResponse(escolher_contexto_page(LOCAIS, EMPRESAS, CSRF_TOKEN))

    @app.post("/set-contexto")
    async def set_contexto(request: Request):
        tok = _token(request)
        if not _require_xhr(request):
            return PlainTextResponse("", status_code=200)  # mania: corpo vazio
        form = dict(await request.form())
        _require_csrf(request, form)
        params = json.loads(form["parametros"])
        ctx(tok)[params["perfil"]] = str(params["id"])
        return PlainTextResponse("1")

    @app.get("/painel-config/local", response_class=HTMLResponse)
    def painel_local(request: Request) -> HTMLResponse:
        _token(request)
        id_local = request.query_params.get("idLocal")
        locais = [loc for loc in LOCAIS if loc["idLocal"] == id_local] or LOCAIS
        return HTMLResponse(local_page(locais, CSRF_TOKEN))

    @app.post("/painel-config/get-salas")
    async def get_salas(request: Request):
        _token(request)
        if not _require_xhr(request):
            return PlainTextResponse("", status_code=200)  # mania: corpo vazio
        form = dict(await request.form())
        _require_csrf(request, form)
        fid = str(json.loads(form["parametros"])["idFaixaHorario"])
        return JSONResponse(salas_por_faixa(fid))

    return app


app = create_app()
