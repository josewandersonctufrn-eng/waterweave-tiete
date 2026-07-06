"""Predição do Índice de Qualidade da Água (IQA) e Oxigênio Dissolvido (OD) por trecho/mês.

Previsão recursiva: cada mês futuro usa as previsões dos meses futuros
anteriores como lag (não há como conhecer o IQA "real" de um mês que ainda
não ocorreu). A vazão e a chuva de meses futuros — que também não são
conhecidas — usam a climatologia mensal histórica do trecho (média por mês
calendário), a mesma técnica de "forçante climatológica" usada em
`models.abm.model` para meses fora do horizonte observado.

Consumido pelo dashboard (projeção de curto prazo) e, potencialmente, pelos
agentes do ABM como fonte alternativa ao cálculo determinístico de
`models.hybrid_bridge` — hoje o ABM usa o determinístico; este módulo serve
o caso de uso estatístico/rápido (ver docstring de `hybrid_bridge`).
"""
from __future__ import annotations

import joblib
import pandas as pd

from waterweave.config import GOLD_DIR
from waterweave.io_delta import read_table
from waterweave.models.ml.train import MODELOS_DIR

_JANELA_LAGS = 12


def _carregar_modelo(alvo: str):
    caminho = MODELOS_DIR / f"{alvo}_model.joblib"
    if not caminho.exists():
        raise FileNotFoundError(f"Modelo '{alvo}' não treinado — rode `python -m waterweave.models.ml.train` primeiro.")
    return joblib.load(caminho)


def _lag(janela: list[float], passos_atras: int) -> float:
    if len(janela) >= passos_atras:
        return janela[-passos_atras]
    return janela[0]


def prever_iqa(trecho_id: str, horizonte_meses: int) -> pd.DataFrame:
    """Retorna a série prevista de IQA/OD para `trecho_id` nos próximos `horizonte_meses`."""
    modelo_iqa = _carregar_modelo("iqa")
    modelo_od = _carregar_modelo("od_mg_l")

    serie = read_table(GOLD_DIR / "serie_temporal_trecho_mes")
    historico = serie[serie["trecho_id"] == trecho_id].sort_values("mes_data")
    if historico.dropna(subset=["iqa", "od_mg_l"]).empty:
        raise ValueError(f"Sem histórico de qualidade da água para '{trecho_id}'.")

    climatologia = historico.dropna(subset=["chuva_mm_media"]).groupby("mes")[["vazao_m3s_medio", "chuva_mm_media"]].mean()

    janela_iqa = list(historico["iqa"].dropna())[-_JANELA_LAGS:]
    janela_od = list(historico["od_mg_l"].dropna())[-_JANELA_LAGS:]
    ultima_data = historico["mes_data"].max()

    linhas = []
    for passo in range(1, horizonte_meses + 1):
        data_prevista = ultima_data + pd.DateOffset(months=passo)
        mes = data_prevista.month
        vazao = climatologia.loc[mes, "vazao_m3s_medio"] if mes in climatologia.index else climatologia["vazao_m3s_medio"].mean()
        chuva = climatologia.loc[mes, "chuva_mm_media"] if mes in climatologia.index else climatologia["chuva_mm_media"].mean()

        entrada = pd.DataFrame(
            [
                {
                    "trecho_id": trecho_id,
                    "mes": mes,
                    "vazao_m3s_medio": vazao,
                    "chuva_mm_media": chuva,
                    "iqa_lag1m": _lag(janela_iqa, 1),
                    "iqa_lag3m": _lag(janela_iqa, 3),
                    "iqa_lag12m": _lag(janela_iqa, 12),
                    "iqa_media_movel_12m": sum(janela_iqa[-12:]) / len(janela_iqa[-12:]),
                    "od_mg_l_lag1m": _lag(janela_od, 1),
                    "od_mg_l_lag3m": _lag(janela_od, 3),
                    "od_mg_l_lag12m": _lag(janela_od, 12),
                    "od_mg_l_media_movel_12m": sum(janela_od[-12:]) / len(janela_od[-12:]),
                }
            ]
        )

        iqa_previsto = float(modelo_iqa.predict(entrada)[0])
        od_previsto = float(modelo_od.predict(entrada)[0])

        janela_iqa.append(iqa_previsto)
        janela_od.append(od_previsto)
        janela_iqa, janela_od = janela_iqa[-_JANELA_LAGS:], janela_od[-_JANELA_LAGS:]

        linhas.append({"trecho_id": trecho_id, "mes_data": data_prevista, "iqa_previsto": iqa_previsto, "od_previsto": od_previsto})

    return pd.DataFrame(linhas)
