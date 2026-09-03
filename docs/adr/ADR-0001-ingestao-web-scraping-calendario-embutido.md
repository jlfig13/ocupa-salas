# ADR-0001 — Ingestão por web scraping de calendário embutido (exceção ao padrão API-REST)

- **Status:** 🟢 Aceito — D1–D7 decididos.
- **Contexto:** projeto BI de Ocupação de Salas. Mapeamento técnico da fonte em
  [`../mapeamento_fonte.md`](../mapeamento_fonte.md); glossário em
  [`../../CONTEXT.md`](../../CONTEXT.md).
- **Nota de portfólio:** este ADR é a reescrita, para domínio fictício, da decisão
  de arquitetura de um projeto corporativo. O padrão "fonte = API REST com token"
  citado abaixo é um padrão de referência genérico (um framework de ingestão
  orientado a catálogo); o ADR registra por que esta fonte é uma **exceção** a ele.

---

## Contexto

A fonte é o sistema **`ReservaSpace`**, aplicação server-rendered (padrão Yii2 +
jQuery). **Não existe endpoint de API para dados de ocupação.**

O que existe:

- Os dados granulares de reserva vêm **embutidos como JSON dentro de um `<script>`
  inline** na página de calendário (`GET /`), no array `events` da inicialização do
  `FullCalendar`.
- A capacidade nominal vem de `POST /painel-config/get-salas`, um por faixa de
  horário, exigindo header `X-Requested-With: XMLHttpRequest` e token CSRF lido de
  `<meta name="csrf-token">`. A lista de faixas vem de outro carregamento
  (`GET /painel-config/local?idLocal=<id>`, variável JS global `locais`).
- Autenticação é **SSO+MFA**. Não há conta de serviço registrada — login pessoal é
  o stopgap.

O framework de ingestão genérico — construído sobre "fonte = API REST com token" —
não modela esta fonte em nenhuma combinação de `auth_type` / `pagination_type`.

## Problema

Fonte que não é REST/HTTP-token exige **ADR antes da implementação**. Lacunas:

1. **Autenticação** é um cookie de sessão de browser (login SSO+MFA semi-manual) —
   não é `bearer_token`, `api_key_header` nem `basic_auth`.
2. **"Paginação"** é fatiar um array JSON de dentro de HTML — não é `page_number`
   nem `cursor`.
3. **Duas chamadas encadeadas** (`GET local` → lista de faixas → `POST get-salas`
   por faixa).
4. **Registros mutáveis re-coletados várias vezes por dia** — o modelo de
   `ON CONFLICT DO NOTHING` não versiona mudança intradiária no mesmo slot.
5. **PII pesada de terceiros** — o payload traz o cadastro completo do membro (CPF,
   RG, data de nascimento, dados pessoais sensíveis) e do contrato (CNPJ, endereço),
   replicado a cada reserva (mapeamento §4).
6. **Capacidade muda no meio do expediente** (overrides datados — mapeamento §6.3) e
   o BI precisa refletir isso durante o dia, o que conflita com um build de
   transformação único por noite.

## Decisões

### D1 — Shape da exceção

**Decisão:** estratégia especial nomeada **pelo comportamento** (`scrape_html_embutido`),
não pela fonte. Só a **extração** é especial; carga em staging, particionamento e
transformação seguem genéricos, mesmo contrato de JSONL. Novo `auth_type:
"sessao_cookie_bootstrap"`.

Neste repo de portfólio, o "shape" está materializado em:
`ocupa_salas.http_client` (encadeamento + manias), `ocupa_salas.parser` (fatiamento),
`ocupa_salas.pipeline` (colunas de rastreio + versionamento).

### D2 — Autenticação: bootstrap de sessão

**Decisão:** cookie obtido por login SSO+MFA **semi-manual** num script de browser,
executado **só no bootstrap** (não em runtime), gravado na Airflow Connection
`reservaspace_{ambiente}` (campo `Extra`, JSON). O runtime é HTTP puro: cookie
armazenado + CSRF raspado do HTML a cada execução. Health check do cookie como
**primeira task** do DAG; `401` / corpo vazio → falha alta pedindo re-bootstrap.

**Fase 1:** login pessoal. **Fase 2:** conta de bot autorizada — só troca o conteúdo
da Connection, nenhum código muda.

### D3 — Staging e idempotência

- **Grão:** uma reserva (`idReserva`). `id_origem` = `idReserva`.
- `data_particao` = `data_interval_start` da execução.
- **Versionamento por mudança:** `UNIQUE (id_origem, data_particao, hash_linha)`;
  grava **linha nova quando `hash_linha` muda**, em vez de `ON CONFLICT DO NOTHING`
  — a fonte é mutável e o histórico é o dado. Re-execução do mesmo slot é
  idempotente (mesmo hash → conflito → nada). No repo, o papel da constraint é do
  `StateStore` (`ocupa_salas.pipeline`).
- **`payload` pós-strip:** a coluna guarda o JSON **já stripado** (D5), não o cru. O
  dado sensível descartado não tem replay — por construção.
- **Tabela de bloco:** metadados da faixa + `countPorStatus`, usada como canário de
  integridade na ingestão.
- **Tabela de capacidade:** resposta de `get-salas` por faixa; grão = sala;
  `id_origem` composto `(idSala, idFaixaHorario)`; `alteraSala[]` e `postos[]` como
  JSON aninhado. Mesmo versionamento por `hash_linha`.

**O que muta num `idReserva` recoletado:** não é só o status —
`checkIn`/`checkOut` e seus `*Por`, `cancelado`/`canceladoPor`, `atendidoPor`,
`idStatusPendencia`, e em remarcação `dataReserva`/`idSala`. `atualizadoEm` é
mantido como coluna escalar — dá ao silver a melhor aproximação da hora da mudança.

**Timeline de status não é do coletor.** A fonte só expõe o status corrente +
`atualizadoEm`. A linha do tempo (`status_anterior`, `status_novo`, `mudou_em`) é um
model dedicado `slv_reservas_status_timeline`, via `lag()` sobre as linhas
versionadas ordenadas por `data_particao`.

### D4 — Cadência e frescura intradiária

**Requisito:** o BI precisa refletir o dado novo durante o expediente (~8
atualizações). **Cadência:** ~8 execuções em horário comercial, sem execução
noturna.

**Decisão:** marts intradiários como `view`, sem build de transformação
intradiário. `gld_capacidade_do_dia` e `gld_ocupacao_corrente` são
`materialized: view`, lendo direto de `stg_*`, com a resolução de versão corrente
(`row_number() over (partition by id_origem order by data_particao desc,
data_extracao desc) = 1`) inline. Cada consulta do BI reflete o último estado da
staging — a frescura vem da cadência de coleta.

Os models pesados de histórico (dimensões, fato acumulado, timeline) seguem no
build noturno.

**Recusada:** runner/pool de transformação próprio + `--select` intradiário — o
volume ínfimo torna `view` não-materializada instantânea; materializar 8×/dia é
custo sem retorno.

### D5 — PII

**Strip na ingestão**, antes de qualquer destino persistido — JSONL em disco
inclusive. O objeto `membro` inteiro **nunca** é serializado.

- **Manter:** escalares do §2.2 do mapeamento + `idMembro` (FK opaca) +
  `membro.contrato.empresa.cnpj`.
- **Descartar:** `cpf`, `rg`, `passaporte`, `dataNascimento`, `sexo`, `email`,
  `telefoneCelular`, `contatoEmergencia`, dados pessoais sensíveis
  (`necessidadesAcessibilidade`, `planoSaudeNumero`, …), endereço e razão social do
  contrato.
- **`observacao`** (texto livre) → descartar (risco de PII digitada à mão).
- **`membro.nome`** → **descartar nesta fase.** O BI é de ocupação (contagens e
  capacidade), não precisa identificar a pessoa; `idMembro` cobre qualquer join.

**Caminho futuro registrado — cifrar o nome.** Se surgir caso de uso real de exibir
nome no BI, a via é campo criptografado (Fernet reversível): chave dedicada, passo
de decriptação no consumo, trilha de auditoria. Custa uma migração de schema e não
há backfill do período em que o nome não foi coletado. **Nunca** hash para o nome —
não entrega nada que `idMembro` já não resolva.

- **Retenção:** 90 dias na `stg_*` (expurgo real por partição) + anonimização por
  `UPDATE ... SET NULL`.

### D6 — Backfill histórico

**Decisão:** **não há backfill histórico.** O coletor é forward-only desde o
primeiro ciclo. `data_particao` de cada carga é o `data_interval_start` da execução;
a série histórica se acumula a partir da entrada em produção.

**Fact-finding que fechou a questão:** a navegação de mês na tela de calendário é
**100 % client-side**. O init do FullCalendar usa `"events"` como **array literal
inline**; os botões `prev`/`next` são os nativos, sem handler que recarregue a
página nem parâmetro de data. Sem `defaultDate`, o payload é uma **janela fixa
mês-vigente→futuro**. Não existe, nesta tela, endpoint que devolva histórico.

**Validações residuais (não-bloqueantes):** fuso horário real da fonte; truncamento
do array em dias de altíssimo volume (o canário do D3 já marca a linha se ocorrer).

### D7 — Seleção de contexto de sessão (`/escolher-contexto`)

**Achado do 1º bootstrap:** com conta de serviço (acesso a vários locais), o `GET /`
autenticado **redireciona para `/escolher-contexto`**. Sem um local fixado na
sessão, nenhuma rota entrega o calendário. O `check_session` do D2 passava mesmo
assim (a tela é página normal, com as `<meta csrf-*>`) — provava "cookie vivo", não
"calendário alcançável".

**Decisão:** o coletor fixa o contexto antes do `GET /` do calendário, com **um
passo condicional**:

1. `GET /` — se o corpo traz `id="escolheLocal"`:
2. `GET /escolher-contexto` → raspa o par CSRF das `<meta>`;
3. `POST /set-contexto`, corpo `parametros={"perfil":"local","id":<id_local>}`,
   headers `X-Requested-With` + `X-CSRF-Token` (aqui o token vai **só no header**);
   resposta de sucesso é o corpo `1`;
4. repete o `GET /`.

Conta com acesso a **um único local** cai direto no calendário e o passo é pulado.
`empresa` é opcional — vira um `POST /set-contexto` extra com `perfil=empresa`
apenas se `id_empresa` estiver configurado. `check_session` passa a rodar a mesma
seleção antes de validar.

## Alternativas recusadas

| Alternativa | Por que não |
|---|---|
| Endpoints Pjax | `500`/`503` consistente |
| Browser headless em runtime | Dependência pesada e frágil; usado só no bootstrap |
| Persistir o objeto `membro` inteiro em staging temporária | Amplia a superfície de dado de terceiros |
| `--select` por fonte / runner intradiário (D4) | Volume ínfimo torna `view` instantânea |
| Backfill por varredura mês a mês em `GET /` (D6) | A tela não navega mês por HTTP |
| Fixar local por query param em vez de `POST /set-contexto` (D7) | Todas as rotas redirecionam até o contexto entrar na sessão pelo `POST` |

## Consequências

- Primeiro `auth_type` e primeira estratégia de scraping — nova superfície de
  manutenção: o parser fica acoplado ao markup e quebra em silêncio se o HTML mudar.
  Mitigação: checagem de schema no parse + alerta.
- Teste unitário do `auth_type` novo obrigatório no mesmo PR.
- Bootstrap manual recorrente enquanto não houver conta de bot.
- Os marts `view` do D4 fazem parsing/tipagem/resolução de versão corrente em tempo
  de consulta. Aceitável pelo volume; revisitar se o BI expandir para múltiplos
  locais.
- A exposição de dado de terceiros pelo fornecedor é **anterior e independente**
  deste ETL — vira registro formal de governança à parte.
