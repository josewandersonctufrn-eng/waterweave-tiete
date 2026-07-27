"""Silver do sensoriamento remoto HISTÓRICO real: normaliza `bronze.sensoriamento_historico`
para o mesmo formato "longo" usado por `silver.sensoriamento` (a planilha ilustrativa) — uma
linha por (ponto, data_coleta, parâmetro) — mas SEM precisar separar uma coluna
`"Coordenadas (Lat/Long)"` (a fonte real já grava `trecho_id` direto): latitude/longitude/nome
do ponto vêm de `connectors.sensoriamento_historico.PONTOS_MONITORAMENTO`, a mesma tabela de
metadados que o conector usa para buscar cada série.

Ver `transform.gold_features.sensoriamento_real_com_fallback_ilustrativo` para como esta
tabela e `silver.sensoriamento` (ilustrativa) são combinadas com prioridade para o dado real.
"""
from __future__ import annotations

import pandas as pd

from waterweave.config import BRONZE_DIR, SILVER_DIR
from waterweave.io_delta import read_table, write_table
from waterweave.ingestion.connectors.sensoriamento_historico import PONTOS_MONITORAMENTO


def build_silver_sensoriamento_historico() -> pd.DataFrame:
    """Normaliza `bronze.sensoriamento_historico`, anexando latitude/longitude/nome do ponto.
    Retorna DataFrame vazio se a Bronze ainda não foi materializada (mesmo contrato de
    `io_delta.read_table` para tabela ausente) — o fetch real via Earth Engine é caro/lento e
    pode não ter rodado ainda em todo ambiente."""
    bronze = read_table(BRONZE_DIR / "sensoriamento_historico")
    if bronze.empty:
        return bronze

    tabela = bronze.rename(columns={"_fonte_tipo": "fonte_tipo"}).copy()
    tabela["data_coleta"] = pd.to_datetime(tabela["data_coleta"])
    tabela["latitude"] = tabela["id_regiao"].map(lambda p: PONTOS_MONITORAMENTO[p]["lat"])
    tabela["longitude"] = tabela["id_regiao"].map(lambda p: PONTOS_MONITORAMENTO[p]["lon"])
    tabela["trecho_nome"] = tabela["id_regiao"].map(lambda p: PONTOS_MONITORAMENTO[p]["nome"])

    write_table(SILVER_DIR / "sensoriamento_historico", tabela)
    return tabela


if __name__ == "__main__":
    build_silver_sensoriamento_historico()
