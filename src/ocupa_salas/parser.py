"""
Parser da tela de calendário (Seam 1) — fatia o array ``events`` embutido e aplica o strip.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues

Entrada: o HTML cru de ``GET /``. Saída: :class:`ParsedPage` com um :class:`Bloco` por
faixa de horário, cada um com suas reservas já stripadas (:mod:`ocupa_salas.strip`) e o
``hash_linha`` calculado. Blocos placeholder (``nonstandard.primeiroDoDia: true``) são
descartados. Qualquer desvio de estrutura levanta :class:`SchemaError` nomeando a chave
que faltou — nunca grava dado vazio (spec, user story 16).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, NamedTuple

from ocupa_salas.canary import normalize_count_por_status
from ocupa_salas.errors import SchemaError
from ocupa_salas.hashing import hash_linha
from ocupa_salas.strip import strip_reserva

# A chave tem que ser exatamente ``events`` (ou ``"events"``): o caractere anterior não
# pode ser parte de um identificador, senão ``calendarEvents":[`` casaria por engano.
_EVENTS_MARKER = re.compile(r"""(?<![A-Za-z0-9_"'])["']?events["']?\s*:\s*\[""")
# Idem para o global ``locais`` — não pode ser sufixo de outro nome (``gruposLocais``).
_LOCAIS_MARKER = re.compile(r"""(?<![A-Za-z0-9_.])locais\s*=\s*\[""")
_META_RE = re.compile(
    r"""<meta\s+[^>]*name=["'](?P<name>csrf-token|csrf-param)["'][^>]*>""",
    re.IGNORECASE,
)
_CONTENT_RE = re.compile(r"""content=["'](?P<content>[^"']*)["']""", re.IGNORECASE)


@dataclass(frozen=True)
class ReservaRecord:
    """Uma reserva pós-strip mais sua impressão digital de versionamento."""

    payload: dict[str, Any]
    hash_linha: str


@dataclass(frozen=True)
class Bloco:
    """Metadados de uma faixa de horário + suas reservas stripadas."""

    id: Any
    title: str | None
    start: str | None
    end: str | None
    count_por_status: dict[str, int] | None
    reservas: list[ReservaRecord]


@dataclass(frozen=True)
class ParsedPage:
    """Resultado do parse: os blocos reais (placeholders já removidos)."""

    blocos: list[Bloco]

    @property
    def reservas(self) -> list[ReservaRecord]:
        """Lista achatada de todas as reservas, na ordem dos blocos."""
        return [rec for bloco in self.blocos for rec in bloco.reservas]


def _slice_json_array(text: str, open_idx: int, *, what: str) -> Any:
    """Extrai o array JSON balanceado que começa em ``text[open_idx] == '['``."""
    depth = 0
    in_str = False
    escaped = False
    for i in range(open_idx, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                raw = text[open_idx : i + 1]
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:  # pragma: no cover - defensivo
                    raise SchemaError(f"array '{what}' não é JSON válido: {exc}") from exc
    raise SchemaError(f"array '{what}' não fecha (colchete sem par) no HTML")


def _find_array(html: str, marker: re.Pattern[str], what: str) -> Any:
    match = marker.search(html)
    if match is None:
        raise SchemaError(f"marcador do array '{what}' ausente no HTML")
    return _slice_json_array(html, match.end() - 1, what=what)


def extract_events(html: str) -> list[Any]:
    """Devolve o array ``events`` cru (lista de blocos), sem strip."""
    events = _find_array(html, _EVENTS_MARKER, "events")
    if not isinstance(events, list):
        raise SchemaError(f"'events' não é lista: {type(events).__name__}")
    return events


class Csrf(NamedTuple):
    """Par CSRF lido do HTML: ``param`` é o nome do campo, ``token`` o valor."""

    param: str
    token: str


def extract_csrf(html: str) -> Csrf:
    """Lê o :class:`Csrf` das tags ``<meta>`` — nunca fixar no código.

    O nome do campo (``csrf-param``) muda por sessão/deploy (mapeamento_fonte.md §6.1).
    """
    found: dict[str, str] = {}
    for meta in _META_RE.finditer(html):
        content = _CONTENT_RE.search(meta.group(0))
        if content is not None:
            found[meta.group("name")] = content.group("content")
    missing = {"csrf-token", "csrf-param"} - found.keys()
    if missing:
        raise SchemaError(f"meta(s) CSRF ausente(s) no HTML: {sorted(missing)}")
    return Csrf(param=found["csrf-param"], token=found["csrf-token"])


def extract_locais(html: str) -> list[Any]:
    """Array cru do global JS ``locais`` de ``/painel-config/local``.

    :func:`extract_faixa_ids` é a leitura de produção; isto expõe o array inteiro para o
    scrub de fixture (:func:`ocupa_salas.scrub.scrub_locais`).
    """
    locais = _find_array(html, _LOCAIS_MARKER, "locais")
    if not isinstance(locais, list):
        raise SchemaError(f"'locais' não é lista: {type(locais).__name__}")
    return locais


def extract_faixa_ids(html: str) -> list[str]:
    """Lista ordenada e sem repetição de ``idFaixaHorario`` do global JS ``locais``.

    Fonte: ``locais[].faixaHorarios[].idFaixaHorario`` (mapeamento_fonte.md §6.1).
    """
    locais = extract_locais(html)
    ids: list[str] = []
    seen: set[str] = set()
    for loc in locais:
        if not isinstance(loc, dict):
            raise SchemaError("item de 'locais' não é objeto")
        faixas = loc.get("faixaHorarios")
        if faixas is None:
            raise SchemaError("local sem 'faixaHorarios' no global 'locais'")
        for faixa in faixas:
            if not isinstance(faixa, dict) or "idFaixaHorario" not in faixa:
                raise SchemaError("faixa sem 'idFaixaHorario' no global 'locais'")
            fid = str(faixa["idFaixaHorario"])
            if fid not in seen:
                seen.add(fid)
                ids.append(fid)
    return ids


def _parse_bloco(item: Any, pos: int) -> Bloco | None:
    if not isinstance(item, dict):
        raise SchemaError(f"item {pos} de 'events' não é objeto: {type(item).__name__}")
    nonstandard = item.get("nonstandard")
    if not isinstance(nonstandard, dict):
        raise SchemaError(f"bloco {pos} sem objeto 'nonstandard'")
    if nonstandard.get("primeiroDoDia") is True:
        return None  # placeholder de cabeçalho de dia — ignorar (mapeamento §2.1)

    reservas_raw = nonstandard.get("reservas")
    if not isinstance(reservas_raw, list):
        raise SchemaError(f"bloco {pos} sem lista 'nonstandard.reservas'")

    registros: list[ReservaRecord] = []
    for raw in reservas_raw:
        payload = strip_reserva(raw)
        registros.append(ReservaRecord(payload=payload, hash_linha=hash_linha(payload)))
    return Bloco(
        id=item.get("id"),
        title=item.get("title"),
        start=item.get("start"),
        end=item.get("end"),
        count_por_status=normalize_count_por_status(nonstandard.get("countPorStatus")),
        reservas=registros,
    )


def parse_page(html: str) -> ParsedPage:
    """Fatia ``events`` do HTML e devolve os blocos reais com reservas stripadas."""
    if not isinstance(html, str) or not html.strip():
        raise SchemaError("HTML vazio ou não textual")
    blocos = [
        bloco
        for pos, item in enumerate(extract_events(html))
        if (bloco := _parse_bloco(item, pos)) is not None
    ]
    return ParsedPage(blocos=blocos)
