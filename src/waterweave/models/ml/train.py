"""Treino dos modelos de ML que aceleram predições de qualidade da água.

Um `RandomForestRegressor` POR TRECHO (Alto/Médio/Baixo Tietê) sobre
`gold.feature_store_ml_anual` (uma linha por trecho/ano — ver ACHADO DE
AUDITORIA DE ML abaixo), com hiperparâmetros ajustados por busca em grade
(`GridSearchCV`) e split treino/teste por ANO (não aleatório) para não vazar
informação do futuro para o passado. Modelos são salvos em
`data/models/{trecho_id}_{alvo}_model.joblib`.

ACHADO DE AUDITORIA DE ML (2026-07, item 1 — vazamento de granularidade):
até a primeira correção, o treino usava `gold.feature_store_ml` (MENSAL), onde
iqa/od_mg_l são o mesmo valor anual repetido nos 12 meses do ano. Isso fazia
`{alvo}_lag1m` ser literalmente igual ao alvo em 11 dos 12 meses — o modelo
estava, na prática, copiando um valor já conhecido na maior parte do tempo.
Corrigido trocando a fonte para `gold.feature_store_ml_anual`, que tem uma
linha por (trecho, ano) e lags em ANOS (`{alvo}_lag1a/2a/3a`) — sem repetição.

ACHADO DE AUDITORIA DE ML (item 2 — generalização espacial): o teste de
generalização cruzada entre trechos (Seção 23 do relatório de EDA) mostrou
que um modelo único treinado num trecho tem R² NEGATIVO quando testado em
outro (de -0,13 a -5,31) — a relação entre as preditoras e o alvo muda de
patamar/inclinação entre Alto/Médio/Baixo Tietê. Um único `RandomForest` com
`trecho_id` como feature categórica está tentando aprender essas 3 relações
distintas ao mesmo tempo. Corrigido treinando um modelo independente por
trecho (`treinar_modelo_trecho`), cada um só vendo os dados daquele trecho.

ACHADO DE AUDITORIA DE ML (item 3 — hiperparâmetros nunca ajustados): antes
desta correção, `n_estimators`/`max_depth` eram fixos "no olho" (200/8) para
todos os modelos. Corrigido com `GridSearchCV` (validação cruzada de 5 folds,
métrica MAE) sobre o conjunto de treino de cada trecho/alvo — com um dataset
tão pequeno (~65 anos de treino por trecho), o ganho de ajustar o modelo aos
dados reais supera o custo computacional, que é irrelevante aqui.

BASELINE DE PERSISTÊNCIA (mesma auditoria, item 1): mesmo sem o vazamento
mensal, `{alvo}_lag1a` (o valor do ano anterior) ainda é a feature mais forte
em qualquer série com autocorrelação temporal — comparar contra esse baseline
trivial ("previsto = valor do ano passado") é o que mostra se o RandomForest
está agregando algo além disso. `treinar_modelo_trecho` calcula esse baseline
no MESMO conjunto de teste; `run()` registra um aviso se o RandomForest não
superar o baseline por margem clara, PARA CADA trecho.
"""
from __future__ import annotations

import logging

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV

from waterweave.config import GOLD_DIR, PROJECT_ROOT, TRECHOS
from waterweave.io_delta import read_table
from waterweave.models.ml.features import montar_matriz_features_anual_por_trecho

logger = logging.getLogger(__name__)

MODELOS_DIR = PROJECT_ROOT / "data" / "models"
ALVOS = ("iqa", "od_mg_l")
ANO_CORTE_TESTE = 2015
# Margem mínima de melhora de MAE sobre o baseline de persistência para o modelo ser
# considerado "agregando valor" de fato, não só reproduzindo o ano passado. 5% é
# deliberadamente conservador — o objetivo é sinalizar dúvida, não travar o pipeline.
MARGEM_MINIMA_SOBRE_BASELINE = 0.05

# Grade de busca deliberadamente modesta: com ~65 linhas de treino por trecho, uma grade
# grande só encontraria combinações que se ajustam ao ruído da validação cruzada, não um
# padrão real. `max_features` limita quantas preditoras cada árvore vê por divisão (reduz
# variância entre árvores); `min_samples_leaf` > 1 evita folhas de uma amostra só, comuns em
# datasets pequenos e um sintoma clássico de overfitting em árvores.
GRADE_HIPERPARAMETROS = {
    "n_estimators": [100, 200, 300],
    "max_depth": [3, 4, 6, None],
    "min_samples_leaf": [1, 2, 4],
    "max_features": ["sqrt", 0.5, 1.0],
}
CV_FOLDS = 5


def _metricas_regressao(y_real: pd.Series, y_predito) -> dict:
    return {
        "mae": float(mean_absolute_error(y_real, y_predito)),
        "rmse": float(np.sqrt(mean_squared_error(y_real, y_predito))),
        "r2": float(r2_score(y_real, y_predito)),
    }


def _buscar_melhor_modelo(X_treino: pd.DataFrame, y_treino: pd.Series) -> GridSearchCV:
    """Busca em grade (5-fold CV, otimizando MAE) sobre `GRADE_HIPERPARAMETROS`."""
    busca = GridSearchCV(
        RandomForestRegressor(random_state=42),
        GRADE_HIPERPARAMETROS,
        scoring="neg_mean_absolute_error",
        cv=CV_FOLDS,
        n_jobs=-1,
    )
    busca.fit(X_treino, y_treino)
    return busca


def treinar_modelo_trecho(gold_df: pd.DataFrame, alvo: str, trecho_id: str, ano_corte_teste: int = ANO_CORTE_TESTE) -> tuple[RandomForestRegressor, dict]:
    """Treina (com busca de hiperparâmetros) e retorna (modelo, métricas) para prever `alvo`
    dentro de UM trecho — ver ACHADO DE AUDITORIA DE ML item 2 na docstring do módulo.

    As métricas incluem, além do desempenho do RandomForest, o baseline de persistência
    ("previsto = valor do ano anterior", `{alvo}_lag1a`) no MESMO conjunto de teste."""
    X, y = montar_matriz_features_anual_por_trecho(gold_df, alvo, trecho_id)
    ano = gold_df.loc[X.index, "ano"]
    treino, teste = ano < ano_corte_teste, ano >= ano_corte_teste

    busca = _buscar_melhor_modelo(X[treino], y[treino])
    modelo = busca.best_estimator_

    metricas: dict = {
        "n_treino": int(treino.sum()),
        "n_teste": int(teste.sum()),
        "melhores_hiperparametros": busca.best_params_,
        "mae_cv_treino": round(float(-busca.best_score_), 4),
    }
    if teste.sum() > 0:
        predito = modelo.predict(X[teste])
        metricas.update(_metricas_regressao(y[teste], predito))

        coluna_lag1a = f"{alvo}_lag1a"
        if coluna_lag1a in X.columns:
            baseline_predito = X.loc[teste, coluna_lag1a]
            metricas_baseline = _metricas_regressao(y[teste], baseline_predito)
            metricas["mae_baseline_persistencia"] = metricas_baseline["mae"]
            metricas["rmse_baseline_persistencia"] = metricas_baseline["rmse"]
            metricas["r2_baseline_persistencia"] = metricas_baseline["r2"]

            if metricas_baseline["mae"] > 0:
                reducao_mae = 1 - (metricas["mae"] / metricas_baseline["mae"])
                metricas["reducao_mae_vs_baseline_pct"] = round(reducao_mae * 100, 1)
                metricas["supera_baseline_com_margem"] = reducao_mae >= MARGEM_MINIMA_SOBRE_BASELINE
            else:
                metricas["reducao_mae_vs_baseline_pct"] = None
                metricas["supera_baseline_com_margem"] = None
        else:
            logger.warning(
                "Baseline de persistência não calculado para '%s/%s': coluna '%s' ausente em X.",
                trecho_id, alvo, coluna_lag1a,
            )

    return modelo, metricas


def run() -> dict[str, dict]:
    """Treina um modelo por (trecho, alvo) e salva em `data/models/{trecho_id}_{alvo}_model.joblib`."""
    gold_df = read_table(GOLD_DIR / "feature_store_ml_anual")
    MODELOS_DIR.mkdir(parents=True, exist_ok=True)

    resultados = {}
    for trecho_id in TRECHOS:
        for alvo in ALVOS:
            chave = f"{trecho_id}/{alvo}"
            modelo, metricas = treinar_modelo_trecho(gold_df, alvo, trecho_id)
            joblib.dump(modelo, MODELOS_DIR / f"{trecho_id}_{alvo}_model.joblib")
            logger.info("Modelo '%s' treinado: %s", chave, metricas)

            if metricas.get("supera_baseline_com_margem") is False:
                logger.warning(
                    "Modelo '%s': MAE (%.4f) não reduz o baseline de persistência (%.4f) em pelo menos "
                    "%.0f%% (redução real: %.1f%%). O RandomForest pode estar apenas reproduzindo a "
                    "autocorrelação da série (ver docstring de train.py) — considere isso antes de usar "
                    "este modelo/SHAP para decisão.",
                    chave, metricas["mae"], metricas["mae_baseline_persistencia"],
                    MARGEM_MINIMA_SOBRE_BASELINE * 100, metricas["reducao_mae_vs_baseline_pct"],
                )
            resultados[chave] = metricas
    return resultados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for chave, metricas in run().items():
        print(f"{chave}: {metricas}")
