"""Treino dos modelos de ML que aceleram predições de qualidade da água.

`RandomForestRegressor` sobre `gold.feature_store_ml`, com split treino/teste
por ANO (não aleatório) para não vazar informação do futuro para o passado —
relevante mesmo em um dataset simulado, como boa prática a manter quando a
fonte virar observação real. Modelos são salvos em `data/models/*.joblib`.
"""
from __future__ import annotations

import logging

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from waterweave.config import GOLD_DIR, PROJECT_ROOT
from waterweave.io_delta import read_table
from waterweave.models.ml.features import PREDITORA_CATEGORICA, montar_matriz_features

logger = logging.getLogger(__name__)

MODELOS_DIR = PROJECT_ROOT / "data" / "models"
ALVOS = ("iqa", "od_mg_l")
ANO_CORTE_TESTE = 2015


def _pipeline() -> Pipeline:
    pre = ColumnTransformer(
        [("trecho", OneHotEncoder(handle_unknown="ignore"), [PREDITORA_CATEGORICA])],
        remainder="passthrough",
    )
    modelo = RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42)
    return Pipeline([("pre", pre), ("regressor", modelo)])


def treinar_modelo_qualidade(gold_df: pd.DataFrame, alvo: str, ano_corte_teste: int = ANO_CORTE_TESTE) -> tuple[Pipeline, dict]:
    """Treina e retorna (modelo, métricas) para prever a variável `alvo` de qualidade da água."""
    X, y = montar_matriz_features(gold_df, alvo)
    ano = gold_df.loc[X.index, "ano"]
    treino, teste = ano < ano_corte_teste, ano >= ano_corte_teste

    modelo = _pipeline()
    modelo.fit(X[treino], y[treino])

    metricas: dict = {"n_treino": int(treino.sum()), "n_teste": int(teste.sum())}
    if teste.sum() > 0:
        predito = modelo.predict(X[teste])
        metricas["mae"] = float(mean_absolute_error(y[teste], predito))
        metricas["r2"] = float(r2_score(y[teste], predito))

    return modelo, metricas


def run() -> dict[str, dict]:
    """Treina os modelos de todos os `ALVOS` e salva em `data/models/`."""
    gold_df = read_table(GOLD_DIR / "feature_store_ml")
    MODELOS_DIR.mkdir(parents=True, exist_ok=True)

    resultados = {}
    for alvo in ALVOS:
        modelo, metricas = treinar_modelo_qualidade(gold_df, alvo)
        joblib.dump(modelo, MODELOS_DIR / f"{alvo}_model.joblib")
        logger.info("Modelo '%s' treinado: %s", alvo, metricas)
        resultados[alvo] = metricas
    return resultados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())
