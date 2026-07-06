"""Silver de qualidade da água/solo: normaliza `bronze.qualidade_solo` para schema comum.

Mantém granularidade anual x trecho (Alto/Médio/Baixo) da fonte original —
não deve ser confundida com granularidade por posto (hidrologia) até que
uma fonte observada (CETESB) com essa resolução esteja disponível.
"""
from __future__ import annotations

import pandas as pd

from waterweave.config import BRONZE_DIR, SILVER_DIR
from waterweave.io_delta import read_table, write_table

_REGIAO_PARA_TRECHO = {
    "alto tietê": "alto_tiete",
    "médio tietê": "medio_tiete",
    "baixo tietê": "baixo_tiete",
}

_RENOMEIA = {
    "Ano": "ano",
    "Região": "regiao",
    "Uso do Solo Predominante": "uso_solo",
    "IQA Médio": "iqa",
    "DBO (mg/L)": "dbo_mg_l",
    "OD (mg/L)": "od_mg_l",
    "Metais Pesados (ppm)": "metais_pesados_ppm",
    "Pesticidas (ppm)": "pesticidas_ppm",
    "Matéria Orgânica (%)": "materia_organica_pct",
    "_fonte_tipo": "fonte_tipo",
}


def build_silver_qualidade() -> pd.DataFrame:
    """Normaliza nomes de parâmetros e classifica cada linha em um trecho."""
    bronze = read_table(BRONZE_DIR / "qualidade_solo")
    tabela = bronze.rename(columns=_RENOMEIA)
    tabela["trecho_id"] = tabela["regiao"].str.lower().map(_REGIAO_PARA_TRECHO)
    colunas = [
        "trecho_id", "ano", "uso_solo", "iqa", "dbo_mg_l", "od_mg_l",
        "metais_pesados_ppm", "pesticidas_ppm", "materia_organica_pct", "fonte_tipo",
    ]
    tabela = tabela[colunas]
    write_table(SILVER_DIR / "qualidade", tabela)
    return tabela


if __name__ == "__main__":
    build_silver_qualidade()
