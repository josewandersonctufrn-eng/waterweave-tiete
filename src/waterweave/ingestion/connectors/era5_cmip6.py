"""Conector para dados climáticos REAIS via Copernicus Climate Data Store (CDS): reanálise ERA5
(histórico observado, `fetch_reanalysis`) e projeções CMIP6 (cenários futuros,
`fetch_projection`) — item 4 do roadmap de pesquisa WaterWeave-Water4All.

ACHADO DE PESQUISA (2026-07): hoje `models.abm.scenarios` só tem um proxy simplificado de
mudança climática (chuva reduzida em 25% fixo, `PARAMETROS_CENARIO["mudanca_climatica_extrema"]`)
e `RioTieteModel` calibra a variabilidade climática só a partir da CLIMATOLOGIA histórica DAEE
já ingerida (`models.abm.model._climatologia_mensal`). Nenhuma das duas fontes usa um cenário de
emissões real (SSP) nem reanálise independente da rede pluviométrica local — este conector
fecha essa lacuna, mas NÃO foi religado a `scenarios.py`/`model.py` aqui (ver "próximos passos"
abaixo): a ligação exige decidir COMO combinar o sinal de grade climática (ERA5/CMIP6, ~28km de
resolução) com a climatologia por trecho já calibrada localmente, o que é uma decisão de
modelagem, não só um encaixe de código.

STATUS DE IMPLEMENTAÇÃO: `fetch_reanalysis`/`fetch_projection` deixaram de ser stubs
`NotImplementedError` e seguem uma rota real de acesso, pesquisada e documentada abaixo — mas,
diferente de `connectors.mapbiomas`/`connectors.sensoriamento_historico` (Earth Engine, onde a
extração já foi ao menos exercida manualmente contra a API), aqui a extração NUNCA foi executada
contra a CDS de verdade: requer um token pessoal (`WATERWEAVE_CDS_API_KEY`, ver
`config.CDS_API_KEY`) que não está disponível neste ambiente de desenvolvimento. A orquestração
em torno da rede (montagem de request, conversão de unidades, agregação espacial) é testável e
testada com `cdsapi`/`xarray` mockados (`tests/test_era5_cmip6.py`, mesma técnica de
`tests/test_mapbiomas.py`/`tests/test_sensoriamento_historico.py`) — antes de usar em produção,
rode manualmente contra 1-2 meses conhecidos e confira os valores contra a climatologia DAEE já
ingerida (`silver.hidrologia`) ou contra literatura.

Rota de acesso pesquisada (CDS API, pacote `cdsapi`), documentada em
https://cds.climate.copernicus.eu/how-to-api (consultada 2026-07):
  - Autenticação: token pessoal, oficialmente gravado em `~/.cdsapirc`, mas a própria
    `cdsapi.Client` aceita `url`/`key` passados explicitamente no construtor — usado aqui
    (`config.CDS_API_URL`/`config.CDS_API_KEY`, variável de ambiente `WATERWEAVE_CDS_API_KEY`),
    mesmo padrão já estabelecido para `config.EARTH_ENGINE_PROJECT`.
  - ERA5 (`fetch_reanalysis`): dataset `reanalysis-era5-single-levels-monthly-means`,
    `product_type = "monthly_averaged_reanalysis"` — a própria CDS já entrega a média mensal
    (mais leve que baixar cada campo horário e agregar localmente). Variáveis usadas:
    `2m_temperature` (K, vira `t2m` no NetCDF) e `total_precipitation` (m/dia — média diária
    acumulada DENTRO do mês, vira `tp`; ver conversão para mm/mês em `_processar_reanalise`).
    Cobertura: 1940-presente, mesmo início de `config.HISTORICO_INICIO`.
  - CMIP6 (`fetch_projection`): dataset `projections-cmip6`, `temporal_resolution = "monthly"`,
    `level = "single_levels"`, variáveis `near_surface_air_temperature` (K, vira `tas`) e
    `precipitation` (kg/m²/s, vira `pr`, quando o modelo escolhido a disponibiliza). A CDS
    aceita só UM `model` por requisição (resolução espacial varia entre modelos, não dá pra
    combinar num único pedido) — `_MODELO_CMIP6_PADRAO` usa um dos modelos mais leves
    recomendados no tutorial oficial da CDS; combinar vários modelos num ensemble (a prática
    correta para reduzir incerteza estrutural) é uma extensão futura, chamando
    `fetch_projection` uma vez por modelo e agregando os DataFrames depois — não feito aqui.
    `experiment` mapeia rótulos populares (`"SSP2-4.5"`) para o id técnico da CDS (`"ssp245"`)
    via `CENARIO_PARA_EXPERIMENTO_CMIP6`.
  - Ambos os datasets retornam arquivos GRIDDED (NetCDF; CMIP6 vem dentro de um `.zip`) — bem
    diferente do padrão ponto-a-ponto de `mapbiomas`/`sensoriamento_historico` (lá, o Earth
    Engine agrega no servidor via `reduceRegion` e devolve só o número; aqui a agregação
    espacial acontece localmente, com `xarray`, depois do download). Latência também é
    diferente: pedidos entram numa fila da CDS e podem levar de segundos a dezenas de minutos —
    `cdsapi.Client.retrieve` já bloqueia e espera internamente, sem precisar de polling manual.

LIMITAÇÕES CONHECIDAS (mesmo espírito das já documentadas em
`connectors.sensoriamento_historico`):
  - Agregação espacial por MÉDIA SIMPLES da grade dentro do bbox (`config.BBOX_BACIA_TIETE`),
    sem ponderar por área de célula (`cos(latitude)`, necessário para agregados GLOBAIS como no
    tutorial oficial da CDS) — a bacia do Tietê é pequena e está longe o bastante do equador
    para essa simplificação ter erro desprezível, mas não foi validado numericamente.
  - Um único bbox para a bacia inteira, não um valor por trecho — na resolução do ERA5/CMIP6
    (~28-250km) um recorte por trecho (que tem só dezenas de km de largura) não adicionaria
    precisão real; se necessário no futuro, os 3 trechos já têm bounding boxes menores
    implícitos nos pontos de `sensoriamento_historico.PONTOS_MONITORAMENTO`.
  - `fetch_projection` não faz ensemble multi-modelo (ver acima).
  - Próximos passos (não feitos aqui): (1) religar a chuva/temperatura do ERA5 para CALIBRAR
    `models.abm.model._climatologia_mensal` no lugar da climatologia só-DAEE; (2) religar o
    delta CMIP6 (projeção - histórico, por mês) para SUBSTITUIR o proxy fixo de -25% de chuva em
    `models.abm.scenarios.PARAMETROS_CENARIO["mudanca_climatica_extrema"]` por um `fator_clima`
    calculado a partir do cenário SSP escolhido.
"""
from __future__ import annotations

import logging
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import cdsapi
import pandas as pd
import xarray as xr

from waterweave.config import BBOX_BACIA_TIETE, CDS_API_KEY, CDS_API_URL, FONTE_TIPO_OBSERVADO, FONTE_TIPO_SIMULADO

logger = logging.getLogger(__name__)

# Rótulo popular -> id técnico do experimento CMIP6 na CDS. Aceita também o id técnico direto
# (`fetch_projection("ssp245", ...)`) — ver `.get(cenario, cenario)` no corpo da função.
CENARIO_PARA_EXPERIMENTO_CMIP6 = {
    "historical": "historical",
    "SSP1-2.6": "ssp126",
    "SSP2-4.5": "ssp245",
    "SSP5-8.5": "ssp585",
}

# Modelo CMIP6 leve (baixo volume de dados), mesma escolha do tutorial oficial da CDS para
# ensembles rápidos — ver limitação sobre ensemble multi-modelo na docstring do módulo.
_MODELO_CMIP6_PADRAO = "mpi_esm1_2_lr"

_SEGUNDOS_POR_DIA = 86400


def _cliente_cds(url: str, key: str | None) -> "cdsapi.Client":
    """Constrói o cliente da CDS API, com mensagem de erro clara se o token não estiver
    configurado — mesmo padrão de `connectors.mapbiomas._geometria_uniao`/
    `connectors.sensoriamento_historico.fetch_series_historica` para `EARTH_ENGINE_PROJECT`."""
    if not key:
        raise RuntimeError(
            "Climate Data Store sem token configurado — defina a variável de ambiente "
            "WATERWEAVE_CDS_API_KEY com o token pessoal obtido em "
            "https://cds.climate.copernicus.eu/how-to-api (ver docstring de "
            "waterweave.config.CDS_API_KEY)."
        )
    return cdsapi.Client(url=url, key=key)


def _area_cds(bbox: tuple[float, float, float, float]) -> list[float]:
    """Converte `(lat_min, lon_min, lat_max, lon_max)` (convenção deste módulo, ver
    `config.BBOX_BACIA_TIETE`) para `[N, W, S, E]`, o formato exigido pelo parâmetro `area` da
    CDS API."""
    lat_min, lon_min, lat_max, lon_max = bbox
    return [lat_max, lon_min, lat_min, lon_max]


def _media_espacial(dataset: "xr.Dataset", variavel: str) -> "xr.DataArray":
    """Média simples (não ponderada por latitude — ver limitação na docstring do módulo) da
    grade dentro do bbox já usado no filtro `area` da requisição, colapsando lat/lon e mantendo
    a dimensão de tempo."""
    dims_espaciais = [d for d in ("latitude", "longitude", "lat", "lon") if d in dataset[variavel].dims]
    return dataset[variavel].mean(dim=dims_espaciais)


def _processar_reanalise(dataset: "xr.Dataset") -> pd.DataFrame:
    """Converte o `xr.Dataset` baixado da CDS (`reanalysis-era5-single-levels-monthly-means`)
    numa série mensal em unidades físicas usuais (°C, mm/mês) — não depende de rede, só de
    `xarray`, testável com um `xr.Dataset` sintético em memória (ver
    `tests/test_era5_cmip6.py`)."""
    temperatura_k = _media_espacial(dataset, "t2m")
    precipitacao_m_dia = _media_espacial(dataset, "tp")

    coluna_tempo = "valid_time" if "valid_time" in dataset.coords else "time"
    tempo = pd.to_datetime(dataset[coluna_tempo].values)

    serie = pd.DataFrame(
        {
            "mes_data": tempo,
            "temperatura_c_media": temperatura_k.values - 273.15,
            # ERA5 monthly-means dá a média DIÁRIA de precipitação do mês (m/dia) — multiplica
            # pelos dias do mês (converte diário -> mensal) e por 1000 (m -> mm).
            "chuva_mm_total": precipitacao_m_dia.values * tempo.days_in_month * 1000.0,
        }
    )
    serie["_fonte_tipo"] = FONTE_TIPO_OBSERVADO
    serie["fonte_dado"] = "ERA5 (ECMWF) via Copernicus Climate Data Store"
    return serie.sort_values("mes_data").reset_index(drop=True)


def _processar_projecao(dataset: "xr.Dataset", experimento: str, modelo: str) -> pd.DataFrame:
    """Mesmo papel de `_processar_reanalise`, para o `xr.Dataset` de uma projeção CMIP6 (um
    modelo/experimento por chamada — ver docstring do módulo)."""
    temperatura_k = _media_espacial(dataset, "tas")
    tempo = pd.to_datetime(dataset["time"].values)

    serie = pd.DataFrame(
        {
            "mes_data": tempo,
            "temperatura_c_media": temperatura_k.values - 273.15,
        }
    )
    if "pr" in dataset.data_vars:
        precipitacao_kg_m2_s = _media_espacial(dataset, "pr")
        # `pr` do CMIP6 vem em kg/m²/s (equivalente a mm/s de lâmina d'água) — multiplica pelos
        # segundos do mês (dias do mês x 86400) para o total mensal em mm.
        serie["chuva_mm_total"] = precipitacao_kg_m2_s.values * _SEGUNDOS_POR_DIA * tempo.days_in_month

    serie["cenario_id"] = experimento
    serie["modelo_cmip6"] = modelo
    serie["_fonte_tipo"] = FONTE_TIPO_SIMULADO
    serie["fonte_dado"] = f"CMIP6 ({modelo}) via Copernicus Climate Data Store"
    return serie.sort_values("mes_data").reset_index(drop=True)


def fetch_reanalysis(
    since: date,
    bbox: tuple[float, float, float, float] = BBOX_BACIA_TIETE,
    ate: date | None = None,
    url: str = CDS_API_URL,
    key: str | None = CDS_API_KEY,
) -> pd.DataFrame:
    """Busca reanálise ERA5 mensal (precipitação total, temperatura média a 2m) para o bbox da
    bacia, de `since` até `ate` (default: hoje). Retorna DataFrame com `mes_data`,
    `temperatura_c_media`, `chuva_mm_total`, `_fonte_tipo` (sempre `FONTE_TIPO_OBSERVADO` — é
    reanálise, não simulação de cenário), `fonte_dado`. Levanta `RuntimeError` claro se `key`
    não estiver configurado — ver docstring do módulo e `config.CDS_API_KEY`."""
    ate = ate or date.today()
    cliente = _cliente_cds(url, key)

    anos = [str(ano) for ano in range(since.year, ate.year + 1)]
    with tempfile.TemporaryDirectory() as pasta_tmp:
        destino = Path(pasta_tmp) / "era5_monthly.nc"
        cliente.retrieve(
            "reanalysis-era5-single-levels-monthly-means",
            {
                "product_type": ["monthly_averaged_reanalysis"],
                "variable": ["2m_temperature", "total_precipitation"],
                "year": anos,
                "month": [f"{mes:02d}" for mes in range(1, 13)],
                "time": ["00:00"],
                "area": _area_cds(bbox),
                "data_format": "netcdf",
            },
            str(destino),
        )
        with xr.open_dataset(destino) as dataset:
            resultado = _processar_reanalise(dataset)

    logger.info("ERA5 (CDS): %d meses processados (%s a %s).", len(resultado), since, ate)
    return resultado


def fetch_projection(
    cenario: str,
    bbox: tuple[float, float, float, float] = BBOX_BACIA_TIETE,
    desde: date | None = None,
    ate: date | None = None,
    modelo: str = _MODELO_CMIP6_PADRAO,
    url: str = CDS_API_URL,
    key: str | None = CDS_API_KEY,
) -> pd.DataFrame:
    """Busca projeção CMIP6 mensal (temperatura a 2m; precipitação quando o modelo a
    disponibiliza) para um cenário/experimento e bbox da bacia. `cenario` aceita tanto o rótulo
    popular (`"SSP2-4.5"`) quanto o id técnico da CDS (`"ssp245"`) — ver
    `CENARIO_PARA_EXPERIMENTO_CMIP6`. `desde`/`ate`, se não informados, usam os limites usuais
    de cada tipo de experimento na CDS (1850-2014 para `historical`, 2015-2100 para os SSPs).
    Levanta `RuntimeError` claro se `key` não estiver configurado."""
    experimento = CENARIO_PARA_EXPERIMENTO_CMIP6.get(cenario, cenario)
    if desde is None or ate is None:
        desde_padrao, ate_padrao = (
            (date(1850, 1, 1), date(2014, 12, 31))
            if experimento == "historical"
            else (date(2015, 1, 1), date(2100, 12, 31))
        )
        desde = desde or desde_padrao
        ate = ate or ate_padrao

    cliente = _cliente_cds(url, key)

    with tempfile.TemporaryDirectory() as pasta_tmp:
        destino_zip = Path(pasta_tmp) / "cmip6.zip"
        cliente.retrieve(
            "projections-cmip6",
            {
                "temporal_resolution": "monthly",
                "experiment": experimento,
                "level": "single_levels",
                "variable": ["near_surface_air_temperature", "precipitation"],
                "model": modelo,
                "date": f"{desde.isoformat()}/{ate.isoformat()}",
                "area": _area_cds(bbox),
                "download_format": "zip",
                "data_format": "netcdf_legacy",
            },
            str(destino_zip),
        )
        with zipfile.ZipFile(destino_zip) as arquivo_zip:
            arquivo_zip.extractall(pasta_tmp)
            netcdfs = [Path(pasta_tmp) / nome for nome in arquivo_zip.namelist() if nome.endswith(".nc")]

        partes = []
        for caminho in netcdfs:
            with xr.open_dataset(caminho) as dataset:
                partes.append(_processar_projecao(dataset, experimento, modelo))
        resultado = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()

    logger.info(
        "CMIP6 (CDS): %d meses processados, cenário %s, modelo %s.", len(resultado), experimento, modelo
    )
    return resultado


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(fetch_reanalysis(date(2020, 1, 1)).to_string())
