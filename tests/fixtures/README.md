# Fixtures

Dublês **sintéticos** — determinísticos, minúsculos, com PII **obviamente falsa**
(`000.000.000-00`, `fake@example.invalid`, CNPJs `11.111.111/0001-11`). Reproduzem a
*forma* documentada em [`../../docs/mapeamento_fonte.md`](../../docs/mapeamento_fonte.md)
(§2.1, §2.2, §4, §6).

Regerar: `python tests/fixtures/_generate.py`.

| Arquivo | Cenário |
|---|---|
| `calendar_dia_normal.html` | 2 dias, blocos placeholder (`primeiroDoDia`), contagens que conferem |
| `calendar_dia_alto_volume.html` | 1 bloco, 40 reservas |
| `calendar_mes_vazio.html` | só placeholders e bloco sem reserva (um sem `countPorStatus`) |
| `calendar_canario_divergente.html` | `countPorStatus` não bate com `reservas[]` (truncamento simulado) |
| `local.html` | global JS `locais` com `faixaHorarios` + metas CSRF (Seam 2) |
| `get_salas.json` | resposta de `POST /painel-config/get-salas` |
| `reserva_raw_com_pii.json` | uma reserva crua com PII sintética, para os testes de strip |
| `escolher_contexto.html` | tela `/escolher-contexto` (seleção de contexto, ADR-0001 D7) |

A fonte real seria capturada com `ocupa-salas-bootstrap scrub` (login SSO+MFA
interativo) e substituiria estes arquivos por versões scrubadas — o fluxo está em
[`../../src/ocupa_salas/bootstrap.py`](../../src/ocupa_salas/bootstrap.py). Neste
repo de portfólio, o papel da "captura real" é do
[`mock_server/`](../../mock_server/), exercitado em `tests/test_mock_server.py`.
