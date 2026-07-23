"""Comparativo de cenários: Atual vs. Alta Restrição de Outorga vs. Mudança Climática Extrema.

Roda o ABM real (`models.abm.scenarios.rodar_cenario`), que por sua vez usa
o balanço hídrico biofísico + Streeter-Phelps (`models.hybrid_bridge`) a
cada mês simulado. Ver docstrings desses módulos para as simplificações
assumidas (coeficientes não calibrados em campo, cada trecho simulado de
forma independente, IQA como proxy simplificado de OD/DBO).
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[3]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from waterweave.config import TRECHOS
from waterweave.models.abm.scenarios import CENARIOS, HORIZONTE_MESES, rodar_cenario
from waterweave.webapp import i18n, theme

st.set_page_config(page_title="Comparativo de Cenários — WaterWeave-Tietê", page_icon="⚖️", layout="wide")
theme.inject_style()
theme.render_sidebar_brand()
i18n.seletor_idioma()

st.title(i18n.t("comp.titulo"))
st.caption(i18n.t("comp.caption"))

HORIZONTE_LABEL = {"curto_prazo": i18n.t("comp.curto_prazo"), "medio_prazo": i18n.t("comp.medio_prazo"), "longo_prazo": i18n.t("comp.longo_prazo")}
CENARIO_I18N = {
    "atual": ("comp.cenario_atual", "comp.cenario_atual.desc"),
    "alta_restricao_outorga": ("comp.cenario_outorga", "comp.cenario_outorga.desc"),
    "mudanca_climatica_extrema": ("comp.cenario_clima", "comp.cenario_clima.desc"),
}


def _nome_cenario(cenario_id: str) -> str:
    chave = CENARIO_I18N.get(cenario_id)
    return i18n.t(chave[0]) if chave else CENARIOS[cenario_id].nome


def _desc_cenario(cenario_id: str) -> str:
    chave = CENARIO_I18N.get(cenario_id)
    return i18n.t(chave[1]) if chave else CENARIOS[cenario_id].descricao


@st.cache_data(ttl=3600, show_spinner="Rodando simulação do ABM...")
def _rodar_todos_cenarios(horizonte_meses: int) -> pd.DataFrame:
    trechos = list(TRECHOS)
    partes = [rodar_cenario(cenario_id, trechos, horizonte_meses) for cenario_id in CENARIOS]
    return pd.concat(partes, ignore_index=True)


horizonte_key = st.radio(
    i18n.t("comp.horizonte"), options=list(HORIZONTE_LABEL), format_func=lambda h: HORIZONTE_LABEL[h], horizontal=True
)
resultado = _rodar_todos_cenarios(HORIZONTE_MESES[horizonte_key])

PARAMETROS = {"iqa": i18n.t("comp.iqa"), "od_mg_l": i18n.t("comp.od"), "dbo_mg_l": i18n.t("comp.dbo"), "vazao_m3s_medio": i18n.t("comp.vazao")}
parametro_key = st.selectbox(i18n.t("comp.parametro"), options=list(PARAMETROS), format_func=lambda k: PARAMETROS[k])

fig = go.Figure()
for cenario_id in CENARIOS:
    serie = resultado[resultado["cenario_id"] == cenario_id].set_index("trecho_id").reindex(list(TRECHOS)).reset_index()
    fig.add_trace(
        go.Bar(
            x=[theme.TRECHO_LABEL[t] for t in serie["trecho_id"]],
            y=serie[parametro_key],
            name=_nome_cenario(cenario_id),
            marker_color=theme.SCENARIO_COLOR[cenario_id],
        )
    )
fig.update_layout(barmode="group")
theme.apply_common_layout(fig, y_title=PARAMETROS[parametro_key])
with st.container(border=True):
    st.plotly_chart(fig, use_container_width=True)

data_final = resultado["mes_data"].iloc[0].strftime("%m/%Y")
st.subheader(i18n.t("comp.tabela_titulo", data=data_final))
tabela = resultado.copy()
tabela["trecho"] = tabela["trecho_id"].map(theme.TRECHO_LABEL)
tabela["cenario"] = tabela["cenario_id"].map(_nome_cenario)
tabela_wide = tabela.pivot(index="trecho", columns="cenario", values=parametro_key)
tabela_wide = tabela_wide[[_nome_cenario(c) for c in CENARIOS]]
st.dataframe(tabela_wide.style.format("{:.2f}"), use_container_width=True)

with st.expander(i18n.t("comp.expander_multas")):
    extras = resultado[["trecho_id", "cenario_id", "multas_acumuladas", "estresse_hidrico"]].copy()
    extras["trecho"] = extras["trecho_id"].map(theme.TRECHO_LABEL)
    extras["cenario"] = extras["cenario_id"].map(_nome_cenario)
    st.dataframe(extras[["trecho", "cenario", "multas_acumuladas", "estresse_hidrico"]], use_container_width=True, hide_index=True)

with st.expander(i18n.t("comp.expander_cenarios")):
    for cenario_id in CENARIOS:
        st.markdown(f"**{_nome_cenario(cenario_id)}** — {_desc_cenario(cenario_id)}")
