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
from waterweave.webapp import theme

st.set_page_config(page_title="Comparativo de Cenários — WaterWeave-Tietê", page_icon="⚖️", layout="wide")
theme.inject_style()
theme.render_sidebar_brand()

st.title("Comparativo de Cenários")
st.caption(
    "Simulação real via ABM (Mesa) + balanço hídrico biofísico + Streeter-Phelps — "
    "não são multiplicadores ilustrativos. Ver `models.hybrid_bridge` para as simplificações assumidas."
)

HORIZONTE_LABEL = {"curto_prazo": "Curto prazo (5 anos)", "medio_prazo": "Médio prazo (15 anos)", "longo_prazo": "Longo prazo (30 anos)"}


@st.cache_data(ttl=3600, show_spinner="Rodando simulação do ABM...")
def _rodar_todos_cenarios(horizonte_meses: int) -> pd.DataFrame:
    trechos = list(TRECHOS)
    partes = [rodar_cenario(cenario_id, trechos, horizonte_meses) for cenario_id in CENARIOS]
    return pd.concat(partes, ignore_index=True)


horizonte_key = st.radio(
    "Horizonte temporal", options=list(HORIZONTE_LABEL), format_func=lambda h: HORIZONTE_LABEL[h], horizontal=True
)
resultado = _rodar_todos_cenarios(HORIZONTE_MESES[horizonte_key])

PARAMETROS = {"iqa": "IQA simulado (proxy 0-100)", "od_mg_l": "Oxigênio Dissolvido simulado (mg/L)", "dbo_mg_l": "DBO simulada (mg/L)", "vazao_m3s_medio": "Vazão simulada (m³/s)"}
parametro_key = st.selectbox("Parâmetro", options=list(PARAMETROS), format_func=lambda k: PARAMETROS[k])

fig = go.Figure()
for cenario_id in CENARIOS:
    serie = resultado[resultado["cenario_id"] == cenario_id].set_index("trecho_id").reindex(list(TRECHOS)).reset_index()
    fig.add_trace(
        go.Bar(
            x=[theme.TRECHO_LABEL[t] for t in serie["trecho_id"]],
            y=serie[parametro_key],
            name=CENARIOS[cenario_id].nome,
            marker_color=theme.SCENARIO_COLOR[cenario_id],
        )
    )
fig.update_layout(barmode="group")
theme.apply_common_layout(fig, y_title=PARAMETROS[parametro_key])
with st.container(border=True):
    st.plotly_chart(fig, use_container_width=True)

data_final = resultado["mes_data"].iloc[0].strftime("%m/%Y")
st.subheader(f"Tabela comparativa — estado simulado ao fim do horizonte ({data_final})")
tabela = resultado.copy()
tabela["trecho"] = tabela["trecho_id"].map(theme.TRECHO_LABEL)
tabela["cenario"] = tabela["cenario_id"].map(lambda c: CENARIOS[c].nome)
tabela_wide = tabela.pivot(index="trecho", columns="cenario", values=parametro_key)
tabela_wide = tabela_wide[[CENARIOS[c].nome for c in CENARIOS]]
st.dataframe(tabela_wide.style.format("{:.2f}"), use_container_width=True)

with st.expander("Multas aplicadas e estresse hídrico durante a simulação"):
    extras = resultado[["trecho_id", "cenario_id", "multas_acumuladas", "estresse_hidrico"]].copy()
    extras["trecho"] = extras["trecho_id"].map(theme.TRECHO_LABEL)
    extras["cenario"] = extras["cenario_id"].map(lambda c: CENARIOS[c].nome)
    st.dataframe(extras[["trecho", "cenario", "multas_acumuladas", "estresse_hidrico"]], use_container_width=True, hide_index=True)

with st.expander("O que cada cenário configura"):
    for cenario in CENARIOS.values():
        st.markdown(f"**{cenario.nome}** — {cenario.descricao}")
