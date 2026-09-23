# BI de Ocupação de Salas

Camada analítica do projeto. Aqui a modelagem está **documentada** (não há um
arquivo de projeto Power BI versionado neste repositório de portfólio).

- [`camada-semantica.md`](camada-semantica.md) — modelo semântico, relações,
  medidas (DAX), regras de cálculo.
- Arquitetura e grão: [`../arquitetura.md`](../arquitetura.md).
- Regras dos números: [`../regras-negocio.md`](../regras-negocio.md).

## Fonte do modelo

`gld_ocupacao_corrente` (view, **DirectQuery** sobre Postgres) + `dCalendario`
(tabela de datas calculada) + `dim_sala` + `dim_status_kpi_role` (referência, sem
relação).

## Painel — "Resumo de Salas"

Página executiva única:

| Bloco | Conteúdo |
|---|---|
| Cabeçalho | slicer de período (obrigatório — RN-07), slicer de sala/turno |
| Cards | Taxa de Ocupação, Vagas Disponíveis, Reservas Realizadas, Vagas Ociosas, % Cancelamento + Falta, Locais |
| Linha do tempo | Taxa de Ocupação por dia × linha de meta 75% (só dentro do intervalo com dado — RN-06) |
| Barras | Taxa de Ocupação por sala e por turno |
| Rodapé | data da última coleta, selo "provisório" quando aplicável (RN-10, DQ-04/05) |
