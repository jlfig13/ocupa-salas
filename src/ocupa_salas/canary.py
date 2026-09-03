"""
Canário de integridade — contagem por status calculada × ``countPorStatus`` do bloco.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues

Divergência entre a contagem derivada de ``reservas[]`` e o ``countPorStatus``
pré-agregado do bloco sinaliza truncamento silencioso do array (mapeamento §2.1). O
``countPorStatus`` real vem por **bucket de workflow**, então os ``idStatusReserva`` são
traduzidos para bucket (:data:`STATUS_ID_TO_BUCKET`, mapa provisório) antes de comparar.
O canário **marca** o bloco (``canario_falhou``) e emite alerta, mas não bloqueia a
carga (spec, user story 15).
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ocupa_salas.errors import SchemaError

if TYPE_CHECKING:
    from ocupa_salas.parser import Bloco

_log = logging.getLogger(__name__)

# ``countPorStatus`` vem como mapa ``{bucket: n}`` chaveado por **bucket de workflow**,
# não por ``idStatusReserva``. A tolerância à lista de objetos fica como defesa.
_COUNT_KEYS = ("count", "total")
_STATUS_KEYS = ("idStatusReserva", "status")

# Mapa PROVISÓRIO ``idStatusReserva`` → bucket de ``countPorStatus``.
# Derivado da dimensão de status (mapeamento §3). Achado empírico documentado: **``9``
# ("Removido") entra no bucket ``cancelado``**, não some. Aberto até validação do
# requerente: destino de ``8`` ("No-Show Recepção") e qual id alimenta ``pendencia``.
STATUS_ID_TO_BUCKET: dict[str, str] = {
    "1": "reservado",
    "2": "cancelado",
    "3": "checkIn",
    "4": "checkOut",
    "5": "noShow",
    "8": "noShow",
    "9": "cancelado",
}


def bucket_do_status(id_status: Any) -> str:
    """``idStatusReserva`` → bucket de ``countPorStatus`` (mapa provisório).

    Status fora do mapa vira ``"id_desconhecido:<n>"`` — divergência proposital, para
    um status novo aparecer no alerta do canário em vez de sumir na tradução.
    """
    return STATUS_ID_TO_BUCKET.get(str(id_status), f"id_desconhecido:{id_status}")


def normalize_count_por_status(raw: Any) -> dict[str, int] | None:
    """Normaliza ``countPorStatus`` para ``{str(status): int}`` — ou ``None`` se ausente.

    Aceita as duas formas plausíveis da fonte: mapa ``{"reservado": 10}`` e lista de
    objetos ``[{"idStatusReserva": 1, "count": 10}]`` (chaves de contagem/status variam).
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return {str(k): int(v) for k, v in raw.items()}
    if isinstance(raw, list):
        out: dict[str, int] = {}
        for item in raw:
            if not isinstance(item, dict):
                raise SchemaError(f"item de 'countPorStatus' não é objeto: {item!r}")
            status = next((item[k] for k in _STATUS_KEYS if k in item), None)
            count = next((item[k] for k in _COUNT_KEYS if k in item), None)
            if status is None or count is None:
                raise SchemaError(f"item de 'countPorStatus' sem status/contagem: {item!r}")
            out[str(status)] = int(count)
        return out
    raise SchemaError(f"'countPorStatus' com forma inesperada: {type(raw).__name__}")


@dataclass(frozen=True)
class CanaryResult:
    """Resultado da checagem de um bloco. Contagens chaveadas por bucket de ``countPorStatus``."""

    status: str  # "match" | "mismatch" | "skipped"
    calculado: dict[str, int]  # buckets derivados de reservas[] via bucket_do_status
    esperado: dict[str, int] | None  # countPorStatus do bloco (já por bucket na fonte)
    detail: str = ""
    diferencas: dict[str, tuple[int, int]] = field(default_factory=dict)  # bucket -> (calc, esp)

    @property
    def ok(self) -> bool:
        return self.status != "mismatch"

    @property
    def canario_falhou(self) -> bool:
        return self.status == "mismatch"


def _sem_zeros(d: dict[str, int]) -> dict[str, int]:
    """Descarta buckets com contagem 0 — a fonte manda ``noShow: 0`` e afins."""
    return {k: v for k, v in d.items() if v}


def check_status_counts(
    status_values: Iterable[Any],
    count_por_status: Any,
    *,
    on_alert: Callable[[CanaryResult], None] | None = None,
    bloco_label: str = "",
) -> CanaryResult:
    """Compara a contagem por bucket derivada de ``reservas[]`` com o ``countPorStatus``.

    Os ``idStatusReserva`` são traduzidos para bucket (:func:`bucket_do_status`) antes
    da comparação, porque a fonte chaveia ``countPorStatus`` por bucket de workflow, não
    por id.
    """
    calculado = dict(Counter(bucket_do_status(s) for s in status_values))
    esperado = normalize_count_por_status(count_por_status)

    if esperado is None:
        return CanaryResult("skipped", calculado, None, "bloco sem 'countPorStatus'")

    calc_cmp, esp_cmp = _sem_zeros(calculado), _sem_zeros(esperado)
    if calc_cmp == esp_cmp:
        return CanaryResult("match", calculado, esperado, "contagens conferem (por bucket)")

    diffs = {
        bucket: (calc_cmp.get(bucket, 0), esp_cmp.get(bucket, 0))
        for bucket in calc_cmp.keys() | esp_cmp.keys()
        if calc_cmp.get(bucket, 0) != esp_cmp.get(bucket, 0)
    }
    label = f" [{bloco_label}]" if bloco_label else ""
    result = CanaryResult(
        "mismatch",
        calculado,
        esperado,
        f"divergência calculado×countPorStatus{label}: {diffs}",
        diffs,
    )
    _log.warning("canário de integridade falhou: %s", result.detail)
    if on_alert is not None:
        on_alert(result)
    return result


def check_bloco_integrity(
    bloco: Bloco,
    *,
    on_alert: Callable[[CanaryResult], None] | None = None,
) -> CanaryResult:
    """Versão para :class:`~ocupa_salas.parser.Bloco` já parseado."""
    return check_status_counts(
        (rec.payload.get("idStatusReserva") for rec in bloco.reservas),
        bloco.count_por_status,
        on_alert=on_alert,
        bloco_label=str(bloco.title or bloco.id or "?"),
    )
