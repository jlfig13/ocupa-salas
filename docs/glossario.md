# Glossário — BI de Ocupação de Salas

> Vocabulário de negócio. O modelo de domínio completo (com termos a evitar) está em
> [`../CONTEXT.md`](../CONTEXT.md); aqui é a versão de consulta rápida.

## Domínio

| Termo | Definição |
|---|---|
| **Reserva** | Horário marcado por um membro para uma sala, identificado por `idReserva`. Grão da tabela-fato. |
| **Bloco de horário** | Faixa de horário de um dia (ex.: "08:00 - 12:00"), item do array `events` da tela de calendário. |
| **Faixa de Horário** | Unidade de configuração da agenda pela qual a capacidade é consultada (`idFaixaHorario`). Um local tem várias (ex.: MANHÃ, TARDE). |
| **Sala** | Espaço reservável dentro de uma faixa que carrega a capacidade nominal e a lista de postos. Nome: `<SALA>_<TURNO>`. |
| **Turno** | Sufixo do nome da sala: `MANHA` ou `TARDE`. |
| **Posto de trabalho** | Estação individual dentro de uma sala. |
| **Local** | Endereço físico do coworking cujas agendas são coletadas. Fase atual: um só. |
| **Capacidade nominal** | `maxReservas` base da sala. |
| **Override de capacidade** | Exceção datada que substitui a capacidade base num intervalo, quando `ativo = 1`. |
| **Capacidade do dia** | Capacidade vigente resolvida para uma data: override que cobre a data (se ativo), senão a base. |
| **Empresa contratante** | Organização com plano corporativo à qual o membro está vinculado. `cnpj` disponível no payload. |

## Ciclo de vida da reserva

| Termo | Definição |
|---|---|
| **Reservado** | Status 1. Horário marcado, ainda não aconteceu. Consome vaga. |
| **Check-In** | Status 3. Membro chegou / uso em curso. Conta como ocupado. |
| **Concluído (Check-Out)** | Status 4. Uso concluído. Conta como ocupado. |
| **Cancelado** | Status 2. Reserva desfeita antes de acontecer. |
| **No-Show** | Status 5 (e "No-Show Recepção", 8). Falta — o membro não apareceu. |
| **Removido** | Status 9. Retirado da agenda. Classificação provisória. |
| **Concluído com Pendência** | Status possível no sistema, ainda não observado no dado. |

## KPIs e métricas

| Termo | Definição |
|---|---|
| **Papel de KPI** | Classificação do status para o cálculo: `ocupado`, `consome_vaga_sinalizado` ou `fora`. |
| **Ocupado** | Reserva que entra no numerador da ocupação (Check-In + Check-Out). |
| **Taxa de ocupação** | Reservas ocupadas ÷ capacidade do dia, como razão de somas. KPI central. |
| **Taxa de ocupação realizada** | Só o que já aconteceu (ocupado ÷ capacidade). |
| **Taxa de ocupação preenchida** | O que aconteceu + o que está reservado ÷ capacidade. "Quão cheia está a agenda". |
| **Taxa de comparecimento** | Realizados ÷ (realizados + cancelados/faltas). |
| **Vagas ociosas** | Capacidade que não virou uso realizado. |
| **Vagas livres** | Capacidade menos realizado menos reservado futuro. |
| **Meta de ocupação** | Limiar fixo de 75%, do requerente — não vem do dado. |
| **Reservas ativas** | Realizados + reservado futuro (o que segue de pé). |

## Pipeline e qualidade

| Termo | Definição |
|---|---|
| **Snapshot** | Extração completa da janela `events` num instante (`data_extracao`). Linhas raw append-only. |
| **Strip** | Remoção dos campos sensíveis (incl. `membro.nome`) na ingestão, antes de qualquer persistência. |
| **Bootstrap de sessão** | Login SSO+MFA semi-manual, feito por humano, que gera o cookie autenticado reutilizável. |
| **Compactação por hash** | Só grava linha raw nova quando o `hash_linha` dos campos-chave difere do último para aquele `idReserva`. |
| **Canário de integridade** | Asserção de que a contagem por status calculada bate com `nonstandard.countPorStatus` do bloco. Divergência = possível truncamento silencioso do array. |
| **Mart intradiário** | Model gold `materialized: view` que lê a staging direto e resolve a versão corrente em tempo de consulta. |
| **`data_referencia`** | Data (sem hora) da reserva no fuso local. Chave dos joins de capacidade e do grão diário. |
| **Forward-only** | O coletor só enxerga do mês vigente para frente. Não há backfill. |
| **Status provisório** | Status cuja classificação de papel ainda não foi validada pelo requerente (`provisional = true`) — hoje 8 e 9. |
| **Selo "provisório"** | Aviso no card quando o número depende de status provisório ou de dia com canário marcado. |
