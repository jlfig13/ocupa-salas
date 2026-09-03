"""Pipeline: colunas de rastreio + versionamento por hash (grava-quando-muda)."""

from __future__ import annotations

import json

import pytest

from conftest import FakeResponse
from ocupa_salas.http_client import Connection
from ocupa_salas.pipeline import StateStore, run_collection, write_jsonl


@pytest.fixture
def conn():
    return Connection(base_url="https://demo.reservaspace.io", cookie="RSSESSID=fake", id_local="1")


@pytest.fixture
def routes(fx):
    return {
        ("GET", "/"): FakeResponse(200, fx("calendar_dia_normal.html")),
        ("GET", "/painel-config/local"): FakeResponse(200, fx("local.html")),
        ("POST", "/painel-config/get-salas"): FakeResponse(200, fx("get_salas.json")),
    }


def _http(routes, make_http):
    return make_http({k: (v if not isinstance(v, list) else list(v)) for k, v in routes.items()})


def test_primeira_corrida_tudo_novo_com_colunas_de_rastreio(conn, routes, make_http):
    run = run_collection(conn, http=make_http(routes), data_particao="2026-08-14")
    assert len(run.linhas_novas) == 6
    assert run.linhas_inalteradas == 0

    linha = run.linhas_novas[0]
    assert linha["fonte"] == "reservaspace"
    assert linha["data_particao"] == "2026-08-14"
    assert linha["data_extracao"]
    assert len(linha["hash_linha"]) == 64
    assert linha["id_origem"] == str(linha["payload"]["idReserva"])

    assert run.capacidade and run.capacidade[0]["id_origem"] == "401:1071"


def test_segunda_corrida_mesmo_estado_nao_gera_linha(conn, routes, make_http, tmp_path):
    state = StateStore(tmp_path / "state.json")
    run_collection(conn, http=make_http(routes), state=state, data_particao="2026-08-14")
    state.save()

    state2 = StateStore(tmp_path / "state.json")
    run2 = run_collection(conn, http=make_http(routes), state=state2, data_particao="2026-08-15")
    assert run2.linhas_novas == []
    assert run2.linhas_inalteradas == 6


def test_mudanca_de_status_gera_linha_nova(conn, routes, fx, make_http, tmp_path):
    state = StateStore(tmp_path / "s.json")
    run_collection(conn, http=make_http(routes), state=state, data_particao="2026-08-14")
    state.save()

    mutado = fx("calendar_dia_normal.html").replace(
        '"idStatusReserva": 1,', '"idStatusReserva": 4,', 1
    )
    routes2 = dict(routes)
    routes2[("GET", "/")] = FakeResponse(200, mutado)
    state2 = StateStore(tmp_path / "s.json")
    run2 = run_collection(conn, http=make_http(routes2), state=state2, data_particao="2026-08-15")
    assert len(run2.linhas_novas) == 1
    assert run2.linhas_inalteradas == 5


def test_write_jsonl(tmp_path):
    rows = [{"a": 1}, {"a": 2, "txt": "ção"}]
    n = write_jsonl(rows, tmp_path / "out.jsonl")
    assert n == 2
    linhas = (tmp_path / "out.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(linhas[1]) == {"a": 2, "txt": "ção"}
