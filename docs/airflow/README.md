# Orquestração (Airflow)

O coletor foi desenhado para rodar como uma **fonte a mais** num Airflow de
ingestão — não um pipeline paralelo (ADR-0001 D1). Este documento mostra o formato;
não há um deployment de Airflow neste repositório de portfólio.

## Connection

`reservaspace_{ambiente}` (`conn_type = http`). Campo `Extra` (JSON), populado pelo
bootstrap semi-manual:

```json
{
  "base_url": "https://demo.reservaspace.io",
  "cookie": "RSSESSID=<segredo da sessão>",
  "id_local": "1",
  "id_empresa": ""
}
```

O cookie **nunca** vai para arquivo, log ou código. O bootstrap
(`ocupa-salas-bootstrap`) abre um browser, o humano faz SSO+MFA, e o cookie
resultante é gravado direto na Connection.

## Cadência

~8 execuções em horário comercial, sem execução noturna (ADR-0001 D4). Grade
candidata de 90 em 90 min entre 08:00 e 18:00 local — como 90 min não divide 60, o
cron precisa de lista explícita de horários ou cai para grade de hora em hora.

## Esqueleto da DAG

```python
from datetime import datetime

from airflow.decorators import dag, task
from airflow.models import Connection

from ocupa_salas.http_client import Connection as SourceConn
from ocupa_salas.pipeline import StateStore, run_collection, write_jsonl


def _source_conn() -> SourceConn:
    extra = Connection.get_connection_from_secrets("reservaspace_prd").extra_dejson
    return SourceConn.from_mapping(extra)


@dag(
    schedule="0 11-21 * * 1-5",          # UTC ≈ horário comercial local, dias úteis
    start_date=datetime(2026, 1, 1),
    catchup=False,                        # forward-only (ADR-0001 D6)
    default_args={"retries": 2},
    tags=["ocupacao", "scraping", "adr-0001"],
)
def ocupa_salas_dag():

    @task
    def health_check() -> None:
        from ocupa_salas.http_client import check_session
        check_session(_source_conn())     # 401 / corpo vazio → falha alta (DQ-01)

    @task
    def collect(data_interval_start=None) -> dict:
        particao = data_interval_start.date().isoformat()
        state = StateStore(f"/data/ocupa_salas/state/{_source_conn().id_local}.json")
        run = run_collection(_source_conn(), state=state, data_particao=particao)
        state.save()
        write_jsonl(run.linhas_novas, f"/data/ocupa_salas/{particao}/reservas.jsonl")
        write_jsonl(run.capacidade, f"/data/ocupa_salas/{particao}/capacidade.jsonl")
        return {"resumo": run.resumo, "canarios_falhos": run.canarios_falhos}

    @task
    def load_staging(payload: dict) -> None:
        # COPY dos JSONL para stg_reservas / stg_capacidade com
        # UNIQUE (id_origem, data_particao, hash_linha) → grava-quando-muda (ADR-0001 D3).
        ...

    load_staging(collect()) if health_check() is None else None


ocupa_salas_dag()
```

O `health_check` é a **primeira task** (spec, user story 11). `catchup=False` porque
a fonte é forward-only — não há janela histórica para preencher.
