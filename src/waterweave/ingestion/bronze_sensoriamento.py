"""Ingestão Bronze de `Sensoriamento_Remoto_Rio_Tiete.xlsx`.

ATENÇÃO DE PROVENIÊNCIA: a própria planilha se descreve como "Dados Recentes
/ Simulação Consolidada" para o período coberto — tratar como
`_fonte_tipo = FONTE_TIPO_SIMULADO` até que os conectores reais (INPE, ESA,
USGS, ANA) do módulo `connectors/` substituam esta fonte por telemetria
orbital ao vivo.

Aba "Dados de Sensoriamento": ID Região, Trecho/Reservatório, Coordenadas,
Data Coleta, Satélite/Sensor, Parâmetro (NDVI, Turbidez, Clorofila-a,
Temperatura da Superfície, Sólidos Suspensos Totais, Nível da Água), Valor
Medido, Unidade, Fonte do Dado.
"""
from __future__ import annotations

import logging

import pandas as pd

from waterweave.config import BRONZE_DIR, FONTE_TIPO_SIMULADO, RAW_SOURCES
from waterweave.io_delta import write_table
from waterweave.ingestion._daee_common import linhas_de_proveniencia

logger = logging.getLogger(__name__)


def run() -> pd.DataFrame:
    """Lê a aba 'Dados de Sensoriamento' e grava em Bronze com proveniência simulada."""
    caminho = RAW_SOURCES["sensoriamento_remoto"]
    tabela = pd.read_excel(caminho, sheet_name="Dados de Sensoriamento")
    for coluna, valores in linhas_de_proveniencia(len(tabela), caminho, FONTE_TIPO_SIMULADO).items():
        tabela[coluna] = valores
    write_table(BRONZE_DIR / "sensoriamento", tabela)
    logger.info("Bronze sensoriamento: %d linhas.", len(tabela))
    return tabela


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
