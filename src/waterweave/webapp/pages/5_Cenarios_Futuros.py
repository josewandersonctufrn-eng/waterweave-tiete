"""Cenários Futuros: o usuário controla as alavancas reais do ABM (saneamento, fiscalização,
controle de agrotóxicos, outorga) e compara, num horizonte contínuo de 5 a 30 anos, o que
acontece com o Rio Tietê se essas medidas NÃO forem tomadas vs. se forem tomadas no nível
escolhido.

Reaproveita 100% do motor de simulação real já existente (`models.abm`, Mesa +
balanço hídrico + Streeter-Phelps via `models.hybrid_bridge`) — os sliders
desta página não são multiplicadores de fachada: eles alimentam parâmetros
reais dos agentes (`IndustriaAgent.crescimento_mensal/teto_fator_carga`,
`PoderPublicoAgent.fiscaliza_em_serio`, `AgricultorAgent.reducao/piso_fator`,
`ComiteBaciaAgent` via `piso_fator_outorga`), extendidos em
`models.abm.agents`/`models.abm.model` especificamente para esta tela.

A mudança climática assumida (`fator_clima`) é aplicada IGUAL nos dois
cenários — é uma condição externa, não uma medida de controle local — para
que a comparação isole o efeito das medidas de gestão da bacia.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[3]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from waterweave.config import TRECHOS
from waterweave.models.abm.scenarios import rodar_cenario_customizado
from waterweave.thresholds import STATUS, status_para_iqa
from waterweave.webapp import theme
from waterweave.webapp.data_loader import load_estacoes_tiete

st.set_page_config(page_title="Cenários Futuros — WaterWeave-Tietê", page_icon="🔮", layout="wide")
theme.inject_style()
theme.render_sidebar_brand()

st.title("Cenários Futuros do Rio Tietê")
st.caption(
    "Ajuste as medidas de gestão da bacia e veja, de 5 a 30 anos à frente, o que acontece "
    "se elas **não** forem tomadas vs. se forem tomadas no nível que você escolher. "
    "Simulação real via ABM (Mesa) + balanço hídrico + Streeter-Phelps — não são "
    "multiplicadores ilustrativos. Ver `models.hybrid_bridge` e `models.abm.agents` para as "
    "simplificações assumidas (coeficientes não calibrados em campo, cada trecho simulado de "
    "forma independente, sem propagar carga de montante para jusante)."
)

TRECHO_IDS = list(TRECHOS)

# ---------------------------------------------------------------------------
# Cenário "não controlado" — patamar fixo, pessimista, representando a
# continuidade das tendências atuais sem novas medidas de controle.
# ---------------------------------------------------------------------------
NAO_CONTROLADO_BASE = dict(
    piso_fator_outorga=0.30,
    restricao_ambiental=False,
    fiscaliza_em_serio=False,
    crescimento_mensal_industria=1.01,
    reducao_por_multa=0.90,
    teto_fator_carga_industria=3.0,
    reducao_agricola=0.99,
    piso_fator_difusa=0.90,
)

# ---------------------------------------------------------------------------
# Controles do usuário
# ---------------------------------------------------------------------------
col_horizonte, col_clima = st.columns([2, 1])
with col_horizonte:
    horizonte_anos = st.slider("Horizonte temporal (anos)", min_value=5, max_value=30, value=15, step=1)
with col_clima:
    clima_severidade = st.slider(
        "Severidade da mudança climática assumida", min_value=60, max_value=105, value=90, format="%d%%",
        help="Fator aplicado à chuva climatológica histórica. Aplicado IGUALMENTE aos dois "
        "cenários abaixo — é uma condição externa, não uma medida de controle da bacia.",
    ) / 100.0

st.markdown("#### Medidas de controle — defina o cenário **controlado**")
c1, c2 = st.columns(2)
c3, c4 = st.columns(2)
with c1:
    saneamento_pct = st.slider(
        "🏭 Investimento em saneamento / tratamento de efluentes", 0, 100, 60, format="%d%%",
        help="Reduz a taxa de crescimento mensal e o teto da carga poluidora industrial/doméstica lançada no rio.",
    )
with c2:
    fiscalizacao_pct = st.slider(
        "👮 Rigor da fiscalização ambiental", 0, 100, 60, format="%d%%",
        help="Acima de 50%, o Poder Público passa a multar/agir já no estado 'sério', não só no 'crítico'; "
        "também aumenta o corte de carga aplicado à indústria quando multada.",
    )
with c3:
    agrotoxicos_pct = st.slider(
        "🌾 Controle de agrotóxicos / poluição difusa agrícola", 0, 100, 60, format="%d%%",
        help="Ativa a restrição ambiental sobre o Agricultor e define o quanto ele reduz o uso de agroquímicos.",
    )
with c4:
    outorga_piso = st.slider(
        "💧 Vazão ecológica mínima reservada (outorga)", 0.30, 0.95, 0.60, step=0.05, format="%.2f",
        help="Fração mínima da vazão simulada que o Comitê de Bacia reserva para diluição/captação — "
        "quanto maior, menos captação é permitida em época de estresse hídrico.",
    )

CONTROLADO_PARAMS = dict(
    piso_fator_outorga=outorga_piso,
    restricao_ambiental=agrotoxicos_pct > 0,
    fiscaliza_em_serio=fiscalizacao_pct >= 50,
    crescimento_mensal_industria=1.01 - 0.008 * (saneamento_pct / 100),
    reducao_por_multa=0.90 - 0.35 * (fiscalizacao_pct / 100),
    teto_fator_carga_industria=3.0 - 1.8 * (saneamento_pct / 100),
    reducao_agricola=0.99 - 0.14 * (agrotoxicos_pct / 100),
    piso_fator_difusa=0.90 - 0.50 * (agrotoxicos_pct / 100),
)


# ---------------------------------------------------------------------------
# Execução do ABM (cacheada pelos valores dos sliders)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner="Rodando o modelo de agentes (ABM)...")
def _rodar(parametros: dict, fator_clima: float, horizonte_meses: int) -> pd.DataFrame:
    parametros_completos = {**parametros, "fator_clima": fator_clima}
    return rodar_cenario_customizado(parametros_completos, TRECHO_IDS, horizonte_meses)


horizonte_meses = horizonte_anos * 12
hist_nao_controlado = _rodar(NAO_CONTROLADO_BASE, clima_severidade, horizonte_meses)
hist_controlado = _rodar(CONTROLADO_PARAMS, clima_severidade, horizonte_meses)

# Média ANUAL (não o último mês) por trecho — o clima simulado é sazonal e o
# último mês de um "ano_relativo" pode cair em período seco ou chuvoso quase
# ao acaso, fazendo IQA/OD oscilar de forma enganosa entre extremos se
# usássemos snapshot pontual. A média suaviza a sazonalidade e reflete melhor
# a condição geral do rio naquele ano — base de KPIs, trajetória e animação 3D.
def _media_anual(historico: pd.DataFrame) -> pd.DataFrame:
    anual = historico.groupby(["trecho_id", "ano_relativo"], as_index=False).agg(
        iqa=("iqa", "mean"), od_mg_l=("od_mg_l", "mean"), dbo_mg_l=("dbo_mg_l", "mean"),
        vazao_m3s_medio=("vazao_m3s_medio", "mean"), multas_acumuladas=("multas_acumuladas", "max"),
    )
    return anual


anual_nao_controlado = _media_anual(hist_nao_controlado)
anual_controlado = _media_anual(hist_controlado)

# ---------------------------------------------------------------------------
# Narrativa: o que muda entre os dois cenários
# ---------------------------------------------------------------------------
st.markdown("### O que muda entre os dois cenários")
st.caption(
    "Estas são as medidas que, se **não** tomadas, geram o cenário à esquerda nos gráficos abaixo."
)
narrativa = []
if saneamento_pct < 20:
    narrativa.append(
        f"🏭 **Saneamento** ({saneamento_pct}%): quase nenhum investimento adicional em tratamento — a carga "
        f"industrial/doméstica pode crescer até {CONTROLADO_PARAMS['teto_fator_carga_industria']:.1f}x o valor "
        f"atual, próximo do teto do cenário não controlado (3,0x)."
    )
else:
    narrativa.append(
        f"🏭 **Saneamento** ({saneamento_pct}%): o teto de crescimento da carga industrial/doméstica cai de "
        f"3,0x (não controlado) para {CONTROLADO_PARAMS['teto_fator_carga_industria']:.1f}x o valor atual, e o "
        f"crescimento mensal desacelera de 1,0% para {(CONTROLADO_PARAMS['crescimento_mensal_industria']-1)*100:.2f}% ao mês."
    )
if fiscalizacao_pct < 50:
    narrativa.append(
        f"👮 **Fiscalização** ({fiscalizacao_pct}%): o Poder Público só age quando o rio já está em estado "
        f"crítico (igual ao cenário não controlado), e o corte de carga aplicado à indústria multada é fraco "
        f"({CONTROLADO_PARAMS['reducao_por_multa']:.0%} do valor anterior)."
    )
else:
    narrativa.append(
        f"👮 **Fiscalização** ({fiscalizacao_pct}%): o Poder Público passa a agir já no estado 'sério', antes "
        f"do colapso, e corta a carga industrial multada para {CONTROLADO_PARAMS['reducao_por_multa']:.0%} do "
        f"valor anterior (contra 90% no cenário não controlado)."
    )
if agrotoxicos_pct < 20:
    narrativa.append(
        "🌾 **Agrotóxicos** (" + str(agrotoxicos_pct) + "%): nenhuma restrição ambiental sobre o uso de "
        "agroquímicos é ativada — igual ao cenário não controlado."
    )
else:
    narrativa.append(
        f"🌾 **Agrotóxicos** ({agrotoxicos_pct}%): restrição ambiental ativa; o uso de agroquímicos pode ser "
        f"reduzido até o piso de {CONTROLADO_PARAMS['piso_fator_difusa']:.0%} da carga difusa-base (contra 90% "
        f"no cenário não controlado)."
    )
narrativa.append(
    f"💧 **Outorga/captação**: vazão ecológica mínima reservada de {outorga_piso:.0%} da vazão simulada "
    f"(contra apenas 30% no cenário não controlado, onde mais água é liberada para captação mesmo em seca)."
)
for linha in narrativa:
    st.markdown(f"- {linha}")

# ---------------------------------------------------------------------------
# KPIs comparativos ao fim do horizonte
# ---------------------------------------------------------------------------
st.markdown(f"### Estado simulado ao final de {horizonte_anos} anos, por trecho")
colunas_kpi = st.columns(len(TRECHO_IDS))
for coluna, trecho_id in zip(colunas_kpi, TRECHO_IDS):
    linha_nc = anual_nao_controlado[
        (anual_nao_controlado.trecho_id == trecho_id) & (anual_nao_controlado.ano_relativo == horizonte_anos)
    ]
    linha_c = anual_controlado[
        (anual_controlado.trecho_id == trecho_id) & (anual_controlado.ano_relativo == horizonte_anos)
    ]
    with coluna, st.container(border=True):
        st.markdown(f"**{theme.TRECHO_LABEL[trecho_id]}**")
        if linha_nc.empty or linha_c.empty:
            st.info("Sem dado simulado para este horizonte.")
            continue
        iqa_nc, iqa_c = float(linha_nc["iqa"].iloc[0]), float(linha_c["iqa"].iloc[0])
        od_nc, od_c = float(linha_nc["od_mg_l"].iloc[0]), float(linha_c["od_mg_l"].iloc[0])
        status_nc = STATUS[status_para_iqa(iqa_nc)]
        status_c = STATUS[status_para_iqa(iqa_c)]
        st.metric("IQA — não controlado", f"{iqa_nc:.1f}", help=status_nc["label"])
        st.metric("IQA — controlado", f"{iqa_c:.1f}", delta=f"{iqa_c - iqa_nc:+.1f}")
        st.markdown(
            f"{status_nc['icon']} não controlado: **{status_nc['label']}** &nbsp;→&nbsp; "
            f"{status_c['icon']} controlado: **{status_c['label']}**"
        )
        st.caption(f"OD: {od_nc:.2f} mg/L → {od_c:.2f} mg/L")

# ---------------------------------------------------------------------------
# Trajetória ao longo do tempo (2D, preciso — complementa a visão 3D)
# ---------------------------------------------------------------------------
st.markdown("### Trajetória ano a ano")
trecho_selecionado = st.selectbox(
    "Trecho", options=TRECHO_IDS, format_func=lambda t: theme.TRECHO_LABEL[t], key="trecho_trajetoria"
)
parametro_key = st.radio(
    "Parâmetro", options=["iqa", "od_mg_l", "dbo_mg_l"],
    format_func=lambda k: {"iqa": "IQA simulado", "od_mg_l": "Oxigênio Dissolvido (mg/L)", "dbo_mg_l": "DBO (mg/L)"}[k],
    horizontal=True,
)
serie_nc = anual_nao_controlado[anual_nao_controlado.trecho_id == trecho_selecionado].sort_values("ano_relativo")
serie_c = anual_controlado[anual_controlado.trecho_id == trecho_selecionado].sort_values("ano_relativo")

fig_traj = go.Figure()
fig_traj.add_trace(go.Scatter(
    x=serie_nc.ano_relativo, y=serie_nc[parametro_key], name="Não controlado",
    line=dict(color="#d03b3b", width=2.5, dash="dash"), mode="lines+markers",
))
fig_traj.add_trace(go.Scatter(
    x=serie_c.ano_relativo, y=serie_c[parametro_key], name="Controlado",
    line=dict(color="#1baf7a", width=2.5), mode="lines+markers",
))
fig_traj.update_xaxes(title="Anos a partir de hoje")
theme.apply_common_layout(fig_traj, y_title=parametro_key)
with st.container(border=True):
    st.plotly_chart(fig_traj, width="stretch")

# ---------------------------------------------------------------------------
# Animação 3D — perfil longitudinal do rio, nascente -> foz, evoluindo ano a ano
# ---------------------------------------------------------------------------
st.markdown("### Animação 3D — o rio inteiro, ano a ano")
st.caption(
    "Eixo Z = severidade da poluição simulada (100 − IQA) — quanto mais alto, pior. Cada ponto real de "
    "monitoramento recebe o valor simulado do trecho ao qual pertence. Use o botão ▶ ou arraste o controle "
    "de ano."
)

estacoes = load_estacoes_tiete().dropna(subset=["longitude", "latitude"]).copy()
estacoes = estacoes.sort_values("longitude", ascending=False).reset_index(drop=True)

STATUS_COLOR = {chave: valor["color"] for chave, valor in STATUS.items()}


def _construir_series_por_ponto(anual: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """Para cada ano, retorna um DataFrame (1 linha por ponto de estação) com iqa/severidade/cor."""
    por_ano = {}
    for ano in sorted(anual["ano_relativo"].unique()):
        estado_trecho = anual[anual.ano_relativo == ano].set_index("trecho_id")["iqa"].to_dict()
        pontos = estacoes.copy()
        pontos["iqa"] = pontos["trecho_id"].map(estado_trecho)
        pontos = pontos.dropna(subset=["iqa"])
        pontos["severidade"] = 100 - pontos["iqa"]
        pontos["cor"] = pontos["iqa"].apply(lambda v: STATUS_COLOR[status_para_iqa(v)])
        por_ano[ano] = pontos
    return por_ano


series_nc = _construir_series_por_ponto(anual_nao_controlado)
series_c = _construir_series_por_ponto(anual_controlado)
anos_disponiveis = sorted(series_nc.keys())


def _stems(pontos: pd.DataFrame):
    """Segmentos verticais (leito -> severidade) separados por None, para 1 único trace por cena."""
    xs, ys, zs = [], [], []
    for _, p in pontos.iterrows():
        xs += [p["longitude"], p["longitude"], None]
        ys += [p["latitude"], p["latitude"], None]
        zs += [0, p["severidade"], None]
    return xs, ys, zs


def _trace_leito(scene_suffix: str) -> go.Scatter3d:
    return go.Scatter3d(
        x=estacoes["longitude"], y=estacoes["latitude"], z=[0] * len(estacoes),
        mode="lines", line=dict(color="#9ec5f4", width=3), showlegend=False,
        scene=scene_suffix, hoverinfo="skip",
    )


def _trace_perfil(pontos: pd.DataFrame, scene_suffix: str, nome: str) -> go.Scatter3d:
    return go.Scatter3d(
        x=pontos["longitude"], y=pontos["latitude"], z=pontos["severidade"],
        mode="lines+markers",
        line=dict(color="#3a3a36", width=4),
        marker=dict(size=6, color=pontos["cor"]),
        text=pontos["municipio"] + " (IQA " + pontos["iqa"].round(1).astype(str) + ")",
        hoverinfo="text", name=nome, scene=scene_suffix, showlegend=False,
    )


def _trace_stems(pontos: pd.DataFrame, scene_suffix: str) -> go.Scatter3d:
    xs, ys, zs = _stems(pontos)
    return go.Scatter3d(
        x=xs, y=ys, z=zs, mode="lines", line=dict(color="rgba(150,60,60,0.35)", width=2),
        scene=scene_suffix, showlegend=False, hoverinfo="skip",
    )


fig3d = make_subplots(
    rows=1, cols=2, specs=[[{"type": "scene"}, {"type": "scene"}]],
    subplot_titles=("Não controlado", "Controlado"), horizontal_spacing=0.02,
)

ano0 = anos_disponiveis[0]
traces_iniciais = [
    _trace_leito("scene"), _trace_stems(series_nc[ano0], "scene"), _trace_perfil(series_nc[ano0], "scene", "Não controlado"),
    _trace_leito("scene2"), _trace_stems(series_c[ano0], "scene2"), _trace_perfil(series_c[ano0], "scene2", "Controlado"),
]
for i, tr in enumerate(traces_iniciais):
    fig3d.add_trace(tr, row=1, col=(1 if i < 3 else 2))

frames = []
for ano in anos_disponiveis:
    xs_nc, ys_nc, zs_nc = _stems(series_nc[ano])
    xs_c, ys_c, zs_c = _stems(series_c[ano])
    frames.append(go.Frame(
        name=str(ano),
        data=[
            go.Scatter3d(x=xs_nc, y=ys_nc, z=zs_nc),
            go.Scatter3d(
                x=series_nc[ano]["longitude"], y=series_nc[ano]["latitude"], z=series_nc[ano]["severidade"],
                marker=dict(color=series_nc[ano]["cor"]),
                text=series_nc[ano]["municipio"] + " (IQA " + series_nc[ano]["iqa"].round(1).astype(str) + ")",
            ),
            go.Scatter3d(x=xs_c, y=ys_c, z=zs_c),
            go.Scatter3d(
                x=series_c[ano]["longitude"], y=series_c[ano]["latitude"], z=series_c[ano]["severidade"],
                marker=dict(color=series_c[ano]["cor"]),
                text=series_c[ano]["municipio"] + " (IQA " + series_c[ano]["iqa"].round(1).astype(str) + ")",
            ),
        ],
        traces=[1, 2, 4, 5],
    ))
fig3d.frames = frames

eixo_cena = dict(
    xaxis_title="Longitude", yaxis_title="Latitude", zaxis_title="Severidade (100 − IQA)",
    aspectmode="manual", aspectratio=dict(x=2.2, y=1.4, z=1.0),
    camera=dict(eye=dict(x=1.6, y=-1.7, z=0.9)),
)
fig3d.update_layout(
    height=620,
    scene=eixo_cena,
    scene2=eixo_cena,
    margin=dict(l=0, r=0, t=40, b=0),
    updatemenus=[dict(
        type="buttons", showactive=False, x=0.02, y=1.08, xanchor="left",
        buttons=[
            dict(label="▶ Reproduzir", method="animate",
                 args=[None, {"frame": {"duration": 700, "redraw": True}, "fromcurrent": True, "transition": {"duration": 200}}]),
            dict(label="⏸ Pausar", method="animate",
                 args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}]),
        ],
    )],
    sliders=[dict(
        active=0, x=0.1, len=0.85, y=0,
        currentvalue=dict(prefix="Ano ", font=dict(size=14)),
        steps=[
            dict(label=str(ano), method="animate",
                 args=[[str(ano)], {"frame": {"duration": 0, "redraw": True}, "mode": "immediate"}])
            for ano in anos_disponiveis
        ],
    )],
)
with st.container(border=True):
    st.plotly_chart(fig3d, width="stretch")

with st.expander("Premissas e limitações desta simulação"):
    st.markdown(
        "- O IQA usado aqui é um **proxy simplificado** (`models.hybrid_bridge.iqa_proxy`, função de OD/DBO), "
        "não o IQA oficial CETESB/NSF de 9 parâmetros.\n"
        "- Cada trecho é simulado **de forma independente** — a carga/vazão do Alto Tietê não é propagada "
        "para o Médio, nem deste para o Baixo (extensão natural, não implementada).\n"
        "- Coeficientes de Streeter-Phelps e do balanço hídrico são valores típicos de literatura, "
        "**não calibrados especificamente para o Tietê**.\n"
        "- A animação 3D atribui a cada ponto real de monitoramento o valor simulado do **trecho** ao qual "
        "pertence — não há simulação em granularidade de ponto individual.\n"
        "- O cenário 'não controlado' é um patamar fixo definido para esta página (não um dos 3 cenários "
        "de `3_Comparativo_Cenarios.py`), representando a continuidade das regras de decisão sem "
        "novas medidas de controle."
    )
