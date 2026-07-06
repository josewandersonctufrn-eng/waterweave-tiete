"""Painel de análise automatizada: relatório textual sintético por trecho e ano."""
from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[3]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import streamlit as st

from waterweave.config import TRECHOS
from waterweave.reports.narrative_generator import gerar_relatorio_trecho
from waterweave.reports.pdf_generator import gerar_relatorio_completo_pdf, gerar_relatorio_trecho_pdf
from waterweave.webapp import theme
from waterweave.webapp.data_loader import load_qualidade_historica

st.set_page_config(page_title="Relatório Automático — WaterWeave-Tietê", page_icon="📝", layout="wide")
theme.inject_style()
theme.render_sidebar_brand()

st.title("Relatório Automático")
st.caption("Análise textual gerada por regras a partir dos indicadores de qualidade da água por trecho/ano.")

qualidade = load_qualidade_historica()
anos_disponiveis = sorted(qualidade["ano"].unique())

col_trecho, col_ano = st.columns(2)
with col_trecho:
    trecho_id = st.selectbox("Trecho", options=list(TRECHOS), format_func=lambda t: theme.TRECHO_LABEL[t])
with col_ano:
    ano = st.select_slider("Ano de referência", options=anos_disponiveis, value=anos_disponiveis[-1])

relatorio = gerar_relatorio_trecho(qualidade, trecho_id, ano)
with st.container(border=True):
    st.markdown(relatorio)

st.download_button(
    "📄 Baixar este relatório em PDF",
    data=gerar_relatorio_trecho_pdf(qualidade, trecho_id, ano),
    file_name=f"relatorio_{trecho_id}_{ano}.pdf",
    mime="application/pdf",
)

st.divider()
st.subheader("Gerar para todos os trechos neste ano")
for outro_trecho in TRECHOS:
    with st.expander(theme.TRECHO_LABEL[outro_trecho], expanded=False):
        st.markdown(gerar_relatorio_trecho(qualidade, outro_trecho, ano))

st.download_button(
    "📄 Baixar relatório de todos os trechos em PDF",
    data=gerar_relatorio_completo_pdf(qualidade, ano),
    file_name=f"relatorio_completo_{ano}.pdf",
    mime="application/pdf",
)
