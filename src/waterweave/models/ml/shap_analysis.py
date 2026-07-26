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

from sklearn.ensemble import RandomForestRegressor

from waterweave.config import GOLD_DIR, PROJECT_ROOT, TRECHOS
from waterweave.io_delta import read_table
from waterweave.models.ml.features import (
    montar_matriz_features_anual_por_trecho,
    montar_matriz_features_drivers_por_trecho,
)
from waterweave.models.ml.train import ALVOS, ANO_CORTE_TESTE, MODELOS_DIR

logger = logging.getLogger(__name__)

SAIDA_DIR = PROJECT_ROOT / "data" / "models" / "shap"

# Hiperparâmetros fixos (não GridSearchCV) para o modelo drivers do item 8 — este modelo é
# puramente diagnóstico (não vai para produção nem é comparado por MAE/R² contra baseline),
# então não vale o custo de uma busca em grade; valores modestos evitam overfitting no dataset
# pequeno (~65 anos) sem preditoras de lag para "segurar" a variância.
_HIPERPARAMETROS_DRIVERS = dict(n_estimators=300, max_depth=4, min_samples_leaf=2, random_state=42)


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


def gerar_graficos(
    shap_values: np.ndarray,
    df_shap_input: pd.DataFrame,
    trecho_id: str,
    alvo: str,
    saida_dir: Path = SAIDA_DIR,
    sufixo: str = "",
) -> tuple[Path, Path]:
    """Salva o gráfico de barras (importância média |SHAP|) e o beeswarm (distribuição do
    impacto por observação) do modelo `trecho_id`/`alvo`, como PNG. `sufixo` (ex.:
    "_drivers") distingue os gráficos do modelo diagnóstico (item 8) dos de produção."""
    saida_dir.mkdir(parents=True, exist_ok=True)
    prefixo = f"{trecho_id}_{alvo}{sufixo}"

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


def explicar_modelo_drivers(gold_df: pd.DataFrame, alvo: str, trecho_id: str, ano_corte_teste: int = ANO_CORTE_TESTE):
    """SHAP diagnóstico SEM os lags do próprio alvo (só ano/vazão/chuva) — ver ACHADO DE
    AUDITORIA DE ML item 8 em `models.ml.features`. `{alvo}_lag1a` domina o SHAP do modelo de
    produção só por autocorrelação temporal genuína, o que é adequado para PREVISÃO mas não
    responde "o que reduz a poluição" — este modelo treina um RandomForest AD-HOC (hiperparâmetros
    fixos, NÃO salvo em `data/models/`, NÃO é o modelo de produção) só sobre os drivers
    exógenos, para uma leitura de interpretabilidade menos dominada pelo "eco" do próprio alvo.

    Treina sobre o MESMO corte treino/teste (`ano_corte_teste`) do modelo de produção, para
    manter os SHAP comparáveis entre as duas versões, mas SEM busca de hiperparâmetros (ver
    `_HIPERPARAMETROS_DRIVERS`) e sem restringir a `fonte_tipo == "observado"` — aqui o
    objetivo é ler a relação entre driver e alvo em todo o histórico disponível, não estimar
    erro de generalização. Retorna (shap_values, X_teste_df, importancia_media_abs)."""
    X, y = montar_matriz_features_drivers_por_trecho(gold_df, alvo, trecho_id)
    ano = gold_df.loc[X.index, "ano"]
    treino, teste = ano < ano_corte_teste, ano >= ano_corte_teste
    if teste.sum() == 0:
        raise ValueError(f"Sem anos de teste (>= {ano_corte_teste}) para '{trecho_id}/{alvo}' no modelo drivers.")

    modelo = RandomForestRegressor(**_HIPERPARAMETROS_DRIVERS)
    modelo.fit(X[treino], y[treino])

    X_teste = X[teste].reset_index(drop=True)
    explainer = shap.TreeExplainer(modelo)
    shap_values = explainer.shap_values(X_teste)

    importancia = pd.Series(np.abs(shap_values).mean(axis=0), index=X_teste.columns).sort_values(ascending=False)

    return shap_values, X_teste, importancia


def run(incluir_drivers: bool = True) -> dict[str, pd.Series]:
    """Explica os modelos de todas as combinações trecho × `ALVOS`, salva os gráficos em
    `data/models/shap/` e retorna a importância média |SHAP| de cada um (chave =
    "trecho_id/alvo"). Se `incluir_drivers` (item 8), também calcula e salva o SHAP do modelo
    diagnóstico sem lags do alvo, sob a chave "trecho_id/alvo/drivers" — ver
    `explicar_modelo_drivers`."""
    gold_df = read_table(GOLD_DIR / "feature_store_ml_anual")
    resultados: dict[str, pd.Series] = {}
    for trecho_id in TRECHOS:
        for alvo in ALVOS:
            shap_values, df_shap_input, importancia = explicar_modelo(gold_df, alvo, trecho_id)
            gerar_graficos(shap_values, df_shap_input, trecho_id, alvo)
            chave = f"{trecho_id}/{alvo}"
            logger.info("SHAP de '%s' calculado (%d observações de teste).", chave, len(df_shap_input))
            resultados[chave] = importancia

            if incluir_drivers:
                try:
                    shap_d, X_d, importancia_d = explicar_modelo_drivers(gold_df, alvo, trecho_id)
                except ValueError as erro:
                    logger.warning("SHAP drivers de '%s' não calculado: %s", chave, erro)
                    continue
                gerar_graficos(shap_d, X_d, trecho_id, alvo, sufixo="_drivers")
                chave_drivers = f"{chave}/drivers"
                logger.info(
                    "SHAP drivers (diagnóstico, item 8) de '%s' calculado (%d observações de teste).",
                    chave_drivers, len(X_d),
                )
                resultados[chave_drivers] = importancia_d
    return resultados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for chave, importancia in run().items():
        print(f"\n--- Importância média |SHAP| — {chave} ---")
        print(importancia.to_string())
