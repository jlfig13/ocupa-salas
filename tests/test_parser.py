"""Seam 1 — parser da tela de calendário: fatiar ``events``, ignorar placeholder, strip, hash."""

from __future__ import annotations

import pytest

from ocupa_salas.errors import SchemaError
from ocupa_salas.parser import extract_csrf, extract_faixa_ids, parse_page
from ocupa_salas.strip import find_forbidden_keys


def test_dia_normal_ignora_placeholder_e_extrai_blocos(fx):
    page = parse_page(fx("calendar_dia_normal.html"))
    assert len(page.blocos) == 3  # 2 placeholders 'primeiroDoDia' descartados
    assert [b.title for b in page.blocos] == ["08:00 - 12:00", "13:00 - 18:00", "08:00 - 12:00"]
    assert len(page.reservas) == 6


def test_nenhuma_reserva_carrega_pii(fx):
    page = parse_page(fx("calendar_dia_normal.html"))
    for rec in page.reservas:
        assert find_forbidden_keys(rec.payload) == []
        assert "cnpj_empresa" in rec.payload


def test_count_por_status_por_bloco(fx):
    page = parse_page(fx("calendar_dia_normal.html"))
    assert page.blocos[0].count_por_status == {"reservado": 1, "checkOut": 2}
    assert page.blocos[1].count_por_status == {"checkIn": 1, "cancelado": 1}


def test_hash_estavel_entre_parses_e_muda_com_conteudo(fx):
    html = fx("calendar_dia_normal.html")
    h1 = [r.hash_linha for r in parse_page(html).reservas]
    h2 = [r.hash_linha for r in parse_page(html).reservas]
    assert h1 == h2

    alterado = html.replace('"idStatusReserva": 1,', '"idStatusReserva": 4,', 1)
    h3 = [r.hash_linha for r in parse_page(alterado).reservas]
    assert h3 != h1
    assert sum(a != b for a, b in zip(h1, h3, strict=True)) == 1


def test_alto_volume(fx):
    page = parse_page(fx("calendar_dia_alto_volume.html"))
    assert len(page.blocos) == 1
    assert len(page.blocos[0].reservas) == 40


def test_mes_vazio(fx):
    page = parse_page(fx("calendar_mes_vazio.html"))
    assert page.reservas == []
    assert any(b.title == "08:00 - 12:00" for b in page.blocos)


def test_erro_claro_sem_marcador_events():
    with pytest.raises(SchemaError, match="events"):
        parse_page("<html><body>sem calendario</body></html>")


def test_marcador_events_nao_casa_sufixo_de_outra_chave():
    with pytest.raises(SchemaError, match="events"):
        parse_page('var x = {"calendarEvents": [1, 2, 3]};')


def test_erro_claro_bloco_sem_nonstandard():
    html = 'x = {"events": [{"id": 1, "title": "08:00 - 12:00"}]}'
    with pytest.raises(SchemaError, match="nonstandard"):
        parse_page(html)


def test_erro_claro_bloco_sem_lista_reservas():
    html = 'x = {"events": [{"id": 1, "nonstandard": {"countPorStatus": {}}}]}'
    with pytest.raises(SchemaError, match="reservas"):
        parse_page(html)


def test_extract_csrf(fx):
    csrf = extract_csrf(fx("calendar_dia_normal.html"))
    assert (csrf.param, csrf.token) == ("reservaspace_csrf", "TESTE-CSRF-TOKEN-abc123")


def test_extract_csrf_ausente():
    with pytest.raises(SchemaError, match="CSRF"):
        extract_csrf("<html><head></head></html>")


def test_extract_faixa_ids(fx):
    assert extract_faixa_ids(fx("local.html")) == ["1071", "1072"]
