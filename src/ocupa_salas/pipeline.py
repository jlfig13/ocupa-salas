"""
Orquestração fina: coleta → strip → versionamento por hash → JSONL com colunas de rastreio.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues

O que o ``sesi-airflow`` faz no ``load_staging`` genérico está aqui em miniatura, para o
repo rodar ponta a ponta: cada linha recebe ``fonte``/``data_extracao``/``data_particao``
/``hash_linha``/``id_origem`` e só é emitida quando o ``hash_linha`` difere do último
conhecido para aquele ``id_origem`` (ADR-0001 D3 — grava-quando-muda, re-execução do
mesmo slot é idempotente). O estado dos hashes vive num JSON simples (``StateStore``);
em produção o papel dele é da constraint ``UNIQUE (id_origem, data_particao, hash_linha)``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ocupa_salas.hashing import hash_linha
from ocupa_salas.http_client import CollectResult, Connection, ReservaSpaceClient

FONTE = "reservaspace"


def _agora_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class StateStore:
    """Mapa ``id_origem -> hash_linha`` do último snapshot visto, persistido em JSON.

    Fica no lugar da constraint de banco que, em produção, decide se a linha é nova.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else None
        self._hashes: dict[str, str] = {}
        if self.path and self.path.exists():
            self._hashes = json.loads(self.path.read_text(encoding="utf-8"))

    def is_new(self, id_origem: str, h: str) -> bool:
        return self._hashes.get(id_origem) != h

    def record(self, id_origem: str, h: str) -> None:
        self._hashes[id_origem] = h

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._hashes, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )


@dataclass
class RunResult:
    """Saída de :func:`run_collection`."""

    data_particao: str
    data_extracao: str
    linhas_novas: list[dict[str, Any]] = field(default_factory=list)
    linhas_inalteradas: int = 0
    capacidade: list[dict[str, Any]] = field(default_factory=list)
    blocos: list[dict[str, Any]] = field(default_factory=list)
    canarios_falhos: int = 0

    @property
    def resumo(self) -> str:
        return (
            f"particao={self.data_particao} novas={len(self.linhas_novas)} "
            f"inalteradas={self.linhas_inalteradas} capacidade={len(self.capacidade)} "
            f"blocos={len(self.blocos)} canarios_falhos={self.canarios_falhos}"
        )


def _linha_rastreada(
    payload: Mapping[str, Any], *, id_origem: str, h: str, data_particao: str, data_extracao: str
) -> dict[str, Any]:
    return {
        "fonte": FONTE,
        "id_origem": id_origem,
        "data_particao": data_particao,
        "data_extracao": data_extracao,
        "hash_linha": h,
        "payload": dict(payload),
    }


def _from_collect_result(
    cr: CollectResult, *, state: StateStore, data_particao: str, data_extracao: str
) -> RunResult:
    run = RunResult(data_particao=data_particao, data_extracao=data_extracao)
    run.blocos = cr.blocos
    run.canarios_falhos = sum(1 for c in cr.canarios if c.canario_falhou)

    for rec in cr.reservas:
        id_origem = str(rec["payload"].get("idReserva"))
        h = rec["hash_linha"]
        if state.is_new(id_origem, h):
            run.linhas_novas.append(
                _linha_rastreada(
                    rec["payload"],
                    id_origem=id_origem,
                    h=h,
                    data_particao=data_particao,
                    data_extracao=data_extracao,
                )
            )
            state.record(id_origem, h)
        else:
            run.linhas_inalteradas += 1

    for sala in cr.capacidade:
        id_origem = f"{sala.get('idSala')}:{sala.get('idFaixaHorario')}"
        h = hash_linha(sala)
        row = _linha_rastreada(
            sala,
            id_origem=id_origem,
            h=h,
            data_particao=data_particao,
            data_extracao=data_extracao,
        )
        run.capacidade.append(row)
        state.record(id_origem, h)

    return run


def run_collection(
    conn: Connection | Mapping[str, Any],
    *,
    state: StateStore | None = None,
    data_particao: str | None = None,
    http: Any | None = None,
    on_alert: Callable[[str], None] | None = None,
) -> RunResult:
    """Coleta um ciclo e devolve as linhas novas já com colunas de rastreio.

    ``data_particao`` default = hoje (UTC). ``state`` default = em memória (tudo é novo).
    """
    conn_obj = conn if isinstance(conn, Connection) else Connection.from_mapping(conn)
    st = state if state is not None else StateStore()
    particao = data_particao or date.today().isoformat()
    extracao = _agora_iso()

    client = ReservaSpaceClient(conn_obj, http=http, on_alert=on_alert)
    cr = client.collect()
    return _from_collect_result(cr, state=st, data_particao=particao, data_extracao=extracao)


def write_jsonl(rows: list[dict[str, Any]], path: Path | str) -> int:
    """Grava ``rows`` como JSON Lines (uma linha por objeto). Devolve a contagem."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)
