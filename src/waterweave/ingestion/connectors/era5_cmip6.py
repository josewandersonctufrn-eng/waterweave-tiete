"""Conector para dados climáticos históricos (CRU/ERA5) e projeções futuras (CMIP6).

ERA5 alimenta a Silver histórica (reanálise horária/diária de precipitação e
temperatura); CMIP6 alimenta os cenários de mudança climática usados no
comparativo de cenários do dashboard (Atual vs. Alta Restrição de Outorga vs.
Mudança Climática Extrema).
"""
from __future__ import annotations

from datetime import date

import pandas as pd


def fetch_reanalysis(since: date, bbox: tuple[float, float, float, float]) -> pd.DataFrame:
    """Busca reanálise ERA5 (precipitação, temperatura) para a bounding box da bacia desde `since`."""
    raise NotImplementedError


def fetch_projection(cenario: str, bbox: tuple[float, float, float, float]) -> pd.DataFrame:
    """Busca projeções CMIP6 para um cenário (ex.: SSP2-4.5, SSP5-8.5) e bounding box informados."""
    raise NotImplementedError
