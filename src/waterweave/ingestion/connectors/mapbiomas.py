"""Conector para uso e cobertura do solo real do MapBiomas (Google Earth Engine).

Implementado em 2026-07 após `earthengine authenticate` do usuário e registro
do projeto Google Cloud `config.EARTH_ENGINE_PROJECT` para uso acadêmico —
antes disso, este módulo era um stub (`NotImplementedError`, ver histórico de
`ingestion.bronze_uso_solo`), já que a rota via Earth Engine exige OAuth
interativo e a rota alternativa (planilha nacional por município, sem Earth
Engine) não havia sido validada ponta a ponta.

Fonte: `projects/mapbiomas-public/assets/brazil/lulc/collection9/
mapbiomas_collection90_integration_v1` — coleção 9 (validada em 2026-07:
39 bandas `classification_1985`...`classification_2023`, uma por ano;
resolução nativa ~30m). Cada banda é uma imagem raster com o CÓDIGO da classe
de uso/cobertura por pixel; não existe "uma linha por medição" como na
CETESB — a única forma prática de trazer isso para uma tabela é agregar área
por classe dentro de uma geometria de interesse, o que este módulo faz via
`reduceRegion` no lado do servidor do Earth Engine (não baixa raster nenhum).

Geometria por trecho: NÃO há delimitação de sub-bacia hidrográfica disponível
neste projeto (exigiria um DEM + acumulação de fluxo, fora de escopo). Como
proxy, usamos um buffer de `BUFFER_METROS` (5 km) ao redor de cada estação de
monitoramento real do trecho (mesmas coordenadas de `bronze.estacoes`/
`silver.estacoes`), unidas em uma única geometria — captura o uso do solo na
vizinhança imediata da rede de monitoramento, não a bacia de drenagem inteira
a montante. Limitação documentada, não escondida: para o Baixo Tietê (só 2
estações reais), a geometria é necessariamente mais esparsa que Alto/Médio
(10/20 estações).

Legenda de classes: baseada na legenda pública da Coleção 9 do MapBiomas
(https://mapbiomas.org/en/codigos-de-legenda), agregada em 5 macro-categorias
para uso no pipeline — a coluna `classe_mapbiomas` (código original) também é
preservada em `bronze.uso_solo` para quem precisar do detalhe fino.
"""
from __future__ import annotations

import logging

import ee
import pandas as pd

from waterweave.config import EARTH_ENGINE_PROJECT

logger = logging.getLogger(__name__)

ASSET_ID = "projects/mapbiomas-public/assets/brazil/lulc/collection9/mapbiomas_collection90_integration_v1"
ANO_MIN_COLECAO = 1985
ANO_MAX_COLECAO = 2023  # atualizar quando o MapBiomas publicar uma nova coleção

BUFFER_METROS = 5_000
ESCALA_METROS = 90  # 3x a resolução nativa (~30m) — suficiente para % de área agregada, ~10x mais rápido que 30m

# Código de classe MapBiomas (Coleção 9) -> macro-categoria. Ver docstring do módulo.
CLASSE_PARA_MACRO: dict[int, str] = {
    # Vegetação natural (florestal e não-florestal)
    1: "natural", 3: "natural", 4: "natural", 5: "natural", 6: "natural", 49: "natural",
    10: "natural", 11: "natural", 12: "natural", 13: "natural", 32: "natural", 29: "natural", 50: "natural",
    # Agropecuária e silvicultura (uso agrícola gerido)
    9: "agropecuaria", 14: "agropecuaria", 18: "agropecuaria", 15: "agropecuaria", 19: "agropecuaria",
    39: "agropecuaria", 20: "agropecuaria", 40: "agropecuaria", 62: "agropecuaria", 41: "agropecuaria",
    36: "agropecuaria", 46: "agropecuaria", 47: "agropecuaria", 35: "agropecuaria", 48: "agropecuaria", 21: "agropecuaria",
    # Urbano/industrial e mineração
    24: "urbano_industrial", 30: "urbano_industrial",
    # Água
    26: "agua", 33: "agua", 31: "agua",
    # Não vegetado (natural ou antrópico ambíguo) / não observado — ver docstring
    23: "nao_vegetado_outro", 25: "nao_vegetado_outro", 27: "nao_observado",
}


def _geometria_uniao(pontos: list[tuple[float, float]], buffer_metros: int) -> ee.Geometry:
    """União dos buffers de `buffer_metros` ao redor de cada ponto (lon, lat)."""
    pts = [ee.Geometry.Point([lon, lat]) for lon, lat in pontos]
    return ee.FeatureCollection(pts).geometry().buffer(buffer_metros).dissolve()


def _area_por_classe_um_ano(imagem_ano: ee.Image, geometria: ee.Geometry, escala_metros: int) -> dict[int, float]:
    """Área (m²) por código de classe MapBiomas dentro de `geometria`, para UMA banda/ano —
    uma chamada de `reduceRegion` no servidor do Earth Engine (não baixa raster)."""
    area_img = ee.Image.pixelArea().addBands(imagem_ano)
    resultado = area_img.reduceRegion(
        reducer=ee.Reducer.sum().group(groupField=1, groupName="classe"),
        geometry=geometria,
        scale=escala_metros,
        maxPixels=1e10,
    ).getInfo()
    return {int(g["classe"]): float(g["sum"]) for g in resultado.get("groups", [])}


def fetch_uso_solo_por_trecho(
    pontos_por_trecho: dict[str, list[tuple[float, float]]],
    ano_inicio: int = ANO_MIN_COLECAO,
    ano_fim: int = ANO_MAX_COLECAO,
    buffer_metros: int = BUFFER_METROS,
    escala_metros: int = ESCALA_METROS,
    project: str = EARTH_ENGINE_PROJECT,
) -> pd.DataFrame:
    """Busca área por classe MapBiomas, por trecho e por ano, via Google Earth Engine.

    `pontos_por_trecho`: `{trecho_id: [(longitude, latitude), ...]}` — normalmente as
    coordenadas reais de `bronze.estacoes`/`silver.estacoes` (ver `ingestion.bronze_uso_solo`,
    que monta esse dict e chama esta função; mantida pura/sem I/O de arquivo aqui para ser
    testável com pontos sintéticos).

    Retorna uma linha por (trecho_id, ano, classe_mapbiomas) com `area_m2` e a
    `macro_categoria` já mapeada (`CLASSE_PARA_MACRO`). Levanta `ee.EEException` se o
    Earth Engine não estiver autenticado/o projeto não existir — o chamador (bronze_uso_solo)
    decide como tratar isso (ver seu docstring)."""
    if not project:
        raise RuntimeError(
            "Earth Engine sem projeto configurado — defina a variável de ambiente "
            "WATERWEAVE_EE_PROJECT com o ID de um projeto Google Cloud com a API do Earth "
            "Engine habilitada (ver docstring de waterweave.config.EARTH_ENGINE_PROJECT)."
        )
    ee.Initialize(project=project)
    colecao = ee.Image(ASSET_ID)

    linhas: list[dict] = []
    for trecho_id, pontos in pontos_por_trecho.items():
        if not pontos:
            logger.warning("Nenhum ponto de monitoramento para o trecho '%s' — pulado.", trecho_id)
            continue
        geometria = _geometria_uniao(pontos, buffer_metros)
        for ano in range(ano_inicio, ano_fim + 1):
            banda = f"classification_{ano}"
            try:
                areas = _area_por_classe_um_ano(colecao.select(banda), geometria, escala_metros)
            except Exception:
                logger.warning("MapBiomas: falha ao buscar %s/%d — pulado.", trecho_id, ano, exc_info=True)
                continue
            for classe, area_m2 in areas.items():
                linhas.append({
                    "trecho_id": trecho_id,
                    "ano": ano,
                    "classe_mapbiomas": classe,
                    "macro_categoria": CLASSE_PARA_MACRO.get(classe, "nao_mapeado"),
                    "area_m2": area_m2,
                    "n_pontos_geometria": len(pontos),
                    "buffer_metros": buffer_metros,
                })
        logger.info(
            "MapBiomas: '%s' — %d pontos, %d anos processados (%d-%d).",
            trecho_id, len(pontos), ano_fim - ano_inicio + 1, ano_inicio, ano_fim,
        )

    return pd.DataFrame(linhas)
