"""
Strip de PII da reserva — whitelist-only, aplicado em memória antes de qualquer escrita.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues

Regra (ADR-0001 D5 / mapeamento_fonte.md §2.2, §4): o objeto ``membro`` inteiro nunca é
serializado. Da reserva sobrevivem só os escalares da whitelist abaixo, mais
``idMembro`` (FK opaca) e ``membro.contrato.empresa.cnpj``. ``observacao`` é descartada
(risco de PII digitada à mão).
"""

from __future__ import annotations

from typing import Any

from ocupa_salas.errors import PIILeakError, SchemaError

#: Escalares da reserva que sobrevivem ao strip (mapeamento_fonte.md §2.2, menos ``observacao``).
RESERVA_SCALARS: tuple[str, ...] = (
    "idReserva",
    "idSalaReserva",
    "idMembro",
    "idStatusReserva",
    "idStatusPendencia",
    "idPostoLocal",
    "idSala",
    "idFaixaHorario",
    "dataReserva",
    "idReservadoPor",
    "dataCriacaoReserva",
    "atualizadoPor",
    "atualizadoEm",
    "checkIn",
    "checkOut",
    "checkInPor",
    "checkOutPor",
    "cancelado",
    "canceladoPor",
    "atendidoPor",
)

#: Coluna derivada: CNPJ da empresa contratante, único campo do cadastro que fica.
_EMPRESA_CNPJ_PATH: tuple[str, ...] = ("membro", "contrato", "empresa", "cnpj")

#: Campos sensíveis no nível do valor — mapeamento_fonte.md §4 + ADR-0001 D5, mais os
#: identificadores com sufixo ``Crm`` (dado replicado do CRM corporativo a montante).
#: Nenhum destes pode aparecer em disco/tabela, nem numa fixture versionada.
FORBIDDEN_PII_FIELDS: frozenset[str] = frozenset(
    {
        # identificação pessoal
        "cpf",
        "rg",
        "passaporte",
        "dataNascimento",
        "sexo",
        # contato pessoal
        "email",
        "telefoneCelular",
        "contatoEmergencia",
        # vínculo contratual (``ativo`` fica de fora — palavra genérica que também
        # aparece em dados legítimos de capacidade, e o strip é whitelist-only)
        "matriculaContrato",
        "dataAdesao",
        "dataEncerramento",
        "categoriaPlano",
        "planoSaudeNumero",
        # preferências / acessibilidade (dado pessoal sensível)
        "necessidadesAcessibilidade",
        "restricaoMobilidade",
        "preferenciasAlimentares",
        # empresa / contrato (texto livre e endereço)
        "razaoSocial",
        "endereco",
        # texto livre com risco de PII
        "nome",
        "observacao",
        # identificadores replicados do CRM (indício de origem em outro sistema)
        "setorCodCrm",
        "setorNomeCrm",
        "centroCustoCodCrm",
        "centroCustoNomeCrm",
        "codMembroCrm",
        "codContratoCrm",
        "unidadeNegocioCrm",
        "id_contrato_crm",
    }
)

#: Contêineres do cadastro que nunca são serializados inteiros (ADR-0001 D5). O strip é
#: whitelist-only, então nada disto deve sobrar na saída — se sobrar, é bug.
FORBIDDEN_CONTAINERS: frozenset[str] = frozenset(
    {
        "membro",
        "contrato",
        "sala",
        "postoLocal",
        "statusReserva",
        "statusPendencia",
    }
)

#: Tudo que jamais pode aparecer na saída do strip.
FORBIDDEN_KEYS: frozenset[str] = FORBIDDEN_PII_FIELDS | FORBIDDEN_CONTAINERS

_FORBIDDEN_LOWER: frozenset[str] = frozenset(k.lower() for k in FORBIDDEN_KEYS)
_FORBIDDEN_PII_LOWER: frozenset[str] = frozenset(k.lower() for k in FORBIDDEN_PII_FIELDS)


def dig(obj: Any, *path: str) -> Any:
    """Navega ``obj[path[0]][path[1]]...`` devolvendo ``None`` no primeiro elo ausente."""
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def kept_membro_fields(raw: dict[str, Any]) -> tuple[Any, Any]:
    """Extrai ``(idMembro, cnpj_empresa)`` — os dois únicos dados do cadastro que ficam.

    ``idMembro`` vem do topo ou de dentro de ``membro``; o CNPJ vem sempre de
    ``membro.contrato.empresa.cnpj`` (ADR-0001 D5). Compartilhado por
    :func:`strip_reserva` e :func:`ocupa_salas.scrub.scrub_reserva`.
    """
    id_membro = raw.get("idMembro")
    if id_membro is None:
        id_membro = dig(raw, "membro", "idMembro")
    return id_membro, dig(raw, *_EMPRESA_CNPJ_PATH)


def find_forbidden_keys(obj: Any, *, pii_only: bool = False, _path: str = "$") -> list[str]:
    """Devolve os caminhos de toda chave proibida encontrada em ``obj`` (recursivo).

    Com ``pii_only=True`` ignora os nomes de contêiner (``membro`` etc.) e olha só
    campos sensíveis no nível do valor — é a varredura usada para validar uma fixture
    scrubada, que preserva a forma aninhada mas não pode conter PII.
    """
    banned = _FORBIDDEN_PII_LOWER if pii_only else _FORBIDDEN_LOWER
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str) and key.lower() in banned:
                hits.append(f"{_path}.{key}")
            hits.extend(find_forbidden_keys(value, pii_only=pii_only, _path=f"{_path}.{key}"))
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            hits.extend(find_forbidden_keys(item, pii_only=pii_only, _path=f"{_path}[{i}]"))
    return hits


def assert_no_pii(obj: Any, *, pii_only: bool = False) -> None:
    """Levanta :class:`PIILeakError` se :func:`find_forbidden_keys` achar qualquer chave.

    Defesa em profundidade sobre a saída do strip (whitelist-only) e sobre fixtures.
    """
    hits = find_forbidden_keys(obj, pii_only=pii_only)
    if hits:
        raise PIILeakError(f"chave(s) sensível(is) presente(s): {hits}")


def strip_reserva(raw: dict[str, Any]) -> dict[str, Any]:
    """Reduz uma reserva crua aos campos permitidos.

    Constrói a saída só a partir de chaves conhecidas — nada é copiado por referência
    de objeto aninhado. Levanta :class:`SchemaError` se faltar ``idReserva`` (o grão)
    e :class:`PIILeakError` se, por bug, algo sensível escapar para a saída.
    """
    if not isinstance(raw, dict):
        raise SchemaError(f"reserva não é objeto: {type(raw).__name__}")
    if "idReserva" not in raw:
        raise SchemaError("reserva sem 'idReserva' (grão da tabela-fato)")

    out: dict[str, Any] = {k: raw[k] for k in RESERVA_SCALARS if k in raw}

    id_membro, cnpj = kept_membro_fields(raw)
    if id_membro is not None:
        out["idMembro"] = id_membro
    if cnpj is not None:
        out["cnpj_empresa"] = cnpj

    assert_no_pii(out)
    return out
