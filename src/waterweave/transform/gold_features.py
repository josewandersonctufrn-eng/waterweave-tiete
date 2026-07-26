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
    média móvel de IQA/OD em ANOS — fonte de treino correta e atual dos
    modelos de ML (ver `models.ml.train`).
  - `gold.estado_inicial_abm`: snapshot mais recente por trecho, usado para
    inicializar o `Model` do Mesa a cada rodada de simulação.

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

import pandas as pd

from waterweave.config import FONTE_TIPO_OBSERVADO, FONTE_TIPO_SIMULADO, GOLD_DIR, SILVER_DIR, TRECHOS
from waterweave.io_delta import read_table, write_table

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
    """Junta vazão + chuva (agregadas por trecho/mês) com qualidade da água (anual, repetida por mês)."""
    vazao = read_table(SILVER_DIR / "vazao_mensal")
    chuva = read_table(SILVER_DIR / "chuva_mensal")
    qualidade = qualidade_real_com_fallback_simulado()

    vazao_trecho = vazao.groupby(["trecho_id", "ano", "mes"], as_index=False).agg(
        vazao_m3s_medio=("vazao_m3s", "mean"), n_postos_vazao=("codigo_posto", "nunique")
    )
    chuva_trecho = chuva.groupby(["trecho_id", "ano", "mes"], as_index=False).agg(
        chuva_mm_media=("altura_mm", "mean"), n_postos_chuva=("codigo_posto", "nunique")
    )

    serie = pd.merge(vazao_trecho, chuva_trecho, on=["trecho_id", "ano", "mes"], how="outer")
    serie = serie.merge(qualidade, on=["trecho_id", "ano"], how="left", suffixes=("", "_qualidade"))
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


def build_feature_store_ml_anual() -> pd.DataFrame:
    """Feature store ANUAL para os modelos de ML — uma linha por (trecho, ano), sem repetição
    mensal. Substitui `build_feature_store_ml` como fonte de treino (ver ACHADO DE AUDITORIA
    DE ML na docstring do módulo).

    Constrói diretamente a partir de `qualidade_real_com_fallback_simulado` (já anual) e de
    vazão/chuva mensais agregadas ao ano inteiro — não passa por `serie_temporal_trecho_mes`
    (que existe para exibição mensal no dashboard, não para treino de modelo). Preenche
    lacunas curtas (até `_LIMITE_PREENCHIMENTO_ANOS` anos) de vazão/chuva por
    forward-fill dentro do trecho — ver ACHADO DE AUDITORIA DE ML item 6 acima."""
    qualidade = qualidade_real_com_fallback_simulado()
    vazao = read_table(SILVER_DIR / "vazao_mensal")
    chuva = read_table(SILVER_DIR / "chuva_mensal")

    vazao_anual = vazao.groupby(["trecho_id", "ano"], as_index=False).agg(
        vazao_m3s_medio=("vazao_m3s", "mean"), n_meses_vazao=("mes", "nunique")
    )
    chuva_anual = chuva.groupby(["trecho_id", "ano"], as_index=False).agg(
        chuva_mm_media=("altura_mm", "mean"), n_meses_chuva=("mes", "nunique")
    )

    tabela = qualidade.merge(vazao_anual, on=["trecho_id", "ano"], how="left")
    tabela = tabela.merge(chuva_anual, on=["trecho_id", "ano"], how="left")
    tabela = tabela.sort_values(["trecho_id", "ano"]).reset_index(drop=True)

    for coluna in ("vazao_m3s_medio", "chuva_mm_media"):
        preenchido = tabela.groupby("trecho_id")[coluna].transform(
            lambda s: s.ffill(limit=_LIMITE_PREENCHIMENTO_ANOS)
        )
        tabela[f"{coluna}_imputado"] = tabela[coluna].isna() & preenchido.notna()
        tabela[coluna] = preenchido

    for coluna in ("iqa", "od_mg_l"):
        grupo = tabela.groupby("trecho_id")[coluna]
        for lag in LAGS_ANOS:
            tabela[f"{coluna}_lag{lag}a"] = grupo.shift(lag)
        tabela[f"{coluna}_media_movel_5a"] = grupo.transform(lambda s: s.rolling(5, min_periods=2).mean())

    return tabela


def build_estado_inicial_abm(serie: pd.DataFrame) -> pd.DataFrame:
    """Snapshot mais recente (com qualidade da água disponível) por trecho, para inicializar o ABM."""
    valido = serie.dropna(subset=["iqa"]).sort_values("mes_data")
    ultimo_por_trecho = valido.groupby("trecho_id", as_index=False).tail(1)
    return ultimo_por_trecho.reset_index(drop=True)


def run() -> dict[str, pd.DataFrame]:
    """Constrói e grava as quatro tabelas Gold, nessa ordem de dependência."""
    serie = build_serie_temporal_trecho_mes()
    write_table(GOLD_DIR / "serie_temporal_trecho_mes", serie, partition_by=["trecho_id"])

    features = build_feature_store_ml(serie)
    write_table(GOLD_DIR / "feature_store_ml", features, partition_by=["trecho_id"])

    features_anual = build_feature_store_ml_anual()
    write_table(GOLD_DIR / "feature_store_ml_anual", features_anual, partition_by=["trecho_id"])

    estado_inicial = build_estado_inicial_abm(serie)
    write_table(GOLD_DIR / "estado_inicial_abm", estado_inicial)

    return {
        "serie_temporal_trecho_mes": serie,
        "feature_store_ml": features,
        "feature_store_ml_anual": features_anual,
        "estado_inicial_abm": estado_inicial,
    }


if __name__ == "__main__":
    run()
