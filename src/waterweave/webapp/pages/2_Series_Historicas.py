"""Séries históricas (1940-2025) de qualidade da água, vazão e chuva."""
from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[3]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import plotly.graph_objects as go
import streamlit as st

from waterweave.config import TRECHOS
from waterweave.webapp import theme
from waterweave.webapp.data_loader import load_chuva_mensal, load_qualidade_historica, load_vazao_mensal

st.set_page_config(page_title="Séries Históricas — WaterWeave-Tietê", page_icon="📈", layout="wide")
theme.inject_style()
theme.render_sidebar_brand()

st.title("Séries Históricas")
st.caption("1940–2025 · qualidade da água, vazão e chuva")

qualidade = load_qualidade_historica()

PARAMETROS = {
    "iqa": ("IQA Médio (0-100)", "iqa"),
    "od_mg_l": ("Oxigênio Dissolvido (mg/L)", "od_mg_l"),
    "dbo_mg_l": ("DBO (mg/L)", "dbo_mg_l"),
    "metais_pesados_ppm": ("Metais Pesados (ppm)", "metais_pesados_ppm"),
    "pesticidas_ppm": ("Pesticidas (ppm)", "pesticidas_ppm"),
    "materia_organica_pct": ("Matéria Orgânica (%)", "materia_organica_pct"),
}

st.subheader("Qualidade da água por trecho")
st.caption("⚠️ Série simulada (proxy histórico) — ver aviso de proveniência em `ingestion.bronze_qualidade_solo`.")

parametro_key = st.selectbox("Parâmetro", options=list(PARAMETROS), format_func=lambda k: PARAMETROS[k][0])
titulo_eixo, coluna = PARAMETROS[parametro_key]

fig = go.Figure()
for trecho_id in TRECHOS:
    serie = qualidade[qualidade["trecho_id"] == trecho_id].sort_values("ano")
    fig.add_trace(
        go.Scatter(
            x=serie["ano"],
            y=serie[coluna],
            mode="lines",
            name=theme.TRECHO_LABEL[trecho_id],
            line=dict(color=theme.TRECHO_COLOR[trecho_id], width=2),
        )
    )
theme.apply_common_layout(fig, y_title=titulo_eixo)
with st.container(border=True):
    st.plotly_chart(fig, use_container_width=True)

with st.expander("Ver tabela"):
    tabela_pivot = qualidade.pivot(index="ano", columns="trecho_id", values=coluna)
    tabela_pivot.columns = [theme.TRECHO_LABEL[c] for c in tabela_pivot.columns]
    st.dataframe(tabela_pivot, use_container_width=True)

st.divider()
st.subheader("Vazão e chuva observadas (rede completa de postos DAEE)")
st.caption("Dado real (não simulado), regularizado para média mensal por posto pelo pipeline de Ingestão.")

trecho_selecionado = st.selectbox("Trecho", options=list(TRECHOS), format_func=lambda t: theme.TRECHO_LABEL[t])

col_vazao, col_chuva = st.columns(2)

with col_vazao, st.container(border=True):
    vazao = load_vazao_mensal(trecho_selecionado)
    if vazao.empty:
        st.info("Sem dado de vazão disponível para este trecho.")
    else:
        postos_vazao = sorted(vazao["codigo_posto"].unique())
        posto_vazao = st.selectbox("Posto fluviométrico", options=postos_vazao, key="posto_vazao")
        serie_posto = vazao[vazao["codigo_posto"] == posto_vazao]
        fig_vazao = go.Figure(
            go.Scatter(
                x=serie_posto["data"], y=serie_posto["vazao_m3s"], mode="lines",
                line=dict(color=theme.TRECHO_COLOR[trecho_selecionado], width=2),
                name=posto_vazao,
            )
        )
        theme.apply_common_layout(fig_vazao, y_title="Vazão média mensal (m³/s)", legend=False)
        st.plotly_chart(fig_vazao, use_container_width=True)

with col_chuva, st.container(border=True):
    chuva = load_chuva_mensal(trecho_selecionado)
    if chuva.empty:
        st.info("Sem dado de chuva disponível para este trecho.")
    else:
        postos_chuva = sorted(chuva["codigo_posto"].unique())
        posto_chuva = st.selectbox("Posto pluviométrico", options=postos_chuva, key="posto_chuva")
        serie_posto = chuva[chuva["codigo_posto"] == posto_chuva]
        fig_chuva = go.Figure(
            go.Scatter(
                x=serie_posto["data"], y=serie_posto["altura_mm"], mode="lines",
                line=dict(color=theme.TRECHO_COLOR[trecho_selecionado], width=2),
                name=posto_chuva,
            )
        )
        theme.apply_common_layout(fig_chuva, y_title="Chuva mensal (mm)", legend=False)
        st.plotly_chart(fig_chuva, use_container_width=True)
