"""Conector para série HISTÓRICA real de sensoriamento remoto (NDVI, temperatura de
superfície, proxy espectral de turbidez) via Landsat/Google Earth Engine — substitui, para
quem tiver credenciais do Earth Engine, a planilha ilustrativa atual
(`ingestion.bronze_sensoriamento`, 14 linhas, jan-jun/2026, autodeclarada "Simulação
Consolidada").

ACHADO DE PESQUISA (2026-07, ver `transform.gold_features`): o valor desta fonte para a
pesquisa de pós-doutorado (metodologia de ML unificando estado do ecossistema e sensoriamento
remoto) só existe se a série tiver sobreposição temporal com o histórico real de qualidade da
água (CETESB, 1978-2024). A planilha ilustrativa (2026) não tem NENHUM ano em comum. Landsat
Collection 2 cobre 1984-presente sem lacuna (combinando os satélites 5/7/8/9) — sobreposição
real de 1984-2024, 41 anos, com a série CETESB.

STATUS DE IMPLEMENTAÇÃO: `fetch_series_historica` está implementada (não é mais um stub) e
segue agora o MESMO padrão validado de `ingestion.connectors.mapbiomas` (2026-07): `import ee`
no nível do módulo, `project` via `config.EARTH_ENGINE_PROJECT`/`WATERWEAVE_EE_PROJECT`, e a
orquestração (`fetch_series_historica` — filtro por `bacias`, tratamento de erro por ponto,
mensagem clara sem projeto configurado) testada com `ee.Initialize`/`_serie_ponto` mockados
(`tests/test_sensoriamento_historico.py`, mesma técnica de `tests/test_mapbiomas.py`) — isso
NÃO testa o cálculo espectral em si (`_serie_ponto`/`_preparar_colecao`/reduceRegion do Earth
Engine), só a montagem/orquestração ao redor dele, o mesmo escopo que `test_mapbiomas.py` já
cobre para `mapbiomas.fetch_uso_solo_por_trecho`. A lógica de extração via Earth Engine em si
NUNCA FOI EXECUTADA CONTRA DADO REAL — segue a API pública documentada do Earth Engine e os
fatores de escala oficiais da USGS Collection 2 Level 2, mas antes de usar em produção, rode
manualmente contra 1-2 pontos/anos conhecidos e confira os valores contra literatura (NDVI de
mata ciliar preservada deveria ficar ~0.6-0.85; turbidez alta na Barra Bonita é consistente com
a eutrofização documentada do reservatório).

Pontos de amostragem: reaproveita os mesmos 7 pontos (`TIE-01`..`TIE-07`) e o mesmo mapeamento
para trecho já usados por `transform.silver_sensoriamento._ID_REGIAO_PARA_TRECHO` — são locais
reais e georreferenciados ao longo do Tietê (a mesma planilha ilustrativa já os usa), e manter
os mesmos IDs deixa a saída deste conector plugável no schema Bronze existente sem precisar
mudar `silver_sensoriamento.py` nem `transform.gold_features.build_indicadores_sensoriamento_anual`.

O que é extraído, por imagem, dentro de um buffer de `RAIO_BUFFER_M` em torno de cada ponto:
  - **NDVI** (mata ciliar / vegetação): (NIR-Red)/(NIR+Red), índice padrão, calibração não
    necessária além da correção de superfície já aplicada pela USGS na Collection 2 Level 2.
  - **Temperatura de superfície** (`ST_B10`/`ST_B6`, já em Kelvin, convertida para °C): direto
    da banda termal, com o fator de escala oficial (ver `_ST_ESCALA`/`_ST_OFFSET_K`).
  - **NDTI** ("proxy de turbidez", (Red-Green)/(Red+Green)): NÃO é turbidez em NTU. É um índice
    espectral correlacionado com sedimento em suspensão na literatura geral, mas NUNCA
    calibrado especificamente para o Tietê (não há par (imagem, medição NTU in situ no mesmo
    dia/local) disponível neste projeto para ajustar uma regressão) — tratar como indicador
    relativo/qualitativo, não como substituto da turbidez real da CETESB.

Limitações conhecidas, documentadas para revisão futura (mesmo espírito das simplificações já
assumidas em `models.biofisico.balanco_hidrico`):
  - O buffer de amostragem mistura água e margem em pontos de rio estreito; para os
    reservatórios (Barra Bonita, Promissão) valeria a pena recortar por uma máscara de água
    real (ex.: `JRC/GSW1_4/GlobalSurfaceWater`) em vez de um buffer circular fixo — não feito
    aqui por tempo.
  - A extração usa `getInfo()` (client-side, uma chamada por ponto) — funciona, mas para os 7
    pontos × ~40 anos × múltiplas imagens por ano isso pode ficar lento; `ee.batch.Export`
    seria mais robusto para uma extração de produção recorrente, não implementado aqui.
  - Máscara de nuvem usa só os bits "Cloud" e "Cloud Shadow" do `QA_PIXEL` (Collection 2); um
    filtro mais estrito incluiria também "Dilated Cloud" (bit 1).
"""
from __future__ import annotations

import logging
from datetime import date

import ee
import pandas as pd

from waterweave.config import EARTH_ENGINE_PROJECT, FONTE_TIPO_OBSERVADO

logger = logging.getLogger(__name__)

# Mesmos pontos/mapeamento de `transform.silver_sensoriamento._ID_REGIAO_PARA_TRECHO`.
PONTOS_MONITORAMENTO: dict[str, dict] = {
    "TIE-01": {"trecho_id": "alto_tiete", "nome": "Salesópolis (Nascente)", "lat": -23.5283, "lon": -45.8394},
    "TIE-02": {"trecho_id": "alto_tiete", "nome": "Mogi das Cruzes", "lat": -23.5208, "lon": -46.1852},
    "TIE-03": {"trecho_id": "alto_tiete", "nome": "Guapira (São Paulo)", "lat": -23.5112, "lon": -46.5181},
    "TIE-04": {"trecho_id": "medio_tiete", "nome": "Barra Bonita (Reservatório)", "lat": -22.6411, "lon": -48.5308},
    "TIE-05": {"trecho_id": "medio_tiete", "nome": "Promissão (Reservatório)", "lat": -21.3142, "lon": -49.8155},
    "TIE-06": {"trecho_id": "baixo_tiete", "nome": "Nova Avanhandava", "lat": -21.1214, "lon": -50.1245},
    "TIE-07": {"trecho_id": "baixo_tiete", "nome": "Foz (Itapura / Rio Paraná)", "lat": -20.6725, "lon": -51.4511},
}

RAIO_BUFFER_M = 300  # raio (m) do buffer de amostragem em torno de cada ponto — ver limitação
                      # sobre reservatórios largos na docstring do módulo.

# Landsat Collection 2 Level 2 — juntas cobrem 1984-presente sem lacuna. `ano_fim_disponivel
#=None` significa "sensor ainda ativo".
_COLECOES = [
    ("LANDSAT/LT05/C02/T1_L2", 1984, 2012),
    ("LANDSAT/LE07/C02/T1_L2", 1999, 2022),
    ("LANDSAT/LC08/C02/T1_L2", 2013, None),
    ("LANDSAT/LC09/C02/T1_L2", 2021, None),
]

# TM/ETM+ (Landsat 5/7) e OLI/TIRS (Landsat 8/9) numeram as bandas de forma diferente — mapa
# explícito para cada coleção, renomeado para nomes comuns ("red"/"green"/"nir"/"termal")
# antes de mesclar as coleções (ver `_preparar_colecao`).
_BANDAS_POR_SENSOR = {
    "LANDSAT/LT05/C02/T1_L2": {"red": "SR_B3", "green": "SR_B2", "nir": "SR_B4", "termal": "ST_B6", "qa": "QA_PIXEL"},
    "LANDSAT/LE07/C02/T1_L2": {"red": "SR_B3", "green": "SR_B2", "nir": "SR_B4", "termal": "ST_B6", "qa": "QA_PIXEL"},
    "LANDSAT/LC08/C02/T1_L2": {"red": "SR_B4", "green": "SR_B3", "nir": "SR_B5", "termal": "ST_B10", "qa": "QA_PIXEL"},
    "LANDSAT/LC09/C02/T1_L2": {"red": "SR_B4", "green": "SR_B3", "nir": "SR_B5", "termal": "ST_B10", "qa": "QA_PIXEL"},
}

# Fatores de escala oficiais da Collection 2 Level 2 (USGS) — SR/ST vêm como inteiro escalado.
_SR_ESCALA, _SR_OFFSET = 0.0000275, -0.2
_ST_ESCALA, _ST_OFFSET_K = 0.00341802, 149.0

# Rótulo/unidade de saída por índice — mesmo vocabulário de `Parâmetro`/`Unidade` já usado na
# planilha ilustrativa (`ingestion.bronze_sensoriamento`), para o restante do pipeline
# (silver/gold) não precisar saber a diferença entre as duas fontes.
_PARAMETRO_POR_COLUNA = {
    "ndvi": ("NDVI (Mata Ciliar)", "Índice (0-1)"),
    "ndti_proxy_turbidez": ("Turbidez (proxy NDTI, não calibrado)", "Índice normalizado"),
    "temp_superficie_c": ("Temperatura da Superfície", "°C"),
}


def _mascara_nuvem(imagem, banda_qa: str):
    """Máscara de nuvem/sombra via bits do `QA_PIXEL` (Collection 2): bit 3 = nuvem, bit 4 =
    sombra de nuvem. Ver limitação sobre "dilated cloud" (bit 1) na docstring do módulo."""
    qa = imagem.select(banda_qa)
    sem_nuvem = qa.bitwiseAnd(1 << 3).eq(0)
    sem_sombra = qa.bitwiseAnd(1 << 4).eq(0)
    return imagem.updateMask(sem_nuvem).updateMask(sem_sombra)


def _indices_por_imagem(imagem):
    """Deriva NDVI, NDTI (proxy de turbidez) e temperatura de superfície (°C) de uma imagem já
    com bandas renomeadas para "red"/"green"/"nir"/"termal" e devidamente escaladas."""
    ndvi = imagem.normalizedDifference(["nir", "red"]).rename("ndvi")
    ndti = imagem.normalizedDifference(["red", "green"]).rename("ndti_proxy_turbidez")
    temp_c = imagem.select("termal").subtract(273.15).rename("temp_superficie_c")
    return imagem.addBands([ndvi, ndti, temp_c])


def _preparar_colecao(id_colecao: str, geometria, data_inicio: str, data_fim: str):
    """Filtra, mascara nuvem, escala e renomeia bandas de UMA coleção Landsat para o esquema
    comum ("red"/"green"/"nir"/"termal") — necessário antes de mesclar sensores diferentes
    (`ee.ImageCollection.merge` exige nomes de banda iguais entre as coleções)."""
    bandas = _BANDAS_POR_SENSOR[id_colecao]

    def _processar(img):
        opticas = (
            img.select([bandas["red"], bandas["green"], bandas["nir"]])
            .rename(["red", "green", "nir"])
            .multiply(_SR_ESCALA)
            .add(_SR_OFFSET)
        )
        termal = img.select([bandas["termal"]]).rename(["termal"]).multiply(_ST_ESCALA).add(_ST_OFFSET_K)
        return ee.Image(opticas.addBands(termal).copyProperties(img, ["system:time_start"]))

    return (
        ee.ImageCollection(id_colecao)
        .filterBounds(geometria)
        .filterDate(data_inicio, data_fim)
        .map(lambda img: _mascara_nuvem(img, bandas["qa"]))
        .map(_processar)
        .map(_indices_por_imagem)
    )


def _serie_ponto(ponto_id: str, metadados: dict, data_inicio: date, data_fim: date) -> pd.DataFrame:
    """Extrai, via Earth Engine, a série anual (mediana por ano-calendário — mais robusta a
    outliers residuais de nuvem que passaram pela máscara) de NDVI/NDTI/temperatura para UM
    ponto de monitoramento. Formato "largo" (uma coluna por índice) — a conversão para o
    schema Bronze (formato longo) é feita à parte por `_formatar_para_schema_bronze`, que não
    depende do pacote `ee` e por isso é testável sem credenciais do Earth Engine."""
    geometria = ee.Geometry.Point([metadados["lon"], metadados["lat"]]).buffer(RAIO_BUFFER_M)

    colecoes = [
        _preparar_colecao(id_colecao, geometria, str(data_inicio), str(data_fim))
        for id_colecao, ano_ini, ano_fim in _COLECOES
        if ano_ini <= data_fim.year and (ano_fim is None or ano_fim >= data_inicio.year)
    ]
    if not colecoes:
        return pd.DataFrame()

    combinada = colecoes[0]
    for extra in colecoes[1:]:
        combinada = combinada.merge(extra)

    def _reduzir(imagem):
        estatisticas = imagem.select(["ndvi", "ndti_proxy_turbidez", "temp_superficie_c"]).reduceRegion(
            reducer=ee.Reducer.mean(), geometry=geometria, scale=30, maxPixels=1e9
        )
        return ee.Feature(None, estatisticas.set("data", imagem.date().format("YYYY-MM-dd")))

    linhas = combinada.map(_reduzir).filter(ee.Filter.notNull(["ndvi"])).getInfo()["features"]
    if not linhas:
        return pd.DataFrame()

    serie = pd.DataFrame([linha["properties"] for linha in linhas])
    serie["ano"] = pd.to_datetime(serie["data"]).dt.year

    anual = serie.groupby("ano")[["ndvi", "ndti_proxy_turbidez", "temp_superficie_c"]].median().reset_index()
    anual["ponto_id"] = ponto_id
    anual["trecho_id"] = metadados["trecho_id"]
    return anual


def _formatar_para_schema_bronze(anual_largo: pd.DataFrame) -> pd.DataFrame:
    """Converte o formato "largo" (`_serie_ponto`, uma coluna por índice) para o formato longo
    do schema Bronze (`ingestion.bronze_sensoriamento`: uma linha por ponto/data/parâmetro) —
    NÃO depende do pacote `ee`, testável com um DataFrame sintético (ver
    `tests/test_sensoriamento_historico.py`)."""
    if anual_largo.empty:
        return anual_largo

    colunas_indice = list(_PARAMETRO_POR_COLUNA)
    longo = anual_largo.melt(
        id_vars=["ponto_id", "trecho_id", "ano"], value_vars=colunas_indice, var_name="_coluna", value_name="valor"
    ).dropna(subset=["valor"])

    longo["parametro"] = longo["_coluna"].map(lambda c: _PARAMETRO_POR_COLUNA[c][0])
    longo["unidade"] = longo["_coluna"].map(lambda c: _PARAMETRO_POR_COLUNA[c][1])
    # mediana anual não tem uma data única real — usa 1º de julho (meio do ano) como data
    # representativa, consistente com a granularidade ANUAL do resto do pipeline de qualidade.
    longo["data_coleta"] = pd.to_datetime({"year": longo["ano"], "month": 7, "day": 1})
    longo["sensor"] = "Landsat Collection 2 (5/7/8/9 mesclados)"
    longo["fonte_dado"] = "USGS/NASA via Google Earth Engine"
    longo["_fonte_tipo"] = FONTE_TIPO_OBSERVADO
    longo["id_regiao"] = longo["ponto_id"]

    colunas_finais = [
        "id_regiao", "trecho_id", "data_coleta", "sensor", "parametro", "valor", "unidade", "fonte_dado", "_fonte_tipo",
    ]
    return longo[colunas_finais].sort_values(["id_regiao", "data_coleta", "parametro"]).reset_index(drop=True)


def fetch_series_historica(
    desde: date, ate: date, bacias: list[str] | None = None, project: str = EARTH_ENGINE_PROJECT
) -> pd.DataFrame:
    """Busca NDVI, temperatura de superfície e NDTI (proxy de turbidez) históricos via Landsat/
    Earth Engine para os pontos de monitoramento do Tietê, no intervalo [`desde`, `ate`].
    `bacias`, se informado, filtra por `trecho_id` (ex.: `["alto_tiete"]`). `project` (default
    `config.EARTH_ENGINE_PROJECT`/`WATERWEAVE_EE_PROJECT`) é o projeto Google Cloud com a API
    do Earth Engine habilitada — mesmo requisito de `ingestion.connectors.mapbiomas`.

    Retorna DataFrame no mesmo schema de `bronze.sensoriamento` (`id_regiao`, `trecho_id`,
    `data_coleta`, `sensor`, `parametro`, `valor`, `unidade`, `fonte_dado`, `_fonte_tipo`),
    pronto para `io_delta.write_table(..., mode="append")`. Levanta `RuntimeError` claro se
    `project` não estiver configurado — ver ACHADO DE PESQUISA e STATUS DE IMPLEMENTAÇÃO na
    docstring do módulo: a ORQUESTRAÇÃO desta função tem teste automatizado (`ee.Initialize`/
    `_serie_ponto` mockados), mas o cálculo espectral em si (`_serie_ponto`) nunca foi
    executado contra o Earth Engine de verdade."""
    if not project:
        raise RuntimeError(
            "Earth Engine sem projeto configurado — defina a variável de ambiente "
            "WATERWEAVE_EE_PROJECT com o ID de um projeto Google Cloud com a API do Earth "
            "Engine habilitada (ver docstring de waterweave.config.EARTH_ENGINE_PROJECT)."
        )
    ee.Initialize(project=project)

    pontos = {k: v for k, v in PONTOS_MONITORAMENTO.items() if bacias is None or v["trecho_id"] in bacias}

    partes: list[pd.DataFrame] = []
    for ponto_id, metadados in pontos.items():
        try:
            serie = _serie_ponto(ponto_id, metadados, desde, ate)
            if not serie.empty:
                partes.append(serie)
        except Exception:
            logger.warning(
                "Sensoriamento histórico (Earth Engine): falha ao extrair série do ponto %s — pulado.",
                ponto_id, exc_info=True,
            )

    anual_largo = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    resultado = _formatar_para_schema_bronze(anual_largo)
    logger.info(
        "Sensoriamento histórico (Earth Engine): %d observações anuais, %d pontos.",
        len(resultado), resultado["id_regiao"].nunique() if not resultado.empty else 0,
    )
    return resultado


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(fetch_series_historica(date(1984, 1, 1), date(2024, 12, 31)).to_string())
