"""Testes de guarda das preditoras de ML (`models.ml.features`) — cobrem os achados de
auditoria que mudam QUAIS colunas entram no modelo. Não envolvem `RandomForestRegressor`
(ver `test_ml_train.py` para a mecânica de treino/avaliação), só pandas puro — mais rápidos e
sem dependência de sklearn instalado.
"""
from __future__ import annotations

import pandas as pd

from waterweave.models.ml.features import (
    TRECHOS_SEM_VAZAO_CONFIAVEL,
    montar_matriz_features_anual_por_trecho,
    montar_matriz_features_drivers_por_trecho,
    preditoras_anuais_do_trecho,
    preditoras_drivers_do_trecho,
)


def _gold_df_sintetico() -> pd.DataFrame:
    """DataFrame no formato de `gold.feature_store_ml_anual`, com `alto_tiete` (vazão
    confiável) e `baixo_tiete` (vazão NÃO confiável — item 5). Uma linha de `alto_tiete` tem
    `vazao_m3s_medio` nula, para exercitar o dropna sem interferir no lag/média móvel."""
    linhas = []
    for trecho_id in ("alto_tiete", "baixo_tiete"):
        for i, ano in enumerate(range(2010, 2020)):
            linhas.append(
                {
                    "trecho_id": trecho_id,
                    "ano": ano,
                    "vazao_m3s_medio": None if (trecho_id == "alto_tiete" and i == 5) else 10.0 + i,
                    "chuva_mm_media": 100.0 + i,
                    "pct_natural": 20.0,
                    "pct_agropecuaria": 50.0,
                    "pct_urbano_industrial": 25.0,
                    "pct_agua": 5.0,
                    "iqa": 60.0 + i,
                    "iqa_lag1a": 59.0 + i,
                    "iqa_lag2a": 58.0 + i,
                    "iqa_lag3a": 57.0 + i,
                    "iqa_media_movel_5a": 60.0 + i,
                    "od_mg_l": 6.0 + i * 0.1,
                    "od_mg_l_lag1a": 5.9 + i * 0.1,
                    "od_mg_l_lag2a": 5.8 + i * 0.1,
                    "od_mg_l_lag3a": 5.7 + i * 0.1,
                    "od_mg_l_media_movel_5a": 6.0 + i * 0.1,
                    "fonte_tipo": "observado",
                }
            )
    return pd.DataFrame(linhas)


def test_baixo_tiete_nao_usa_vazao_como_preditora():
    """ACHADO item 5: a série de vazão do Baixo Tietê tem inconsistência estrutural (curva de
    dupla massa quebrada, Q5/Q95 muito abaixo dos outros trechos) — não pode entrar como
    preditora nesse trecho, nem na matriz de produção nem na de drivers."""
    assert "baixo_tiete" in TRECHOS_SEM_VAZAO_CONFIAVEL
    assert "vazao_m3s_medio" not in preditoras_anuais_do_trecho("baixo_tiete")
    assert "vazao_m3s_medio" not in preditoras_drivers_do_trecho("baixo_tiete")


def test_outros_trechos_mantem_vazao_como_preditora():
    """A remoção do item 5 é ESPECÍFICA do Baixo Tietê — Alto/Médio Tietê não podem perder a
    preditora por engano numa refatoração futura."""
    assert "vazao_m3s_medio" in preditoras_anuais_do_trecho("alto_tiete")
    assert "vazao_m3s_medio" in preditoras_drivers_do_trecho("medio_tiete")


def test_matriz_por_trecho_respeita_lista_de_preditoras_do_trecho():
    gold = _gold_df_sintetico()

    X_baixo, y_baixo = montar_matriz_features_anual_por_trecho(gold, "iqa", "baixo_tiete")
    assert "vazao_m3s_medio" not in X_baixo.columns
    assert set(X_baixo.columns) == set(preditoras_anuais_do_trecho("baixo_tiete"))
    assert len(X_baixo) == len(y_baixo) == 10  # nenhuma linha perdida: baixo não depende de vazão

    X_alto, y_alto = montar_matriz_features_anual_por_trecho(gold, "iqa", "alto_tiete")
    assert len(X_alto) == len(y_alto) == 9  # a única linha com vazão nula foi descartada pelo dropna


def test_matriz_drivers_nao_tem_lags_do_alvo():
    """ACHADO item 8: a matriz "drivers" existe justamente para NÃO conter `{alvo}_lag*a` nem
    `{alvo}_media_movel_5a` — é o que evita o SHAP ser dominado pela autocorrelação do alvo."""
    gold = _gold_df_sintetico()
    X, y = montar_matriz_features_drivers_por_trecho(gold, "iqa", "alto_tiete")
    assert not any("lag" in col or "media_movel" in col for col in X.columns)
    assert set(X.columns) <= {
        "ano", "vazao_m3s_medio", "chuva_mm_media",
        "pct_natural", "pct_agropecuaria", "pct_urbano_industrial", "pct_agua",
    }
    assert len(X) == len(y)


def test_preditoras_drivers_sao_subconjunto_das_preditoras_de_producao():
    """A versão "drivers" nunca pode introduzir uma preditora que a versão de produção não
    tenha — só remove os lags do alvo, não adiciona nada novo."""
    for trecho_id in ("alto_tiete", "medio_tiete", "baixo_tiete"):
        producao = set(preditoras_anuais_do_trecho(trecho_id))
        drivers = set(preditoras_drivers_do_trecho(trecho_id))
        assert drivers <= producao, f"drivers de {trecho_id} tem preditora fora da produção"
