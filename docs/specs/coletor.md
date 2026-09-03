# Spec — Coletor de Ocupação de Salas

> Design/contexto: [`../../CONTEXT.md`](../../CONTEXT.md),
> [`../mapeamento_fonte.md`](../mapeamento_fonte.md),
> [`../adr/ADR-0001`](../adr/ADR-0001-ingestao-web-scraping-calendario-embutido.md).

## Problem Statement

O BI de Ocupação de Salas precisa de dados granulares de reserva e de capacidade
nominal por faixa de horário. O sistema de origem (`ReservaSpace`) **não expõe
API**: o que existe está embutido como JSON num `<script>` da tela de calendário, e
a capacidade só vem por um POST autenticado com exigências não-óbvias (header
`X-Requested-With`, token CSRF do DOM). A extração manual não escala e não sustenta
um BI atualizado várias vezes ao dia. Além disso, o payload devolve o cadastro
completo do membro e do contrato replicado a cada reserva — dado sensível de
terceiros que não pode ser persistido.

## Solution

Um coletor automatizado, rodando como fonte de **estratégia especial** (não cabe no
framework REST genérico), que:

- autentica por um **cookie de sessão** obtido num bootstrap semi-manual de login
  SSO+MFA, guardado em Airflow Connection;
- a cada ~90 min em horário comercial, baixa a página de calendário, **fatia o array
  `events`** e busca a capacidade por faixa;
- **descarta todos os campos sensíveis na ingestão**, antes de qualquer
  persistência, mantendo só os escalares + `idMembro` + `cnpj_empresa`;
- grava **snapshots versionados** (linha nova quando o conteúdo muda);
- expõe ao BI **marts intradiários como `view`** e **models de histórico** no build
  noturno.

## User Stories

1. Como analista de BI, quero a taxa de ocupação por faixa e por sala, para enxergar
   capacidade ociosa.
2. Como analista de BI, quero que "capacidade do dia" respeite os overrides datados,
   para não comparar realizado contra uma capacidade base que ninguém usa.
3. Como analista de BI, quero a ocupação do dia corrente atualizada durante o
   expediente.
4. Como analista de BI, quero uma dimensão de status estável para agrupar KPIs.
5. Como analista de BI, quero distinguir reserva que "consome vaga" de reserva que
   não consome.
6. Como analista de BI, quero uma linha do tempo de status por reserva, para medir
   lead time e permanência.
7. Como gestor de agenda (requerente), quero tratamento definido para "Removido" e
   "No-Show Recepção".
8. Como engenheiro de dados, quero que o coletor rode como uma fonte a mais,
   seguindo o catálogo e a carga genérica.
9. Como engenheiro de dados, quero a lógica especial isolada num módulo nomeado pelo
   comportamento (fatiamento de HTML embutido).
10. Como engenheiro de dados, quero um cabeçalho de proveniência em cada módulo.
11. Como operador, quero que a primeira task da DAG verifique o cookie e falhe alto
    quando ele expirar.
12. Como operador, quero `200` com corpo vazio tratado como erro explícito.
13. Como operador, quero retry com backoff em falha transitória, alerta só após
    esgotar as tentativas.
14. Como operador, quero idempotência por `data_particao` + hash.
15. Como operador, quero um canário de integridade (contagem calculada ×
    `countPorStatus`).
16. Como operador, quero o parser falhando com mensagem clara quando o HTML mudar de
    forma.
17. Como responsável por privacidade, quero garantia de que CPF, RG, data de
    nascimento, dados pessoais sensíveis, e-mail e telefone **nunca** são escritos
    em disco nem em tabela.
18. Como responsável por privacidade, quero o nome do membro descartado nesta fase,
    com um caminho documentado (campo criptografado) caso o BI precise exibir nome.
19. Como responsável por privacidade, quero a staging herdando retenção (expurgo por
    partição, anonimização por `UPDATE SET NULL`).
20. Como engenheiro de dados, quero o `payload` gravado já sem os campos sensíveis.
21. Como analista de BI, quero um backfill de histórico no primeiro carregamento.
    **(Não atendível — ADR-0001 D6: a fonte não expõe histórico por scraping.
    Forward-only.)**
22. Como engenheiro de dados, quero a capacidade por faixa coletada no mesmo ciclo
    da reserva (overrides podem ser cadastrados no meio do expediente).
23. Como analista de BI, quero o CNPJ da empresa contratante no modelo, para cruzar
    ocupação por empresa.
24. Como engenheiro de dados, quero o teto no nível do posto modelado separado do
    teto da sala, até a regra de combinação ser observada.

## Implementation Decisions

**Forma da integração (ADR-0001 D1).** Estratégia especial nomeada pelo
comportamento; só a extração é especial. Novo `auth_type:
"sessao_cookie_bootstrap"`.

**Autenticação (D2).** Cookie de bootstrap semi-manual na Connection
`reservaspace_{ambiente}`. Runtime HTTP puro: cookie + CSRF do `<meta>`. Header
`X-Requested-With` obrigatório nos POST.

**Extração.** Chamadas encadeadas:
0. **Seleção de contexto (condicional — D7).** Se o `GET /` cai em
   `/escolher-contexto` (marcador `id="escolheLocal"`): `GET /escolher-contexto` p/
   CSRF → `POST /set-contexto` (`parametros={"perfil":"local","id":<id_local>}`,
   CSRF só no header) → repete `GET /`. `id_empresa` → POST extra.
1. `GET /` → fatiar `events` → reservas + metadados de bloco. Linhas
   `nonstandard.primeiroDoDia: true` ignoradas.
2. `GET /painel-config/local?idLocal=<id>` → lista de `idFaixaHorario` do global
   `locais` → para cada faixa, `POST /painel-config/get-salas`.

**Strip de PII (D5).** Em memória, antes de qualquer escrita. Whitelist-only. O
objeto `membro` inteiro nunca é serializado.

**Schema e staging (D3).** `stg_reservas` (grão = uma reserva),
`stg_reservas_bloco` (metadados + `countPorStatus`), `stg_capacidade` (resposta de
`get-salas`; grão = sala; `id_origem` composto). Colunas de rastreio padrão.
`data_particao` = `data_interval_start`.

**Idempotência (D3).** `UNIQUE (id_origem, data_particao, hash_linha)`; grava linha
nova quando `hash_linha` muda. O `payload` gravado é o pós-strip.

**Cadência (D4).** ~8 execuções em horário comercial, sem execução noturna. Reserva
e capacidade no mesmo ciclo.

**Camadas de transformação.**
- Bronze/Silver/Gold **tabela** (dimensões, fato acumulado,
  `slv_reservas_status_timeline`, `capacidade_sala_dia`, `capacidade_posto_dia`): no
  build noturno.
- Gold **`view`** intradiário (`gld_capacidade_do_dia`, `gld_ocupacao_corrente`): lê
  `stg_*` direto, resolve versão corrente inline, não materializa.

**Papel de KPI (provisório).** `dim_status_kpi_role` marcando cada status como
"ocupado" / "consome vaga sinalizado" / "fora", com `provisional = true` até
validação. Default: ocupado = {Check-In (3), Concluído (4)}; fora = {Cancelado (2),
No-Show (5), No-Show Recepção (8), Removido (9)}.

**Canário de integridade.** Na ingestão, contagem por bucket derivada de `reservas[]`
× `countPorStatus`; divergência gera alerta sem bloquear (linha marcada).

## Testing Decisions

**Seam 1 — parser + strip** (`tests/test_parser.py`, `test_strip.py`, sem rede).
Entrada: fixtures de HTML sintético (dia normal, alto volume, mês vazio, canário
divergente). Asserções: campos da whitelist presentes; **nenhum** campo sensível;
`countPorStatus` por bloco; linhas `primeiroDoDia` ignoradas; `hash_linha` estável
para conteúdo igual e diferente para conteúdo alterado; erro claro quando uma chave
some.

**Seam 2 — cliente HTTP** (`tests/test_http_client.py`, respostas stub).
`X-Requested-With` ausente → `200` vazio como erro; cookie inválido → `401` faz o
health check falhar alto; CSRF do `<meta>` no corpo e no header; retry/backoff;
encadeamento; **seleção de contexto (D7)**.

**Ponta a ponta** (`tests/test_mock_server.py`). O coletor roda contra o
`mock_server` via `TestClient` — encadeamento completo, strip verificado, canário
saudável, versionamento idempotente.

## Out of Scope

- **Múltiplos locais.** Fase atual é local único.
- **Automação do login SSO+MFA sem intervenção.**
- **Fechamento das fórmulas de KPI** (status 8/9 provisórios).
- **Regra de combinação entre teto de sala e teto de posto.**
- **Backfill histórico** (ADR-0001 D6).
