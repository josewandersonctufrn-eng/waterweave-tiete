"""Modelo biofísico de qualidade da água — curva de depleção de oxigênio de Streeter-Phelps.

Formulação clássica: o déficit de OD a jusante de um lançamento de DBO
decai/cresce por desoxigenação (kd) e reaeração (kr) ao longo do tempo de
trânsito até o ponto de observação. Coeficientes kd/kr usam valores típicos
de literatura para rios de médio porte — não calibrados para o Tietê
especificamente (exigiria campanhas de campo fora do escopo deste
projeto).
"""
from __future__ import annotations

import math

KD_DESOXIGENACAO_DIA = 0.23  # 1/dia, típico para DBO de origem doméstica/mista
KR_REAERACAO_DIA = 0.40  # 1/dia, típico para rio de médio porte com alguma turbulência
OD_SATURACAO_MG_L = 9.08  # mg/L, aprox. a 20°C e baixa altitude


def _velocidade_m_s(vazao_m3s: float) -> float:
    """Relação simplificada de geometria hidráulica (velocidade cresce com a vazão)."""
    return max(0.05, 0.12 * max(vazao_m3s, 0.01) ** 0.3)


def simular_od_dbo(
    vazao_m3s: float,
    carga_dbo_kg_dia: float,
    distancia_km: float,
    od_montante_mg_l: float | None = None,
) -> tuple[float, float]:
    """Retorna (OD_mg_L, DBO_mg_L) estimados a `distancia_km` a jusante do lançamento.

    `carga_dbo_kg_dia` é a carga poluidora efetiva (industrial + difusa)
    lançada no trecho; `vazao_m3s` é a vazão disponível para diluição
    (já descontada eventual captação/outorga).
    """
    vazao_m3s = max(vazao_m3s, 0.01)
    velocidade = _velocidade_m_s(vazao_m3s)
    tempo_dias = (distancia_km * 1000 / velocidade) / 86400

    l0_mg_l = (carga_dbo_kg_dia * 1_000_000) / (vazao_m3s * 86400 * 1000)  # kg/dia -> mg/L diluído na vazão
    od_montante = od_montante_mg_l if od_montante_mg_l is not None else OD_SATURACAO_MG_L
    d0 = max(0.0, OD_SATURACAO_MG_L - od_montante)

    if abs(KR_REAERACAO_DIA - KD_DESOXIGENACAO_DIA) < 1e-9:
        deficit = (KD_DESOXIGENACAO_DIA * l0_mg_l * tempo_dias) * math.exp(-KD_DESOXIGENACAO_DIA * tempo_dias) + d0 * math.exp(
            -KR_REAERACAO_DIA * tempo_dias
        )
    else:
        deficit = (KD_DESOXIGENACAO_DIA * l0_mg_l / (KR_REAERACAO_DIA - KD_DESOXIGENACAO_DIA)) * (
            math.exp(-KD_DESOXIGENACAO_DIA * tempo_dias) - math.exp(-KR_REAERACAO_DIA * tempo_dias)
        ) + d0 * math.exp(-KR_REAERACAO_DIA * tempo_dias)

    od_jusante = max(0.0, OD_SATURACAO_MG_L - deficit)
    dbo_jusante = l0_mg_l * math.exp(-KD_DESOXIGENACAO_DIA * tempo_dias)
    return od_jusante, dbo_jusante
