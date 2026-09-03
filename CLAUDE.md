# ocupa-salas

Projeto de **estudo e portfólio**. Coletor Python + camada analítica de **ocupação
de salas** de uma plataforma fictícia de reserva (`ReservaSpace`). Extrai o array
`events` do HTML de uma tela de calendário (padrão Yii2 + FullCalendar) e a
capacidade nominal via `POST /painel-config/get-salas`.

**Nada aqui é real.** A fonte é o servidor `mock_server/` (FastAPI), com dados
gerados por semente fixa. Não há informação de empresa, pessoa ou sistema real.
Este repo é a reescrita, sem dados sensíveis, de um projeto corporativo que não
pode ser publicado — os conceitos e a arquitetura são os mesmos.

Mapeamento da fonte fictícia: `docs/mapeamento_fonte.md`. Decisão de ingestão:
`docs/adr/ADR-0001`. Modelo de domínio: `CONTEXT.md`.

## Cabeçalho de proveniência (obrigatório em todo módulo do coletor)

Todo arquivo de `src/ocupa_salas/` abre com:

```python
"""
<propósito do módulo em uma linha>

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues
"""
```

`tests/test_provenance.py` falha se algum módulo perder o cabeçalho.

## Convenções

- **Terminologia:** use os termos do `CONTEXT.md` (Reserva, Bloco de horário,
  Faixa de Horário, Sala, Override de capacidade, etc.). Não derivar para
  sinônimos que o glossário evita.
- **Sem credencial no código.** Runtime lê `OCUPA_SALAS_*` (ver `ocupa_salas.config`)
  ou a Airflow Connection. O `mock_server` não tem login.
- **Falhar alto.** Cada mania da fonte tem um erro nomeado em `ocupa_salas.errors`;
  nunca engolir um `200` vazio como "zero registros".
- **PII:** o strip é whitelist-only e roda antes de qualquer escrita. `find_forbidden_keys`
  é a varredura de defesa em profundidade — nenhuma fixture versionada pode conter
  chave de `FORBIDDEN_PII_FIELDS`.

## Fluxo de trabalho

- `python -m pytest -q` · `python -m ruff check .`
- `python -m ocupa_salas --mock collect` roda o coletor ponta a ponta contra o mock.
- Regerar fixtures: `python tests/fixtures/_generate.py`.
- Issues/specs como GitHub Issues (`gh` CLI).
