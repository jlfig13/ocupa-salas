"""Ponta a ponta: o coletor roda contra a fonte fictícia (mock_server) via TestClient."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from mock_server.app import create_app  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from ocupa_salas.canary import check_bloco_integrity  # noqa: E402
from ocupa_salas.http_client import Connection, ReservaSpaceClient  # noqa: E402
from ocupa_salas.parser import parse_page  # noqa: E402
from ocupa_salas.pipeline import run_collection  # noqa: E402
from ocupa_salas.strip import find_forbidden_keys  # noqa: E402


@pytest.fixture
def http():
    return TestClient(create_app())


def _conn(cookie: str = "RSSESSID=demo") -> Connection:
    return Connection(base_url="http://testserver", cookie=cookie, id_local="1")


def test_conta_demo_passa_por_escolher_contexto_e_coleta(http):
    result = ReservaSpaceClient(_conn(), http=http).collect()
    assert result.reservas
    assert result.capacidade
    for rec in result.reservas:
        assert find_forbidden_keys(rec["payload"]) == []


def test_conta_solo_vai_direto_ao_calendario(http):
    result = ReservaSpaceClient(_conn("RSSESSID=solo"), http=http).collect()
    assert result.reservas


def test_sessao_expirada_falha_alto(http):
    from ocupa_salas.errors import SessionExpiredError

    with pytest.raises(SessionExpiredError):
        ReservaSpaceClient(_conn("RSSESSID=expired"), http=http).collect()


def test_canario_saudavel_na_fonte_ficticia(http):
    # GET / da conta solo entrega o calendário; countPorStatus é montado para bater.
    page = parse_page(http.get("/", headers={"Cookie": "RSSESSID=solo"}).text)
    assert page.blocos
    assert all(check_bloco_integrity(b).ok for b in page.blocos)


def test_pipeline_versiona_contra_a_fonte_ficticia(http, tmp_path):
    from ocupa_salas.pipeline import StateStore

    st = StateStore(tmp_path / "state.json")
    run1 = run_collection(_conn("RSSESSID=solo"), http=http, state=st, data_particao="2026-09-01")
    st.save()
    assert run1.linhas_novas

    st2 = StateStore(tmp_path / "state.json")
    run2 = run_collection(_conn("RSSESSID=solo"), http=http, state=st2, data_particao="2026-09-01")
    assert run2.linhas_novas == []
