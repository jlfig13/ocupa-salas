"""``hash_linha`` — determinístico, insensível à ordem de chave, sensível a valor."""

from __future__ import annotations

from ocupa_salas.hashing import hash_linha


def test_deterministico_e_insensivel_a_ordem():
    a = {"idReserva": 1, "idStatusReserva": 3, "cnpj_empresa": "22.222.222/0001-22"}
    b = {"cnpj_empresa": "22.222.222/0001-22", "idStatusReserva": 3, "idReserva": 1}
    assert hash_linha(a) == hash_linha(b)


def test_muda_com_qualquer_escalar():
    base = {"idReserva": 1, "idStatusReserva": 1}
    assert hash_linha(base) != hash_linha({**base, "idStatusReserva": 4})


def test_hex_sha256():
    h = hash_linha({"idReserva": 1})
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
