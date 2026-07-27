"""Mapa interativo das estações de monitoramento do Rio Tietê (Folium)."""
from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[3]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from waterweave.webapp import i18n, theme
from waterweave.webapp.data_loader import load_estacoes_tiete, load_sensoriamento

# Ícone do ponto de sensoriamento por proveniência predominante entre seus parâmetros mais
# recentes — verde só quando TODOS já vêm do Landsat real, cinza-claro se algum ainda depende
# da planilha ilustrativa (ver `_resumo_sensoriamento_por_ponto`).
_COR_POR_FONTE = {"observado": "green", "misto": "orange", "simulado": "lightgray"}


def _resumo_sensoriamento_por_ponto(sensoriamento: pd.DataFrame) -> pd.DataFrame:
    """Reduz o formato longo (ponto/data/parâmetro) para UMA linha por `id_regiao`: a
    observação mais recente de CADA parâmetro disponível naquele ponto, mais uma proveniência
    agregada (`fonte_tipo`: "observado" só se todos os parâmetros mais recentes forem reais,
    "misto" se houver mistura, "simulado" se nenhum for real) — é o que popula o popup do
    mapa, então precisa refletir com precisão o que é medição real e o que ainda não é."""
    if sensoriamento.empty:
        return sensoriamento

    mais_recente_idx = sensoriamento.groupby(["id_regiao", "parametro"])["data_coleta"].idxmax()
    recentes = sensoriamento.loc[mais_recente_idx]

    linhas = []
    for id_regiao, grupo in recentes.groupby("id_regiao"):
        fontes = set(grupo["fonte_tipo"])
        fonte_agregada = "observado" if fontes == {"observado"} else ("simulado" if fontes == {"simulado"} else "misto")
        parametros = [
            {
                "parametro": r["parametro"],
                "valor": r["valor"],
                "unidade": r["unidade"],
                "ano": r["data_coleta"].year,
                "fonte_tipo": r["fonte_tipo"],
            }
            for _, r in grupo.iterrows()
        ]
        primeira = grupo.iloc[0]
        linhas.append(
            {
                "id_regiao": id_regiao,
                "trecho_id": primeira["trecho_id"],
                "trecho_nome": primeira["trecho_nome"],
                "latitude": primeira["latitude"],
                "longitude": primeira["longitude"],
                "fonte_tipo": fonte_agregada,
                "ano_mais_recente": grupo["data_coleta"].dt.year.max(),
                "parametros": parametros,
            }
        )
    return pd.DataFrame(linhas)


def _popup_html_sensoriamento(ponto: pd.Series) -> str:
    linhas_parametros = "".join(
        f"<tr><td>{p['parametro']}</td><td style='text-align:right'>{p['valor']:.2f} {p['unidade']} "
        f"({p['ano']})</td></tr>"
        for p in ponto["parametros"]
    )
    rotulo_fonte = i18n.t(f"mapa.sensoriamento_{ponto['fonte_tipo']}")
    return (
        f"<b>{ponto['trecho_nome']}</b> ({ponto['id_regiao']})<br>"
        f"<span style='color:#555'>{rotulo_fonte}</span>"
        f"<table style='margin-top:4px'>{linhas_parametros}</table>"
    )

st.set_page_config(page_title="Mapa Interativo — WaterWeave-Tietê", page_icon="🗺️", layout="wide")
theme.inject_style()
theme.render_sidebar_brand()
i18n.seletor_idioma()

st.title(i18n.t("mapa.titulo"))
st.caption(i18n.t("mapa.caption"))

estacoes = load_estacoes_tiete()
sensoriamento = load_sensoriamento()

trechos_disponiveis = sorted(estacoes["trecho_id"].unique(), key=list(theme.TRECHO_LABEL).index)
selecionados = st.multiselect(
    i18n.t("mapa.filtrar_trecho"),
    options=trechos_disponiveis,
    default=trechos_disponiveis,
    format_func=lambda t: theme.TRECHO_LABEL[t],
)
mostrar_sensoriamento = st.checkbox(i18n.t("mapa.mostrar_sensoriamento"), value=True)

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
            f"{estacao['municipio']}<br>{i18n.t('mapa.classe')}: {estacao['classe_uso']}<br>"
            f"{i18n.t('mapa.trecho')}: {theme.TRECHO_LABEL[estacao['trecho_id']]}",
            max_width=250,
        ),
        tooltip=estacao["codigo_posto"],
    ).add_to(mapa)

if mostrar_sensoriamento:
    resumo_sensoriamento = _resumo_sensoriamento_por_ponto(sensoriamento)
    for _, ponto in resumo_sensoriamento.iterrows():
        folium.Marker(
            location=[ponto["latitude"], ponto["longitude"]],
            icon=folium.Icon(color=_COR_POR_FONTE[ponto["fonte_tipo"]], icon="satellite", prefix="fa"),
            popup=folium.Popup(_popup_html_sensoriamento(ponto), max_width=280),
            tooltip=f"{ponto['trecho_nome']} ({ponto['ano_mais_recente']})",
        ).add_to(mapa)
    st.caption(f"🛰️ {i18n.t('mapa.sensoriamento_ressalva')}")

legenda_html = "".join(
    f'<span style="color:{theme.TRECHO_COLOR[t]}">●</span> {theme.TRECHO_LABEL[t]} &nbsp;'
    for t in trechos_disponiveis
)
if mostrar_sensoriamento:
    legenda_html += "&nbsp;&nbsp;|&nbsp;&nbsp;🛰️ " + "".join(
        f'<span style="color:{cor}">●</span> {i18n.t(f"mapa.sensoriamento_{fonte}")} &nbsp;'
        for fonte, cor in _COR_POR_FONTE.items()
    )
st.markdown(legenda_html, unsafe_allow_html=True)
st_folium(mapa, width=None, height=600, returned_objects=[])

st.subheader(i18n.t("mapa.tabela_estacoes"))
st.dataframe(
    estacoes_filtradas[["codigo_posto", "corpo_hidrico", "municipio", "classe_uso", "trecho_id"]],
    use_container_width=True,
    hide_index=True,
)
