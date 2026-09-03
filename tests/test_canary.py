"""Canário de integridade — contagem calculada × countPorStatus (por bucket de workflow)."""

from __future__ import annotations

import pytest

from ocupa_salas.canary import (
    bucket_do_status,
    check_bloco_integrity,
    check_status_counts,
    normalize_count_por_status,
)
from ocupa_salas.errors import SchemaError
from ocupa_salas.parser import parse_page


def test_bucket_do_status_mapa_provisorio():
    assert bucket_do_status(1) == "reservado"
    assert bucket_do_status(9) == "cancelado"  # achado: "Removido" cai em cancelado
    assert bucket_do_status(6).startswith("id_desconhecido")


def test_match_quando_contagens_conferem():
    r = check_status_counts([1, 4, 4], {"reservado": 1, "checkOut": 2})
    assert r.status == "match" and r.ok and not r.canario_falhou


def test_mismatch_marca_sem_bloquear():
    alertas = []
    r = check_status_counts([1, 1], {"reservado": 5}, on_alert=alertas.append)
    assert r.status == "mismatch" and r.canario_falhou
    assert r.diferencas["reservado"] == (2, 5)
    assert len(alertas) == 1


def test_skipped_quando_bloco_sem_count():
    assert check_status_counts([1, 2], None).status == "skipped"


def test_normalize_aceita_mapa_e_lista():
    assert normalize_count_por_status({"reservado": 3}) == {"reservado": 3}
    assert normalize_count_por_status([{"idStatusReserva": 1, "count": 3}]) == {"1": 3}
    assert normalize_count_por_status(None) is None
    with pytest.raises(SchemaError):
        normalize_count_por_status(42)


def test_fixture_divergente_liga_o_canario(fx):
    page = parse_page(fx("calendar_canario_divergente.html"))
    result = check_bloco_integrity(page.blocos[0])
    assert result.canario_falhou


def test_fixture_normal_todos_conferem(fx):
    page = parse_page(fx("calendar_dia_normal.html"))
    assert all(check_bloco_integrity(b).ok for b in page.blocos)
