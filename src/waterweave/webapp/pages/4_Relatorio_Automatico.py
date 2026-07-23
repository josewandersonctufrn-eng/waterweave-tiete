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
from waterweave.reports.pdf_generator import (
    gerar_relatorio_todos_trechos_pdf_completo,
    gerar_relatorio_todos_trechos_pdf_resumido,
    gerar_relatorio_trecho_pdf_completo,
    gerar_relatorio_trecho_pdf_resumido,
)
from waterweave.webapp import i18n, theme
from waterweave.webapp.data_loader import load_qualidade_historica

st.set_page_config(page_title="Relatório Automático — WaterWeave-Tietê", page_icon="📝", layout="wide")
theme.inject_style()
theme.render_sidebar_brand()
i18n.seletor_idioma()

st.title(i18n.t("rel.titulo"))
st.caption(i18n.t("rel.caption"))

qualidade = load_qualidade_historica()
anos_disponiveis = sorted(qualidade["ano"].unique())

col_trecho, col_ano = st.columns(2)
with col_trecho:
    trecho_id = st.selectbox(i18n.t("mapa.trecho"), options=list(TRECHOS), format_func=lambda t: theme.TRECHO_LABEL[t])
with col_ano:
    ano = st.select_slider(i18n.t("rel.ano_referencia"), options=anos_disponiveis, value=anos_disponiveis[-1])

relatorio = gerar_relatorio_trecho(qualidade, trecho_id, ano)
with st.container(border=True):
    st.markdown(relatorio)

formato_pdf = st.radio(
    i18n.t("pdf.formato_label"),
    options=["resumido", "completo"],
    format_func=lambda f: i18n.t(f"pdf.formato_{f}"),
    horizontal=True,
    captions=[i18n.t("pdf.formato_resumido_desc"), i18n.t("pdf.formato_completo_desc")],
)
gerar_trecho_pdf = gerar_relatorio_trecho_pdf_resumido if formato_pdf == "resumido" else gerar_relatorio_trecho_pdf_completo
gerar_todos_pdf = gerar_relatorio_todos_trechos_pdf_resumido if formato_pdf == "resumido" else gerar_relatorio_todos_trechos_pdf_completo

st.download_button(
    i18n.t("rel.baixar_pdf"),
    data=gerar_trecho_pdf(qualidade, trecho_id, ano),
    file_name=f"relatorio_{trecho_id}_{ano}_{formato_pdf}.pdf",
    mime="application/pdf",
)

st.divider()
st.subheader(i18n.t("rel.gerar_todos"))
for outro_trecho in TRECHOS:
    with st.expander(theme.TRECHO_LABEL[outro_trecho], expanded=False):
        st.markdown(gerar_relatorio_trecho(qualidade, outro_trecho, ano))

st.download_button(
    i18n.t("rel.baixar_pdf_todos"),
    data=gerar_todos_pdf(qualidade, ano),
    file_name=f"relatorio_completo_{ano}_{formato_pdf}.pdf",
    mime="application/pdf",
)
