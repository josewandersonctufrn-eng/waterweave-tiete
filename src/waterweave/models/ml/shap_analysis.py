"""Interpretabilidade (SHAP) dos modelos treinados em `models.ml.train`.

Explica os modelos (um por trecho × alvo — ver ACHADO DE AUDITORIA DE ML
item 2 em `models.ml.train`) sobre o MESMO conjunto de teste usado para
reportar MAE/R² em `train.py` (ano >= `ANO_CORTE_TESTE`) — nunca sobre o
conjunto de treino, para não confundir "o que o modelo memorizou" com "o que
o modelo usa para generalizar". Usa `shap.TreeExplainer`, exato e rápido para
ensembles de árvore (não precisa de dataset de referência/background como os
explicadores genéricos model-agnostic).

Opera sobre `gold.feature_store_ml_anual` (granularidade ANUAL — ver ACHADO
DE AUDITORIA DE ML em `transform.gold_features` e em `models.ml.train`): os
gráficos mostram `{alvo}_lag1a` (ano anterior), não `{alvo}_lag1m` (mês
anterior) — sem a repetição artificial do valor anual em 12 meses que
existia na versão mensal. Como os modelos agora são por trecho (não têm mais
`trecho_id` como preditora — cada modelo já é específico de um trecho), os
gráficos são gerados um a um para cada combinação trecho × alvo.
"""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap

from waterweave.config import GOLD_DIR, PROJECT_ROOT, TRECHOS
from waterweave.io_delta import read_table
from waterweave.models.ml.features import montar_matriz_features_anual_por_trecho
from waterweave.models.ml.train import ALVOS, ANO_CORTE_TESTE, MODELOS_DIR

logger = logging.getLogger(__name__)

SAIDA_DIR = PROJECT_ROOT / "data" / "models" / "shap"


def explicar_modelo(gold_df: pd.DataFrame, alvo: str, trecho_id: str, ano_corte_teste: int = ANO_CORTE_TESTE):
    """Calcula os SHAP values do modelo `trecho_id`/`alvo` (já treinado e salvo em
    `data/models/`) sobre o conjunto de teste (ano >= `ano_corte_teste`). Retorna
    (shap_values, X_teste_df, importancia_media_abs)."""
    X, y = montar_matriz_features_anual_por_trecho(gold_df, alvo, trecho_id)
    ano = gold_df.loc[X.index, "ano"]
    teste = ano >= ano_corte_teste
    X_teste = X[teste].reset_index(drop=True)

    modelo = joblib.load(MODELOS_DIR / f"{trecho_id}_{alvo}_model.joblib")

    explainer = shap.TreeExplainer(modelo)
    shap_values = explainer.shap_values(X_teste)

    importancia = pd.Series(np.abs(shap_values).mean(axis=0), index=X_teste.columns).sort_values(ascending=False)

    return shap_values, X_teste, importancia


def gerar_graficos(shap_values: np.ndarray, df_shap_input: pd.DataFrame, trecho_id: str, alvo: str, saida_dir: Path = SAIDA_DIR) -> tuple[Path, Path]:
    """Salva o gráfico de barras (importância média |SHAP|) e o beeswarm (distribuição do
    impacto por observação) do modelo `trecho_id`/`alvo`, como PNG."""
    saida_dir.mkdir(parents=True, exist_ok=True)
    prefixo = f"{trecho_id}_{alvo}"

    plt.figure()
    shap.summary_plot(shap_values, df_shap_input, plot_type="bar", show=False)
    caminho_barra = saida_dir / f"{prefixo}_shap_bar.png"
    plt.tight_layout()
    plt.savefig(caminho_barra, dpi=150)
    plt.close()

    plt.figure()
    shap.summary_plot(shap_values, df_shap_input, show=False)
    caminho_beeswarm = saida_dir / f"{prefixo}_shap_beeswarm.png"
    plt.tight_layout()
    plt.savefig(caminho_beeswarm, dpi=150)
    plt.close()

    return caminho_barra, caminho_beeswarm


def run() -> dict[str, pd.Series]:
    """Explica os modelos de todas as combinações trecho × `ALVOS`, salva os gráficos em
    `data/models/shap/` e retorna a importância média |SHAP| de cada um (chave =
    "trecho_id/alvo")."""
    gold_df = read_table(GOLD_DIR / "feature_store_ml_anual")
    resultados: dict[str, pd.Series] = {}
    for trecho_id in TRECHOS:
        for alvo in ALVOS:
            shap_values, df_shap_input, importancia = explicar_modelo(gold_df, alvo, trecho_id)
            gerar_graficos(shap_values, df_shap_input, trecho_id, alvo)
            chave = f"{trecho_id}/{alvo}"
            logger.info("SHAP de '%s' calculado (%d observações de teste).", chave, len(df_shap_input))
            resultados[chave] = importancia
    return resultados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for chave, importancia in run().items():
        print(f"\n--- Importância média |SHAP| — {chave} ---")
        print(importancia.to_string())
