"""Cenários Futuros: o usuário escolhe quais fatores da água priorizar e o esforço de controle,
e vê uma cena 3D do Rio Tietê evoluindo de 5 a 30 anos — reaproveitando o mesmo motor real de
simulação (ABM + balanço hídrico + Streeter-Phelps + `models.biofisico.parametros_estendidos`)
das demais páginas, sem os cartões técnicos de um dashboard de dados.

Os 4 controles do usuário (poluição orgânica/sanitária, poluição agrícola/sedimentar, vazão
ecológica, severidade climática) alimentam parâmetros reais do ABM (ver
`models.abm.agents`/`models.abm.model`) — não são multiplicadores de fachada. A cena 3D
(`webapp.components.rio_3d`) é 100% pilotada pelos valores simulados de cada ano, não uma
animação solta.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[3]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from waterweave.config import TRECHOS
from waterweave.models.abm.scenarios import rodar_cenario_customizado
from waterweave.webapp import theme
from waterweave.webapp.components.rio_3d import renderizar_html

st.set_page_config(page_title="Cenários Futuros — WaterWeave-Tietê", page_icon="🔮", layout="wide")
theme.inject_style()
theme.render_sidebar_brand()

st.title("Cenários Futuros do Rio Tietê")
st.caption("Escolha o que priorizar e veja o rio daqui a 5 a 30 anos.")

TRECHO_IDS = list(TRECHOS)

CAMPOS_SAIDA = [
    "iqa", "od_mg_l", "dbo_mg_l", "turbidez_ntu", "solidos_totais_mg_l", "temperatura_c",
    "ph", "fosforo_mg_l", "nitrogenio_mg_l", "metais_toxicos_indice", "e_coli_nmp_100ml", "indice_biotico",
]

# ---------------------------------------------------------------------------
# Cenário "não controlado" — patamar fixo, pessimista (continuidade das regras
# de decisão de hoje, sem novas medidas).
# ---------------------------------------------------------------------------
NAO_CONTROLADO_BASE = dict(
    piso_fator_outorga=0.30, restricao_ambiental=False, fiscaliza_em_serio=False,
    crescimento_mensal_industria=1.01, reducao_por_multa=0.90, teto_fator_carga_industria=3.0,
    reducao_agricola=0.99, piso_fator_difusa=0.90,
)

# ---------------------------------------------------------------------------
# Seleção de trecho e horizonte
# ---------------------------------------------------------------------------
col_trecho, col_horizonte, col_clima = st.columns([1.2, 1.4, 1])
with col_trecho:
    trecho_id = st.selectbox("Trecho do rio", options=TRECHO_IDS, format_func=lambda t: theme.TRECHO_LABEL[t])
with col_horizonte:
    horizonte_anos = st.slider("Daqui a quantos anos?", 5, 30, 15, step=1)
with col_clima:
    clima_severidade = st.slider(
        "Mudança climática esperada", 60, 105, 90, format="%d%%",
        help="Quanto menor, mais seco/quente — aplicado igualmente aos dois cenários.",
    ) / 100.0

st.divider()

# ---------------------------------------------------------------------------
# Fatores da água — o usuário escolhe o que priorizar controlar
# ---------------------------------------------------------------------------
st.markdown("### O que você quer priorizar controlar?")

col_fis, col_quim, col_bio = st.columns(3)

with col_fis:
    st.markdown("**Fatores Físicos**")
    st.caption("Alteram a estética da água e afetam a vida aquática e a entrada de luz.")
    st.markdown(
        "- **Turbidez**: partículas em suspensão (argila, lodo) que impedem a luz de penetrar.\n"
        "- **Temperatura**: influencia a solubilidade de gases (oxigênio) e o metabolismo aquático.\n"
        "- **Sólidos Totais**: minerais e matéria orgânica dissolvida na água."
    )
    controlar_fisico = st.checkbox("Controlar sedimentos/erosão (Turbidez, Sólidos Totais)", value=True)
    esforco_fisico = st.slider("Esforço", 0, 100, 60, format="%d%%", key="esforco_fisico", disabled=not controlar_fisico)
    st.caption("Temperatura reflete só o cenário climático — não é controlável por gestão local.")

with col_quim:
    st.markdown("**Fatores Químicos**")
    st.caption("Indicam a presença de poluentes e a capacidade do rio de sustentar a vida.")
    st.markdown(
        "- **Oxigênio Dissolvido (OD)**: essencial para peixes e plantas; baixo OD indica esgoto.\n"
        "- **DBO**: oxigênio consumido para decompor matéria orgânica; alta DBO = poluição orgânica.\n"
        "- **pH**: acidez/alcalinidade da água.\n"
        "- **Nutrientes (Fósforo e Nitrogênio)**: excesso causa eutrofização (proliferação de algas).\n"
        "- **Metais Pesados e Tóxicos**: chumbo, mercúrio, agrotóxicos."
    )
    controlar_organico = st.checkbox("Controlar esgoto/efluentes (OD, DBO, pH, parte dos Metais)", value=True)
    esforco_organico = st.slider("Esforço", 0, 100, 60, format="%d%%", key="esforco_organico", disabled=not controlar_organico)
    controlar_nutrientes = st.checkbox("Controlar fertilizantes/agrotóxicos (Nutrientes, parte dos Metais)", value=True)
    esforco_nutrientes = st.slider("Esforço", 0, 100, 60, format="%d%%", key="esforco_nutrientes", disabled=not controlar_nutrientes)

with col_bio:
    st.markdown("**Fatores Biológicos**")
    st.caption("Avaliam a saúde do ecossistema a curto e longo prazo.")
    st.markdown(
        "- **E. coli** (ex-Coliformes Termotolerantes): contaminação fecal, risco à saúde pública.\n"
        "- **Macroinvertebrados e Peixes**: espécies sensíveis à poluição, indicador da saúde do rio."
    )
    st.caption("Ambos são resultado do que acontece nas outras duas colunas — não têm controle próprio.")
    outorga_piso = st.slider(
        "💧 Vazão ecológica mínima reservada", 0.30, 0.95, 0.60, step=0.05, format="%.2f",
        help="Fração da vazão simulada reservada para diluição — quanto maior, menos captação é permitida em seca.",
    )

esforco_sedimentar = esforco_fisico if controlar_fisico else 0
esforco_esgoto = esforco_organico if controlar_organico else 0
esforco_agricola = esforco_nutrientes if controlar_nutrientes else 0

CONTROLADO_PARAMS = dict(
    piso_fator_outorga=outorga_piso,
    restricao_ambiental=(esforco_agricola > 0) or (esforco_sedimentar > 0),
    fiscaliza_em_serio=esforco_esgoto >= 50,
    crescimento_mensal_industria=1.01 - 0.008 * (esforco_esgoto / 100),
    reducao_por_multa=0.90 - 0.35 * (esforco_esgoto / 100),
    teto_fator_carga_industria=3.0 - 1.8 * (esforco_esgoto / 100),
    reducao_agricola=0.99 - 0.14 * (max(esforco_agricola, esforco_sedimentar) / 100),
    piso_fator_difusa=0.90 - 0.50 * (max(esforco_agricola, esforco_sedimentar) / 100),
)

st.divider()

# ---------------------------------------------------------------------------
# Executa o ABM (cacheado) e prepara a série anual para a cena 3D
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner="Simulando o rio...")
def _rodar(parametros: dict, fator_clima: float, horizonte_meses: int) -> pd.DataFrame:
    parametros_completos = {**parametros, "fator_clima": fator_clima}
    return rodar_cenario_customizado(parametros_completos, TRECHO_IDS, horizonte_meses)


def _serie_anual(historico: pd.DataFrame, trecho: str) -> list[dict]:
    sub = historico[historico.trecho_id == trecho]
    agregacoes = {campo: (campo, "mean") for campo in CAMPOS_SAIDA}
    anual = sub.groupby("ano_relativo", as_index=False).agg(**agregacoes)
    anual = anual.rename(columns={"ano_relativo": "ano"}).sort_values("ano")
    return anual.to_dict(orient="records")


horizonte_meses = horizonte_anos * 12
hist_nao_controlado = _rodar(NAO_CONTROLADO_BASE, clima_severidade, horizonte_meses)
hist_controlado = _rodar(CONTROLADO_PARAMS, clima_severidade, horizonte_meses)

serie_nc = _serie_anual(hist_nao_controlado, trecho_id)
serie_c = _serie_anual(hist_controlado, trecho_id)

html = renderizar_html(serie_c, serie_nc, ano_min=1, ano_max=horizonte_anos, altura_px=620)
components.html(html, height=640, scrolling=False)

with st.expander("Como isso é calculado"):
    st.markdown(
        "Simulação real via ABM (Mesa) + balanço hídrico + Streeter-Phelps "
        "(`models.hybrid_bridge`, `models.abm.agents`) + submodelos de Turbidez/Sólidos/"
        "Temperatura/pH/Fósforo/Nitrogênio/E. coli/Metais/Índice Biótico "
        "(`models.biofisico.parametros_estendidos`), ancorados em médias reais 2012-2024 da "
        "CETESB. O cenário 'não controlado' é um patamar fixo pessimista definido nesta página. "
        "Cada trecho é simulado de forma independente, sem propagar carga/vazão de montante "
        "para jusante. IQA é um proxy simplificado de OD/DBO, não o IQA oficial de 9 parâmetros. "
        "Índice Biótico (macroinvertebrados/peixes) e o índice de Metais/Tóxicos são proxies "
        "ilustrativos combinando os demais parâmetros simulados — o projeto não tem dado real de "
        "biomonitoramento nem série completa de metais individuais ingerida no pipeline."
    )
