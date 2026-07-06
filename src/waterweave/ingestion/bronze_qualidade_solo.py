"""Ingestão Bronze de `Planilha_Historica_Solo_Sedimentos_Rio_Tiete_1940_2025.xlsx`.

ATENÇÃO DE PROVENIÊNCIA: esta planilha é declarada pela própria fonte como
"dados históricos consolidados e SIMULADOS com base nas tendências dos
relatórios da CETESB, DAEE e SOS Mata Atlântica" — não é telemetria direta.
A ingestão marca `_fonte_tipo = FONTE_TIPO_SIMULADO` para todas as linhas,
permitindo que o dashboard e os modelos tratem esta série como proxy
histórico e não como observação de campo.

Aba "Dados Históricos": Ano, Região (Alto/Médio/Baixo Tietê), Uso do Solo
Predominante, IQA Médio, DBO (mg/L), OD (mg/L), Metais Pesados (ppm),
Pesticidas (ppm), Matéria Orgânica (%).
"""
from __future__ import annotations

import logging

import pandas as pd

from waterweave.config import BRONZE_DIR, FONTE_TIPO_SIMULADO, RAW_SOURCES
from waterweave.io_delta import write_table
from waterweave.ingestion._daee_common import linhas_de_proveniencia

logger = logging.getLogger(__name__)


def run() -> pd.DataFrame:
    """Lê a aba 'Dados Históricos', e grava em Bronze com proveniência simulada."""
    caminho = RAW_SOURCES["qualidade_solo_sedimentos"]
    tabela = pd.read_excel(caminho, sheet_name="Dados Históricos")
    for coluna, valores in linhas_de_proveniencia(len(tabela), caminho, FONTE_TIPO_SIMULADO).items():
        tabela[coluna] = valores
    write_table(BRONZE_DIR / "qualidade_solo", tabela)
    logger.info("Bronze qualidade_solo: %d linhas.", len(tabela))
    return tabela


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
