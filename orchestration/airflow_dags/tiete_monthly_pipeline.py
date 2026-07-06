"""DAG do Airflow que aciona `waterweave.ingestion.monthly_job` mensalmente.

Agendamento sugerido: primeiro dia útil de cada mês, dando tempo para ANA,
DAEE e CETESB publicarem os dados do mês anterior. Tarefas em sequência:
ingest_bronze -> refresh_silver_gold -> retrain_ml (trimestral) -> notify.
"""
from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

from waterweave.ingestion.monthly_job import main as run_monthly_job

with DAG(
    dag_id="tiete_monthly_pipeline",
    schedule="@monthly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as dag:
    ingest_bronze = PythonOperator(
        task_id="ingest_bronze_and_refresh_gold",
        python_callable=run_monthly_job,
    )
