"""Paleta e convenções visuais compartilhadas por todas as páginas do dashboard.

Valores vindos da skill de dataviz do projeto (paleta validada para
distinção categórica sob daltonismo, sequencial de uma cor para magnitude,
divergente para deltas de cenário e status fixo para alertas).
"""
from __future__ import annotations

import plotly.graph_objects as go

from waterweave.config import TRECHOS
from waterweave.thresholds import STATUS, status_para_iqa, status_para_od  # noqa: F401 (re-exported for webapp callers)

# Categórica: ordem fixa, nunca ciclar. Usada por trecho (Alto/Médio/Baixo)
# e, quando preciso, por parâmetro dentro de um mesmo trecho.
CATEGORICAL = {
    "blue": "#2a78d6",
    "aqua": "#1baf7a",
    "yellow": "#eda100",
    "green": "#008300",
    "violet": "#4a3aa7",
    "red": "#e34948",
    "magenta": "#e87ba4",
    "orange": "#eb6834",
}

# Um trecho -> uma cor, sempre a mesma em todas as páginas.
TRECHO_COLOR = {
    "alto_tiete": CATEGORICAL["blue"],
    "medio_tiete": CATEGORICAL["aqua"],
    "baixo_tiete": CATEGORICAL["orange"],
}

TRECHO_LABEL = {trecho_id: trecho.nome for trecho_id, trecho in TRECHOS.items()}

# Um cenário -> uma cor, sempre a mesma em todas as páginas (distinta das cores de trecho).
SCENARIO_COLOR = {
    "atual": CATEGORICAL["blue"],
    "alta_restricao_outorga": CATEGORICAL["violet"],
    "mudanca_climatica_extrema": CATEGORICAL["red"],
}

# Sequencial (uma cor, claro -> escuro) para magnitude contínua (ex.: mapa de calor de turbidez).
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]

# Divergente para deltas de cenário (% de variação vs. Atual). Ponto médio neutro.
DIVERGING = {"neg": "#2a78d6", "mid": "#f0efec", "pos": "#e34948"}

MUTED_INK = "#898781"
GRIDLINE = "#e1e0d9"


def apply_common_layout(fig: go.Figure, *, y_title: str, legend: bool = True) -> go.Figure:
    """Aplica chrome consistente: fundo transparente (segue o tema do Streamlit),
    grid discreto, eixo único, legenda só quando há >=2 séries."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=40, b=10),
        hovermode="x unified",
        font=dict(color=MUTED_INK),
    )
    fig.update_xaxes(showgrid=False, showline=True, linecolor=GRIDLINE)
    fig.update_yaxes(title=y_title, showgrid=True, gridcolor=GRIDLINE, zeroline=False)
    return fig
