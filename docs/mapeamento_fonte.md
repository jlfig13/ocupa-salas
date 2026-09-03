# Mapeamento de Dados — Fonte fictícia `ReservaSpace`

> Projeto: BI de Ocupação de Salas (estudo / portfólio)
> Escopo desta fase: local único "Coworking Central"
> A fonte é simulada por [`mock_server/`](../mock_server/). Este documento descreve a
> fonte **como se tivesse sido levantada via DevTools** — é o artefato de
> engenharia reversa que o projeto original produziu, reescrito para o domínio
> fictício.

---

## 1. Resumo do achado

O sistema **não expõe endpoint de API para dados de ocupação**. É uma aplicação
server-rendered (padrão Yii2 + jQuery). Os dados granulares de reserva, no entanto,
**estão embutidos como JSON dentro de um `<script>` inline** na página de calendário
(`GET /`), na chamada de inicialização do plugin `FullCalendar`:

```js
jQuery('#calendarioReservas').fullCalendar({
  ...
  "events": [ ... ]
})
```

Isso muda a estratégia de coleta: em vez de parsear a tabela HTML ou depender de
endpoints Pjax (instáveis), o coletor **extrai e parseia apenas o array `events`** de
dentro do HTML retornado.

---

## 2. Estrutura dos dados

### 2.1 Nível "bloco de horário" (item do array `events`)

Cada item representa uma faixa de horário (ex.: "08:00 - 12:00") de um dia. Contém
metadado do bloco e, dentro de `nonstandard.reservas`, a lista de reservas
individuais daquela faixa.

Campos relevantes do bloco:

- `id` — pode ser `null` (primeiro item de cada dia, placeholder/cabeçalho —
  **ignorar no parsing**, identificável por `nonstandard.primeiroDoDia: true`)
- `title` — string do horário, ex. `"08:00 - 12:00"`
- `start`, `end` — timestamps do bloco
- `nonstandard.reservas` — array de reservas (ver 2.2)
- `nonstandard.countPorStatus` — contagem pré-agregada **por bucket de workflow**
  (`reservado`/`cancelado`/`checkIn`/`checkOut`/`noShow`/`pendencia`). Usado como
  canário de integridade, não como fonte primária de KPI.

### 2.2 Nível "reserva" (item de `nonstandard.reservas`)

Grão mais fino disponível — um registro por reserva individual.

**Campos escalares (manter — usar para o modelo de dados):**

| Campo | Descrição |
|---|---|
| `idReserva` | PK da reserva |
| `idSalaReserva` | agrupador (uso ainda não confirmado) |
| `idMembro` | FK para membro — **extrair só o id**, ver 2.3 |
| `idStatusReserva` | FK para status (dimensão mapeada, seção 3) |
| `idStatusPendencia` | FK para pendência, quando status = "Concluído com Pendência" |
| `idPostoLocal` | FK posto de trabalho |
| `idSala` | FK sala |
| `idFaixaHorario` | FK faixa de horário (pode vir `null` no payload do calendário) |
| `dataReserva` | timestamp com offset da reserva |
| `idReservadoPor` | id do usuário que reservou |
| `dataCriacaoReserva` | timestamp de criação do registro |
| `observacao` | texto livre (pode ser null) — **descartado no strip** |
| `atualizadoPor` / `atualizadoEm` | auditoria — `atualizadoEm` é mantido |
| `checkIn` / `checkOut` | timestamps, null se não ocorreu |
| `checkInPor` / `checkOutPor` | id do usuário |
| `cancelado` / `canceladoPor` | flag e auditoria de cancelamento |
| `atendidoPor` | id do responsável pelo atendimento |

**Campos aninhados — ⚠️ tratamento especial (ver seção 4):**
`membro`, `sala`, `statusReserva`, `statusPendencia`.

### 2.3 Objeto `membro` (aninhado)

Traz o cadastro **completo** do membro, não apenas identificação — incluindo
`contrato` e `contrato.empresa` aninhados (3 níveis). Contém CPF, RG, data de
nascimento, e dados pessoais sensíveis (necessidades de acessibilidade, número de
plano de saúde, contato de emergência).

Ponto positivo: `membro.contrato.empresa.cnpj` já vem no payload — resolve, sem
integração externa, o cruzamento de ocupação por empresa contratante.

---

## 3. Dimensão de status (`idStatusReserva`)

Extraída por varredura de uma amostra de reservas:

| id | nomeStatus | bucket `countPorStatus` (provisório) |
|---|---|---|
| 1 | Reservado | `reservado` |
| 2 | Cancelado | `cancelado` |
| 3 | Check-In | `checkIn` |
| 4 | Concluído (Check-Out) | `checkOut` |
| 5 | No-Show | `noShow` |
| 8 | No-Show Recepção | `noShow` (a confirmar) |
| 9 | Removido | `cancelado` (verificado empiricamente) |
| — | Concluído com Pendência | `pendencia` (nenhum id observado alimentando) |

**Sobre `countPorStatus`:** vem como mapa `{bucket: n}` chaveado por **bucket de
workflow**, não por `idStatusReserva`. O canário (`ocupa_salas.canary`) traduz
id→bucket por `STATUS_ID_TO_BUCKET` antes de comparar.

**Pendências:** IDs **6 e 7 não observados** — testar com outra amostra antes de
fechar a dimensão. "No-Show Recepção" (8) e "Removido" (9) precisam de definição
operacional confirmada pelo requerente — em especial se "Removido" entra ou não no
denominador de capacidade.

---

## 4. Governança e privacidade — achado crítico

O payload de `events` expõe, em cada reserva, o cadastro completo do membro (CPF,
RG, data de nascimento, dados pessoais sensíveis) e do contrato (CNPJ, endereço),
**replicado a cada ocorrência**.

**Origem dos dados:** vários campos do objeto `membro` trazem sufixo `Crm`
(`setorCodCrm`, `centroCustoCodCrm`, `codMembroCrm`, `id_contrato_crm`, …) — indício
de que o cadastro não é nativo da plataforma de reserva, e sim **replicado de um CRM
corporativo a montante**. A superfície de exposição é maior do que "só este sistema".

**Campos sensíveis expostos por reserva** (dentro de `membro`):

| Categoria | Campos |
|---|---|
| Identificação pessoal | `cpf`, `rg`, `passaporte`, `dataNascimento`, `sexo` |
| Contato pessoal | `email`, `telefoneCelular`, `contatoEmergencia` |
| Vínculo contratual | `matriculaContrato`, `dataAdesao`, `dataEncerramento`, `categoriaPlano` |
| Dado pessoal sensível | `necessidadesAcessibilidade`, `restricaoMobilidade`, `preferenciasAlimentares`, `planoSaudeNumero` |
| Contrato / empresa | `contrato.cnpj`, `contrato.razaoSocial`, `contrato.endereco`, `contrato.empresa.cnpj`, `contrato.empresa.razaoSocial` |

**Controle de acesso:** não há segregação além do **login** — qualquer usuário
autenticado consegue consultar o cadastro completo de qualquer membro. Sem
mascaramento de campo, sem log de auditoria de consulta.

**Ação — em duas frentes:**

1. **Coletor:** extrair apenas os escalares da seção 2.2. Dos aninhados, no máximo
   `membro.idMembro` e `membro.contrato.empresa.cnpj` — nunca serializar ou
   persistir o objeto `membro` inteiro, nem temporariamente. (Implementado em
   `ocupa_salas.strip`, whitelist-only.)
2. **Fora do escopo, a reportar:** o volume de dado sensível devolvido por uma tela
   de calendário, somado à ausência de controle de acesso, é exposição
   desnecessária do sistema fornecedor. Vale registro formal ao responsável pela
   plataforma e à área de privacidade.

---

## 5. Notas técnicas adicionais

- **Peso do payload:** a maior parte do peso do `GET /` está nos objetos aninhados
  (seção 4), não no volume de reservas. Após o strip, o dado útil cai para poucas
  dezenas de KB.
- **Pjax não confiável:** endpoints Pjax retornam `500`/`503` de forma consistente.
  Não usar como via principal.
- **Autenticação:** login via SSO+MFA. O bootstrap de sessão é semi-manual e produz
  um cookie reutilizável (ADR-0001 D2).

## 5.1 Seleção de contexto — `/escolher-contexto` + `/set-contexto`

**Achado do 1º bootstrap contra produção.** Com uma conta de serviço (acesso a mais
de um local), o `GET /` autenticado **redireciona para `/escolher-contexto`** — tela
"Selecione um Local / Selecione uma Empresa". Enquanto a sessão não tem um local
fixado, **nenhuma rota entrega o calendário**.

`/escolher-contexto` é página normal: **200**, com o par CSRF nas `<meta>`. Cada
`<select>` (`#escolheLocal`, `#escolheEmpresa`) dispara a mesma chamada:

```
POST /set-contexto
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest      ← obrigatório
X-CSRF-Token: <token>                  ← token do meta csrf-token de /escolher-contexto

Body:
  parametros = {"perfil":"local","id":"1"}   (JSON stringificado; "empresa" para o filtro de empresa)
```

⚠️ Aqui o token CSRF vai **só no header** `X-CSRF-Token` — diferente de
`/painel-config/get-salas` (§6.1), onde vai também no corpo.

**Resposta:** `200`, corpo = **`1`** (dígito único). **Sem `Set-Cookie`** — o
contexto é gravado server-side contra a sessão. `GET /` seguinte entrega o
calendário.

**Regras para o coletor:**

- **`empresa` é opcional.** Local sozinho libera o calendário. `id_empresa` só entra
  se um recorte por empresa for necessário.
- **Passo condicional.** Conta com acesso a **um único local** cai direto no
  calendário. O coletor decide pelo corpo do `GET /`: se contém `id="escolheLocal"`,
  roda a seleção e repete o `GET /`.
- **CSRF por sessão/deploy** — sempre raspar do `<meta>`, nunca fixar.

---

## 6. Endpoint de capacidade — `/painel-config/get-salas`

Fonte da **capacidade nominal** (denominador da taxa de ocupação). Não vem embutido
no carregamento inicial — é buscado sob demanda, por faixa de horário, via POST
autenticado.

### 6.1 Requisição

```
POST /painel-config/get-salas
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest      ← obrigatório
X-CSRF-Token: <token>                  ← obrigatório

Body:
  parametros      = {"idFaixaHorario":"1071"}   (JSON stringificado)
  <csrf-param>    = <token>                       (nome do campo vem do meta csrf-param)
```

⚠️ Sem o header `X-Requested-With`, o servidor responde **200 OK com corpo vazio** —
sem erro explícito. Tratado como `EmptyBodyError`.

`idFaixaHorario` vem do array `locais[].faixaHorarios[]`, embutido no carregamento de
`GET /painel-config/local?idLocal=<id>` (variável JS global `locais`).

### 6.2 Estrutura da resposta

```json
[
  {
    "idSala": "401",
    "maxReservas": "8",
    "nome": "SALA FOCO 01_MANHA",
    "idFaixaHorario": "1071",
    "alteraSala": [
      { "idAlteraSala": "4", "maxReserva": "16", "dataInicio": "2026-08-14", "dataFim": "2026-08-14", "ativo": "1" }
    ],
    "postos": [
      { "idPostoLocal": "401P1", "nomeProc": "Estação de trabalho", "maxReservas": "0", "peso": "1", "ativo": "1" }
    ]
  }
]
```

### 6.3 ⚠️ Achado crítico — capacidade não é fixa, é regra + exceção por data

`maxReservas` da **sala** tem um valor base, mas `alteraSala` traz **overrides por
intervalo de datas** aplicados manualmente. A capacidade do dia **não é um valor
único por sala/faixa** — é resolvida em tempo de consulta: se existe um item em
`alteraSala` cobrindo a data (`dataInicio ≤ dia ≤ dataFim` e `ativo = 1`), usa
`maxReserva` dele; senão, usa `maxReservas` base.

`postos[].maxReservas = "0"` significa "capacidade não fixa no nível do posto" — a
resolução vem inteira da regra acima. Quando `≠ 0`, o valor limita o posto
especificamente (regra de combinação com o teto da sala a confirmar).

### 6.4 Frequência de coleta

Este endpoint entra **no mesmo ciclo** do fato de reserva, porque os overrides de
`alteraSala` podem ser cadastrados no meio do expediente.

---

## 7. Próximos passos

1. Confirmar destino dos status 6/7 e a definição operacional de 8 e 9.
2. Confirmar truncamento do array `reservas` em dias de altíssimo volume (o canário
   marca a linha se ocorrer).
3. Confirmar o fuso real da fonte contra um `start` conhecido.
4. Testar sala com mais de um posto com `maxReservas ≠ 0` simultâneo.
