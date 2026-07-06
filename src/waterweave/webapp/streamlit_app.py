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
from waterweave.webapp import theme
from waterweave.webapp.data_loader import load_estacoes_tiete, load_qualidade_historica

st.set_page_config(page_title="WaterWeave-Tietê", page_icon="💧", layout="wide")
theme.inject_style()
theme.render_sidebar_brand()

with st.sidebar:
    st.markdown("#### Menu de Navegação")
    st.markdown(
        """
        - **Mapa Interativo** — estações de monitoramento georreferenciadas, nascente → foz.
        - **Séries Históricas** — vazão, chuva e qualidade da água, 1940-2025.
        - **Comparativo de Cenários** — Atual vs. Alta Restrição de Outorga vs. Mudança Climática Extrema.
        - **Relatório Automático** — análise textual sintética por trecho e ano.
        """
    )

st.title("WaterWeave-Tietê")
st.caption(
    "Gestão sustentável de recursos hídricos do Rio Tietê — Salesópolis (nascente) "
    "até Itapura (foz no Rio Paraná). Histórico 1940-2025 com automação mensal."
)

qualidade = load_qualidade_historica()
estacoes = load_estacoes_tiete()
ultimo_ano = int(qualidade["ano"].max())
qualidade_recente = qualidade[qualidade["ano"] == ultimo_ano]

st.subheader(f"Panorama por trecho — {ultimo_ano}")
st.caption(
    "⚠️ Os indicadores de qualidade da água abaixo vêm de uma série **simulada** "
    "(proxy histórico baseado em tendências CETESB/DAEE), não de telemetria direta — "
    "ver `ingestion.bronze_qualidade_solo`."
)

colunas = st.columns(len(TRECHOS))
for coluna, trecho_id in zip(colunas, TRECHOS):
    linha = qualidade_recente[qualidade_recente["trecho_id"] == trecho_id]
    n_estacoes = int((estacoes["trecho_id"] == trecho_id).sum())
    with coluna, st.container(border=True):
        st.markdown(f"**{theme.TRECHO_LABEL[trecho_id]}**")
        if linha.empty:
            st.info("Sem dado para o ano mais recente.")
            continue
        iqa = float(linha["iqa"].iloc[0])
        od = float(linha["od_mg_l"].iloc[0])
        dbo = float(linha["dbo_mg_l"].iloc[0])
        status = theme.STATUS[theme.status_para_iqa(iqa)]
        st.metric("IQA médio", f"{iqa:.1f}", help="Índice de Qualidade da Água (0-100)")
        st.metric("OD (mg/L)", f"{od:.2f}")
        st.metric("DBO (mg/L)", f"{dbo:.2f}")
        st.markdown(f"{status['icon']} **{status['label']}** · {n_estacoes} estações monitoradas")
