"""Orquestrador do job mensal de ingestão (acionado por Airflow DAG ou cron).

Ordem de execução:
  1. Bronze das fontes estáticas locais (arquivos DAEE + planilhas já em
     disco) — hoje um rescan completo a cada rodada (arquivos são poucos o
     bastante para isso ser barato); a Delta table é sobrescrita com
     `schema_mode="overwrite"` (ver `io_delta.write_table`).
  2. Conectores ao vivo. `ana_snirh` é real (API pública HidroWeb da ANA,
     sem chave) e seu resultado é anexado (`mode="append"`) direto nas
     tabelas Bronze de fluviometria/pluviometria, no mesmo schema
     "consolidado" que os arquivos DAEE já usam — ver
     `connectors.ana_snirh`. `cetesb` e `mapbiomas` seguem como
     `NotImplementedError` (a primeira não tem API pública documentada, a
     segunda depende de autenticação Google Earth Engine do usuário — ver
     docstrings de cada uma) e são puladas com aviso, sem derrubar o job.
  3. Silver e Gold são sempre recomputados por inteiro a partir da Bronze
     (custo baixo no volume atual de dados; trocar por reprocessamento
     incremental por trecho é uma otimização futura, não uma correção).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime

from waterweave.config import BRONZE_DIR, PIPELINE_CONTROL_FILE
from waterweave.io_delta import write_table
from waterweave.ingestion import (
    bronze_daee_fluviometria,
    bronze_daee_pluviometria,
    bronze_estacoes,
    bronze_qualidade_solo,
    bronze_sensoriamento,
)
from waterweave.ingestion.connectors import ana_snirh, cetesb, mapbiomas
from waterweave.transform import gold_features, silver_estacoes, silver_hidrologia, silver_qualidade, silver_sensoriamento

logger = logging.getLogger(__name__)

# era5_cmip6 não entra aqui: seu contrato é diferente (fetch_reanalysis/
# fetch_projection, com bounding box), não fetch_new_records(since) — é acionado
# separadamente quando a modelagem climática precisar de cenários (ver `models.abm.scenarios`).
# ana_snirh também não entra: seu retorno (dict de DataFrames) é tratado à parte
# em `run_live_connectors`, gravado direto nas tabelas Bronze correspondentes.
_CONECTORES_STUB = {
    "cetesb": cetesb,
    "mapbiomas": mapbiomas,
}


def get_last_successful_run() -> date | None:
    """Lê a data da última execução mensal bem-sucedida a partir da tabela de controle."""
    if not PIPELINE_CONTROL_FILE.exists():
        return None
    conteudo = json.loads(PIPELINE_CONTROL_FILE.read_text(encoding="utf-8"))
    ultima = conteudo.get("last_successful_run")
    return date.fromisoformat(ultima) if ultima else None


def _set_last_successful_run(quando: date) -> None:
    PIPELINE_CONTROL_FILE.parent.mkdir(parents=True, exist_ok=True)
    PIPELINE_CONTROL_FILE.write_text(json.dumps({"last_successful_run": quando.isoformat()}), encoding="utf-8")


def run_bronze_static_sources() -> None:
    """Executa todos os módulos `bronze_*` sobre os arquivos disponíveis localmente."""
    bronze_daee_fluviometria.run()
    bronze_daee_pluviometria.run()
    bronze_estacoes.run()
    bronze_qualidade_solo.run()
    bronze_sensoriamento.run()


def run_live_connectors(since: date) -> None:
    """Executa o conector real (ANA/SNIRH) e os que ainda são stub, sem derrubar o job em nenhum dos dois casos."""
    try:
        resultado = ana_snirh.fetch_new_records(since)
        for nome_tabela, df in resultado.items():
            if df is not None and not df.empty:
                write_table(BRONZE_DIR / nome_tabela, df, mode="append", partition_by=["trecho_id"])
                logger.info("ANA/SNIRH: +%d linhas em bronze.%s", len(df), nome_tabela)
    except Exception:
        logger.warning("Conector 'ana_snirh' falhou — seguindo sem seus dados.", exc_info=True)

    for nome, modulo in _CONECTORES_STUB.items():
        try:
            modulo.fetch_new_records(since)
        except NotImplementedError:
            logger.info("Conector '%s' ainda não implementado — pulado nesta rodada.", nome)
        except Exception:
            logger.warning("Conector '%s' falhou — seguindo sem seus dados.", nome, exc_info=True)


def run_silver_gold_refresh() -> None:
    """Recomputa Silver (todas as tabelas) e Gold (todas as tabelas) a partir da Bronze atual."""
    silver_estacoes.build_silver_estacoes()
    silver_hidrologia.build_silver_hidrologia()
    silver_qualidade.build_silver_qualidade()
    silver_sensoriamento.build_silver_sensoriamento()
    gold_features.run()


def main() -> None:
    """Ponto de entrada único para o agendador (Airflow/cron) chamar mensalmente."""
    ultima_execucao = get_last_successful_run()
    logger.info("Última execução bem-sucedida: %s", ultima_execucao or "nunca")

    run_bronze_static_sources()
    run_live_connectors(since=ultima_execucao or date(1940, 1, 1))
    run_silver_gold_refresh()

    hoje = datetime.now().date()
    _set_last_successful_run(hoje)
    logger.info("Job mensal concluído em %s.", hoje)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
