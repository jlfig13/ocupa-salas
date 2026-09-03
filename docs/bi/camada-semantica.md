# Camada Semântica — BI de Ocupação de Salas

> Modelo, relações e medidas. Regras em
> [`../regras-negocio.md`](../regras-negocio.md); campos em
> [`../dicionario-dados.md`](../dicionario-dados.md).

## 1. Tabelas

| Tabela | Modo | Papel |
|---|---|---|
| `gld_ocupacao_corrente` | DirectQuery | **fato** pré-agregado por (`data_referencia`, `sala_sk`, `faixa_horario_sk`) |
| `dCalendario` | Calculada (`CALENDAR`) | tabela de datas; marcada como Tabela de Datas |
| `dim_sala` | DirectQuery | `sala_sk`, `nome_sala`, `turno` |
| `dim_status_kpi_role` | Import | referência (papel de KPI); **oculta, sem relação** — a view já traz baldes agregados |
| `_medidas` | Tabela técnica sem dados | hospeda todas as medidas |

## 2. Relações

```
dCalendario[Data]        1 —— *  gld_ocupacao_corrente[data_referencia]   (filtro único, ativo)
dim_sala[sala_sk]        1 —— *  gld_ocupacao_corrente[sala_sk]           (filtro único, ativo)
```

`dim_status_kpi_role` não se relaciona — existe só para documentar o mapa de papéis
no próprio modelo.

## 3. Medidas (DAX)

Sintaxe Power BI. `SUM` sobre a view pré-agregada; as taxas são **razão de somas**
(RN-05), com `DIVIDE` para blindar divisão por zero.

### Pasta: Volume

```dax
Vagas Disponíveis   = SUM ( gld_ocupacao_corrente[capacidade_do_dia] )
Reservas Realizadas = SUM ( gld_ocupacao_corrente[qtd_ocupado] )
Reservado Futuro    = SUM ( gld_ocupacao_corrente[qtd_consome_vaga_sinalizado] )
Cancelamentos + Faltas = SUM ( gld_ocupacao_corrente[qtd_fora] )
Reservas             = SUM ( gld_ocupacao_corrente[qtd_reservas] )
Reservas Ativas      = [Reservas Realizadas] + [Reservado Futuro]
Vagas Ociosas        = MAX ( [Vagas Disponíveis] - [Reservas Realizadas], 0 )
Vagas Livres         = MAX ( [Vagas Disponíveis] - [Reservas Realizadas] - [Reservado Futuro], 0 )
```

### Pasta: Taxas

```dax
Taxa de Ocupação Realizada =
    DIVIDE ( [Reservas Realizadas], [Vagas Disponíveis] )

Taxa de Ocupação Preenchida =
    DIVIDE ( [Reservas Realizadas] + [Reservado Futuro], [Vagas Disponíveis] )

Taxa de Comparecimento =
    DIVIDE ( [Reservas Realizadas], [Reservas Realizadas] + [Cancelamentos + Faltas] )

% Ociosas          = DIVIDE ( [Vagas Ociosas], [Vagas Disponíveis] )
% Cancelamento+Falta = DIVIDE ( [Cancelamentos + Faltas], [Reservas] )

-- Card adaptativo: Realizada se todo o período está no passado, senão Preenchida
Taxa de Ocupação (card) =
    VAR MaxData = MAX ( gld_ocupacao_corrente[data_referencia] )
    RETURN
        IF ( MaxData < TODAY (), [Taxa de Ocupação Realizada], [Taxa de Ocupação Preenchida] )
```

### Pasta: Meta

```dax
Meta de Ocupação = 0.75

Meta (linha do gráfico) =
    VAR TemDado =
        NOT ISBLANK ( [Reservas] ) || NOT ISBLANK ( [Vagas Disponíveis] )
    RETURN IF ( TemDado, [Meta de Ocupação] )   -- só desenha dentro do intervalo com dado (RN-06)

Gap vs Meta = [Taxa de Ocupação (card)] - [Meta de Ocupação]
```

### Pasta: Contexto

```dax
Locais = 1        -- constante até rollout multi-local (RN-09)

Dias no Período =
    CALCULATE ( DISTINCTCOUNT ( gld_ocupacao_corrente[data_referencia] ) )

Última Coleta =
    "Coleta mais recente: " & FORMAT ( MAX ( gld_ocupacao_corrente[data_extracao] ), "dd/MM/yyyy HH:mm" )
```

### Pasta: Qualidade

```dax
Alerta Status Não Mapeado =
    VAR N = SUM ( gld_ocupacao_corrente[qtd_desconhecido] )
    RETURN IF ( N > 0, "⚠ " & N & " reserva(s) com status fora do mapa de KPI" )

Dias com Canário Falho =
    CALCULATE (
        DISTINCTCOUNT ( gld_ocupacao_corrente[data_referencia] ),
        gld_ocupacao_corrente[canario_falhou] = TRUE ()
    )

Selo Provisório =
    IF (
        CALCULATE ( COUNTROWS ( gld_ocupacao_corrente ), gld_ocupacao_corrente[tem_status_provisional] = TRUE () ) > 0
            || [Dias com Canário Falho] > 0,
        "número provisório — ver docs/qualidade-dados.md"
    )
```

## 4. Perguntas de Q&A (sinônimos)

| Pergunta natural | Medida |
|---|---|
| "qual a ocupação" / "taxa de uso" | Taxa de Ocupação (card) |
| "salas vazias" / "vagas sobrando" | Vagas Ociosas / Vagas Livres |
| "faltas" / "no-show" | Cancelamentos + Faltas |
| "batemos a meta" | Gap vs Meta |
