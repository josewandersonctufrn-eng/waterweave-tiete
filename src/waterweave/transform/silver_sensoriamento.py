"""Silver de sensoriamento remoto: normaliza `bronze.sensoriamento` para schema comum.

Uma linha por (ponto, data_coleta, parâmetro) já é a granularidade da fonte;
o trabalho aqui é separar `Coordenadas (Lat/Long)` em duas colunas decimais
e mapear cada ponto (`TIE-01`..`TIE-07`) para o trecho correspondente, com
base na geografia real do local descrito em `Trecho / Reservatório`.
"""
from __future__ import annotations

import pandas as pd

from waterweave.config import BRONZE_DIR, SILVER_DIR
from waterweave.io_delta import read_table, write_table

# Baseado no local real de cada ponto (ver `Trecho / Reservatório` na fonte):
# TIE-01 Salesópolis (nascente), TIE-02 Mogi das Cruzes, TIE-03 Guapira (São
# Paulo) -> bacia do Alto Tietê; TIE-04 Barra Bonita e TIE-05 Promissão
# (reservatórios) -> Médio Tietê; TIE-06 Nova Avanhandava e TIE-07 Foz
# (Itapura/Rio Paraná) -> Baixo Tietê.
_ID_REGIAO_PARA_TRECHO = {
    "TIE-01": "alto_tiete",
    "TIE-02": "alto_tiete",
    "TIE-03": "alto_tiete",
    "TIE-04": "medio_tiete",
    "TIE-05": "medio_tiete",
    "TIE-06": "baixo_tiete",
    "TIE-07": "baixo_tiete",
}

_RENOMEIA = {
    "ID Região": "id_regiao",
    "Trecho / Reservatório": "trecho_nome",
    "Coordenadas (Lat/Long)": "coordenadas",
    "Data Coleta": "data_coleta",
    "Satélite / Sensor": "sensor",
    "Parâmetro": "parametro",
    "Valor Medido": "valor",
    "Unidade": "unidade",
    "Fonte do Dado": "fonte_dado",
    "_fonte_tipo": "fonte_tipo",
}


def build_silver_sensoriamento() -> pd.DataFrame:
    """Normaliza coordenadas, parâmetros e associa cada ponto ao trecho correspondente."""
    bronze = read_table(BRONZE_DIR / "sensoriamento")
    tabela = bronze.rename(columns=_RENOMEIA)
    coords = tabela["coordenadas"].str.split(",", expand=True)
    tabela["latitude"] = coords[0].astype(float)
    tabela["longitude"] = coords[1].astype(float)
    tabela["trecho_id"] = tabela["id_regiao"].map(_ID_REGIAO_PARA_TRECHO)
    write_table(SILVER_DIR / "sensoriamento", tabela)
    return tabela


if __name__ == "__main__":
    build_silver_sensoriamento()
