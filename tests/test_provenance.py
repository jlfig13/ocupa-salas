"""Todo módulo do coletor carrega o cabeçalho de proveniência (CLAUDE.md, user story 10)."""

from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "ocupa_salas"
MODULES = sorted(p for p in SRC.glob("*.py"))

_REQUIRED = [
    "Projeto",
    "github.com/jlfig13/ocupa-salas",
    "Domínio",
    "Dados",
    "ADR-0001",
    "Dúvidas",
]


@pytest.mark.parametrize("module", MODULES, ids=lambda p: p.name)
def test_cabecalho_de_proveniencia(module: Path):
    head = module.read_text(encoding="utf-8")[:1200]
    faltando = [marker for marker in _REQUIRED if marker not in head]
    assert not faltando, f"{module.name} sem marcadores de proveniência: {faltando}"
