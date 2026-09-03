# Dicionário de Dados — BI de Ocupação de Salas

> Campos das camadas do pipeline. Regras em [`regras-negocio.md`](regras-negocio.md);
> origem em [`linhagem.md`](linhagem.md).

## 1. Saída do coletor — `reservas.jsonl` (pós-strip)

Uma linha por versão de reserva.

| Coluna | Tipo | Origem | Nota |
|---|---|---|---|
| `fonte` | str | coletor | constante `"reservaspace"` |
| `id_origem` | str | `payload.idReserva` | grão |
| `data_particao` | date | execução | `data_interval_start` |
| `data_extracao` | timestamptz | coletor | instante do snapshot |
| `hash_linha` | str(64) | `ocupa_salas.hashing` | SHA-256 do payload canônico |
| `payload` | json | fonte, pós-strip | ver 1.1 |

### 1.1 `payload` da reserva (pós-strip)

| Campo | Tipo | Nota |
|---|---|---|
| `idReserva` | int | PK |
| `idMembro` | int | FK opaca (pseudônimo) — **sem nome** |
| `cnpj_empresa` | str | derivado de `membro.contrato.empresa.cnpj` |
| `idStatusReserva` | int | FK dimensão de status |
| `idStatusPendencia` | int/null | quando "Concluído com Pendência" |
| `idSala` / `idPostoLocal` / `idFaixaHorario` | str | FKs de capacidade (`idFaixaHorario` pode ser null) |
| `idSalaReserva` | int | agrupador (uso não confirmado) |
| `dataReserva` | str (ISO offset) | horário marcado |
| `dataCriacaoReserva` | str | criação do registro |
| `atualizadoEm` / `atualizadoPor` | str | auditoria — `atualizadoEm` = dica de hora da mudança |
| `checkIn` / `checkOut` | str/null | timestamps |
| `checkInPor` / `checkOutPor` | str/null | id do usuário |
| `cancelado` | int (0/1) | flag |
| `canceladoPor` / `atendidoPor` | str/null | id do usuário |
| `idReservadoPor` | str | id do usuário que reservou |

**Removidos no strip (nunca em disco):** todo o objeto `membro` exceto `idMembro` e
`contrato.empresa.cnpj`; `observacao`; todos os campos de
[`FORBIDDEN_PII_FIELDS`](../src/ocupa_salas/strip.py).

## 2. Saída do coletor — `capacidade.jsonl`

Uma linha por sala × faixa.

| Campo do `payload` | Tipo | Nota |
|---|---|---|
| `idSala` | str | PK (com `idFaixaHorario`) |
| `idFaixaHorario` | str | |
| `maxReservas` | str→int | capacidade base da sala |
| `nome` | str | `<SALA>_<TURNO>` (rótulo — não é PII; renomeado para `nomeSala` nas fixtures) |
| `alteraSala[]` | json | overrides datados: `dataInicio`, `dataFim`, `maxReserva`, `ativo` |
| `postos[]` | json | `idPostoLocal`, `maxReservas` (0 = sem teto de posto), `peso` |

## 3. Camada gold — `gld_ocupacao_corrente` (view, DirectQuery)

Grão: **(`data_referencia`, `faixa_horario_sk`, `sala_sk`)**.

| Coluna | Tipo | Regra |
|---|---|---|
| `data_referencia` | date | data (sem hora) da reserva no fuso local |
| `sala_sk` / `faixa_horario_sk` | int | surrogates |
| `nome_sala` / `turno` | str | de `dim_sala` |
| `capacidade_do_dia` | int | RN-03 |
| `tem_override` | bool | RN-03 |
| `qtd_ocupado` | int | RN-02 |
| `qtd_consome_vaga_sinalizado` | int | RN-02 |
| `qtd_fora` | int | RN-02 |
| `qtd_desconhecido` | int | RN-02 — deve ser 0 |
| `qtd_reservas` | int | soma |
| `tem_status_provisional` | bool | RN-10 |
| `canario_falhou` | bool | dia com truncamento suspeito |

## 4. Medidas do BI (resumo)

Organizadas em 5 pastas: **Volume**, **Taxas**, **Meta**, **Contexto**, **Qualidade**.
Definições completas em [`bi/camada-semantica.md`](bi/camada-semantica.md). Todas as
taxas seguem RN-05 (razão de somas). Sinônimos para Q&A: "ocupação" → Taxa de
Ocupação; "salas vazias" → Vagas Ociosas; "faltas" → Cancelamentos + Faltas.
