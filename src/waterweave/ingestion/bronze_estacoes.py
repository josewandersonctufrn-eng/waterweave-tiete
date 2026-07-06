"""Ingestão Bronze da tabela mestra de estações (`cod_latlong.xlsx`).

Fonte já estruturada (uma linha por ponto de monitoramento em todo o estado
de SP, não só no Tietê): CodInterAguas, TipoRede, UGRHI, CodPonto,
SistHidrico, Classe, Municipio, UF, Localizacao, LongDecml, LattDecml.
Bronze mantém o mirror completo (699 estações); o filtro para o eixo do
Rio Tietê e a classificação por trecho é regra de negócio e fica em
`transform.silver_estacoes`.
"""
from __future__ import annotations

import logging

import pandas as pd

from waterweave.config import BRONZE_DIR, FONTE_TIPO_OBSERVADO, RAW_SOURCES
from waterweave.io_delta import write_table
from waterweave.ingestion._daee_common import linhas_de_proveniencia

logger = logging.getLogger(__name__)


def run() -> pd.DataFrame:
    """Lê `cod_latlong.xlsx` e grava a dimensão de estações em Bronze."""
    caminho = RAW_SOURCES["estacoes"]
    tabela = pd.read_excel(caminho, sheet_name="Plan1")
    for coluna, valores in linhas_de_proveniencia(len(tabela), caminho, FONTE_TIPO_OBSERVADO).items():
        tabela[coluna] = valores
    write_table(BRONZE_DIR / "estacoes", tabela)
    logger.info("Bronze estações: %d linhas.", len(tabela))
    return tabela


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
