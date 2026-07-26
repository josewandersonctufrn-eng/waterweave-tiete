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

ACHADO DE AUDITORIA DE ML (item 4 — split único e pequeno): `treinar_modelo_trecho`
usa um único corte treino/teste (`ANO_CORTE_TESTE`) — com ~65 anos de dado por
trecho, isso deixa poucos anos de teste independentes, e a métrica reportada
depende de quais anos, especificamente, caíram do lado do teste (pode ser um
período fácil ou difícil por acaso). `validacao_walk_forward_trecho` corrige
isso com validação em janela expansiva: para cada ano candidato a partir de
`ANO_CORTE_TESTE`, treina (com busca de hiperparâmetros) só com os anos
estritamente anteriores e testa naquele ano — repete para todo ano disponível,
nunca vazando futuro para passado. O modelo salvo em produção continua sendo o
de `treinar_modelo_trecho` (treinado uma vez, sobre o máximo de histórico
disponível antes do corte); o walk-forward é diagnóstico, não o modelo
implantado — troque essa decisão se quiser reajustar hiperparâmetros a cada
novo ano em produção.

ACHADO DE AUDITORIA DE ML (item 7 — métricas sem quebra por trecho): antes do
item 2 (modelo único com `trecho_id` como feature), MAE/R² do split único
eram pooled entre os 3 trechos — um trecho ruim podia ficar escondido atrás
de dois bons. Isso já deixou de ser um problema estrutural com os modelos
separados por trecho (cada `treinar_modelo_trecho` já reporta métricas de UM
trecho só), mas `resumir_walk_forward_por_trecho` completa o quadro: agrega
os folds do walk-forward por (trecho, alvo) e mostra, lado a lado, qual
trecho tem desempenho estável entre anos e qual tem MAE variando demais fold
a fold (`mae_desvio` alto) — informação que um único split nunca revela.

ACHADO DE AUDITORIA DE ML (item 2 [numeração original da auditoria de dados,
não confundir com o item 2 de generalização espacial acima] — mistura de
fonte real e simulada no ALVO de treino): `qualidade_real_com_fallback_simulado`
(`transform.gold_features`) injeta a série SIMULADA em ~48% dos trecho-anos
(pré-1978 e lacunas recentes) — treinar sobre esse alvo misto ensina o
modelo, em quase metade dos casos, o padrão de uma planilha autodeclarada
"simulada com base em tendências", não hidrologia real. Corrigido:
`treinar_modelo_trecho` e `validacao_walk_forward_trecho` agora treinam, por
padrão (`restringir_treino_a_observado=True`), só sobre linhas com
`fonte_tipo == "observado"` — há histórico real suficiente por trecho
(35-45 anos) para isso não esvaziar o treino. As métricas de teste também são
quebradas por `fonte_tipo` (`mae_teste_observado`/`mae_teste_simulado`), para
deixar visível se o conjunto de teste em si está contaminado com anos
simulados (o que tornaria o MAE reportado parcialmente uma medida de "o
modelo aprendeu a imitar o gerador sintético", não desempenho real).
"""
from __future__ import annotations

import logging

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV

from waterweave.config import FONTE_TIPO_OBSERVADO, FONTE_TIPO_SIMULADO, GOLD_DIR, PROJECT_ROOT, TRECHOS
from waterweave.io_delta import read_table
from waterweave.models.ml.features import montar_matriz_features_anual_por_trecho

# Mínimo de anos reais exigido para treinar só com fonte_tipo == "observado" (item 2). Abaixo
# disso, cai de volta para incluir o fallback simulado, com aviso — não faz sentido travar o
# treino num trecho que ainda não tenha histórico real suficiente.
MIN_ANOS_TREINO_OBSERVADO = 10

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


def _mascara_treino_observado(
    fonte: pd.Series, treino_mask: pd.Series, restringir_a_observado: bool, contexto: str
) -> pd.Series:
    """Restringe `treino_mask` a `fonte_tipo == "observado"` (item 2) — com fallback (e aviso)
    para o treino original se sobrar menos que `MIN_ANOS_TREINO_OBSERVADO` linhas reais."""
    if not restringir_a_observado:
        return treino_mask
    treino_observado = treino_mask & (fonte == FONTE_TIPO_OBSERVADO)
    if treino_observado.sum() < MIN_ANOS_TREINO_OBSERVADO:
        logger.warning(
            "%s: só %d anos reais disponíveis para treino (mínimo %d) — usando fallback simulado "
            "também neste treino, além do real.",
            contexto, int(treino_observado.sum()), MIN_ANOS_TREINO_OBSERVADO,
        )
        return treino_mask
    return treino_observado


def _metricas_por_fonte(y_teste: pd.Series, predito, fonte_teste: pd.Series) -> dict:
    """Quebra as métricas de teste por `fonte_tipo` (item 2) — real vs. simulado, quando ambas
    existem no conjunto de teste."""
    saida: dict = {}
    predito = pd.Series(predito, index=y_teste.index)
    for rotulo, valor_fonte in (("observado", FONTE_TIPO_OBSERVADO), ("simulado", FONTE_TIPO_SIMULADO)):
        sub = fonte_teste == valor_fonte
        saida[f"n_teste_{rotulo}"] = int(sub.sum())
        if sub.sum() > 0:
            m = _metricas_regressao(y_teste[sub], predito[sub])
            saida[f"mae_teste_{rotulo}"] = m["mae"]
            saida[f"rmse_teste_{rotulo}"] = m["rmse"]
    return saida


def treinar_modelo_trecho(
    gold_df: pd.DataFrame,
    alvo: str,
    trecho_id: str,
    ano_corte_teste: int = ANO_CORTE_TESTE,
    restringir_treino_a_observado: bool = True,
) -> tuple[RandomForestRegressor, dict]:
    """Treina (com busca de hiperparâmetros) e retorna (modelo, métricas) para prever `alvo`
    dentro de UM trecho — ver ACHADO DE AUDITORIA DE ML item 2 (generalização espacial) na
    docstring do módulo.

    Por padrão (`restringir_treino_a_observado=True`), treina só sobre `fonte_tipo ==
    "observado"` — ver ACHADO DE AUDITORIA DE ML item 2 (mistura real/simulado no alvo). As
    métricas incluem o desempenho do RandomForest (geral e quebrado por `fonte_tipo` do
    conjunto de teste), o baseline de persistência ("previsto = valor do ano anterior",
    `{alvo}_lag1a`) no MESMO conjunto de teste."""
    X, y = montar_matriz_features_anual_por_trecho(gold_df, alvo, trecho_id)
    ano = gold_df.loc[X.index, "ano"]
    fonte = gold_df.loc[X.index, "fonte_tipo"]
    treino, teste = ano < ano_corte_teste, ano >= ano_corte_teste
    treino = _mascara_treino_observado(fonte, treino, restringir_treino_a_observado, f"{trecho_id}/{alvo}")

    busca = _buscar_melhor_modelo(X[treino], y[treino])
    modelo = busca.best_estimator_

    metricas: dict = {
        "n_treino": int(treino.sum()),
        "n_teste": int(teste.sum()),
        "treino_restrito_a_observado": bool((fonte[treino] == FONTE_TIPO_OBSERVADO).all()),
        "melhores_hiperparametros": busca.best_params_,
        "mae_cv_treino": round(float(-busca.best_score_), 4),
    }
    if teste.sum() > 0:
        predito = modelo.predict(X[teste])
        metricas.update(_metricas_regressao(y[teste], predito))
        metricas.update(_metricas_por_fonte(y[teste], predito, fonte[teste]))

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


# Anos de treino mínimos para um fold do walk-forward valer a pena: com CV_FOLDS=5 dentro da
# busca de hiperparâmetros, cada fold interno já perde ~1/5 do treino — abaixo disso o
# GridSearchCV estaria ajustando hiperparâmetros com poucochíssimo dado por fold interno.
MIN_ANOS_TREINO_WALK_FORWARD = 15


def validacao_walk_forward_trecho(
    gold_df: pd.DataFrame,
    alvo: str,
    trecho_id: str,
    ano_minimo_teste: int = ANO_CORTE_TESTE,
    passo_anos: int = 1,
    min_anos_treino: int = MIN_ANOS_TREINO_WALK_FORWARD,
    restringir_treino_a_observado: bool = True,
) -> pd.DataFrame:
    """Validação em janela expansiva (walk-forward) para UM (trecho, alvo) — ver ACHADO DE
    AUDITORIA DE ML, item 4, na docstring do módulo. Uma linha por ano de teste candidato;
    cada fold treina (com busca de hiperparâmetros) só sobre os anos estritamente anteriores
    e testa naquele ano — nunca informação do futuro vazando para o passado.

    Por padrão (`restringir_treino_a_observado=True`), cada fold também restringe o treino a
    `fonte_tipo == "observado"` (mesmo fallback de `MIN_ANOS_TREINO_OBSERVADO` de
    `treinar_modelo_trecho` — ver ACHADO DE AUDITORIA DE ML, item 2 de mistura real/simulado,
    na docstring do módulo) e reporta `mae_teste_observado`/`mae_teste_simulado` por fold."""
    X, y = montar_matriz_features_anual_por_trecho(gold_df, alvo, trecho_id)
    ano = gold_df.loc[X.index, "ano"]
    fonte = gold_df.loc[X.index, "fonte_tipo"]
    coluna_lag1a = f"{alvo}_lag1a"

    anos_candidatos = sorted(a for a in ano[ano >= ano_minimo_teste].unique())[::passo_anos]
    linhas = []
    for ano_teste in anos_candidatos:
        treino_mask = ano < ano_teste
        teste_mask = ano == ano_teste
        treino_mask = _mascara_treino_observado(
            fonte, treino_mask, restringir_treino_a_observado, f"{trecho_id}/{alvo} (walk-forward {ano_teste})"
        )
        if treino_mask.sum() < min_anos_treino or teste_mask.sum() == 0:
            continue

        busca = _buscar_melhor_modelo(X[treino_mask], y[treino_mask])
        modelo = busca.best_estimator_
        predito = modelo.predict(X[teste_mask])
        metricas_fold = _metricas_regressao(y[teste_mask], predito)
        metricas_fonte = _metricas_por_fonte(y[teste_mask], predito, fonte[teste_mask])

        baseline_predito = X.loc[teste_mask, coluna_lag1a]
        metricas_baseline = _metricas_regressao(y[teste_mask], baseline_predito)
        reducao_mae_pct = (
            round((1 - metricas_fold["mae"] / metricas_baseline["mae"]) * 100, 1)
            if metricas_baseline["mae"] > 0 else None
        )

        linhas.append({
            "trecho_id": trecho_id, "alvo": alvo, "ano_teste": ano_teste,
            "n_treino": int(treino_mask.sum()), "n_teste": int(teste_mask.sum()),
            "treino_restrito_a_observado": bool((fonte[treino_mask] == FONTE_TIPO_OBSERVADO).all()),
            "mae": metricas_fold["mae"], "rmse": metricas_fold["rmse"], "r2": metricas_fold["r2"],
            **metricas_fonte,
            "mae_baseline_persistencia": metricas_baseline["mae"],
            "reducao_mae_vs_baseline_pct": reducao_mae_pct,
        })

    return pd.DataFrame(linhas)


def resumir_walk_forward_por_trecho(resultados_wf: pd.DataFrame) -> pd.DataFrame:
    """Agrega os folds de `validacao_walk_forward_trecho` (concatenados entre trechos/alvos) em
    um resumo por (trecho, alvo) — ver ACHADO DE AUDITORIA DE ML, item 7, na docstring do
    módulo. `mae_desvio` alto sinaliza um trecho cujo desempenho varia muito de ano para ano
    (pouco confiável), não só um MAE médio ruim."""
    if resultados_wf.empty:
        return resultados_wf
    resumo = resultados_wf.groupby(["trecho_id", "alvo"]).agg(
        n_folds=("ano_teste", "count"),
        mae_medio=("mae", "mean"), mae_mediana=("mae", "median"), mae_desvio=("mae", "std"),
        rmse_medio=("rmse", "mean"), r2_medio=("r2", "mean"),
        mae_baseline_medio=("mae_baseline_persistencia", "mean"),
        pct_folds_supera_baseline=(
            "reducao_mae_vs_baseline_pct",
            lambda s: float((s.dropna() >= MARGEM_MINIMA_SOBRE_BASELINE * 100).mean() * 100) if s.notna().any() else None,
        ),
    ).reset_index()
    return resumo.round(4)


def run(incluir_walk_forward: bool = True) -> dict[str, dict]:
    """Treina um modelo por (trecho, alvo), salva em
    `data/models/{trecho_id}_{alvo}_model.joblib`, e — se `incluir_walk_forward` — roda a
    validação em janela expansiva (item 4) e salva o resumo por trecho (item 7) em
    `data/models/resumo_walk_forward.csv` e os folds completos em
    `data/models/{trecho_id}_{alvo}_walk_forward.csv`. O modelo salvo em produção é sempre o
    de `treinar_modelo_trecho` (split único, mas treinado com o máximo de histórico
    disponível) — o walk-forward é só diagnóstico de confiabilidade."""
    gold_df = read_table(GOLD_DIR / "feature_store_ml_anual")
    MODELOS_DIR.mkdir(parents=True, exist_ok=True)

    resultados = {}
    todos_folds_wf = []
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

            if incluir_walk_forward:
                folds = validacao_walk_forward_trecho(gold_df, alvo, trecho_id)
                if not folds.empty:
                    folds.to_csv(MODELOS_DIR / f"{trecho_id}_{alvo}_walk_forward.csv", index=False)
                    todos_folds_wf.append(folds)
                    logger.info(
                        "Walk-forward '%s': %d folds, MAE médio %.4f (split único: %.4f).",
                        chave, len(folds), folds["mae"].mean(), metricas.get("mae", float("nan")),
                    )
                else:
                    logger.warning(
                        "Walk-forward '%s': nenhum fold com histórico de treino suficiente "
                        "(mínimo %d anos) — resumo não gerado para esta combinação.",
                        chave, MIN_ANOS_TREINO_WALK_FORWARD,
                    )

    if incluir_walk_forward and todos_folds_wf:
        folds_completos = pd.concat(todos_folds_wf, ignore_index=True)
        resumo = resumir_walk_forward_por_trecho(folds_completos)
        resumo.to_csv(MODELOS_DIR / "resumo_walk_forward.csv", index=False)
        logger.info("Resumo walk-forward por trecho:\n%s", resumo.to_string(index=False))

    return resultados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for chave, metricas in run().items():
        print(f"{chave}: {metricas}")
