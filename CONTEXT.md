# ocupa-salas — Coletor de Ocupação de Salas

Contexto do pipeline que extrai dados de reserva e capacidade de uma plataforma
fictícia de reserva de salas (`ReservaSpace`) e os modela em camadas medallion
(raw → gold) para um BI de Ocupação de Salas. Fase atual: **local único**.

> A fonte é simulada por [`mock_server/`](mock_server/). Nenhuma informação real.

## Language

### Fonte

**Reserva**:
Registro atômico de um horário marcado por um membro para uma sala, identificado por `idReserva`. É o grão da tabela-fato.
_Evitar_: agendamento, booking, marcação.

**Bloco de horário**:
Faixa de horário de um dia específico (ex. "08:00 - 12:00"), item do array `events` da tela de calendário. Contém a lista de reservas daquele intervalo.
_Evitar_: evento (colide com o array `events` da fonte), slot.

**Faixa de Horário**:
Unidade de configuração da agenda pela qual a capacidade é consultada, identificada por `idFaixaHorario`. Um local tem várias faixas (ex. MANHÃ, TARDE).
_Evitar_: turno, período, janela.

**Sala**:
Espaço reservável dentro de uma faixa que carrega a capacidade nominal (`maxReservas` base) e a lista de postos de trabalho. Alvo do endpoint `get-salas`. Formato do nome: `<SALA>_<TURNO>`.
_Evitar_: grupo, recurso.

**Posto de trabalho**:
Estação individual dentro de uma sala (`idPostoLocal`). Pode ter teto próprio (`maxReservas ≠ 0`) ou não (`= 0` → capacidade resolvida no nível da sala).

**Override de capacidade**:
Exceção datada (`alteraSala`) que substitui o `maxReservas` base da sala durante um intervalo de datas, quando `ativo = 1`.
_Evitar_: alteração, ajuste, exceção.

**Capacidade do dia**:
A capacidade vigente resolvida para uma data específica: o override que cobre a data (se ativo), senão o `maxReservas` base da sala.

**Status da Reserva**:
Dimensão do ciclo de vida da reserva (`idStatusReserva`). IDs 1–5, 8 e 9 observados; 6 e 7 não confirmados.

**Local**:
Endereço físico do coworking cujas agendas são coletadas. Escopo desta fase: apenas o local `1` ("Coworking Central").
_Evitar_: unidade, filial, sede.

**Membro**:
Pessoa com plano ativo na plataforma, geralmente vinculada a uma empresa contratante (plano corporativo). A fonte devolve o cadastro completo do membro por reserva — ver Strip.
_Evitar_: usuário, cliente, funcionário.

### Pipeline

**Snapshot**:
Uma extração completa da janela de `events` em um instante, marcada com `data_extracao`. As linhas raw são append-only — nunca atualizadas nem deletadas.
_Evitar_: carga, batch, extração (quando referindo-se ao artefato datado).

**Strip**:
Remoção, no momento da ingestão e antes de qualquer persistência (inclusive staging), dos campos sensíveis aninhados do objeto `membro` e do contrato. Inclui `membro.nome` — descartado nesta fase; cifrar (Fernet) é o caminho futuro registrado se o BI precisar exibir nome (ADR-0001 D5).
_Evitar_: limpeza, filtro, anonimização.

**Bootstrap de sessão**:
Login SSO+MFA semi-manual, feito por um humano, que produz o cookie autenticado reutilizável gravado na Airflow Connection. As execuções do coletor reaproveitam esse cookie. Contra o `mock_server` não há login.
_Evitar_: autenticação, login (quando referindo-se especificamente a esse passo manual).

**Campo pseudônimo**:
Chave que identifica indiretamente a pessoa sem expor dado sensível — aqui, `idMembro` mantido como FK opaca.

**Compactação por hash**:
Regra de ingestão que só grava uma linha raw nova quando o `hash_linha` dos campos da whitelist difere do último registrado para aquele `idReserva`. Mantém histórico, elimina snapshots idênticos, preserva o append-only.
_Evitar_: dedup, deduplicação, CDC.

**Canário de integridade**:
Asserção, na ingestão, de que a contagem por status calculada de `reservas[]` bate com `nonstandard.countPorStatus` do bloco. Divergência sinaliza truncamento silencioso do array. O `countPorStatus` é chaveado por **bucket de workflow** (`reservado`, `cancelado`, `checkIn`, `checkOut`, `noShow`, `pendencia`), não por `idStatusReserva` — a comparação traduz id→bucket pelo mapa provisório `STATUS_ID_TO_BUCKET` (`ocupa_salas.canary`), no qual `9` ("Removido") cai em `cancelado`.
_Evitar_: countPorStatus por id, rótulo de status.

### Modelagem

**Papel de KPI**:
Classificação de cada status para efeito de cálculo da ocupação: "ocupado" (entra no numerador), "consome vaga sinalizado", ou "fora". Definida na tabela `dim_status_kpi_role`, hoje provisória (`provisional = true`) até validação do requerente.

**Taxa de ocupação**:
KPI central: reservas com papel "ocupado" sobre a `capacidade_do_dia` da sala. "Removido" provisoriamente fora do denominador.

**capacidade_sala_dia**:
Linha silver com a capacidade resolvida no nível da sala para uma data (regra do override datado, senão base).

**capacidade_posto_dia**:
Linha silver com o teto no nível do posto para uma data, quando `posto.maxReservas ≠ 0`. Mantida separada de `capacidade_sala_dia` — a regra de combinação entre as duas ainda não foi observada.

**Timeline de status**:
Model silver (`slv_reservas_status_timeline`) que deriva `status_anterior` → `status_novo` e `mudou_em` a partir das linhas versionadas da staging, via `lag()` ordenado por `data_particao`. O coletor não produz isso — a fonte só expõe o status corrente, nunca o histórico.
_Evitar_: histórico de status, trilha de status.

**Mart intradiário**:
Model gold `materialized: view` (`gld_capacidade_do_dia`, `gld_ocupacao_corrente`) que lê direto da `stg_*` e resolve a versão corrente de cada reserva em tempo de consulta. Não materializa, então reflete a última coleta sem depender do build noturno — é o que dá frescura intradiária ao BI (ADR-0001 D4).
_Evitar_: view ao vivo, mart em tempo real.

**data_referencia**:
Data (sem hora) da reserva no fuso local, derivada explicitamente no silver a partir do timestamp com offset. Chave dos joins de intervalo de capacidade e do grão diário de ocupação.

**Backfill**:
Não há. Descartado no ADR-0001 D6: a tela de calendário não navega mês por HTTP — `events` é array estático forward-only, sem parâmetro de data. O coletor é **forward-only** desde o primeiro ciclo; a série histórica se acumula a partir da entrada em produção, com `data_particao` = `data_interval_start` da execução.
_Evitar_: carga histórica, recarga.
