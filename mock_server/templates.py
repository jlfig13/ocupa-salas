"""
Builders de HTML da fonte fictícia — imitam a página Yii2 + FullCalendar do original.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Dados   : 100% fictícios.
"""

from __future__ import annotations

import json
from typing import Any

CSRF_PARAM = "reservaspace_csrf"


def _head(csrf_token: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f'<meta name="csrf-param" content="{CSRF_PARAM}">'
        f'<meta name="csrf-token" content="{csrf_token}">'
        "</head><body>"
    )


def calendar_page(events: list[Any], csrf_token: str) -> str:
    return (
        _head(csrf_token)
        + '<div id="calendarioReservas"></div><script>\n'
        + "jQuery('#calendarioReservas').fullCalendar({\n"
        + '  "editable": false,\n'
        + '  "events": '
        + json.dumps(events, ensure_ascii=False)
        + "\n});\n</script></body></html>"
    )


def local_page(locais: list[Any], csrf_token: str) -> str:
    return (
        _head(csrf_token)
        + "<script>\nvar locais = "
        + json.dumps(locais, ensure_ascii=False)
        + ";\n</script></body></html>"
    )


def escolher_contexto_page(locais: list[Any], empresas: list[Any], csrf_token: str) -> str:
    def _opt(value: str, label: str) -> str:
        return f'<option value="{value}">{label}</option>'

    opts_l = "".join(_opt(loc["idLocal"], loc["nome"]) for loc in locais)
    opts_e = "".join(_opt(emp["idEmpresa"], emp["nome"]) for emp in empresas)
    return (
        _head(csrf_token)
        + "<h1>Selecione um Local</h1>"
        + f'<select id="escolheLocal">{opts_l}</select>'
        + f'<select id="escolheEmpresa">{opts_e}</select>'
        + "<p>Escolha um local para continuar.</p>"
        + "</body></html>"
    )
