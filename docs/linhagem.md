# Linhagem de Dados — BI de Ocupação de Salas

> Da fonte fictícia ao painel. Campos em
> [`dicionario-dados.md`](dicionario-dados.md); regras em
> [`regras-negocio.md`](regras-negocio.md).

## 1. Fluxo macro

```
ReservaSpace (HTML + get-salas)
  → coletor (parser + strip + canário + hash)          [src/ocupa_salas]
  → reservas.jsonl / capacidade.jsonl                   [pipeline, colunas de rastreio]
  → stg_reservas / stg_reservas_bloco / stg_capacidade  [staging, append-only, versionado]
  → silver (conformação, dimensões, capacidade do dia, timeline)
  → gld_ocupacao_corrente (view)  +  fct_ocupacao_dia (table, noturno)
  → modelo semântico (DirectQuery)
  → Painel Resumo de Salas
```

## 2. Linhagem campo-a-campo das métricas

| Métrica do painel | Deriva de | Regra |
|---|---|---|
| **Vagas Disponíveis** | `stg_capacidade.maxReservas` + `alteraSala[]` | RN-03 → `capacidade_do_dia`; Σ no período |
| **Reservas Realizadas** | `stg_reservas.payload.idStatusReserva` ∈ {3,4} | RN-01/RN-02 → `qtd_ocupado`; Σ |
| **Reservado (futuro)** | `idStatusReserva = 1` | `qtd_consome_vaga_sinalizado`; Σ |
| **Cancelamentos + Faltas** | `idStatusReserva` ∈ {2,5,8,9} | `qtd_fora`; Σ |
| **Taxa de Ocupação Realizada** | `qtd_ocupado` / `capacidade_do_dia` | RN-05 (razão de somas) |
| **Taxa de Ocupação Preenchida** | (`qtd_ocupado` + `qtd_consome_vaga_sinalizado`) / `capacidade_do_dia` | RN-05 |
| **Taxa de Comparecimento** | `qtd_ocupado` / (`qtd_ocupado` + `qtd_fora`) | RN-05 |
| **Meta** | constante 75% | RN-06 — não vem do dado |
| **`data_referencia`** | `payload.dataReserva` | offset → data local, derivado no silver |
| **`tem_override`** | `alteraSala[]` cobrindo a data com `ativo=1` | RN-03 |
| **`tem_status_provisional`** | `dim_status_kpi_role.provisional` (status 8, 9) | RN-10 |
| **`canario_falhou`** | `stg_reservas_bloco` marcado na ingestão | canário (contagem × `countPorStatus`) |

## 3. Resolução da versão corrente

`gld_ocupacao_corrente` resolve, por `id_origem`, a linha mais recente:

```sql
row_number() over (
  partition by id_origem
  order by data_particao desc, data_extracao desc
) = 1
```

Não materializa → cada consulta reflete a última coleta na `stg_*` (ADR-0001 D4).

## 4. Pontos de perda deliberada

| Onde | O que se perde | Por quê |
|---|---|---|
| Strip (ingestão) | `membro.*` sensível, `observacao` | ADR-0001 D5 — dado de terceiros, sem replay por construção |
| Forward-only | meses anteriores à entrada em produção | ADR-0001 D6 — a fonte não expõe histórico por scraping |
| `payload` pós-strip na staging | JSON cru byte a byte | desvio deliberado do "raw fiel" — o sensível não pode existir em disco |
