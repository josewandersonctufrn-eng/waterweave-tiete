"""Testes de guarda do treino por trecho (`models.ml.train`) — cobrem os achados de auditoria
que mudam COMO o modelo é treinado/avaliado: ausência de vazamento temporal entre folds (item
4) e separação de fonte real/simulada (item 2). Não testam a acurácia do RandomForest em si
(sem sentido em dado sintético pequeno) — testam que a MECÂNICA de treino/avaliação está
correta, que é justamente o que os itens 2 e 4 da auditoria corrigiram.
"""
from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("sklearn")

from waterweave.models.ml import train as train_mod
from waterweave.models.ml.features import montar_matriz_features_anual_por_trecho


def test_mascara_treino_observado_restringe_por_padrao():
    """ACHADO item 2: por padrão, o treino deve ficar só com `fonte_tipo == 'observado'`,
    desde que sobrem >= `MIN_ANOS_TREINO_OBSERVADO` linhas reais."""
    fonte = pd.Series(["observado"] * 20 + ["simulado"] * 20)
    treino_mask = pd.Series([True] * 40)
    resultado = train_mod._mascara_treino_observado(fonte, treino_mask, True, "teste")
    assert resultado.sum() == 20
    assert (fonte[resultado] == "observado").all()


def test_mascara_treino_observado_cai_para_fallback_se_poucos_anos_reais():
    """Com menos que `MIN_ANOS_TREINO_OBSERVADO` anos reais disponíveis, a função deve manter
    a máscara de treino ORIGINAL (incluindo simulado) em vez de esvaziar o treino — travar o
    pipeline num trecho sem histórico real suficiente seria pior que usar o fallback."""
    fonte = pd.Series(["observado"] * 3 + ["simulado"] * 20)
    treino_mask = pd.Series([True] * 23)
    resultado = train_mod._mascara_treino_observado(fonte, treino_mask, True, "teste")
    assert resultado.sum() == 23


def test_mascara_treino_observado_desligada_nao_filtra():
    fonte = pd.Series(["observado"] * 5 + ["simulado"] * 5)
    treino_mask = pd.Series([True] * 10)
    resultado = train_mod._mascara_treino_observado(fonte, treino_mask, False, "teste")
    assert resultado.sum() == 10


def test_metricas_por_fonte_quebra_contagens_e_mae_corretamente():
    y = pd.Series([10.0, 20.0, 30.0, 40.0], index=[0, 1, 2, 3])
    predito = [11.0, 19.0, 32.0, 41.0]
    fonte = pd.Series(["observado", "observado", "simulado", "simulado"], index=[0, 1, 2, 3])
    metricas = train_mod._metricas_por_fonte(y, predito, fonte)
    assert metricas["n_teste_observado"] == 2
    assert metricas["n_teste_simulado"] == 2
    assert metricas["mae_teste_observado"] == pytest.approx(1.0)
    assert metricas["mae_teste_simulado"] == pytest.approx(1.5)


def test_metricas_por_fonte_sem_uma_das_fontes_no_teste():
    """Se o conjunto de teste for 100% observado (caso comum: anos recentes raramente caem no
    fallback simulado), a quebra por simulado deve reportar n=0 sem quebrar."""
    y = pd.Series([10.0, 20.0])
    predito = [10.0, 20.0]
    fonte = pd.Series(["observado", "observado"])
    metricas = train_mod._metricas_por_fonte(y, predito, fonte)
    assert metricas["n_teste_observado"] == 2
    assert metricas["n_teste_simulado"] == 0
    assert "mae_teste_simulado" not in metricas  # não calcula MAE sobre um conjunto vazio


def test_treinar_modelo_trecho_retorna_metricas_completas(gold_df_sintetico):
    gold = gold_df_sintetico()
    modelo, metricas = train_mod.treinar_modelo_trecho(gold, "iqa", "alto_tiete")

    assert metricas["n_treino"] > 0
    assert metricas["n_teste"] > 0
    assert metricas["treino_restrito_a_observado"] is True
    for chave in ("mae", "rmse", "r2", "mae_baseline_persistencia", "reducao_mae_vs_baseline_pct"):
        assert chave in metricas
    # a quebra por fonte do teste tem que fechar com o total de teste
    assert metricas["n_teste_observado"] + metricas.get("n_teste_simulado", 0) == metricas["n_teste"]


def test_treinar_modelo_trecho_restringir_desligado_usa_mais_anos_de_treino(gold_df_sintetico):
    """Com `restringir_treino_a_observado=False`, o treino deve enxergar TODOS os anos antes
    do corte (real + simulado) — estritamente mais (ou igual) que com a restrição ligada."""
    gold = gold_df_sintetico()
    _, metricas_restrito = train_mod.treinar_modelo_trecho(gold, "iqa", "alto_tiete", restringir_treino_a_observado=True)
    _, metricas_completo = train_mod.treinar_modelo_trecho(gold, "iqa", "alto_tiete", restringir_treino_a_observado=False)
    assert metricas_completo["n_treino"] >= metricas_restrito["n_treino"]
    assert metricas_completo["treino_restrito_a_observado"] is False


def test_walk_forward_nunca_vaza_ano_futuro_para_o_treino(gold_df_sintetico):
    """ACHADO item 4: a garantia central do walk-forward. Recalcula, fold a fold, a máscara de
    treino de forma independente (mesma lógica que `validacao_walk_forward_trecho` usa
    internamente) e confirma que nenhum ano de treino é >= ano de teste daquele fold."""
    gold = gold_df_sintetico(n_anos=40)
    folds = train_mod.validacao_walk_forward_trecho(
        gold, "iqa", "alto_tiete", ano_minimo_teste=2010, min_anos_treino=15,
    )
    assert not folds.empty
    assert folds["ano_teste"].is_unique

    X, y = montar_matriz_features_anual_por_trecho(gold, "iqa", "alto_tiete")
    ano = gold.loc[X.index, "ano"]
    fonte = gold.loc[X.index, "fonte_tipo"]
    for _, fold in folds.iterrows():
        treino_mask = ano < fold["ano_teste"]
        treino_mask = train_mod._mascara_treino_observado(fonte, treino_mask, True, "recalculo")
        assert int(treino_mask.sum()) == fold["n_treino"]
        assert ano[treino_mask].max() < fold["ano_teste"]


def test_walk_forward_janela_e_expansiva(gold_df_sintetico):
    """Janela EXPANSIVA: o número de anos de treino não pode diminuir conforme o ano de teste
    avança — cada fold treina com tudo que o fold anterior tinha, mais um ano a mais."""
    gold = gold_df_sintetico(n_anos=40)
    folds = train_mod.validacao_walk_forward_trecho(
        gold, "iqa", "alto_tiete", ano_minimo_teste=2010, min_anos_treino=15,
    )
    n_treino_por_ano = folds.sort_values("ano_teste")["n_treino"]
    assert (n_treino_por_ano.diff().dropna() >= 0).all()


def test_resumir_walk_forward_agrega_por_trecho_e_alvo(gold_df_sintetico):
    gold = gold_df_sintetico(n_anos=40)
    folds = train_mod.validacao_walk_forward_trecho(gold, "iqa", "alto_tiete", ano_minimo_teste=2010, min_anos_treino=15)
    resumo = train_mod.resumir_walk_forward_por_trecho(folds)
    assert set(resumo["trecho_id"]) == {"alto_tiete"}
    assert set(resumo["alvo"]) == {"iqa"}
    assert resumo.loc[0, "n_folds"] == len(folds)
