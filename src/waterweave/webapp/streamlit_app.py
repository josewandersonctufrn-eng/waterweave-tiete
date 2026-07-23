"""Ponto de entrada do dashboard interativo (Streamlit) — WaterWeave-Tietê.

Página inicial: visão geral (KPIs por trecho) + navegação para as páginas
de detalhe em `pages/`. Todo o acesso a dado passa por `data_loader.py`,
que lê as tabelas Silver/Gold produzidas por `waterweave.ingestion` — ver
aviso de proveniência por fonte em cada função desse módulo.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Garante que `src/` esteja no sys.path mesmo se a instalação editável
# (`pip install -e .`, ver requirements.txt) não for respeitada pelo
# ambiente de deploy (ex.: Streamlit Community Cloud) — funciona
# independentemente de packaging, sem custo extra localmente.
_SRC_DIR = Path(__file__).resolve().parents[2]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import streamlit as st

from waterweave.config import TRECHOS
from waterweave.webapp import i18n, theme
from waterweave.webapp.data_loader import load_estacoes_tiete, load_qualidade_historica

st.set_page_config(page_title="WaterWeave-Tietê", page_icon="💧", layout="wide")
theme.inject_style()
theme.render_sidebar_brand()
i18n.seletor_idioma()

with st.sidebar:
    st.markdown(f"#### {i18n.t('nav.titulo')}")
    st.markdown(
        f"""
        - **{i18n.t('nav.mapa')}** — {i18n.t('nav.mapa.desc')}
        - **{i18n.t('nav.series')}** — {i18n.t('nav.series.desc')}
        - **{i18n.t('nav.comparativo')}** — {i18n.t('nav.comparativo.desc')}
        - **{i18n.t('nav.cenarios_futuros')}** — {i18n.t('nav.cenarios_futuros.desc')}
        - **{i18n.t('nav.relatorio')}** — {i18n.t('nav.relatorio.desc')}
        """
    )

st.title(i18n.t("home.titulo"))
st.caption(i18n.t("home.caption"))

qualidade = load_qualidade_historica()
estacoes = load_estacoes_tiete()
ultimo_ano = int(qualidade["ano"].max())
qualidade_recente = qualidade[qualidade["ano"] == ultimo_ano]

st.subheader(i18n.t("home.panorama", ano=ultimo_ano))
st.caption(i18n.t("home.aviso_simulado"))

colunas = st.columns(len(TRECHOS))
for coluna, trecho_id in zip(colunas, TRECHOS):
    linha = qualidade_recente[qualidade_recente["trecho_id"] == trecho_id]
    n_estacoes = int((estacoes["trecho_id"] == trecho_id).sum())
    with coluna, st.container(border=True):
        st.markdown(f"**{theme.TRECHO_LABEL[trecho_id]}**")
        if linha.empty:
            st.info(i18n.t("home.sem_dado"))
            continue
        iqa = float(linha["iqa"].iloc[0])
        od = float(linha["od_mg_l"].iloc[0])
        dbo = float(linha["dbo_mg_l"].iloc[0])
        status = theme.STATUS[theme.status_para_iqa(iqa)]
        st.metric(i18n.t("home.iqa_medio"), f"{iqa:.1f}", help="Índice de Qualidade da Água (0-100)")
        st.metric(i18n.t("series.od"), f"{od:.2f}")
        st.metric(i18n.t("series.dbo"), f"{dbo:.2f}")
        st.markdown(f"{status['icon']} **{theme.status_label(theme.status_para_iqa(iqa))}** · {i18n.t('home.estacoes_monitoradas', n=n_estacoes)}")
