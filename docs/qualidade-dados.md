# Qualidade de Dados — BI de Ocupação de Salas

> Controles, limiares e checklist pré-divulgação. Regras em
> [`regras-negocio.md`](regras-negocio.md).

## Controles

| # | Controle | Onde | Ação na falha |
|---|---|---|---|
| **DQ-01** | `GET /` traz a tela autenticada (marcadores `csrf-token` + `calendarioReservas`) | coletor (`_require_authenticated_page`) | `SessionExpiredError` — falha alta, pede re-bootstrap |
| **DQ-02** | POST não devolve `200` com corpo vazio | coletor (`_text_or_empty_error`) | `EmptyBodyError` — nunca tratar como "zero registros" |
| **DQ-03** | HTML da fonte bate com o schema esperado (chaves presentes) | parser (`SchemaError`) | falha alta nomeando a chave que sumiu — não grava dado vazio |
| **DQ-04** | Canário: contagem por bucket calculada = `nonstandard.countPorStatus` | `ocupa_salas.canary` | **marca** o bloco (`canario_falhou`), alerta, **não bloqueia** |
| **DQ-05** | Nenhum status fora do mapa de papel de KPI (`qtd_desconhecido = 0`) | silver / medida `Alerta Status Não Mapeado` | acende selo no painel; abrir issue para completar `dim_status_kpi_role` |
| **DQ-06** | Nenhuma chave de `FORBIDDEN_PII_FIELDS` na saída do strip nem em fixture versionada | `assert_no_pii` / `test_provenance` / `test_strip` | `PIILeakError` — a carga não segue |
| **DQ-07** | Idempotência: re-executar o mesmo slot não gera linha nova | `StateStore` / `UNIQUE (id_origem, data_particao, hash_linha)` | conflito → nada (comportamento esperado) |
| **DQ-08** | `capacidade_do_dia > 0` para toda linha do fato com reservas | silver | linha sem capacidade → quarentena + alerta (sala sem `maxReservas` nem override) |

## Limiares

| Métrica | Verde | Amarelo | Vermelho |
|---|---|---|---|
| Taxa de Ocupação Realizada | ≥ 75% (meta) | 60–75% | < 60% |
| `qtd_desconhecido` (total do período) | 0 | 1–5 | > 5 |
| Blocos com `canario_falhou` (por coleta) | 0 | 1–3 | > 3 |
| Idade do cookie de sessão | < 7 d | 7–14 d | > 14 d (re-bootstrap) |

## Checklist pré-divulgação

- [ ] Slicer de período aplicado (RN-07) — a taxa global sem recorte não vale.
- [ ] `qtd_desconhecido = 0` no período (DQ-05).
- [ ] Nenhum dia relevante com `canario_falhou` (DQ-04); se houver, nota no material.
- [ ] Selo "provisório" checado — números que dependem de status 8/9 (RN-10).
- [ ] Card "Locais" = 1 (RN-09) — se ≠ 1, a fase multi-local começou e as regras mudam.
- [ ] Data da última coleta (`data_extracao` máx) dentro da janela esperada.
