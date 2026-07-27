"""Ingestão Bronze de uso e cobertura do solo real (MapBiomas via Google Earth Engine).

Fecha a lacuna documentada em `ingestion.connectors.mapbiomas` (stub até
2026-07): `uso_solo` no pipeline vinha inteiramente da planilha simulada
(`silver.qualidade`, texto livre tipo "Metropolitano/Industrial"), nunca de
dado real de sensoriamento remoto — apesar de o MapBiomas (Coleção 9, 1985-
2023, acesso público via Earth Engine) estar disponível o tempo todo.

Diferente dos demais módulos Bronze (mirror quase literal de uma planilha),
aqui a "linha" bruta já é uma agregação de área por classe MapBiomas dentro
de um buffer ao redor das estações reais de cada trecho (ver docstring de
`connectors.mapbiomas` para a limitação de não ter delimitação de bacia
hidrográfica) — não existe uma granularidade mais fina que fizesse sentido
guardar (o raster teria bilhões de pixels).

Depende de `bronze.estacoes` já existir (para ter as coordenadas reais) — por
isso entra em `ingestion.monthly_job.run_bronze_static_sources()` DEPOIS de
`bronze_estacoes.run()`, não antes. A classificação por trecho reaproveita
`transform.silver_estacoes._ugrhi_para_trecho` (mesma regra de negócio, sem
duplicar a lógica) em vez de esperar `silver.estacoes` já estar pronta —
evita uma dependência de ordem bronze→silver→bronze que não existe hoje em
nenhum outro módulo.

Requer `earthengine authenticate` (feito uma vez, interativo, pelo usuário
fora deste pipeline) e `config.EARTH_ENGINE_PROJECT` configurado. Se a
autenticação não existir/expirar, `run()` propaga a exceção — o chamador
(`monthly_job.run_bronze_static_sources`) NÃO tem hoje um try/except por
fonte (diferente de `run_live_connectors`), então uma falha aqui interrompe
o job mensal; ver ACHADO DE AUDITORIA em `monthly_job` se isso precisar de
um fallback silencioso no futuro.
"""
from __future__ import annotations

import datetime as _dt
import logging

import pandas as pd

from waterweave.config import BRONZE_DIR, FONTE_TIPO_OBSERVADO
from waterweave.io_delta import read_table, write_table
from waterweave.ingestion.connectors import mapbiomas
from waterweave.transform.silver_estacoes import _ugrhi_para_trecho

logger = logging.getLogger(__name__)


def _pontos_reais_por_trecho() -> dict[str, list[tuple[float, float]]]:
    """Coordenadas (longitude, latitude) das estações reais do eixo do Tietê, por trecho —
    mesmo filtro/classificação de `transform.silver_estacoes.build_silver_estacoes`, aplicado
    aqui sobre `bronze.estacoes` diretamente (ver docstring do módulo)."""
    bronze = read_table(BRONZE_DIR / "estacoes")
    mascara = bronze["CodPonto"].astype(str).str.startswith(("TIET", "TIBT"))
    tabela = bronze.loc[mascara].copy()
    tabela["trecho_id"] = tabela["UGRHI"].apply(_ugrhi_para_trecho)
    tabela = tabela.dropna(subset=["trecho_id", "LongDecml", "LattDecml"])

    pontos: dict[str, list[tuple[float, float]]] = {}
    for trecho_id, grupo in tabela.groupby("trecho_id"):
        pontos[trecho_id] = list(zip(grupo["LongDecml"].astype(float), grupo["LattDecml"].astype(float)))
    return pontos


def run() -> pd.DataFrame:
    """Busca área por classe MapBiomas (1985-2023) por trecho via Earth Engine e grava em Bronze."""
    pontos_por_trecho = _pontos_reais_por_trecho()
    tabela = mapbiomas.fetch_uso_solo_por_trecho(pontos_por_trecho)

    agora = _dt.datetime.now().isoformat(timespec="seconds")
    tabela["_ingested_at"] = agora
    tabela["_source_file"] = mapbiomas.ASSET_ID
    tabela["_fonte_tipo"] = FONTE_TIPO_OBSERVADO

    write_table(BRONZE_DIR / "uso_solo", tabela, partition_by=["trecho_id"])
    logger.info(
        "Bronze uso_solo: %d linhas (%d trechos, %d-%d).",
        len(tabela), tabela["trecho_id"].nunique(),
        mapbiomas.ANO_MIN_COLECAO, mapbiomas.ANO_MAX_COLECAO,
    )
    return tabela


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
