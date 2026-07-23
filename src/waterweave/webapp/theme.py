"""Paleta e convenções visuais compartilhadas por todas as páginas do dashboard.

Valores vindos da skill de dataviz do projeto (paleta validada para
distinção categórica sob daltonismo, sequencial de uma cor para magnitude,
divergente para deltas de cenário e status fixo para alertas).
"""
from __future__ import annotations

from collections.abc import Mapping

import plotly.graph_objects as go
import streamlit as st

from waterweave.config import TRECHOS
from waterweave.thresholds import STATUS, status_para_iqa, status_para_od  # noqa: F401 (re-exported for webapp callers)
from waterweave.webapp import i18n

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

_TRECHO_CHAVE_I18N = {"alto_tiete": "trecho.alto", "medio_tiete": "trecho.medio", "baixo_tiete": "trecho.baixo"}


class _TrechoLabelMapping(Mapping):
    """Mapping trecho_id -> nome traduzido no idioma corrente da sessão. Implementa
    `Mapping` (não um `dict` estático) para que `theme.TRECHO_LABEL[t]`, `.map(theme.TRECHO_LABEL)`
    e `list(theme.TRECHO_LABEL)` continuem funcionando em todos os call sites existentes,
    mas resolvendo a tradução em tempo real a cada chamada."""

    def __getitem__(self, trecho_id: str) -> str:
        chave = _TRECHO_CHAVE_I18N.get(trecho_id)
        return i18n.t(chave) if chave else trecho_id

    def __iter__(self):
        return iter(TRECHOS)

    def __len__(self) -> int:
        return len(TRECHOS)


TRECHO_LABEL = _TrechoLabelMapping()


def status_label(status_key: str) -> str:
    """Rótulo traduzido do status fixo (Bom/Atenção/Sério/Crítico) no idioma corrente."""
    return i18n.t(f"status.{ {'good': 'bom', 'warning': 'atencao', 'serious': 'serio', 'critical': 'critico'}[status_key] }")

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


def inject_style() -> None:
    """Injeta o CSS compartilhado (tipografia, espaçamento, cards) — chamar uma vez no topo de cada página.

    Complementa `.streamlit/config.toml` (cores/paleta de widgets nativos);
    aqui só refinamos tipografia e espaçamento que o theme.toml não cobre.
    """
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] { font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif; }

        /* Menos espaço morto no topo — a primeira dobra some com "cara de template" */
        .block-container { padding-top: 2.2rem; padding-bottom: 3rem; }

        h1 { font-weight: 700; letter-spacing: -0.02em; }
        h2, h3 { font-weight: 600; letter-spacing: -0.01em; }

        /* KPIs como cartões discretos, em vez do st.metric "nu" */
        div[data-testid="stMetric"] {
            background: var(--secondary-background-color, #f2f1ee);
            border: 1px solid rgba(11,11,11,0.08);
            border-radius: 10px;
            padding: 0.9rem 1rem 0.7rem;
        }
        div[data-testid="stMetricLabel"] { font-weight: 500; }

        /* Remove o rodapé "Made with Streamlit" — ruído visual, não informação */
        footer { visibility: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_brand() -> None:
    """Cabeçalho de marca discreto no topo da sidebar — chamar uma vez por página."""
    st.sidebar.markdown(
        """
        <div style="padding: 0.2rem 0 1rem; border-bottom: 1px solid rgba(11,11,11,0.08); margin-bottom: 1rem;">
            <div style="font-weight:700; font-size:1.05rem; letter-spacing:-0.01em;">WaterWeave</div>
            <div style="font-size:0.75rem; color:#898781; text-transform:uppercase; letter-spacing:0.06em;">
                Rio Tietê · 1940–2025
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
