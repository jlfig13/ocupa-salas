"""Strip de PII — whitelist-only: sobra o escalar + idMembro + cnpj_empresa, nada sensível."""

from __future__ import annotations

import pytest

from ocupa_salas.errors import PIILeakError, SchemaError
from ocupa_salas.strip import assert_no_pii, find_forbidden_keys, strip_reserva


def test_strip_mantem_whitelist_e_derivados(fx_json):
    raw = fx_json("reserva_raw_com_pii.json")
    out = strip_reserva(raw)

    assert out["idReserva"] == 999001
    assert out["idStatusReserva"] == 4
    assert out["idMembro"] == 9000
    assert out["cnpj_empresa"] == "22.222.222/0001-22"


def test_strip_remove_todo_campo_sensivel(fx_json):
    raw = fx_json("reserva_raw_com_pii.json")
    # sanidade: a entrada crua REALMENTE tem PII
    assert find_forbidden_keys(raw) != []

    out = strip_reserva(raw)
    assert find_forbidden_keys(out) == []
    assert "membro" not in out
    assert "observacao" not in out


def test_strip_sem_id_reserva_falha_claro():
    with pytest.raises(SchemaError, match="idReserva"):
        strip_reserva({"idStatusReserva": 1})


def test_assert_no_pii_dispara_na_entrada_crua(fx_json):
    with pytest.raises(PIILeakError):
        assert_no_pii(fx_json("reserva_raw_com_pii.json"))


def test_find_forbidden_keys_pii_only_ignora_containers():
    obj = {"membro": {"idMembro": 1}}  # 'membro' é container, não PII de valor
    assert find_forbidden_keys(obj, pii_only=True) == []
    assert "$.membro" in find_forbidden_keys(obj)
