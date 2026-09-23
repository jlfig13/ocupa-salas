"""
Exceções do coletor — cada mania da fonte vira um erro nomeado, nunca um silêncio.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues
"""

from __future__ import annotations


class OcupaSalasError(Exception):
    """Raiz de todos os erros do coletor."""


class SchemaError(OcupaSalasError):
    """O HTML da fonte não bate com o schema esperado (chave/estrutura ausente).

    A mensagem sempre nomeia a chave ou o trecho de estrutura que faltou, para o
    parser falhar alto em vez de gravar dado vazio (spec, user story 16).
    """


class PIILeakError(OcupaSalasError):
    """Uma chave sensível sobreviveu ao strip — trava antes de qualquer escrita.

    Defesa em profundidade: o strip é whitelist-only, então este erro nunca deve
    disparar; se disparar, é bug no strip e a carga não pode seguir
    (ADR-0001 D5).
    """


class EmptyBodyError(OcupaSalasError):
    """``200 OK`` com corpo vazio — efeito de faltar ``X-Requested-With`` no POST.

    Tratado como erro explícito, nunca como "zero registros"
    (mapeamento_fonte.md §6.1).
    """


class SessionExpiredError(OcupaSalasError):
    """Cookie de sessão inválido/expirado (``401``). Pede re-bootstrap.

    A mensagem sempre instrui a refazer o bootstrap de sessão — é a ação do
    operador, não algo que o coletor resolve sozinho (ADR-0001 D2).
    """

    def __init__(self, detail: str = "") -> None:
        base = "sessão inválida (401) — refazer bootstrap de sessão da fonte"
        super().__init__(f"{base}: {detail}" if detail else base)


class UpstreamError(OcupaSalasError):
    """Falha transitória da fonte (``5xx``/timeout) persistente após todas as tentativas."""
