"""Limiares de classificação do estado ecológico, compartilhados por `reports` e `webapp`.

Módulo de domínio puro (sem dependência de Streamlit) para que
`reports.narrative_generator` e outros consumidores não-web possam
classificar IQA/OD sem importar a camada de apresentação.
"""
from __future__ import annotations

STATUS = {
    "good": {"color": "#0ca30c", "icon": "✅", "label": "Bom"},
    "warning": {"color": "#fab219", "icon": "⚠️", "label": "Atenção"},
    "serious": {"color": "#ec835a", "icon": "🟠", "label": "Sério"},
    "critical": {"color": "#d03b3b", "icon": "🔴", "label": "Crítico"},
}


def status_para_od(od_mg_l: float) -> str:
    """Classifica Oxigênio Dissolvido (mg/L) em status fixo, seguindo limiares CONAMA/CETESB."""
    if od_mg_l < 2:
        return "critical"
    if od_mg_l < 4:
        return "serious"
    if od_mg_l < 5:
        return "warning"
    return "good"


def status_para_iqa(iqa: float) -> str:
    """Classifica Índice de Qualidade da Água (0-100) em status fixo."""
    if iqa < 25:
        return "critical"
    if iqa < 50:
        return "serious"
    if iqa < 70:
        return "warning"
    return "good"
