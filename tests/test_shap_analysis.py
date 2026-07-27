"""Teste de guarda do SHAP diagnóstico sem lags do alvo (`models.ml.shap_analysis`, ACHADO DE
AUDITORIA DE ML item 8). Não valida os valores SHAP em si (sem sentido em dado sintético
pequeno) — valida que o modelo "drivers" realmente não vê nenhuma coluna de lag/média móvel do
alvo, que é o próprio ponto do item 8 (SHAP dominado por autocorrelação, não por driver real).
"""
from __future__ import annotations

import pytest

pytest.importorskip("sklearn")
pytest.importorskip("shap")

from waterweave.models.ml.shap_analysis import explicar_modelo_drivers


def test_shap_drivers_nao_usa_nenhuma_coluna_de_lag_do_alvo(gold_df_sintetico):
    gold = gold_df_sintetico()
    shap_values, X_teste, importancia = explicar_modelo_drivers(gold, "iqa", "alto_tiete")

    assert not any("lag" in col or "media_movel" in col for col in X_teste.columns)
    assert set(X_teste.columns) <= {
        "ano", "vazao_m3s_medio", "chuva_mm_media",
        "pct_natural", "pct_agropecuaria", "pct_urbano_industrial", "pct_agua",
    }
    assert shap_values.shape[0] == len(X_teste)
    assert shap_values.shape[1] == len(X_teste.columns)
    assert set(importancia.index) == set(X_teste.columns)


def test_explicar_modelo_drivers_levanta_erro_sem_anos_de_teste(gold_df_sintetico):
    """Se `ano_corte_teste` for maior que qualquer ano disponível, a função deve falhar de
    forma explícita (`ValueError`), não silenciosamente retornar um SHAP vazio ou quebrar com
    um erro genérico do sklearn/shap difícil de diagnosticar."""
    gold = gold_df_sintetico()
    with pytest.raises(ValueError):
        explicar_modelo_drivers(gold, "iqa", "alto_tiete", ano_corte_teste=3000)
