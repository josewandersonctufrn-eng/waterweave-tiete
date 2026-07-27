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
`NotImplementedError` e seguem uma rota real de acesso, pesquisada e documentada abaixo.

ACHADO (execução real, 2026-07 — primeira vez que `fetch_reanalysis`/`fetch_projection`
rodaram contra a CDS de verdade, token pessoal `WATERWEAVE_CDS_API_KEY` configurado): o formato
de resposta real difere do assumido na pesquisa original, em dois pontos:
  1. ERA5 (`fetch_reanalysis`): mesmo com `data_format: "netcdf"`, a CDS retorna um `.zip`
     contendo DOIS arquivos NetCDF separados — `t2m` (variável instantânea, stream `avgua`) e
     `tp` (variável acumulada, stream `avgad`) NÃO vêm no mesmo arquivo, e o `valid_time` de
     `tp` tem um offset de +6h em relação ao de `t2m` (mesmo mês nominal, hora do dia diferente
     — comportamento normal do processamento de variáveis acumuladas do ERA5).
     `_processar_reanalise` foi corrigida para aceitar uma LISTA de datasets e fundir os dois
     por MÊS-CALENDÁRIO (não pelo timestamp exato).
  2. CMIP6 (`fetch_projection`): (a) o id técnico do experimento tem underscores entre os
     dígitos (`"ssp2_4_5"`, não `"ssp245"` — `CENARIO_PARA_EXPERIMENTO_CMIP6` corrigido); (b) o
     parâmetro `"level"` não deve ser enviado para variáveis de superfície como
     `near_surface_air_temperature`/`precipitation` (o schema real da CDS mostra o conjunto de
     níveis válidos como VAZIO para essas variáveis — enviar `"single_levels"` quebrava o
     request); (c) o parâmetro correto para o intervalo de datas é `year`+`month` (arrays), não
     `"date": "YYYY-MM-DD/YYYY-MM-DD"` (que não existe no schema do processo); (d) pedir
     `near_surface_air_temperature`+`precipitation` na MESMA requisição faz a CDS devolver
     silenciosamente só uma das duas variáveis (confirmado empiricamente: só `tas` voltava,
     `pr` sumia sem erro) — `fetch_projection` agora faz UMA requisição por variável
     (`_baixar_variavel_cmip6`) e funde os resultados em `_processar_projecao` (que passou a
     receber um dict `{"tas": ds, "pr": ds}` em vez de um único dataset).

Validado com dado real: ERA5 2020-2026 (temperatura ~17-26°C, chuva concentrada out-mar,
plausível para a bacia do Tietê) e a calibração completa `calibrar_fatores_clima_cenarios()`
(baseline CMIP6 `historical` 1995-2014 vs. projeção `ssp5_8_5` 2040-2060, modelo
`mpi_esm1_2_lr`) — resultado real: `fator_clima["mudanca_climatica_extrema"] = 0.982`, ou seja,
apenas ~1,8% mais seco no cenário mais extremo (SSP5-8.5) que no baseline, bem menos severo que
o proxy fixo de -25% (`fator_clima = 0.75`) usado antes desta calibração — ver `salvar_calibracao_fator_clima`
e `models.abm.clima_real` para como esse número passou a substituir o proxy fixo em
`models.abm.scenarios.PARAMETROS_CENARIO["mudanca_climatica_extrema"]`. Baseado em UM único
modelo CMIP6 (ver limitação sobre ensemble multi-modelo abaixo) — não tratar como consenso.

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
  - Próximos passos (não feitos aqui): religar a chuva/temperatura do ERA5 para CALIBRAR
    `models.abm.model._climatologia_mensal` no lugar da climatologia só-DAEE — o item de
    religar CMIP6 ao `fator_clima` do ABM (antes listado aqui) foi feito, ver
    `calibrar_fatores_clima_cenarios`/`models.abm.clima_real` abaixo.

ATUALIZAÇÃO (2026-07, CMIP6 -> `fator_clima` do ABM): `calibrar_fatores_clima_cenarios`
substitui o proxy fixo de -25% de chuva em
`models.abm.scenarios.PARAMETROS_CENARIO["mudanca_climatica_extrema"]` por um fator calculado a
partir da razão entre a precipitação média projetada (CMIP6, cenário SSP5-8.5, numa janela de
anos futura) e a precipitação média do período de referência `historical` (1995-2014, a mesma
baseline de 20 anos usada pelo IPCC AR6) — ver `CENARIO_ABM_PARA_SSP`. Como isso exige rede e
token CDS (indisponíveis no boot da aplicação Streamlit em produção), a calibração NÃO roda ao
vivo: é um passo em lote (`python -m waterweave.ingestion.connectors.era5_cmip6`, ou chamando
`calibrar_fatores_clima_cenarios`/`salvar_calibracao_fator_clima` manualmente) que grava o
resultado em `config.FATOR_CLIMA_CALIBRACAO_FILE` (JSON pequeno, versionado). `models.abm.clima_real`
lê esse arquivo de forma síncrona e rápida (sem rede) — se ele não existir (checkout novo, ou
antes da primeira calibração), cai de volta no valor fixo de -25%, com aviso no log — mesmo
espírito de fallback documentado (real-quando-disponível, simulado-como-piso) já usado em
`transform.gold_features.qualidade_real_com_fallback_simulado`/`uso_solo_da_linha`.
"""
from __future__ import annotations

import json
import logging
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import cdsapi
import pandas as pd
import xarray as xr

from waterweave.config import (
    BBOX_BACIA_TIETE,
    CDS_API_KEY,
    CDS_API_URL,
    FATOR_CLIMA_CALIBRACAO_FILE,
    FONTE_TIPO_OBSERVADO,
    FONTE_TIPO_SIMULADO,
)

logger = logging.getLogger(__name__)

# Rótulo popular -> id técnico do experimento CMIP6 na CDS. Aceita também o id técnico direto
# (`fetch_projection("ssp245", ...)`) — ver `.get(cenario, cenario)` no corpo da função.
CENARIO_PARA_EXPERIMENTO_CMIP6 = {
    "historical": "historical",
    "SSP1-2.6": "ssp1_2_6",
    "SSP2-4.5": "ssp2_4_5",
    "SSP5-8.5": "ssp5_8_5",
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


def _processar_reanalise(datasets: list["xr.Dataset"]) -> pd.DataFrame:
    """Converte os `xr.Dataset` baixados da CDS (`reanalysis-era5-single-levels-monthly-means`)
    numa série mensal em unidades físicas usuais (°C, mm/mês) — não depende de rede, só de
    `xarray`/`pandas`, testável com uma lista de `xr.Dataset` sintéticos em memória (ver
    `tests/test_era5_cmip6.py`).

    Recebe uma LISTA porque a CDS retorna `t2m` e `tp` em arquivos NetCDF SEPARADOS (ver ACHADO
    na docstring do módulo) — funde os dois por MÊS-CALENDÁRIO, não pelo timestamp exato (o
    `valid_time` de `tp`, variável acumulada, vem com +6h de offset em relação ao de `t2m`,
    mesmo mês nominal). Levanta `ValueError` claro se alguma das duas variáveis não aparecer em
    nenhum dos datasets recebidos."""
    partes: dict[str, pd.DataFrame] = {}
    for dataset in datasets:
        for variavel in ("t2m", "tp"):
            if variavel not in dataset.data_vars:
                continue
            coluna_tempo = "valid_time" if "valid_time" in dataset.coords else "time"
            tempo = pd.to_datetime(dataset[coluna_tempo].values)
            media = _media_espacial(dataset, variavel).values
            partes[variavel] = pd.DataFrame({"mes": pd.PeriodIndex(tempo, freq="M"), variavel: media})

    faltando = {"t2m", "tp"} - set(partes)
    if faltando:
        raise ValueError(
            f"Variável(is) ausente(s) na resposta da CDS para reanálise ERA5: {sorted(faltando)} "
            "(ver ACHADO na docstring do módulo sobre t2m/tp virem em arquivos separados)."
        )

    combinado = partes["t2m"].merge(partes["tp"], on="mes", how="inner")
    combinado["mes_data"] = combinado["mes"].dt.to_timestamp()

    serie = pd.DataFrame(
        {
            "mes_data": combinado["mes_data"],
            "temperatura_c_media": combinado["t2m"] - 273.15,
            # ERA5 monthly-means dá a média DIÁRIA de precipitação do mês (m/dia) — multiplica
            # pelos dias do mês (converte diário -> mensal) e por 1000 (m -> mm).
            "chuva_mm_total": combinado["tp"] * combinado["mes_data"].dt.days_in_month * 1000.0,
        }
    )
    serie["_fonte_tipo"] = FONTE_TIPO_OBSERVADO
    serie["fonte_dado"] = "ERA5 (ECMWF) via Copernicus Climate Data Store"
    return serie.sort_values("mes_data").reset_index(drop=True)


def _processar_projecao(datasets: dict[str, "xr.Dataset"], experimento: str, modelo: str) -> pd.DataFrame:
    """Mesmo papel de `_processar_reanalise`, para os `xr.Dataset` de uma projeção CMIP6 (um
    modelo/experimento por chamada — ver docstring do módulo). `datasets` é um dict
    `{"tas": xr.Dataset, "pr": xr.Dataset}` — uma chave por VARIÁVEL, não um único dataset com
    as duas (ver ACHADO na docstring do módulo: pedir `tas`+`pr` na MESMA requisição faz a CDS
    devolver silenciosamente só uma das duas — cada variável precisa da sua própria requisição).
    `"pr"` é opcional (nem todo modelo CMIP6 disponibiliza precipitação mensal)."""
    tempo_tas = pd.to_datetime(datasets["tas"]["time"].values)
    temperatura_k = _media_espacial(datasets["tas"], "tas")

    serie = pd.DataFrame({"mes_data": tempo_tas, "temperatura_c_media": temperatura_k.values - 273.15})

    if "pr" in datasets:
        tempo_pr = pd.to_datetime(datasets["pr"]["time"].values)
        precipitacao_kg_m2_s = _media_espacial(datasets["pr"], "pr")
        # `pr` do CMIP6 vem em kg/m²/s (equivalente a mm/s de lâmina d'água) — multiplica pelos
        # segundos do mês (dias do mês x 86400) para o total mensal em mm. Funde por
        # MÊS-CALENDÁRIO (não por timestamp exato — mesma cautela de `_processar_reanalise`,
        # já que `tas`/`pr` vêm de requisições/arquivos separados e podem ter "dia do mês"
        # nominal ligeiramente diferente entre variáveis)."
        chuva = pd.DataFrame(
            {
                "mes": pd.PeriodIndex(tempo_pr, freq="M"),
                "chuva_mm_total": precipitacao_kg_m2_s.values * _SEGUNDOS_POR_DIA * tempo_pr.days_in_month,
            }
        )
        serie["mes"] = pd.PeriodIndex(tempo_tas, freq="M")
        serie = serie.merge(chuva, on="mes", how="left").drop(columns="mes")

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
        # A CDS retorna um .zip com t2m/tp em arquivos separados (ver ACHADO na docstring do
        # módulo) — mas trata também o caso de vir um único .nc direto, caso esse comportamento
        # mude de novo no futuro.
        if zipfile.is_zipfile(destino):
            with zipfile.ZipFile(destino) as arquivo_zip:
                arquivo_zip.extractall(pasta_tmp)
                netcdfs = [Path(pasta_tmp) / nome for nome in arquivo_zip.namelist() if nome.endswith(".nc")]
        else:
            netcdfs = [destino]

        datasets = []
        for caminho in netcdfs:
            with xr.open_dataset(caminho) as dataset:
                datasets.append(dataset.load())
        resultado = _processar_reanalise(datasets)

    logger.info("ERA5 (CDS): %d meses processados (%s a %s).", len(resultado), since, ate)
    return resultado


def _baixar_variavel_cmip6(
    cliente: "cdsapi.Client",
    pasta_tmp: str,
    variavel: str,
    experimento: str,
    modelo: str,
    anos: list[str],
    bbox: tuple[float, float, float, float],
) -> "xr.Dataset":
    """Baixa UMA variável CMIP6 (uma requisição por variável — ver ACHADO na docstring do
    módulo sobre `tas`+`pr` na mesma requisição fazer a CDS devolver só uma das duas em
    silêncio) e devolve o `xr.Dataset` já carregado em memória (arquivo fechado antes de
    retornar, seguro para o `tempfile.TemporaryDirectory` ser limpo depois)."""
    destino_zip = Path(pasta_tmp) / f"cmip6_{variavel}.zip"
    cliente.retrieve(
        "projections-cmip6",
        {
            "temporal_resolution": "monthly",
            "experiment": experimento,
            "variable": [variavel],
            "model": modelo,
            "year": anos,
            "month": [f"{mes:02d}" for mes in range(1, 13)],
            "area": _area_cds(bbox),
            "download_format": "zip",
            "data_format": "netcdf_legacy",
        },
        str(destino_zip),
    )
    with zipfile.ZipFile(destino_zip) as arquivo_zip:
        arquivo_zip.extractall(pasta_tmp)
        netcdfs = [nome for nome in arquivo_zip.namelist() if nome.endswith(".nc")]
    with xr.open_dataset(Path(pasta_tmp) / netcdfs[0]) as dataset:
        return dataset.load()


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
    Levanta `RuntimeError` claro se `key` não estiver configurado.

    Faz UMA requisição por variável (temperatura, depois precipitação) — ver ACHADO na
    docstring do módulo: pedir as duas na MESMA requisição faz a CDS devolver silenciosamente
    só uma delas. Se a requisição de precipitação falhar (modelo/experimento sem essa variável
    disponível), segue só com temperatura e registra um aviso — mesmo espírito de
    `fator_precipitacao_relativo`, que já levanta erro claro se `chuva_mm_total` for necessária
    e não estiver disponível."""
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
    anos = [str(ano) for ano in range(desde.year, ate.year + 1)]

    with tempfile.TemporaryDirectory() as pasta_tmp:
        datasets = {"tas": _baixar_variavel_cmip6(cliente, pasta_tmp, "near_surface_air_temperature", experimento, modelo, anos, bbox)}
        try:
            datasets["pr"] = _baixar_variavel_cmip6(cliente, pasta_tmp, "precipitation", experimento, modelo, anos, bbox)
        except Exception:
            logger.warning(
                "CMIP6 (CDS): precipitação indisponível para modelo=%s, experimento=%s — "
                "seguindo só com temperatura.", modelo, experimento, exc_info=True,
            )
        resultado = _processar_projecao(datasets, experimento, modelo)

    logger.info(
        "CMIP6 (CDS): %d meses processados, cenário %s, modelo %s.", len(resultado), experimento, modelo
    )
    return resultado


# ---------------------------------------------------------------------------------------------
# CMIP6 -> `fator_clima` do ABM (`models.abm.scenarios.PARAMETROS_CENARIO`) — ver ATUALIZAÇÃO na
# docstring do módulo.
# ---------------------------------------------------------------------------------------------

# Período de referência ("baseline") padrão do IPCC AR6 para medir mudança climática relativa —
# 20 anos, encerrando no último ano do experimento `historical` do CMIP6 (2014). Usar a MESMA
# janela de 20 anos nos dois lados (baseline e futuro) evita que a diferença de tamanho de
# amostra, por si só, mude a média comparada.
BASELINE_CMIP6_DESDE = date(1995, 1, 1)
BASELINE_CMIP6_ATE = date(2014, 12, 31)
JANELA_ANOS_PADRAO = 20

# Cenário do ABM (`models.abm.scenarios.PARAMETROS_CENARIO`) -> experimento CMIP6 usado para
# calibrar seu `fator_clima`. Só "mudanca_climatica_extrema" tem uma contraparte CMIP6 hoje
# (os outros 2 cenários do ABM não são climáticos — mexem em outorga/fiscalização, não em
# chuva); ampliar esse mapa é a forma natural de adicionar novos cenários climáticos no futuro
# (ex.: "mudanca_climatica_moderada" -> "ssp245"), sem mexer em `calibrar_fatores_clima_cenarios`.
CENARIO_ABM_PARA_SSP = {"mudanca_climatica_extrema": "SSP5-8.5"}


def fator_precipitacao_relativo(baseline: pd.DataFrame, projecao: pd.DataFrame) -> float:
    """Razão entre a precipitação média mensal projetada e a precipitação média mensal do
    período de referência — o `fator_clima` que `models.abm.model.RioTieteModel.step` usa como
    multiplicador direto da climatologia de chuva (`chuva_mes = chuva_climatologica *
    fator_clima`, ver `models.abm.model`). Valores < 1.0 = cenário mais seco que o baseline; > 1.0
    = mais chuvoso. Não depende de rede — pura manipulação dos DataFrames já baixados, testável
    com dados sintéticos (ver `tests/test_era5_cmip6.py`).

    Levanta `ValueError` claro se `chuva_mm_total` não estiver disponível em algum dos dois
    (alguns modelos CMIP6 não expõem a variável `pr`, ver LIMITAÇÕES na docstring do módulo) —
    melhor falhar alto do que silenciosamente calibrar um fator só de temperatura como se fosse
    de chuva."""
    for nome, tabela in (("baseline", baseline), ("projecao", projecao)):
        if "chuva_mm_total" not in tabela.columns or tabela["chuva_mm_total"].dropna().empty:
            raise ValueError(
                f"'{nome}' sem dado de precipitação ('chuva_mm_total') — o modelo CMIP6 escolhido "
                "pode não expor a variável 'pr' para este experimento (ver LIMITAÇÕES na "
                "docstring de waterweave.ingestion.connectors.era5_cmip6)."
            )
    media_baseline = baseline["chuva_mm_total"].mean()
    media_projecao = projecao["chuva_mm_total"].mean()
    if not media_baseline:
        raise ValueError("Precipitação média do baseline é zero — divisão por zero evitada.")
    return float(media_projecao / media_baseline)


def calibrar_fator_clima_ssp(
    experimento: str,
    ano_futuro_centro: int,
    janela_anos: int = JANELA_ANOS_PADRAO,
    bbox: tuple[float, float, float, float] = BBOX_BACIA_TIETE,
    modelo: str = _MODELO_CMIP6_PADRAO,
    url: str = CDS_API_URL,
    key: str | None = CDS_API_KEY,
) -> float:
    """Calibra um `fator_clima` para UM experimento SSP: busca a projeção `historical` (baseline
    `BASELINE_CMIP6_DESDE`-`BASELINE_CMIP6_ATE`) e a projeção do `experimento` numa janela de
    `janela_anos` centrada em `ano_futuro_centro`, e retorna a razão entre as duas
    (`fator_precipitacao_relativo`). Faz 2 chamadas de rede (`fetch_projection` duas vezes) —
    lento, não chamar num caminho quente da aplicação."""
    meio_janela = janela_anos // 2
    baseline = fetch_projection(
        "historical", bbox, desde=BASELINE_CMIP6_DESDE, ate=BASELINE_CMIP6_ATE, modelo=modelo, url=url, key=key
    )
    projecao = fetch_projection(
        experimento,
        bbox,
        desde=date(ano_futuro_centro - meio_janela, 1, 1),
        ate=date(ano_futuro_centro + meio_janela, 12, 31),
        modelo=modelo,
        url=url,
        key=key,
    )
    return fator_precipitacao_relativo(baseline, projecao)


def calibrar_fatores_clima_cenarios(
    ano_futuro_centro: int = 2050,
    janela_anos: int = JANELA_ANOS_PADRAO,
    bbox: tuple[float, float, float, float] = BBOX_BACIA_TIETE,
    modelo: str = _MODELO_CMIP6_PADRAO,
    url: str = CDS_API_URL,
    key: str | None = CDS_API_KEY,
) -> dict[str, float]:
    """Calibra `fator_clima` para TODOS os cenários do ABM que têm contraparte CMIP6
    (`CENARIO_ABM_PARA_SSP`) — hoje só `"mudanca_climatica_extrema"`. Retorna
    `{cenario_id: fator_clima}`, pronto para `salvar_calibracao_fator_clima`. `ano_futuro_centro`
    (default 2050) é um horizonte de médio prazo razoável para o uso típico do dashboard
    ("Cenários Futuros" vai até 30 anos à frente); recalibrar para outro horizonte é só chamar
    de novo com outro `ano_futuro_centro`."""
    return {
        cenario_id: calibrar_fator_clima_ssp(experimento, ano_futuro_centro, janela_anos, bbox, modelo, url, key)
        for cenario_id, experimento in CENARIO_ABM_PARA_SSP.items()
    }


def salvar_calibracao_fator_clima(
    fatores: dict[str, float], caminho: Path = FATOR_CLIMA_CALIBRACAO_FILE, **metadados_extra
) -> Path:
    """Grava `fatores` (saída de `calibrar_fatores_clima_cenarios`) em `caminho` (default
    `config.FATOR_CLIMA_CALIBRACAO_FILE`), com metadados de proveniência (quando/com qual modelo
    foi calibrado) — lido por `models.abm.clima_real.fator_clima_calibrado` sem precisar de rede."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conteudo = {
        "fatores_clima": fatores,
        "modelo_cmip6": _MODELO_CMIP6_PADRAO,
        "baseline": {"desde": BASELINE_CMIP6_DESDE.isoformat(), "ate": BASELINE_CMIP6_ATE.isoformat()},
        "calibrado_em": datetime.now(timezone.utc).isoformat(),
        **metadados_extra,
    }
    caminho.write_text(json.dumps(conteudo, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Calibração de fator_clima gravada em %s: %s", caminho, fatores)
    return caminho


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(fetch_reanalysis(date(2020, 1, 1)).to_string())
    fatores = calibrar_fatores_clima_cenarios()
    salvar_calibracao_fator_clima(fatores)
