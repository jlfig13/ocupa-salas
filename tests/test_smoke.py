"""Fumaça: o pacote importa e expõe a superfície pública documentada."""

from __future__ import annotations

import ocupa_salas


def test_superficie_publica():
    for nome in (
        "ReservaSpaceClient",
        "Connection",
        "parse_page",
        "strip_reserva",
        "hash_linha",
        "run_collection",
        "check_session",
    ):
        assert hasattr(ocupa_salas, nome), nome
