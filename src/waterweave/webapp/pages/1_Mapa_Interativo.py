"""Mapa interativo das estações de monitoramento do Rio Tietê (Folium)."""
from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[3]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import folium
import streamlit as st
from streamlit_folium import st_folium

from waterweave.webapp import theme
from waterweave.webapp.data_loader import load_estacoes_tiete, load_sensoriamento

st.set_page_config(page_title="Mapa Interativo — WaterWeave-Tietê", page_icon="🗺️", layout="wide")
theme.inject_style()
theme.render_sidebar_brand()

st.title("Mapa Interativo — Rio Tietê")
st.caption("Estações fluvio/pluviométricas (DAEE) e pontos de sensoriamento remoto, da nascente à foz.")

estacoes = load_estacoes_tiete()
sensoriamento = load_sensoriamento()

trechos_disponiveis = sorted(estacoes["trecho_id"].unique(), key=list(theme.TRECHO_LABEL).index)
selecionados = st.multiselect(
    "Filtrar por trecho",
    options=trechos_disponiveis,
    default=trechos_disponiveis,
    format_func=lambda t: theme.TRECHO_LABEL[t],
)
mostrar_sensoriamento = st.checkbox("Mostrar pontos de sensoriamento remoto (dado simulado)", value=True)

estacoes_filtradas = estacoes[estacoes["trecho_id"].isin(selecionados)]

centro_lat = estacoes_filtradas["latitude"].mean() if not estacoes_filtradas.empty else -22.9
centro_lon = estacoes_filtradas["longitude"].mean() if not estacoes_filtradas.empty else -47.5
mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=7, tiles="cartodbpositron")

for _, estacao in estacoes_filtradas.iterrows():
    cor = theme.TRECHO_COLOR[estacao["trecho_id"]]
    folium.CircleMarker(
        location=[estacao["latitude"], estacao["longitude"]],
        radius=7,
        color=cor,
        fill=True,
        fill_color=cor,
        fill_opacity=0.85,
        weight=2,
        popup=folium.Popup(
            f"<b>{estacao['codigo_posto']}</b><br>{estacao['corpo_hidrico']}<br>"
            f"{estacao['municipio']}<br>Classe: {estacao['classe_uso']}<br>"
            f"Trecho: {theme.TRECHO_LABEL[estacao['trecho_id']]}",
            max_width=250,
        ),
        tooltip=estacao["codigo_posto"],
    ).add_to(mapa)

if mostrar_sensoriamento:
    for _, ponto in sensoriamento.drop_duplicates("id_regiao").iterrows():
        folium.Marker(
            location=[ponto["latitude"], ponto["longitude"]],
            icon=folium.Icon(color="gray", icon="satellite", prefix="fa"),
            popup=folium.Popup(f"<b>{ponto['trecho_nome']}</b><br>({ponto['id_regiao']}) — sensoriamento simulado", max_width=250),
            tooltip=ponto["trecho_nome"],
        ).add_to(mapa)

legenda_html = "".join(
    f'<span style="color:{theme.TRECHO_COLOR[t]}">●</span> {theme.TRECHO_LABEL[t]} &nbsp;'
    for t in trechos_disponiveis
)
st.markdown(legenda_html, unsafe_allow_html=True)
st_folium(mapa, width=None, height=600, returned_objects=[])

st.subheader("Tabela de estações")
st.dataframe(
    estacoes_filtradas[["codigo_posto", "corpo_hidrico", "municipio", "classe_uso", "trecho_id"]],
    use_container_width=True,
    hide_index=True,
)
