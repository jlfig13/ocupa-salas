"""
Gerador sintético determinístico da fonte fictícia.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Dados   : 100% fictícios. PII obviamente falsa, replicada por reserva como a fonte real
          faz (mapeamento_fonte.md §4) — é o que dá ao strip algo contra o que rodar.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Any

SEED = 42

# Espelho do mapa provisório de produção (ocupa_salas.canary.STATUS_ID_TO_BUCKET) para os
# ids que este gerador usa. O countPorStatus da fonte é chaveado por bucket de workflow.
_STATUS_BUCKET = {
    1: "reservado",
    2: "cancelado",
    3: "checkIn",
    4: "checkOut",
    5: "noShow",
    9: "cancelado",
}
_STATUS_NOME = {
    1: "Reservado",
    2: "Cancelado",
    3: "Check-In",
    4: "Concluído",
    5: "No-Show",
    9: "Removido",
}

# -- catálogo estático ------------------------------------------------------

LOCAIS: list[dict[str, Any]] = [
    {
        "idLocal": "1",
        "nome": "Coworking Central",
        "endereco": "Rua Fictícia, 100 - Bairro Exemplo",
        "email": "central@reservaspace.invalid",
        "atualizadoPor": "USR-ADMIN-0001",
        "faixaHorarios": [
            {
                "idFaixaHorario": "1071",
                "idLocal": "1",
                "nomeFaixa": "MANHA",
                "horaInicial": "08:00",
                "horaFinal": "12:00",
                "diasSemana": "1,2,3,4,5",
                "diasMes": None,
                "horaMarcada": "1",
                "ativo": "1",
                "atualizadoPor": "USR-ADMIN-0001",
            },
            {
                "idFaixaHorario": "1072",
                "idLocal": "1",
                "nomeFaixa": "TARDE",
                "horaInicial": "13:00",
                "horaFinal": "18:00",
                "diasSemana": "1,2,3,4,5",
                "diasMes": None,
                "horaMarcada": "1",
                "ativo": "1",
                "atualizadoPor": "USR-ADMIN-0001",
            },
        ],
    },
    {
        "idLocal": "2",
        "nome": "Coworking Zona Norte",
        "endereco": "Av. Imaginária, 4000",
        "email": "zn@reservaspace.invalid",
        "atualizadoPor": "USR-ADMIN-0001",
        "faixaHorarios": [
            {
                "idFaixaHorario": "2081",
                "idLocal": "2",
                "nomeFaixa": "INTEGRAL",
                "horaInicial": "08:00",
                "horaFinal": "20:00",
                "diasSemana": "1,2,3,4,5,6",
                "diasMes": None,
                "horaMarcada": "1",
                "ativo": "1",
            }
        ],
    },
]

EMPRESAS: list[dict[str, Any]] = [
    {"idEmpresa": "10", "nome": "Acme Consultoria (fictícia)"},
    {"idEmpresa": "11", "nome": "Globex Design (fictícia)"},
]

_SALAS_BASE = {
    "1071": [
        ("401", "SALA FOCO 01_MANHA", 8),
        ("402", "SALA REUNIÃO A_MANHA", 12),
        ("403", "LAB CRIATIVO_MANHA", 20),
    ],
    "1072": [
        ("451", "SALA FOCO 01_TARDE", 8),
        ("452", "SALA REUNIÃO A_TARDE", 12),
        ("453", "AUDITÓRIO_TARDE", 40),
    ],
    "2081": [
        ("601", "OPEN SPACE_INTEGRAL", 60),
    ],
}


def _rng(*parts: Any) -> random.Random:
    return random.Random(f"{SEED}:" + ":".join(str(p) for p in parts))


def salas_por_faixa(id_faixa: str, *, hoje: date | None = None) -> list[dict[str, Any]]:
    """Resposta de ``POST /painel-config/get-salas`` para uma faixa (mapeamento §6.2)."""
    hoje = hoje or date.today()
    out: list[dict[str, Any]] = []
    for id_sala, nome, base in _SALAS_BASE.get(id_faixa, []):
        rng = _rng("sala", id_sala)
        # override de capacidade cobrindo alguns dias da janela (mapeamento §6.3)
        alteracoes: list[dict[str, Any]] = []
        if rng.random() < 0.7:
            ini = hoje + timedelta(days=rng.randint(0, 3))
            fim = ini + timedelta(days=rng.randint(1, 4))
            alteracoes.append(
                {
                    "idAlteraSala": f"{id_sala}A1",
                    "maxReserva": str(base + rng.choice([4, 8, 12])),
                    "dataInicio": ini.isoformat(),
                    "dataFim": fim.isoformat(),
                    "ativo": "1",
                }
            )
        out.append(
            {
                "idSala": id_sala,
                "maxReservas": str(base),
                "nome": nome,
                "idFaixaHorario": id_faixa,
                "alteraSala": alteracoes,
                "postos": [
                    {
                        "idPostoLocal": f"{id_sala}P1",
                        "nomeProc": "Estação de trabalho",
                        "maxReservas": "0",
                        "peso": "1",
                        "ativo": "1",
                    }
                ],
            }
        )
    return out


# -- PII sintética (replicada por reserva) --------------------------------

def _membro(id_membro: int) -> dict[str, Any]:
    rng = _rng("membro", id_membro)
    return {
        "idMembro": id_membro,
        "nome": f"FULANO SINTÉTICO {id_membro}",
        "cpf": "000.000.000-00",
        "rg": "00.000.000-0",
        "passaporte": "AB000000",
        "dataNascimento": "1990-01-01",
        "sexo": rng.choice(["M", "F", "NB"]),
        "email": f"membro{id_membro}@example.invalid",
        "telefoneCelular": "(00) 00000-0000",
        "contatoEmergencia": "CONTATO FALSO (00) 90000-0000",
        "matriculaContrato": f"CT-{id_membro:05d}",
        "dataAdesao": "2024-03-01",
        "dataEncerramento": None,
        "ativo": 1,
        "categoriaPlano": rng.choice(["FLEX", "FIXO", "CORPORATIVO"]),
        "planoSaudeNumero": "SIM-000000",
        "necessidadesAcessibilidade": rng.choice(["", "", "cadeirante", "libras"]),
        "restricaoMobilidade": 0,
        "preferenciasAlimentares": rng.choice(["", "vegetariano", "sem lactose"]),
        "setorCodCrm": "CRM-SET-1",
        "setorNomeCrm": "SETOR SINTÉTICO",
        "centroCustoCodCrm": "CRM-CC-9",
        "centroCustoNomeCrm": "CENTRO DE CUSTO SINTÉTICO",
        "codMembroCrm": f"CRM-M-{id_membro}",
        "codContratoCrm": "CRM-CT-1",
        "unidadeNegocioCrm": "UN SINTÉTICA",
        "id_contrato_crm": "CRM-1",
        "contrato": {
            "cnpj": "11.111.111/0001-11",
            "razaoSocial": "CONTRATANTE SINTÉTICA LTDA",
            "endereco": "RUA FALSA, 123",
            "empresa": {
                "cnpj": f"22.222.222/000{1 + (id_membro % 3)}-22",
                "razaoSocial": "GRUPO SINTÉTICO S.A.",
            },
        },
    }


# -- calendário (array events) ------------------------------------------

def _reserva(
    id_reserva: int, id_status: int, *, id_membro: int, id_sala: str, dia: str, hora: str
) -> dict[str, Any]:
    check = id_status in (3, 4)
    concluido = id_status == 4
    return {
        "idReserva": id_reserva,
        "idSalaReserva": int(id_sala) % 97,
        "idMembro": id_membro,
        "idStatusReserva": id_status,
        "idStatusPendencia": None,
        "idPostoLocal": f"{id_sala}P1",
        "idSala": id_sala,
        "idFaixaHorario": None,
        "dataReserva": f"{dia}T{hora}:00-03:00",
        "idReservadoPor": "USR-AAAA-0001",
        "dataCriacaoReserva": f"{dia}T07:00:00-03:00",
        "atualizadoPor": "USR-AAAA-0002",
        "atualizadoEm": f"{dia}T{hora}:30-03:00",
        "checkIn": f"{dia}T{hora}:05-03:00" if check else None,
        "checkOut": f"{dia}T{hora}:55-03:00" if concluido else None,
        "checkInPor": "USR-BBBB-0003" if check else None,
        "checkOutPor": "USR-BBBB-0003" if concluido else None,
        "cancelado": 1 if id_status in (2, 9) else 0,
        "canceladoPor": "USR-CCCC-0004" if id_status in (2, 9) else None,
        "atendidoPor": "USR-PROF-0009" if concluido else None,
        "observacao": "TEXTO LIVRE DIGITADO — risco de PII",
        "membro": _membro(id_membro),
        "sala": {"id": id_sala, "nome": "SALA SINTÉTICA"},
        "statusReserva": {"id": id_status, "nome": _STATUS_NOME[id_status]},
    }


def _placeholder(dia: str) -> dict[str, Any]:
    return {
        "id": None,
        "title": "",
        "start": dia,
        "end": dia,
        "nonstandard": {"primeiroDoDia": True, "reservas": []},
    }


def _bloco(bid: int, title: str, dia: str, reservas: list[dict[str, Any]]) -> dict[str, Any]:
    count: dict[str, int] = {}
    for r in reservas:
        b = _STATUS_BUCKET[r["idStatusReserva"]]
        count[b] = count.get(b, 0) + 1
    ini, fim = title.split(" - ")
    return {
        "id": bid,
        "title": title,
        "start": f"{dia}T{ini}:00-03:00",
        "end": f"{dia}T{fim}:00-03:00",
        "nonstandard": {"reservas": reservas, "countPorStatus": count},
    }


def calendar_events(*, hoje: date | None = None, dias: int = 10) -> list[dict[str, Any]]:
    """Array ``events`` — janela forward-only do dia vigente para frente (ADR-0001 D6)."""
    hoje = hoje or date.today()
    events: list[dict[str, Any]] = []
    rid = 500_000
    mid = 9_000
    for offset in range(dias):
        d = hoje + timedelta(days=offset)
        if d.weekday() >= 5:  # fim de semana sem grade
            continue
        dia = d.isoformat()
        events.append(_placeholder(dia))
        _slots = (
            ("08:00 - 12:00", ("401", "402", "403")),
            ("13:00 - 18:00", ("451", "452", "453")),
        )
        for slot_ix, (title, slots) in enumerate(_slots):
            rng = _rng("bloco", dia, title)
            reservas: list[dict[str, Any]] = []
            for id_sala in slots:
                for _ in range(rng.randint(1, 5)):
                    rid += 1
                    mid = 9_000 + (rid % 40)
                    # dias mais próximos: mais check-in/out; dias distantes: quase tudo reservado
                    if offset <= 1:
                        status = rng.choice([1, 3, 4, 4, 2, 5])
                    elif offset <= 3:
                        status = rng.choice([1, 1, 3, 2, 9])
                    else:
                        status = rng.choice([1, 1, 1, 2])
                    hora = title.split(" - ")[0]
                    reservas.append(
                        _reserva(rid, status, id_membro=mid, id_sala=id_sala, dia=dia, hora=hora)
                    )
            events.append(_bloco(1000 + offset * 2 + slot_ix, title, dia, reservas))
    return events


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
