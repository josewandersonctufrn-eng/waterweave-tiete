"""Camada de uso e cobertura do solo: converte classes de uso do solo em parâmetros biofísicos.

Coeficientes de escoamento (fração da precipitação que vira escoamento
direto — lógica tipo Curve Number, simplificada). As classes abaixo são
exatamente as que aparecem em `silver.qualidade` (coluna `uso_solo`); ao
trocar essa fonte simulada por uso do solo real (MapBiomas, via
`ingestion.connectors.mapbiomas`), os nomes de classe devem ser
remapeados aqui.
"""
from __future__ import annotations

_COEFICIENTE_POR_CLASSE = {
    "Agrícola / Vegetação Natural": 0.20,
    "Pecuária e Vegetação": 0.25,
    "Agrícola Tradicional": 0.35,
    "Hidrovia e Agropecuária": 0.35,
    "Agroindustrial (Cana / Citros)": 0.45,
    "Metropolitano / Industrial": 0.70,
    "Urbano Intenso / Industrial": 0.80,
}

_COEFICIENTE_PADRAO = 0.35  # fallback para classes não catalogadas


def classe_para_coeficiente_escoamento(classe_uso_solo: str | None) -> float:
    """Retorna o coeficiente de escoamento superficial associado à classe de uso do solo."""
    if classe_uso_solo is None:
        return _COEFICIENTE_PADRAO
    return _COEFICIENTE_POR_CLASSE.get(classe_uso_solo, _COEFICIENTE_PADRAO)
