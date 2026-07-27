"""Camada Gold: agregações finais consumidas por ML, ABM e dashboard.

Tabelas produzidas:
  - `gold.serie_temporal_trecho_mes`: uma linha por (trecho, mês) com vazão e
    chuva médias entre todos os postos do trecho, mais os indicadores de
    qualidade da água do ano correspondente (a série de qualidade é anual,
    então é repetida em todos os meses daquele ano — granularidade real,
    não inventada). É a tabela que o dashboard consome diretamente.
  - `gold.feature_store_ml`: mesma granularidade MENSAL, com lags e média
    móvel de IQA/OD. MANTIDA por compatibilidade, mas NÃO É MAIS a fonte de
    treino dos modelos (ver ACHADO DE AUDITORIA DE ML abaixo) — hoje só serve
    quem eventualmente precise de vazão/chuva mensal com lag; para
    qualidade da água, use `gold.feature_store_ml_anual`.
  - `gold.feature_store_ml_anual`: uma linha por (trecho, ano), com lags e
    média móvel de IQA/OD em ANOS, mais vazão/chuva e — desde 2026-07 —
    percentual de área por macro-categoria de uso do solo real (MapBiomas,
    ver ACHADO DE PESQUISA "uso do solo REAL" abaixo) — fonte de treino
    correta e atual dos modelos de ML (ver `models.ml.train`).
  - `gold.estado_inicial_abm`: snapshot mais recente por trecho, usado para
    inicializar o `Model` do Mesa a cada rodada de simulação.
  - `gold.sensoriamento_trecho_ano`: uma linha por (trecho, ano) com os
    indicadores de sensoriamento remoto (NDVI, turbidez, clorofila-a,
    temperatura de superfície, sólidos suspensos totais, nível d'água) —
    ver ACHADO DE PESQUISA (integração de sensoriamento remoto) abaixo
    para por que ela NÃO é juntada a `feature_store_ml_anual`.
  - `gold.servicos_ecossistemicos_trecho_ano`: uma linha por (trecho, ano) com os serviços
    ecossistêmicos de REGULAÇÃO DA QUALIDADE DA ÁGUA e PROVISÃO HÍDRICA (fração 0-1), calculados
    sobre o histórico REAL — item 5 do roadmap de pesquisa, ver `models.servicos_ecossistemicos`
    e `build_servicos_ecossistemicos_historico` para por que SUPORTE À BIODIVERSIDADE não entra
    aqui (só computável no braço simulado do ABM).

ACHADO DE PESQUISA (2026-07, integração de sensoriamento remoto — pesquisa de
pós-doutorado / projeto WaterWeave-Water4All): `silver.sensoriamento` (NDVI,
turbidez, clorofila-a, temperatura de superfície, sólidos suspensos totais,
nível d'água, ver `ingestion.bronze_sensoriamento`) nunca era lida por
nenhuma tabela Gold nem entrava como preditora do ML — a "integração de
dados heterogêneos de sensoriamento remoto e in situ" que a pesquisa se
propõe a desenvolver não existia de fato no pipeline, mesmo com a ingestão
já pronta. `build_indicadores_sensoriamento_anual` fecha a agregação (uma
linha por trecho/ano, no mesmo padrão de `build_feature_store_ml_anual`).

RESSALVA (por que NÃO entra em `feature_store_ml_anual`, ainda): a planilha
fonte (`Sensoriamento_Remoto_Rio_Tiete.xlsx`) tem 14 linhas no total,
cobrindo só jan-jun/2026, e se autodeclara "Dados Recentes / Simulação
Consolidada" — não é série histórica real, e não tem NENHUM ano em comum com
`qualidade_real_com_fallback_simulado` (CETESB real vai até 2024). Um merge
por (trecho, ano) hoje produziria 100% de NaN nas colunas de sensoriamento
para todo o histórico de treino — pior que inútil, um dropna sobre essas
colunas destruiria o conjunto de treino inteiro (o mesmo erro que o item 6
da auditoria de ML já corrigiu para vazão/chuva). Por isso esta tabela é
gravada separada: serve para (a) já deixar pronta a mecânica de fusão de
dado heterogêneo que a pesquisa precisa, e (b) uma leitura pontual "o que o
satélite mostra agora", sem contaminar o treino.

ATUALIZAÇÃO (2026-07, sensoriamento histórico REAL): `ingestion.connectors.sensoriamento_historico`
(Landsat Collection 2 via Google Earth Engine, 1984-presente) deixou de ser stub — quando
`bronze_sensoriamento_historico.run()` já foi executado, `silver.sensoriamento_historico` TEM
39+ anos em comum com a série real da CETESB. `sensoriamento_real_com_fallback_ilustrativo`
(abaixo) combina as duas fontes com prioridade para o dado real (mesmo padrão de
`qualidade_real_com_fallback_simulado`), e `build_indicadores_sensoriamento_anual` passou a
usar essa fusão em vez de ler `silver.sensoriamento` isolada. Mesmo assim, esta tabela
CONTINUA fora de `feature_store_ml_anual` por enquanto — não por falta de sobreposição
temporal (que agora existe), mas porque os índices espectrais (NDVI/proxy NDTI de
turbidez/temperatura) nunca foram calibrados contra medição in situ do Tietê (ver RESSALVA em
`ingestion.connectors.sensoriamento_historico`); usá-los como preditora de ML antes dessa
validação arriscaria o mesmo tipo de "ruído estrutural disfarçado de sinal" que o item 5 da
auditoria de ML já identificou para vazão do Baixo Tietê. Hoje `gold.sensoriamento_trecho_ano`
alimenta o Mapa Interativo do dashboard (`webapp/pages/1_Mapa_Interativo.py`), não o ML.

ACHADO DE PESQUISA (2026-07, uso do solo REAL como preditora de ML): diferente do
sensoriamento remoto acima, `silver.uso_solo` (MapBiomas real, via
`ingestion.bronze_uso_solo`/`ingestion.connectors.mapbiomas`, 1985-2023) TEM sobreposição
temporal real com a série de qualidade da água (CETESB 1978-2024) — 39 anos em comum. Por
isso, ao contrário do sensoriamento remoto, esta fonte É juntada a `feature_store_ml_anual`
(ver bloco de imputação de uso do solo dentro de `build_feature_store_ml_anual`): percentual
de área por macro-categoria (`pct_natural`/`pct_agropecuaria`/`pct_urbano_industrial`/
`pct_agua`) vira preditora real de ML, fechando a lacuna de "transformações no uso do solo"
como driver de qualidade da água que a pesquisa de pós-doutorado pede. Ver
`models.ml.features` para a lista de preditoras atualizada.

ACHADO DE AUDITORIA DE ML (2026-07): `iqa`/`od_mg_l`/`dbo_mg_l`/
`metais_pesados_ppm` só existem em granularidade ANUAL na fonte (tanto a
CETESB real quanto o fallback simulado) — `build_serie_temporal_trecho_mes`
repete o mesmo valor anual nos 12 meses do ano para poder casar com a
granularidade mensal de vazão/chuva no dashboard (isso é correto e honesto
para EXIBIÇÃO). Mas usar essa série repetida como base para `_lag1m` em
`build_feature_store_ml` é uma armadilha: como o valor é constante dentro do
ano, `iqa_lag1m` é literalmente igual ao alvo em 11 dos 12 meses — o modelo
antigo estava, na prática, copiando um valor já conhecido na maior parte do
tempo, não prevendo genuinamente (ver o baseline de persistência adicionado
em `models.ml.train` para essa mesma auditoria, que tornou isso visível nas
métricas). `build_feature_store_ml_anual` corrige isso: uma linha por
(trecho, ano), sem repetição — a mesma granularidade real da variável-alvo.
"""
from __future__ import annotations

import logging

import pandas as pd

from waterweave.config import FONTE_TIPO_OBSERVADO, FONTE_TIPO_SIMULADO, GOLD_DIR, SILVER_DIR, TRECHOS
from waterweave.io_delta import read_table, write_table

logger = logging.getLogger(__name__)

LAGS_MESES = (1, 3, 12)
LAGS_ANOS = (1, 2, 3)


def qualidade_real_com_fallback_simulado() -> pd.DataFrame:
    """Prioriza `silver.qualidade_cetesb` (real, CETESB 1978-2024) sobre `silver.qualidade`
    (simulado) por (trecho_id, ano) — o simulado só preenche anos sem medição real
    (majoritariamente 1940-1977, antes do início da série CETESB, e eventuais anos com
    cobertura real insuficiente). Ver ACHADO DE AUDITORIA em `ingestion.monthly_job` —
    antes desta função o dashboard/ABM/ML liam 100% do simulado."""
    real = read_table(SILVER_DIR / "qualidade_cetesb")
    simulado = read_table(SILVER_DIR / "qualidade")
    combinado = pd.concat([real, simulado], ignore_index=True)
    prioridade = combinado["fonte_tipo"].map({FONTE_TIPO_OBSERVADO: 0, FONTE_TIPO_SIMULADO: 1})
    combinado = combinado.assign(_prioridade=prioridade).sort_values(["trecho_id", "ano", "_prioridade"])
    combinado = combinado.drop_duplicates(subset=["trecho_id", "ano"], keep="first").drop(columns="_prioridade")
    return combinado.reset_index(drop=True)


def build_serie_temporal_trecho_mes() -> pd.DataFrame:
    """Junta vazão + chuva (agregadas por trecho/mês) com qualidade da água (anual, repetida
    por mês) e uso do solo real (MapBiomas, `silver.uso_solo` — ver ACHADO DE PESQUISA "uso do
    solo REAL" na docstring do módulo). As colunas `pct_*` ficam NaN fora da cobertura
    MapBiomas (antes de 1985/depois de 2023) — SEM imputação aqui (diferente de
    `build_feature_store_ml_anual`): esta tabela alimenta o ABM/dashboard, que já sabem cair
    para a classe `uso_solo` simulada quando o percentual real não existe (ver
    `models.hybrid_bridge.uso_solo_da_linha`)."""
    vazao = read_table(SILVER_DIR / "vazao_mensal")
    chuva = read_table(SILVER_DIR / "chuva_mensal")
    qualidade = qualidade_real_com_fallback_simulado()
    uso_solo_real = read_table(SILVER_DIR / "uso_solo")

    vazao_trecho = vazao.groupby(["trecho_id", "ano", "mes"], as_index=False).agg(
        vazao_m3s_medio=("vazao_m3s", "mean"), n_postos_vazao=("codigo_posto", "nunique")
    )
    chuva_trecho = chuva.groupby(["trecho_id", "ano", "mes"], as_index=False).agg(
        chuva_mm_media=("altura_mm", "mean"), n_postos_chuva=("codigo_posto", "nunique")
    )

    serie = pd.merge(vazao_trecho, chuva_trecho, on=["trecho_id", "ano", "mes"], how="outer")
    serie = serie.merge(qualidade, on=["trecho_id", "ano"], how="left", suffixes=("", "_qualidade"))
    if not uso_solo_real.empty:
        serie = serie.merge(uso_solo_real[["trecho_id", "ano", *COLUNAS_USO_SOLO]], on=["trecho_id", "ano"], how="left")
    else:
        for coluna in COLUNAS_USO_SOLO:
            serie[coluna] = pd.NA
    serie["mes_data"] = pd.to_datetime(dict(year=serie["ano"], month=serie["mes"], day=1))
    return serie.sort_values(["trecho_id", "mes_data"]).reset_index(drop=True)


def build_feature_store_ml(serie: pd.DataFrame) -> pd.DataFrame:
    """Deriva lags e média móvel de IQA/OD a partir de `serie_temporal_trecho_mes`, por trecho."""
    tabela = serie.sort_values(["trecho_id", "mes_data"]).copy()
    for coluna in ("iqa", "od_mg_l"):
        grupo = tabela.groupby("trecho_id")[coluna]
        for lag in LAGS_MESES:
            tabela[f"{coluna}_lag{lag}m"] = grupo.shift(lag)
        tabela[f"{coluna}_media_movel_12m"] = grupo.transform(lambda s: s.rolling(12, min_periods=3).mean())
    return tabela



# ACHADO DE AUDITORIA DE ML (item 6 — dropna agressivo): `montar_matriz_features_anual*`
# descarta a linha inteira se QUALQUER preditora estiver nula — para vazao_m3s_medio, isso
# penaliza desproporcionalmente Alto Tietê (~27% de anos sem medição) e Baixo Tietê (~10%),
# ver relatório de qualidade de dados hidrológicos. Preencher esses buracos com o último ano
# conhecido (forward-fill, LIMITADO a 2 anos consecutivos — nunca com mais que isso, para não
# inventar um regime hidrológico inteiro sobre uma lacuna grande) recupera linhas de treino
# sem inflar a confiança em anos realmente sem dado. NÃO se aplica aos lags/média móvel de
# iqa/od_mg_l: uma lacuna real ali significa "não sabemos o valor de X anos atrás", e
# imputar isso esconderia incerteza genuína sobre o próprio alvo, não sobre uma preditora
# exógena — ver docstring do módulo.
_LIMITE_PREENCHIMENTO_ANOS = 2

# Colunas de uso do solo real (MapBiomas, via `ingestion.bronze_uso_solo`/`silver_uso_solo`) —
# ver ACHADO DE PESQUISA "uso do solo REAL" na docstring do módulo. As 4 macro-categorias mais
# informativas para driver de qualidade da água entram como preditora; `pct_nao_vegetado_outro`
# e `pct_nao_observado` (catch-all/ruído de classificação) ficam de fora — ver
# `models.ml.features` para a lista de preditoras final.
COLUNAS_USO_SOLO = ["pct_natural", "pct_agropecuaria", "pct_urbano_industrial", "pct_agua"]

# Cobertura real do MapBiomas é 1985-2023 (`connectors.mapbiomas.ANO_MIN_COLECAO`/
# `ANO_MAX_COLECAO`); a série de qualidade real vai de 1978 a 2024 — as únicas lacunas
# possíveis são nas BORDAS: até 7 anos antes de 1985 (1978-1984) e alguns anos depois de 2023.
# Uso do solo muda muito mais devagar ano a ano que vazão/chuva (não há "seca de uso do solo"),
# então um limite maior que `_LIMITE_PREENCHIMENTO_ANOS` é defensável aqui — mas ainda LIMITADO
# (não `ffill`/`bfill` sem limite), para não estender uma distribuição de 1985 silenciosamente
# até 1940 se um trecho tiver uma lacuna maior que a esperada.
_LIMITE_PREENCHIMENTO_USO_SOLO_ANOS = 10

# Fração da vazão média histórica de um trecho usada como proxy de "captação necessária" — vale
# tanto para `models.abm.model.RioTieteModel.captacao_necessaria_m3s` (estresse hídrico) quanto
# para o serviço ecossistêmico de PROVISÃO HÍDRICA aqui (`build_servicos_ecossistemicos_historico`)
# — mesma régua nos dois lugares, ver `models.servicos_ecossistemicos`. NÃO é um dado real de
# outorga (o projeto não ingeriu registro de outorga/uso consuntivo real) — é uma aproximação
# documentada, definida aqui (a camada mais "de baixo" que os dois consumidores já importam,
# evitando um import circular: `hybrid_bridge`/`model.py` já importam `gold_features`, não o
# contrário).
FRACAO_VAZAO_CAPTACAO_NECESSARIA = 0.15


def build_feature_store_ml_anual() -> pd.DataFrame:
    """Feature store ANUAL para os modelos de ML — uma linha por (trecho, ano), sem repetição
    mensal. Substitui `build_feature_store_ml` como fonte de treino (ver ACHADO DE AUDITORIA
    DE ML na docstring do módulo).

    Constrói diretamente a partir de `qualidade_real_com_fallback_simulado` (já anual) e de
    vazão/chuva mensais agregadas ao ano inteiro — não passa por `serie_temporal_trecho_mes`
    (que existe para exibição mensal no dashboard, não para treino de modelo). Preenche
    lacunas curtas (até `_LIMITE_PREENCHIMENTO_ANOS` anos) de vazão/chuva por
    forward-fill dentro do trecho — ver ACHADO DE AUDITORIA DE ML item 6 acima. Desde 2026-07,
    junta também `silver.uso_solo` (MapBiomas real) — ver ACHADO DE PESQUISA "uso do solo
    REAL" acima — com preenchimento em AMBAS as direções (`ffill`+`bfill`, limitado a
    `_LIMITE_PREENCHIMENTO_USO_SOLO_ANOS`), porque a lacuna real fica nas BORDAS da série
    (antes de 1985, depois de 2023), não no meio."""
    qualidade = qualidade_real_com_fallback_simulado()
    vazao = read_table(SILVER_DIR / "vazao_mensal")
    chuva = read_table(SILVER_DIR / "chuva_mensal")
    uso_solo = read_table(SILVER_DIR / "uso_solo")

    vazao_anual = vazao.groupby(["trecho_id", "ano"], as_index=False).agg(
        vazao_m3s_medio=("vazao_m3s", "mean"), n_meses_vazao=("mes", "nunique")
    )
    chuva_anual = chuva.groupby(["trecho_id", "ano"], as_index=False).agg(
        chuva_mm_media=("altura_mm", "mean"), n_meses_chuva=("mes", "nunique")
    )

    tabela = qualidade.merge(vazao_anual, on=["trecho_id", "ano"], how="left")
    tabela = tabela.merge(chuva_anual, on=["trecho_id", "ano"], how="left")
    if not uso_solo.empty:
        tabela = tabela.merge(uso_solo[["trecho_id", "ano", *COLUNAS_USO_SOLO]], on=["trecho_id", "ano"], how="left")
    else:
        for coluna in COLUNAS_USO_SOLO:
            tabela[coluna] = pd.NA
    tabela = tabela.sort_values(["trecho_id", "ano"]).reset_index(drop=True)

    for coluna in ("vazao_m3s_medio", "chuva_mm_media"):
        preenchido = tabela.groupby("trecho_id")[coluna].transform(
            lambda s: s.ffill(limit=_LIMITE_PREENCHIMENTO_ANOS)
        )
        tabela[f"{coluna}_imputado"] = tabela[coluna].isna() & preenchido.notna()
        tabela[coluna] = preenchido

    for coluna in COLUNAS_USO_SOLO:
        preenchido = tabela.groupby("trecho_id")[coluna].transform(
            lambda s: s.ffill(limit=_LIMITE_PREENCHIMENTO_USO_SOLO_ANOS).bfill(limit=_LIMITE_PREENCHIMENTO_USO_SOLO_ANOS)
        )
        tabela[f"{coluna}_imputado"] = tabela[coluna].isna() & pd.notna(preenchido)
        tabela[coluna] = preenchido

    for coluna in ("iqa", "od_mg_l"):
        grupo = tabela.groupby("trecho_id")[coluna]
        for lag in LAGS_ANOS:
            tabela[f"{coluna}_lag{lag}a"] = grupo.shift(lag)
        tabela[f"{coluna}_media_movel_5a"] = grupo.transform(lambda s: s.rolling(5, min_periods=2).mean())

    return tabela


# Nomes de coluna estáveis (independentes do texto exato do `Parâmetro` na planilha fonte) —
# mesmo padrão de `silver_sensoriamento._ID_REGIAO_PARA_TRECHO`: mapa explícito em vez de
# normalizar o texto às cegas, porque "Turbidez" aqui e a `turbidez_ntu` de outro lugar do
# pipeline precisam continuar claramente distintas (esta é sensoriamento remoto, não medição
# in situ da CETESB) — daí o sufixo `_sensoriamento` onde poderia haver ambiguidade.
_PARAMETRO_SENSORIAMENTO_PARA_COLUNA = {
    "NDVI (Mata Ciliar)": "ndvi_mata_ciliar",
    "Turbidez": "turbidez_ntu_sensoriamento",
    "Clorofila-a": "clorofila_a_mg_m3",
    "Temperatura da Superfície": "temperatura_superficie_c",
    "Sólidos Suspensos Totais": "solidos_suspensos_totais_mg_l_sensoriamento",
    "Nível da Água Altimetria": "nivel_agua_m",
    # Landsat real (connectors.sensoriamento_historico) — NÃO é a mesma grandeza da "Turbidez"
    # em NTU acima (essa vem da planilha ilustrativa/simulada): é um índice espectral (NDTI)
    # nunca calibrado contra medição in situ, daí a coluna própria em vez de misturar as duas.
    "Turbidez (proxy NDTI, não calibrado)": "turbidez_proxy_ndti_sensoriamento",
}


def _normalizar_nome_parametro(parametro: str) -> str:
    """Fallback para um `Parâmetro` sem entrada em `_PARAMETRO_SENSORIAMENTO_PARA_COLUNA` —
    slug ascii/snake_case, para a coluna existir (e ser óbvia) em vez de a linha ser
    descartada silenciosamente."""
    import unicodedata

    sem_acento = unicodedata.normalize("NFKD", parametro).encode("ascii", "ignore").decode("ascii")
    return "_".join(filter(None, "".join(c if c.isalnum() else " " for c in sem_acento).lower().split()))


def sensoriamento_real_com_fallback_ilustrativo() -> pd.DataFrame:
    """Combina `silver.sensoriamento_historico` (real, Landsat 1984-presente) com
    `silver.sensoriamento` (ilustrativa/simulada, planilha 2026) por (id_regiao, ano,
    parametro) — mesmo padrão de `qualidade_real_com_fallback_simulado`: o dado real tem
    prioridade, a planilha simulada só preenche onde não existe medição real (na prática, hoje
    isso é sobretudo o próprio ano corrente, ainda sem imagem Landsat processada com qualidade
    definitiva). Retorna `silver.sensoriamento` (ilustrativa) sem alteração se a Bronze real
    ainda não foi materializada (`bronze_sensoriamento_historico.run()` nunca executado)."""
    ilustrativo = read_table(SILVER_DIR / "sensoriamento")
    real = read_table(SILVER_DIR / "sensoriamento_historico")
    if real.empty:
        return ilustrativo

    # `data_coleta` normalizada para datetime em AMBOS os lados antes do concat: a planilha
    # ilustrativa volta de `read_table` como string (round-trip Excel -> Delta), enquanto o
    # Landsat real já vem como Timestamp — sem normalizar aqui, o resultado combinado tem uma
    # coluna de tipo misto (Timestamp e str) que quebra qualquer consumidor a jusante que
    # espere `.dt`/`.year` direto (ver `webapp/pages/1_Mapa_Interativo.py`).
    real = real.assign(data_coleta=pd.to_datetime(real["data_coleta"]))
    ilustrativo = ilustrativo.assign(data_coleta=pd.to_datetime(ilustrativo["data_coleta"]))
    real = real.assign(ano=real["data_coleta"].dt.year, _prioridade=0)
    ilustrativo = ilustrativo.assign(ano=ilustrativo["data_coleta"].dt.year, _prioridade=1)

    combinado = pd.concat([real, ilustrativo], ignore_index=True)
    combinado = combinado.sort_values(["id_regiao", "ano", "parametro", "_prioridade"])
    combinado = combinado.drop_duplicates(subset=["id_regiao", "ano", "parametro"], keep="first")
    return combinado.drop(columns=["ano", "_prioridade"]).reset_index(drop=True)


def build_indicadores_sensoriamento_anual() -> pd.DataFrame:
    """Agrega o sensoriamento remoto (real com fallback ilustrativo, ver
    `sensoriamento_real_com_fallback_ilustrativo`) para uma linha por (trecho, ano) — ver
    ATUALIZAÇÃO na docstring do módulo para o porquê desta tabela ficar separada de
    `feature_store_ml_anual` por enquanto (índices espectrais ainda não calibrados, não falta
    de sobreposição temporal).

    Retorna DataFrame vazio se nem a fonte real nem a ilustrativa foram materializadas ainda
    (mesmo contrato de `io_delta.read_table` para tabela ausente)."""
    sensoriamento = sensoriamento_real_com_fallback_ilustrativo()
    if sensoriamento.empty:
        return sensoriamento

    tabela = sensoriamento.copy()
    tabela["ano"] = pd.to_datetime(tabela["data_coleta"]).dt.year
    tabela["coluna"] = tabela["parametro"].map(_PARAMETRO_SENSORIAMENTO_PARA_COLUNA)

    sem_mapeamento = tabela["coluna"].isna() & tabela["parametro"].notna()
    if sem_mapeamento.any():
        desconhecidos = sorted(tabela.loc[sem_mapeamento, "parametro"].unique())
        logger.warning(
            "Parâmetro(s) de sensoriamento sem entrada em _PARAMETRO_SENSORIAMENTO_PARA_COLUNA: "
            "%s — usando nome normalizado (slug) como fallback, em vez de descartar a linha.",
            desconhecidos,
        )
        tabela.loc[sem_mapeamento, "coluna"] = tabela.loc[sem_mapeamento, "parametro"].map(_normalizar_nome_parametro)

    agregado = (
        tabela.groupby(["trecho_id", "ano", "coluna"])["valor"]
        .mean()
        .unstack("coluna")
        .reset_index()
    )
    agregado.columns.name = None

    contagem = (
        tabela.groupby(["trecho_id", "ano"]).size().rename("n_observacoes_sensoriamento").reset_index()
    )
    # "observado" só se TODAS as observações do (trecho, ano) vieram do Landsat real —
    # transparência para o Mapa Interativo distinguir o que é medição real do que ainda é
    # preenchido pela planilha ilustrativa (ver `sensoriamento_real_com_fallback_ilustrativo`).
    fonte = (
        tabela.groupby(["trecho_id", "ano"])["fonte_tipo"]
        .apply(lambda s: s.iloc[0] if s.nunique() == 1 else "misto")
        .rename("sensoriamento_fonte_tipo")
        .reset_index()
    )
    resultado = agregado.merge(contagem, on=["trecho_id", "ano"], how="left")
    return resultado.merge(fonte, on=["trecho_id", "ano"], how="left")


def build_servicos_ecossistemicos_historico(features_anual: pd.DataFrame) -> pd.DataFrame:
    """Serviços ecossistêmicos REGULAÇÃO DA QUALIDADE DA ÁGUA e PROVISÃO HÍDRICA, calculados
    sobre o histórico REAL (uma linha por trecho/ano) — item 5 do roadmap de pesquisa
    WaterWeave-Water4All. Ver ACHADO DE PESQUISA em `models.servicos_ecossistemicos` para por
    que SUPORTE À BIODIVERSIDADE não entra aqui (falta série real de turbidez/toxicidade — só
    computável no braço simulado do ABM, ver `models.servicos_ecossistemicos.calcular_servicos_do_passo`).

    `captacao_necessaria_m3s` usa a MESMA aproximação já empregada pelo ABM
    (`models.abm.model.RioTieteModel.captacao_necessaria_m3s`, 15% da vazão média histórica do
    trecho) — não é um dado real de outorga, é a mesma simplificação documentada, aplicada aqui
    de forma consistente (para o serviço de provisão do histórico e o do ABM usarem a mesma
    régua)."""
    from waterweave.models import servicos_ecossistemicos as se

    colunas_base = ["trecho_id", "ano", "iqa", "vazao_m3s_medio"]
    if "fonte_tipo" in features_anual.columns:
        colunas_base.append("fonte_tipo")
    base = features_anual[colunas_base].copy()
    if base.empty:
        return base

    necessidade_por_trecho = base.groupby("trecho_id")["vazao_m3s_medio"].mean() * FRACAO_VAZAO_CAPTACAO_NECESSARIA
    base["captacao_necessaria_m3s"] = base["trecho_id"].map(necessidade_por_trecho)

    base["regulacao_qualidade_agua"] = base["iqa"].map(se.regulacao_qualidade_agua)
    base["provisao_hidrica"] = base.apply(
        lambda linha: se.provisao_hidrica(linha["vazao_m3s_medio"], linha["captacao_necessaria_m3s"]), axis=1
    )
    return base.sort_values(["trecho_id", "ano"]).reset_index(drop=True)


def build_estado_inicial_abm(serie: pd.DataFrame) -> pd.DataFrame:
    """Snapshot mais recente (com qualidade da água disponível) por trecho, para inicializar o ABM."""
    valido = serie.dropna(subset=["iqa"]).sort_values("mes_data")
    ultimo_por_trecho = valido.groupby("trecho_id", as_index=False).tail(1)
    return ultimo_por_trecho.reset_index(drop=True)


def run() -> dict[str, pd.DataFrame]:
    """Constrói e grava as cinco tabelas Gold, nessa ordem de dependência."""
    serie = build_serie_temporal_trecho_mes()
    write_table(GOLD_DIR / "serie_temporal_trecho_mes", serie, partition_by=["trecho_id"])

    features = build_feature_store_ml(serie)
    write_table(GOLD_DIR / "feature_store_ml", features, partition_by=["trecho_id"])

    features_anual = build_feature_store_ml_anual()
    write_table(GOLD_DIR / "feature_store_ml_anual", features_anual, partition_by=["trecho_id"])

    estado_inicial = build_estado_inicial_abm(serie)
    write_table(GOLD_DIR / "estado_inicial_abm", estado_inicial)

    sensoriamento_anual = build_indicadores_sensoriamento_anual()
    if not sensoriamento_anual.empty:
        write_table(GOLD_DIR / "sensoriamento_trecho_ano", sensoriamento_anual, partition_by=["trecho_id"])
    else:
        logger.info("gold.sensoriamento_trecho_ano não gravada: silver.sensoriamento ainda vazia.")

    servicos_ecossistemicos = build_servicos_ecossistemicos_historico(features_anual)
    if not servicos_ecossistemicos.empty:
        write_table(GOLD_DIR / "servicos_ecossistemicos_trecho_ano", servicos_ecossistemicos, partition_by=["trecho_id"])
    else:
        logger.info("gold.servicos_ecossistemicos_trecho_ano não gravada: feature_store_ml_anual ainda vazia.")

    return {
        "serie_temporal_trecho_mes": serie,
        "feature_store_ml": features,
        "feature_store_ml_anual": features_anual,
        "estado_inicial_abm": estado_inicial,
        "sensoriamento_trecho_ano": sensoriamento_anual,
        "servicos_ecossistemicos_trecho_ano": servicos_ecossistemicos,
    }


if __name__ == "__main__":
    run()
