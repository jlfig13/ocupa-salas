"""
Scrub de captura crua → fixture versionável, sem PII (apoio ao bootstrap).

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues

A captura crua de ``GET /`` traz o cadastro completo do membro (mapeamento_fonte.md §4)
e fica em path gitignored (``.captures/``). Para virar fixture de teste versionável, o
array ``events`` passa por aqui: a forma aninhada é preservada (o parser precisa
exercitar ``membro.contrato.empresa.cnpj``), mas todo campo sensível é removido e o
resto do objeto ``membro`` é reduzido ao esqueleto mínimo.
"""

from __future__ import annotations

from typing import Any

from ocupa_salas.strip import RESERVA_SCALARS, assert_no_pii, kept_membro_fields

#: Campos de ``locais[].faixaHorarios[]`` que a fixture versionada preserva — o que
#: :func:`ocupa_salas.parser.extract_faixa_ids` lê + metadados da faixa úteis ao silver.
#: GUIDs de auditoria e o resto do cadastro do local são descartados.
FAIXA_HORARIO_FIELDS: tuple[str, ...] = (
    "idFaixaHorario",
    "idLocal",
    "nomeFaixa",
    "horaInicial",
    "horaFinal",
    "diasSemana",
    "diasMes",
    "horaMarcada",
    "ativo",
)


def scrub_reserva(raw: dict[str, Any]) -> dict[str, Any]:
    """Reduz uma reserva crua à forma segura de fixture.

    Mantém os escalares da whitelist e um ``membro`` esqueleto com apenas ``idMembro``
    e ``contrato.empresa.cnpj`` (CNPJ da empresa contratante é explicitamente retido
    pelo ADR-0001 D5).
    """
    out: dict[str, Any] = {k: raw[k] for k in RESERVA_SCALARS if k in raw}

    id_membro, cnpj = kept_membro_fields(raw)

    skeleton: dict[str, Any] = {}
    if id_membro is not None:
        skeleton["idMembro"] = id_membro
    if cnpj is not None:
        skeleton["contrato"] = {"empresa": {"cnpj": cnpj}}
    if skeleton:
        out["membro"] = skeleton
    return out


def scrub_events(events: list[Any]) -> list[Any]:
    """Aplica :func:`scrub_reserva` a cada bloco, preservando metadados do bloco."""
    scrubbed: list[Any] = []
    for item in events:
        if not isinstance(item, dict):
            scrubbed.append(item)
            continue
        block = dict(item)
        nonstd = block.get("nonstandard")
        if isinstance(nonstd, dict):
            new_nonstd = dict(nonstd)
            reservas = nonstd.get("reservas")
            if isinstance(reservas, list):
                new_nonstd["reservas"] = [
                    scrub_reserva(a) if isinstance(a, dict) else a for a in reservas
                ]
            block["nonstandard"] = new_nonstd
        scrubbed.append(block)

    assert_no_pii(scrubbed, pii_only=True)
    return scrubbed


def scrub_locais(locais: list[Any]) -> list[Any]:
    """Reduz o global JS ``locais`` à forma segura de fixture.

    Mantém ``idLocal`` e ``faixaHorarios[]`` (só a whitelist
    :data:`FAIXA_HORARIO_FIELDS`). Todo o resto do cadastro do local — ``nome``,
    ``endereco``, ``email``, ``telefone``, GUIDs de auditoria — é descartado. A
    varredura full (não ``pii_only``) tem que voltar limpa.
    """
    out: list[Any] = []
    for loc in locais:
        if not isinstance(loc, dict):
            out.append(loc)
            continue
        faixas = [
            {k: f[k] for k in FAIXA_HORARIO_FIELDS if k in f}
            for f in loc.get("faixaHorarios") or []
            if isinstance(f, dict)
        ]
        out.append({"idLocal": loc.get("idLocal"), "faixaHorarios": faixas})

    assert_no_pii(out)
    return out


def scrub_get_salas(salas: list[Any]) -> list[Any]:
    """Neutraliza a resposta de ``get-salas`` para virar fixture versionável.

    ``nome`` (rótulo da sala, ex. ``"SALA FOCO 01_MANHA"``) **não é PII**, mas a regra do
    repo é: nenhuma chave de :data:`ocupa_salas.strip.FORBIDDEN_PII_FIELDS` numa fixture
    versionada. A chave é renomeada para ``nomeSala`` (valor preservado); forma e
    contagens (``maxReservas``, ``peso``, ``postos[]``) ficam intactas.
    """
    out: list[Any] = []
    for s in salas:
        if not isinstance(s, dict):
            out.append(s)
            continue
        item = {k: v for k, v in s.items() if k != "nome"}
        if "nome" in s:
            item["nomeSala"] = s["nome"]
        out.append(item)

    assert_no_pii(out, pii_only=True)
    return out
