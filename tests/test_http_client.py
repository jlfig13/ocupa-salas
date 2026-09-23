"""Seam 2 — cliente HTTP: fluxo encadeado, manias da fonte, retry/backoff, health check."""

from __future__ import annotations

import json

import pytest
from requests import exceptions as rexc

from conftest import FakeResponse
from ocupa_salas.errors import EmptyBodyError, SessionExpiredError, UpstreamError
from ocupa_salas.http_client import Connection, ReservaSpaceClient, check_session, collect


@pytest.fixture
def conn():
    return Connection(
        base_url="https://demo.reservaspace.io",
        cookie="RSSESSID=fake",
        id_local="1",
        max_attempts=4,
        backoff_base=0.0,
    )


@pytest.fixture
def happy_routes(fx):
    return {
        ("GET", "/"): FakeResponse(200, fx("calendar_dia_normal.html")),
        ("GET", "/config/unidade"): FakeResponse(200, fx("local.html")),
        ("POST", "/config/capacidade-salas"): FakeResponse(200, fx("capacidade_salas.json")),
    }


def test_fluxo_encadeado_monta_as_chamadas_esperadas(conn, happy_routes, make_http):
    http = make_http(happy_routes)
    result = collect(conn, http=http)

    assert http.paths() == [
        "/",
        "/config/unidade",
        "/config/capacidade-salas",
        "/config/capacidade-salas",
    ]
    assert len(result.reservas) == 6
    assert len(result.blocos) == 3
    assert len(result.capacidade) == 2
    assert all(c.ok for c in result.canarios)


# -- ADR-0001 D7: seleção de contexto (/selecionar-contexto) -----------------


@pytest.fixture
def escolher_routes(fx, happy_routes):
    happy_routes[("GET", "/")] = [
        FakeResponse(200, fx("selecionar_contexto.html")),
        FakeResponse(200, fx("calendar_dia_normal.html")),
    ]
    selecao = FakeResponse(200, fx("selecionar_contexto.html"))
    happy_routes[("GET", "/selecionar-contexto")] = selecao
    happy_routes[("POST", "/aplicar-contexto")] = FakeResponse(200, "1")
    return happy_routes


def test_seleciona_local_quando_cai_no_selecionar_contexto(conn, escolher_routes, make_http):
    http = make_http(escolher_routes)
    result = collect(conn, http=http)

    assert http.paths()[:4] == ["/", "/selecionar-contexto", "/aplicar-contexto", "/"]
    setc = next(c for c in http.calls if c["path"] == "/aplicar-contexto")
    assert setc["headers"]["X-Requested-With"] == "XMLHttpRequest"
    assert setc["headers"]["X-CSRF-Token"] == "TESTE-CSRF-TOKEN-abc123"
    assert json.loads(setc["data"]["filtro"]) == {"escopo": "local", "id": "1"}
    assert len(result.reservas) == 6


def test_conta_local_unico_pula_selecionar_contexto(conn, happy_routes, make_http):
    http = make_http(happy_routes)
    collect(conn, http=http)
    assert "/selecionar-contexto" not in http.paths()
    assert "/aplicar-contexto" not in http.paths()


def test_seleciona_empresa_quando_configurada(conn, escolher_routes, make_http):
    conn.id_empresa = "10"
    http = make_http(escolher_routes)
    collect(conn, http=http)

    perfis = [
        json.loads(c["data"]["filtro"]) for c in http.calls if c["path"] == "/aplicar-contexto"
    ]
    assert perfis == [{"escopo": "local", "id": "1"}, {"escopo": "empresa", "id": "10"}]


def test_aplicar_contexto_resposta_inesperada_falha(conn, escolher_routes, make_http):
    escolher_routes[("POST", "/aplicar-contexto")] = FakeResponse(200, "0")
    with pytest.raises(UpstreamError, match="aplicar-contexto"):
        collect(conn, http=make_http(escolher_routes))


def test_health_check_seleciona_contexto_antes_de_validar(conn, escolher_routes, make_http):
    http = make_http(escolher_routes)
    assert check_session(conn, http=http) is True
    assert http.paths() == ["/", "/selecionar-contexto", "/aplicar-contexto", "/"]


def test_fetch_raw_inclui_selecionar_contexto_se_houve_selecao(conn, escolher_routes, make_http):
    raw = ReservaSpaceClient(conn, http=make_http(escolher_routes)).fetch_raw()
    assert "selecionar-contexto.html" in raw
    assert 'id="seletorUnidade"' in raw["selecionar-contexto.html"]


def test_fetch_raw_sem_selecionar_contexto_quando_pulou(conn, happy_routes, make_http):
    raw = ReservaSpaceClient(conn, http=make_http(happy_routes)).fetch_raw()
    assert "selecionar-contexto.html" not in raw


def test_connection_from_mapping_id_empresa_opcional():
    sem = Connection.from_mapping({"host": "https://x", "cookie": "c", "id_local": "9"})
    assert sem.id_empresa == ""
    com = Connection.from_mapping(
        {"host": "https://x", "cookie": "c", "id_local": "9", "id_empresa": "10"}
    )
    assert com.id_empresa == "10"


def test_post_leva_xhr_e_csrf_do_meta(conn, happy_routes, make_http):
    http = make_http(happy_routes)
    collect(conn, http=http)
    post = next(c for c in http.calls if c["method"] == "POST")
    assert post["headers"]["X-Requested-With"] == "XMLHttpRequest"
    assert post["headers"]["X-CSRF-Token"] == "TESTE-CSRF-TOKEN-abc123"
    assert post["data"]["reservaspace_csrf"] == "TESTE-CSRF-TOKEN-abc123"
    assert json.loads(post["data"]["filtro"]) == {"idTurno": "1071"}


def test_200_corpo_vazio_e_erro_explicito(conn, happy_routes, make_http):
    happy_routes[("POST", "/config/capacidade-salas")] = FakeResponse(200, "   ")
    with pytest.raises(EmptyBodyError, match="X-Requested-With"):
        collect(conn, http=make_http(happy_routes))


def test_401_falha_alta_pedindo_rebootstrap(conn, happy_routes, make_http):
    happy_routes[("GET", "/")] = FakeResponse(401, "")
    with pytest.raises(SessionExpiredError, match="refazer bootstrap"):
        collect(conn, http=make_http(happy_routes))


def test_health_check_ok_e_falha(conn, happy_routes, make_http):
    assert check_session(conn, http=make_http(happy_routes)) is True

    happy_routes[("GET", "/")] = FakeResponse(401, "")
    with pytest.raises(SessionExpiredError):
        check_session(conn, http=make_http(happy_routes))
    assert check_session(conn, http=make_http(happy_routes), raise_on_invalid=False) is False


def test_health_check_falha_em_200_com_pagina_de_login(conn, happy_routes, make_http):
    happy_routes[("GET", "/")] = FakeResponse(200, "<html><body>Faça login no SSO</body></html>")
    with pytest.raises(SessionExpiredError, match="login SSO"):
        check_session(conn, http=make_http(happy_routes))
    with pytest.raises(SessionExpiredError):
        collect(conn, http=make_http(happy_routes))


def test_fetch_raw_devolve_corpos_crus_nomeados(conn, happy_routes, make_http):
    raw = ReservaSpaceClient(conn, http=make_http(happy_routes)).fetch_raw()
    assert set(raw) == {
        "calendar.html",
        "local.html",
        "capacidade-salas_1071.json",
        "capacidade-salas_1072.json",
    }
    assert "agendaReservas" in raw["calendar.html"]


def test_retry_com_backoff_em_5xx_depois_sucesso(conn, happy_routes, make_http):
    ok = happy_routes[("GET", "/")]
    happy_routes[("GET", "/")] = [FakeResponse(500, ""), ok]
    sleeps: list[float] = []
    result = collect(conn, http=make_http(happy_routes), sleep=sleeps.append)
    assert len(result.reservas) == 6
    assert len(sleeps) == 1


def test_alerta_so_depois_de_esgotar_tentativas(conn, happy_routes, make_http):
    happy_routes[("GET", "/")] = [FakeResponse(500, "") for _ in range(4)]
    alertas: list[str] = []
    sleeps: list[float] = []
    with pytest.raises(UpstreamError, match="4 tentativas"):
        collect(conn, http=make_http(happy_routes), sleep=sleeps.append, on_alert=alertas.append)
    assert len(sleeps) == 3
    assert len(alertas) == 1


def test_retry_em_timeout(conn, happy_routes, make_http):
    ok = happy_routes[("GET", "/")]
    happy_routes[("GET", "/")] = [rexc.Timeout, ok]
    result = collect(conn, http=make_http(happy_routes), sleep=lambda _: None)
    assert len(result.reservas) == 6


def test_connection_from_mapping():
    c = Connection.from_mapping({"host": "https://x/", "cookie": "c", "id_local": "9"})
    assert c.base_url == "https://x" and c.cookie == "c" and c.id_local == "9"


def test_client_direto(conn, happy_routes, make_http):
    client = ReservaSpaceClient(conn, http=make_http(happy_routes))
    assert client.check_session() is True
