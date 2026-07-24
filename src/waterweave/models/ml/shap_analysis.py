"""Interpretabilidade (SHAP) dos modelos treinados em `models.ml.train`.

Explica os dois modelos (IQA e OD) sobre o MESMO conjunto de teste usado para
reportar MAE/R² em `train.py` (ano >= `ANO_CORTE_TESTE`) — nunca sobre o
conjunto de treino, para não confundir "o que o modelo memorizou" com "o que
o modelo usa para generalizar". Usa `shap.TreeExplainer`, exato e rápido para
ensembles de árvore (não precisa de dataset de referência/background como os
explicadores genéricos model-agnostic).
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

from waterweave.config import GOLD_DIR, PROJECT_ROOT
from waterweave.io_delta import read_table
from waterweave.models.ml.features import montar_matriz_features
from waterweave.models.ml.train import ALVOS, ANO_CORTE_TESTE, MODELOS_DIR

logger = logging.getLogger(__name__)

SAIDA_DIR = PROJECT_ROOT / "data" / "models" / "shap"


def _nome_limpo(nome_coluna_transformada: str) -> str:
    """Remove o prefixo que o `ColumnTransformer` adiciona (ex.: "remainder__mes" -> "mes")."""
    return nome_coluna_transformada.split("__", 1)[-1]


def explicar_modelo(gold_df: pd.DataFrame, alvo: str, ano_corte_teste: int = ANO_CORTE_TESTE):
    """Calcula os SHAP values do modelo `alvo` (já treinado e salvo em `data/models/`) sobre o
    conjunto de teste (ano >= `ano_corte_teste`). Retorna (shap_values, X_teste_df,
    importancia_media_abs) — `X_teste_df` mantém os valores originais (não codificados) das
    features, para os gráficos exibirem números interpretáveis (ex.: "mês 7"), não o one-hot."""
    X, y = montar_matriz_features(gold_df, alvo)
    ano = gold_df.loc[X.index, "ano"]
    teste = ano >= ano_corte_teste
    X_teste = X[teste].reset_index(drop=True)

    modelo = joblib.load(MODELOS_DIR / f"{alvo}_model.joblib")
    pre = modelo.named_steps["pre"]
    regressor = modelo.named_steps["regressor"]

    X_teste_transformada = pre.transform(X_teste)
    nomes_features = [_nome_limpo(n) for n in pre.get_feature_names_out()]

    explainer = shap.TreeExplainer(regressor)
    shap_values = explainer.shap_values(X_teste_transformada)

    df_shap_input = pd.DataFrame(X_teste_transformada, columns=nomes_features)
    importancia = pd.Series(np.abs(shap_values).mean(axis=0), index=nomes_features).sort_values(ascending=False)

    return shap_values, df_shap_input, importancia


def gerar_graficos(shap_values: np.ndarray, df_shap_input: pd.DataFrame, alvo: str, saida_dir: Path = SAIDA_DIR) -> tuple[Path, Path]:
    """Salva o gráfico de barras (importância média |SHAP|) e o beeswarm (distribuição do
    impacto por observação) do modelo `alvo`, como PNG."""
    saida_dir.mkdir(parents=True, exist_ok=True)

    plt.figure()
    shap.summary_plot(shap_values, df_shap_input, plot_type="bar", show=False)
    caminho_barra = saida_dir / f"{alvo}_shap_bar.png"
    plt.tight_layout()
    plt.savefig(caminho_barra, dpi=150)
    plt.close()

    plt.figure()
    shap.summary_plot(shap_values, df_shap_input, show=False)
    caminho_beeswarm = saida_dir / f"{alvo}_shap_beeswarm.png"
    plt.tight_layout()
    plt.savefig(caminho_beeswarm, dpi=150)
    plt.close()

    return caminho_barra, caminho_beeswarm


def run() -> dict[str, pd.Series]:
    """Explica os modelos de todos os `ALVOS`, salva os gráficos em `data/models/shap/` e
    retorna a importância média |SHAP| de cada um (chave = alvo)."""
    gold_df = read_table(GOLD_DIR / "feature_store_ml")
    resultados: dict[str, pd.Series] = {}
    for alvo in ALVOS:
        shap_values, df_shap_input, importancia = explicar_modelo(gold_df, alvo)
        gerar_graficos(shap_values, df_shap_input, alvo)
        logger.info("SHAP de '%s' calculado (%d observações de teste).", alvo, len(df_shap_input))
        resultados[alvo] = importancia
    return resultados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for alvo_nome, importancia in run().items():
        print(f"\n--- Importância média |SHAP| — {alvo_nome} ---")
        print(importancia.to_string())
