# Regras de Negócio — BI de Ocupação de Salas

> Regras que governam os números do painel. Termos em
> [`glossario.md`](glossario.md); campos em [`dicionario-dados.md`](dicionario-dados.md);
> origem em [`linhagem.md`](linhagem.md).

## RN-01 · Papel de KPI do status

Cada `idStatusReserva` recebe um **papel de KPI** (`dim_status_kpi_role`):

| id | Status | Balde (`bucket_count_por_status`) | Papel (`papel_kpi`) | Provisório |
|---:|---|---|---|:--:|
| 1 | Reservado | `reservado` | `consome_vaga_sinalizado` | não |
| 2 | Cancelado | `cancelado` | `fora` | não |
| 3 | Check-In | `checkIn` | `ocupado` | não |
| 4 | Concluído (Check-Out) | `checkOut` | `ocupado` | não |
| 5 | No-Show | `noShow` | `fora` | não |
| 8 | No-Show Recepção | `noShow` | `fora` | **sim** |
| 9 | Removido | `cancelado` | `fora` | **sim** |

Status **fora deste mapa** → papel `desconhecido`: não entra em nenhum KPI e liga o
alerta de qualidade (ver [`qualidade-dados.md`](qualidade-dados.md) DQ-05).

## RN-02 · Contagens do fato (por sala/faixa/dia)

A view agrega as reservas da versão corrente:

| Coluna | Regra |
|---|---|
| `qtd_ocupado` | nº de reservas com papel `ocupado` (Check-In + Check-Out) |
| `qtd_consome_vaga_sinalizado` | nº com papel `consome_vaga_sinalizado` (status Reservado) |
| `qtd_fora` | nº com papel `fora` (Cancelado + No-Show + Removido) |
| `qtd_desconhecido` | nº com papel `desconhecido` (status não mapeado) — **deve ser 0** |
| `qtd_reservas` | total = soma dos quatro acima |

## RN-03 · Capacidade do dia

`capacidade_do_dia` = **override** de capacidade que cobre a data (se `ativo = 1`),
senão o `maxReservas` **base** da sala. `tem_override` sinaliza qual foi usado.

## RN-04 · Métricas de volume

| Métrica | Definição |
|---|---|
| **Vagas Disponíveis** | Σ `capacidade_do_dia` no período |
| **Reservas Realizadas** | Σ `qtd_ocupado` (Check-In + Check-Out juntos) |
| **Reservado (futuro)** | Σ `qtd_consome_vaga_sinalizado` |
| **Reservas Ativas** | Realizadas + Reservado (o que segue de pé) |
| **Cancelamentos + Faltas** | Σ `qtd_fora` (combinado) |
| **Vagas Ociosas** | `máx(Disponíveis − Realizadas, 0)` — o `máx(…,0)` protege overbooking pontual |
| **Vagas Livres** | `máx(Disponíveis − Realizadas − Reservado, 0)` |

## RN-05 · Taxa de ocupação (razão de somas)

Sempre **Σ numerador ÷ Σ denominador**, recalculada em cada nível de agregação.
**Nunca** média/soma da coluna `taxa_ocupacao` por linha (armadilha de
razão-de-médias).

| Métrica | Numerador | Denominador |
|---|---|---|
| **Taxa de Ocupação Realizada** | Σ `qtd_ocupado` | Σ `capacidade_do_dia` |
| **Taxa de Ocupação Preenchida** | Σ (`qtd_ocupado` + `qtd_consome_vaga_sinalizado`) | Σ `capacidade_do_dia` |
| **Taxa de Comparecimento** | Σ `qtd_ocupado` | Σ (`qtd_ocupado` + `qtd_fora`) |
| **% Ociosas** | Ociosas | Σ `capacidade_do_dia` |
| **% Cancelamento + Falta** | Σ `qtd_fora` | `qtd_reservas` |

**Taxa de Ocupação (card):** mostra a **Realizada** quando todo o período
selecionado está no passado; senão a **Preenchida** (agenda futura ainda vai ter
check-in).

## RN-06 · Meta de ocupação

Meta = **75%**, constante (não vem do dado). No gráfico de linha, a linha de meta só
é desenhada **dentro do intervalo de datas com dado** — não se estende sobre o
calendário vazio.

## RN-07 · Período é obrigatório

O denominador de qualquer taxa só faz sentido para dias que **aconteceram ou vão
acontecer no recorte**. Somar a janela inteira (mês vigente → futuro) mistura dias
que não ocorreram e derruba a taxa global. → **Todo visual precisa de slicer de
período.** Default útil: hoje / semana corrente.

## RN-08 · Janela forward-only

A fonte expõe `events` como array estático do mês vigente para frente. Não há
navegação por mês nem backfill. A **série histórica se acumula a partir da entrada
em produção**.

## RN-09 · Local único

O coletor fixa **um** local por Connection. `idLocal` não aparece no payload da
reserva. Card "Locais" = **1** constante até rollout multi-local.

## RN-10 · Status provisório

Os status **8** e **9** têm classificação provisória (`provisional = true`) até
validação do requerente. Toda célula que dependa deles carrega
`tem_status_provisional = true`; o número do painel sai com **selo "provisório"**.
"Removido" (9) está **provisoriamente fora** do denominador da ocupação.

## RN-11 · Privacidade

`membro.nome` e dados do contrato são removidos na ingestão (strip), antes de
qualquer persistência. `idMembro` fica como chave pseudônima opaca. O painel **não
exibe pessoas** — só agrega por sala/turno/dia/empresa.
