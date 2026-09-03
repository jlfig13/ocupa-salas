"""
Gera as fixtures deste diretório.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md

Estas fixtures são SINTÉTICAS: reproduzem a *forma* documentada no mapeamento
(§2.1, §2.2, §4, §6) com PII obviamente falsa (``000.000.000-00`` etc.), para o
parser e o strip terem contra o que rodar. A fonte real seria capturada com
``ocupa-salas-bootstrap scrub``.

Uso: ``python tests/fixtures/_generate.py``
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent

# countPorStatus da fonte é chaveado por bucket de workflow. Espelho do mapa de
# produção (ocupa_salas.canary.STATUS_ID_TO_BUCKET) para os ids que estas fixtures usam.
_STATUS_BUCKET = {1: "reservado", 2: "cancelado", 3: "checkIn", 4: "checkOut", 5: "noShow"}

_FAKE_MEMBRO = {
    "idMembro": 0,  # sobrescrito por reserva
    "nome": "FULANO SINTÉTICO DE TAL",
    "cpf": "000.000.000-00",
    "rg": "00.000.000-0",
    "passaporte": "AB000000",
    "dataNascimento": "1990-01-01",
    "sexo": "M",
    "email": "fake@example.invalid",
    "telefoneCelular": "(00) 00000-0000",
    "contatoEmergencia": "FALSO (00) 90000-0000",
    "matriculaContrato": "CT-0001",
    "dataAdesao": "2024-01-01",
    "dataEncerramento": None,
    "ativo": 1,
    "categoriaPlano": "CORPORATIVO",
    "planoSaudeNumero": "SIM-000000",
    "necessidadesAcessibilidade": "",
    "restricaoMobilidade": 0,
    "preferenciasAlimentares": "",
    "setorCodCrm": "CRM-SET-1",
    "setorNomeCrm": "SETOR SINTÉTICO",
    "centroCustoCodCrm": "CRM-CC-9",
    "centroCustoNomeCrm": "CC SINTÉTICO",
    "codMembroCrm": "CRM-M-1",
    "codContratoCrm": "CRM-CT-1",
    "unidadeNegocioCrm": "UN SINTÉTICA",
    "id_contrato_crm": "CRM-1",
    "contrato": {
        "cnpj": "11.111.111/0001-11",
        "razaoSocial": "CONTRATANTE SINTÉTICA LTDA",
        "endereco": "RUA FALSA, 123",
        "empresa": {"cnpj": "22.222.222/0001-22", "razaoSocial": "GRUPO SINTÉTICO S.A."},
    },
}


def _reserva(id_res: int, id_status: int, *, id_membro: int = 9000, check: bool = False) -> dict:
    membro = json.loads(json.dumps(_FAKE_MEMBRO))
    membro["idMembro"] = id_membro
    return {
        "idReserva": id_res,
        "idSalaReserva": 5,
        "idMembro": id_membro,
        "idStatusReserva": id_status,
        "idStatusPendencia": None,
        "idPostoLocal": "401P1",
        "idSala": "401",
        "idFaixaHorario": "1071",
        "dataReserva": "2026-08-14T08:30:00-03:00",
        "idReservadoPor": "USR-AAAA-0001",
        "dataCriacaoReserva": "2026-08-01T10:00:00-03:00",
        "atualizadoPor": "USR-AAAA-0002",
        "atualizadoEm": "2026-08-14T08:35:00-03:00",
        "checkIn": "2026-08-14T08:28:00-03:00" if check else None,
        "checkOut": "2026-08-14T09:10:00-03:00" if check and id_status == 4 else None,
        "checkInPor": "USR-BBBB-0003" if check else None,
        "checkOutPor": "USR-BBBB-0003" if check and id_status == 4 else None,
        "cancelado": 1 if id_status == 2 else 0,
        "canceladoPor": "USR-CCCC-0004" if id_status == 2 else None,
        "atendidoPor": "USR-PROF-0009" if id_status == 4 else None,
        "observacao": "TEXTO LIVRE DIGITADO - risco de PII",
        "membro": membro,
        "sala": {"id": "401", "nome": "SALA SINTÉTICA"},
        "statusReserva": {"id": id_status, "nome": f"STATUS {id_status}"},
    }


def _placeholder(dia: str) -> dict:
    return {
        "id": None,
        "title": "",
        "start": dia,
        "end": dia,
        "nonstandard": {"primeiroDoDia": True, "reservas": []},
    }


def _bloco(bid: int, title: str, dia: str, reservas: list[dict], count: dict | None) -> dict:
    ns: dict = {"reservas": reservas}
    if count is not None:
        ns["countPorStatus"] = count
    ini, fim = title.split(" - ")
    return {
        "id": bid,
        "title": title,
        "start": f"{dia}T{ini}:00-03:00",
        "end": f"{dia}T{fim}:00-03:00",
        "nonstandard": ns,
    }


_PAGE = """<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="csrf-param" content="reservaspace_csrf">
<meta name="csrf-token" content="TESTE-CSRF-TOKEN-abc123">
</head><body>
<div id="calendarioReservas"></div>
<script>
jQuery('#calendarioReservas').fullCalendar({{
  "editable": false,
  "events": {events}
}});
</script>
</body></html>
"""


def _write(name: str, events: list[dict]) -> None:
    html = _PAGE.format(events=json.dumps(events, ensure_ascii=False, indent=2))
    (HERE / name).write_text(html, encoding="utf-8")
    print(f"wrote {name} ({len(html)} bytes)")


def main() -> None:
    # Dia normal: 2 dias, placeholders, contagens que conferem com countPorStatus.
    normal = [
        _placeholder("2026-08-14"),
        _bloco(
            1001, "08:00 - 12:00", "2026-08-14",
            [_reserva(100001, 1), _reserva(100002, 4, check=True), _reserva(100003, 4, check=True)],
            {"reservado": 1, "checkOut": 2},
        ),
        _bloco(
            1002, "13:00 - 18:00", "2026-08-14",
            [_reserva(100004, 3, check=True), _reserva(100005, 2)],
            {"checkIn": 1, "cancelado": 1},
        ),
        _placeholder("2026-08-15"),
        _bloco(
            1003, "08:00 - 12:00", "2026-08-15",
            [_reserva(100006, 5, id_membro=9001)], {"noShow": 1},
        ),
    ]
    _write("calendar_dia_normal.html", normal)

    # Alto volume: um bloco com 40 reservas; countPorStatus confere.
    big = [
        _reserva(200000 + i, (i % 5) + 1, id_membro=9000 + (i % 7), check=(i % 5) >= 2)
        for i in range(40)
    ]
    count: dict[str, int] = {}
    for a in big:
        k = _STATUS_BUCKET[a["idStatusReserva"]]
        count[k] = count.get(k, 0) + 1
    alto = [_placeholder("2026-08-20"), _bloco(1004, "08:00 - 18:00", "2026-08-20", big, count)]
    _write("calendar_dia_alto_volume.html", alto)

    # Mês vazio: só placeholders e blocos sem reserva. O 2º bloco não traz countPorStatus.
    vazio = [
        _placeholder("2026-09-01"),
        _bloco(1005, "08:00 - 12:00", "2026-09-01", [], {}),
        _bloco(1006, "13:00 - 18:00", "2026-09-01", [], None),
        _placeholder("2026-09-02"),
    ]
    _write("calendar_mes_vazio.html", vazio)

    # Canário divergente: countPorStatus não bate com reservas[] (truncamento simulado).
    trunc = [
        _placeholder("2026-08-21"),
        _bloco(
            1007, "08:00 - 12:00", "2026-08-21",
            [_reserva(300001, 1), _reserva(300002, 1)],
            {"reservado": 5},
        ),
    ]
    _write("calendar_canario_divergente.html", trunc)

    # Config de local: global JS `locais` com faixas + metas CSRF (Seam 2).
    locais = [
        {
            "idLocal": "1",
            "nome": "COWORKING CENTRAL",
            "faixaHorarios": [
                {"idFaixaHorario": "1071", "nomeFaixa": "MANHA"},
                {"idFaixaHorario": "1072", "nomeFaixa": "TARDE"},
            ],
        }
    ]
    local_html = (
        "<!doctype html><html><head>"
        '<meta name="csrf-param" content="reservaspace_csrf">'
        '<meta name="csrf-token" content="TESTE-CSRF-TOKEN-abc123">'
        "</head><body><script>\n"
        f"var locais = {json.dumps(locais, ensure_ascii=False)};\n"
        "</script></body></html>\n"
    )
    (HERE / "local.html").write_text(local_html, encoding="utf-8")
    print("wrote local.html")

    # Tela /escolher-contexto (ADR-0001 D7): marcador id="escolheLocal" + par CSRF.
    escolher = (
        "<!doctype html><html><head>"
        '<meta name="csrf-param" content="reservaspace_csrf">'
        '<meta name="csrf-token" content="TESTE-CSRF-TOKEN-abc123">'
        "</head><body><h1>Selecione um Local</h1>"
        '<select id="escolheLocal"><option value="1">COWORKING CENTRAL</option></select>'
        '<select id="escolheEmpresa"><option value="10">ACME (fictícia)</option></select>'
        "</body></html>\n"
    )
    (HERE / "escolher_contexto.html").write_text(escolher, encoding="utf-8")
    print("wrote escolher_contexto.html")

    # Resposta de get-salas (mapeamento_fonte.md §6.2).
    capacidade = [
        {
            "idSala": "401",
            "maxReservas": "8",
            "nome": "SALA FOCO 01_MANHA",
            "idFaixaHorario": "1071",
            "alteraSala": [
                {
                    "idAlteraSala": "4",
                    "maxReserva": "16",
                    "dataInicio": "2026-08-14",
                    "dataFim": "2026-08-14",
                    "ativo": "1",
                }
            ],
            "postos": [
                {
                    "idPostoLocal": "401P1",
                    "nomeProc": "Estação de trabalho",
                    "maxReservas": "0",
                    "peso": "1",
                    "ativo": "1",
                }
            ],
        }
    ]
    (HERE / "get_salas.json").write_text(
        json.dumps(capacidade, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("wrote get_salas.json")

    # Reserva crua única com PII sintética, para os testes de strip.
    (HERE / "reserva_raw_com_pii.json").write_text(
        json.dumps(_reserva(999001, 4, check=True), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("wrote reserva_raw_com_pii.json")


if __name__ == "__main__":
    main()
