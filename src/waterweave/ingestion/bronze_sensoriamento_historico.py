"""Ingestão Bronze do sensoriamento remoto HISTÓRICO real (Landsat/Google Earth Engine).

Grava numa tabela SEPARADA de `bronze.sensoriamento` (a planilha ilustrativa lida por
`bronze_sensoriamento.py`, autodeclarada "Dados Recentes / Simulação Consolidada") — as duas
fontes têm schema incompatível na origem: a planilha usa títulos em português com uma única
coluna `"Coordenadas (Lat/Long)"` (string "lat, lon"), enquanto `connectors.sensoriamento_historico`
já produz colunas snake_case com `trecho_id` calculado direto. Tentar concatenar as duas ANTES
de normalizar geraria colunas duplicadas/inconsistentes; a fusão com prioridade para o dado
real acontece em `transform.gold_features.sensoriamento_real_com_fallback_ilustrativo`, no
mesmo padrão já usado para `qualidade_real_com_fallback_simulado` (CETESB vs. planilha
simulada) — aqui, na Bronze, cada fonte só grava o que é dela.

Fonte não é um arquivo local (é uma busca ao vivo no Earth Engine) — mesmo padrão de
`bronze_uso_solo.py` (ver `tests/test_pipeline_paridade.py::_MODULOS_BRONZE_SEM_RAW_SOURCE`).

RESSALVA DE VALIDAÇÃO (ver `connectors.sensoriamento_historico`, seção "STATUS DE
IMPLEMENTAÇÃO"): os índices espectrais (NDVI, proxy NDTI de turbidez, temperatura de
superfície) nunca foram calibrados contra medição in situ do Tietê — plausíveis à luz da
literatura geral (checado manualmente contra 2022-2023 em `alto_tiete` antes deste módulo
entrar em produção: NDVI ~0.62-0.66 em Salesópolis/nascente preservada, ~0.22-0.24 nos pontos
urbanos de Mogi/Guapira — consistente com o esperado), mas não substituem medição de campo.

Requer `earthengine authenticate` (feito uma vez, interativo, pelo usuário fora deste
pipeline) e `config.EARTH_ENGINE_PROJECT` configurado — mesmo requisito de `bronze_uso_solo`.
Pode ser LENTO (múltiplos pontos x décadas de imagens Landsat, `getInfo()` uma chamada por
ponto) — ver limitação de performance na docstring de `connectors.sensoriamento_historico`.
"""
from __future__ import annotations

import datetime as _dt
import logging
from datetime import date

import pandas as pd

from waterweave.config import BRONZE_DIR
from waterweave.io_delta import write_table
from waterweave.ingestion.connectors import sensoriamento_historico

logger = logging.getLogger(__name__)

ANO_INICIO_PADRAO = 1984  # Landsat 5 TM (Collection 2) — ver connectors.sensoriamento_historico._COLECOES


def run(desde: date | None = None, ate: date | None = None) -> pd.DataFrame:
    """Busca a série histórica real (Landsat, `desde`-`ate`) via Earth Engine e grava em Bronze.
    Por padrão, `desde=1984-01-01` (início da cobertura Landsat 5) e `ate=hoje`."""
    desde = desde or date(ANO_INICIO_PADRAO, 1, 1)
    ate = ate or date.today()

    tabela = sensoriamento_historico.fetch_series_historica(desde, ate)
    if tabela.empty:
        logger.warning("Bronze sensoriamento_historico: fetch retornou vazio (%s-%s).", desde, ate)
        return tabela

    tabela["_ingested_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    tabela["_source_file"] = "Google Earth Engine (Landsat Collection 2, ver connectors.sensoriamento_historico)"

    write_table(BRONZE_DIR / "sensoriamento_historico", tabela, partition_by=["trecho_id"])
    logger.info(
        "Bronze sensoriamento_historico: %d linhas, %d pontos, %s-%s.",
        len(tabela), tabela["id_regiao"].nunique(), desde, ate,
    )
    return tabela


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
