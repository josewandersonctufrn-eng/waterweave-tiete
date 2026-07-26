"""Predição do Índice de Qualidade da Água (IQA) e Oxigênio Dissolvido (OD) por trecho/ano.

Previsão recursiva: cada ano futuro usa as previsões dos anos futuros
anteriores como lag (não há como conhecer o IQA "real" de um ano que ainda
não ocorreu). A vazão e a chuva de anos futuros — que também não são
conhecidas — usam a média histórica do trecho (dos últimos `_JANELA_CLIMATOLOGIA`
anos), a mesma ideia de "forçante climatológica" usada em `models.abm.model`
para períodos fora do horizonte observado, só que sem a dimensão de mês
(ver ACHADO DE AUDITORIA DE ML em `transform.gold_features`: a granularidade
real da qualidade da água é anual, não mensal — este módulo previa por mês
antes da correção, o que forçava uma resolução temporal que a fonte não tem).

Consumido pelo dashboard (projeção de curto prazo) e, potencialmente, pelos
agentes do ABM como fonte alternativa ao cálculo determinístico de
`models.hybrid_bridge` — hoje o ABM usa o determinístico; este módulo serve
o caso de uso estatístico/rápido (ver docstring de `hybrid_bridge`).

Carrega um modelo POR TRECHO (ver ACHADO DE AUDITORIA DE ML item 2 em
`models.ml.train`: um modelo único generaliza mal entre trechos) — por isso
a linha de entrada NÃO tem mais a coluna `trecho_id` (o modelo já é
específico daquele trecho, diferente da versão anterior com um modelo único
para o rio inteiro).
"""
from __future__ import annotations

import joblib
import pandas as pd

from waterweave.config import GOLD_DIR
from waterweave.io_delta import read_table
from waterweave.models.ml.train import MODELOS_DIR

_JANELA_LAGS = 5
_JANELA_CLIMATOLOGIA_ANOS = 10


def _carregar_modelo(trecho_id: str, alvo: str):
    caminho = MODELOS_DIR / f"{trecho_id}_{alvo}_model.joblib"
    if not caminho.exists():
        raise FileNotFoundError(
            f"Modelo '{trecho_id}/{alvo}' não treinado — rode `python -m waterweave.models.ml.train` primeiro."
        )
    return joblib.load(caminho)


def _lag(janela: list[float], passos_atras: int) -> float:
    if len(janela) >= passos_atras:
        return janela[-passos_atras]
    return janela[0]


def prever_iqa(trecho_id: str, horizonte_anos: int) -> pd.DataFrame:
    """Retorna a série prevista de IQA/OD para `trecho_id` nos próximos `horizonte_anos`."""
    modelo_iqa = _carregar_modelo(trecho_id, "iqa")
    modelo_od = _carregar_modelo(trecho_id, "od_mg_l")

    serie = read_table(GOLD_DIR / "feature_store_ml_anual")
    historico = serie[serie["trecho_id"] == trecho_id].sort_values("ano")
    if historico.dropna(subset=["iqa", "od_mg_l"]).empty:
        raise ValueError(f"Sem histórico de qualidade da água para '{trecho_id}'.")

    recente = historico.dropna(subset=["vazao_m3s_medio", "chuva_mm_media"]).tail(_JANELA_CLIMATOLOGIA_ANOS)
    vazao_media = recente["vazao_m3s_medio"].mean()
    chuva_media = recente["chuva_mm_media"].mean()

    janela_iqa = list(historico["iqa"].dropna())[-_JANELA_LAGS:]
    janela_od = list(historico["od_mg_l"].dropna())[-_JANELA_LAGS:]
    ultimo_ano = int(historico["ano"].max())

    linhas = []
    for passo in range(1, horizonte_anos + 1):
        ano_previsto = ultimo_ano + passo

        entrada = pd.DataFrame(
            [
                {
                    "ano": ano_previsto,
                    "vazao_m3s_medio": vazao_media,
                    "chuva_mm_media": chuva_media,
                    "iqa_lag1a": _lag(janela_iqa, 1),
                    "iqa_lag2a": _lag(janela_iqa, 2),
                    "iqa_lag3a": _lag(janela_iqa, 3),
                    "iqa_media_movel_5a": sum(janela_iqa[-5:]) / len(janela_iqa[-5:]),
                    "od_mg_l_lag1a": _lag(janela_od, 1),
                    "od_mg_l_lag2a": _lag(janela_od, 2),
                    "od_mg_l_lag3a": _lag(janela_od, 3),
                    "od_mg_l_media_movel_5a": sum(janela_od[-5:]) / len(janela_od[-5:]),
                }
            ]
        )

        iqa_previsto = float(modelo_iqa.predict(entrada)[0])
        od_previsto = float(modelo_od.predict(entrada)[0])

        janela_iqa.append(iqa_previsto)
        janela_od.append(od_previsto)
        janela_iqa, janela_od = janela_iqa[-_JANELA_LAGS:], janela_od[-_JANELA_LAGS:]

        linhas.append({"trecho_id": trecho_id, "ano": ano_previsto, "iqa_previsto": iqa_previsto, "od_previsto": od_previsto})

    return pd.DataFrame(linhas)
