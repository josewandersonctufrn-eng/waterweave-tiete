"""Ponte híbrida: integra o balanço hídrico biofísico com a resposta de qualidade da água
a cada passo mensal, sob os parâmetros de decisão que os agentes do ABM ajustam.

Não inclui o modelo de ML aqui — `models.ml.predict_iqa` serve um propósito
diferente (previsão estatística rápida a partir do histórico observado,
para o dashboard) do que este módulo (simulação determinística por
cenário, para o ABM `step` a `step`). Ambos consomem a mesma Gold, mas não
se chamam um ao outro.

Calibração: o balanço hídrico (`models.biofisico.balanco_hidrico`) produz
um ÍNDICE de escoamento (mm/mês), não uma vazão absoluta — ver docstring
daquele módulo. Aqui ele é convertido para m³/s por um fator calibrado uma
única vez por trecho: roda-se o balanço sobre toda a chuva histórica do
trecho e ancora-se a média do índice resultante na vazão média REAL
observada (`gold.serie_temporal_trecho_mes`) no mesmo período.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from waterweave.config import GOLD_DIR
from waterweave.io_delta import read_table
from waterweave.models.biofisico import balanco_hidrico, parametros_estendidos, qualidade_agua

# Distância típica entre um lançamento de efluente e o ponto de monitoramento
# dentro do trecho (km) — muito menor que o comprimento total do trecho
# (`config.TRECHOS`, que mede distância acumulada da nascente): o
# Streeter-Phelps aqui modela a resposta de curto alcance a um lançamento,
# não o trecho inteiro. Valores aproximados, sem calibração de campo.
DISTANCIA_REFERENCIA_KM = {"alto_tiete": 25.0, "medio_tiete": 35.0, "baixo_tiete": 45.0}

IQA_PESO_OD = 20.0
IQA_PESO_DBO = 2.0
IQA_OFFSET = 40.0

# Fração da carga poluidora total observada atribuída a fontes industriais
# (pontuais) vs. difusas agrícolas — a Gold não desagrega por fonte, então
# esta é uma suposição documentada para dar ao ABM duas alavancas
# independentes (Indústria e Agricultor).
FRACAO_CARGA_INDUSTRIAL = 0.6
FRACAO_CARGA_DIFUSA = 0.4


def iqa_proxy(od_mg_l: float, dbo_mg_l: float) -> float:
    """Proxy simplificado de IQA a partir de OD/DBO.

    NÃO é o IQA oficial (NSF/CETESB, que pondera 9 parâmetros: OD,
    coliformes, pH, DBO, temperatura, nitrogênio, fósforo, turbidez,
    sólidos totais) — serve apenas para o ABM ter um indicador rápido e
    monotônico na direção certa (sobe com OD, desce com DBO).
    """
    valor = IQA_PESO_OD * od_mg_l - IQA_PESO_DBO * dbo_mg_l + IQA_OFFSET
    return max(0.0, min(100.0, valor))


@dataclass
class ParametrosAgentes:
    """Parâmetros de decisão que os agentes do ABM ajustam a cada passo."""

    fator_outorga: float = 0.90  # fração da vazão simulada que permanece disponível para diluição
    fator_carga_industria: float = 1.0  # multiplicador sobre a carga industrial-base
    fator_carga_difusa: float = 1.0  # multiplicador sobre a carga difusa agrícola-base


@dataclass
class PassoHibrido:
    trecho_id: str
    mes_data: pd.Timestamp
    estado_hidrologico: balanco_hidrico.EstadoHidrologico
    vazao_simulada_m3s: float
    od_simulado_mg_l: float
    dbo_simulado_mg_l: float
    iqa_simulado: float
    turbidez_ntu: float
    solidos_totais_mg_l: float
    temperatura_c: float
    ph: float
    fosforo_mg_l: float
    nitrogenio_mg_l: float
    e_coli_nmp_100ml: float
    metais_toxicos_indice: float
    indice_biotico: float


@lru_cache(maxsize=None)
def _fator_conversao_indice_para_vazao(trecho_id: str) -> float:
    """Calibra (uma vez, em cache) o fator m³/s por mm de índice de escoamento para o trecho."""
    serie = read_table(GOLD_DIR / "serie_temporal_trecho_mes")
    historico = serie[serie["trecho_id"] == trecho_id].dropna(subset=["chuva_mm_media"]).sort_values("mes_data")
    if historico.empty:
        return 1.0

    estado = balanco_hidrico.estado_inicial(trecho_id)
    indices = []
    for _, linha in historico.iterrows():
        estado = balanco_hidrico.simular_passo_mensal(estado, linha["chuva_mm_media"], linha.get("uso_solo"))
        indices.append(estado.indice_escoamento_mm)

    indice_medio = sum(indices) / len(indices)
    vazao_media_real = historico["vazao_m3s_medio"].dropna().mean()
    if indice_medio <= 0 or pd.isna(vazao_media_real):
        return 1.0
    return float(vazao_media_real / indice_medio)


@lru_cache(maxsize=None)
def carga_base_trecho_kg_dia(trecho_id: str) -> float:
    """Carga poluidora total implícita nos dados históricos mais recentes (kg DBO/dia).

    Back-calculada de `DBO(mg/L) x vazão(m³/s) x 86.4` sobre o último ano
    com dado de qualidade disponível — ancora a simulação em magnitude
    real, em vez de um valor de carga arbitrário.
    """
    serie = read_table(GOLD_DIR / "serie_temporal_trecho_mes")
    historico = serie[serie["trecho_id"] == trecho_id].dropna(subset=["dbo_mg_l"]).sort_values("mes_data")
    if historico.empty:
        return 0.0
    ultimo = historico.iloc[-1]
    vazao_ref = historico["vazao_m3s_medio"].dropna().mean()
    if pd.isna(vazao_ref):
        return 0.0
    return float(ultimo["dbo_mg_l"] * vazao_ref * 86.4)


@lru_cache(maxsize=None)
def _vazao_media_historica_trecho(trecho_id: str) -> float:
    """Vazão média histórica real do trecho (`gold.serie_temporal_trecho_mes`) — usada só para
    back-calcular a carga-base dos parâmetros estendidos (`carga_base_*_kg_dia`), mesmo padrão
    de `carga_base_trecho_kg_dia`."""
    serie = read_table(GOLD_DIR / "serie_temporal_trecho_mes")
    historico = serie[serie["trecho_id"] == trecho_id]["vazao_m3s_medio"].dropna()
    return float(historico.mean()) if not historico.empty else 1.0


@lru_cache(maxsize=None)
def carga_base_fosforo_kg_dia(trecho_id: str) -> float:
    return parametros_estendidos.carga_base_kg_dia(
        parametros_estendidos.ANCORA_FOSFORO_MG_L[trecho_id], _vazao_media_historica_trecho(trecho_id)
    )


@lru_cache(maxsize=None)
def carga_base_nitrogenio_kg_dia(trecho_id: str) -> float:
    return parametros_estendidos.carga_base_kg_dia(
        parametros_estendidos.ANCORA_NITROGENIO_MG_L[trecho_id], _vazao_media_historica_trecho(trecho_id)
    )


@lru_cache(maxsize=None)
def carga_base_ecoli_kg_dia(trecho_id: str) -> float:
    return parametros_estendidos.carga_base_kg_dia(
        parametros_estendidos.ANCORA_ECOLI_NMP_100ML[trecho_id], _vazao_media_historica_trecho(trecho_id)
    )


def estado_hidrologico_inicial(trecho_id: str) -> balanco_hidrico.EstadoHidrologico:
    return balanco_hidrico.estado_inicial(trecho_id)


def executar_passo(
    trecho_id: str,
    mes_data: pd.Timestamp,
    estado_hidrologico_anterior: balanco_hidrico.EstadoHidrologico,
    parametros_agentes: ParametrosAgentes,
    chuva_mm: float,
    uso_solo: str | None,
    fator_clima: float = 1.0,
) -> PassoHibrido:
    """Executa um passo mensal completo (biofísico -> qualidade da água) para um trecho,
    sob os parâmetros de decisão vigentes dos agentes."""
    novo_estado_hidrologico = balanco_hidrico.simular_passo_mensal(estado_hidrologico_anterior, chuva_mm, uso_solo)
    fator = _fator_conversao_indice_para_vazao(trecho_id)
    vazao_simulada = max(0.01, novo_estado_hidrologico.indice_escoamento_mm * fator)

    carga_base = carga_base_trecho_kg_dia(trecho_id)
    carga_total = (
        parametros_agentes.fator_carga_industria * FRACAO_CARGA_INDUSTRIAL * carga_base
        + parametros_agentes.fator_carga_difusa * FRACAO_CARGA_DIFUSA * carga_base
    )
    vazao_diluicao = vazao_simulada * parametros_agentes.fator_outorga

    od, dbo = qualidade_agua.simular_od_dbo(vazao_diluicao, carga_total, DISTANCIA_REFERENCIA_KM[trecho_id])
    iqa = iqa_proxy(od, dbo)

    estendidos = parametros_estendidos.simular_parametros_estendidos(
        trecho_id=trecho_id,
        fator_carga_industria=parametros_agentes.fator_carga_industria,
        fator_carga_difusa=parametros_agentes.fator_carga_difusa,
        vazao_diluicao_m3s=vazao_diluicao,
        indice_escoamento_mm=novo_estado_hidrologico.indice_escoamento_mm,
        dbo_simulado_mg_l=dbo,
        od_simulado_mg_l=od,
        fator_clima=fator_clima,
        carga_base_fosforo_kg_dia=carga_base_fosforo_kg_dia(trecho_id),
        carga_base_nitrogenio_kg_dia=carga_base_nitrogenio_kg_dia(trecho_id),
        carga_base_ecoli_kg_dia=carga_base_ecoli_kg_dia(trecho_id),
    )

    return PassoHibrido(
        trecho_id=trecho_id,
        mes_data=mes_data,
        estado_hidrologico=novo_estado_hidrologico,
        vazao_simulada_m3s=vazao_simulada,
        od_simulado_mg_l=od,
        dbo_simulado_mg_l=dbo,
        iqa_simulado=iqa,
        turbidez_ntu=estendidos.turbidez_ntu,
        solidos_totais_mg_l=estendidos.solidos_totais_mg_l,
        temperatura_c=estendidos.temperatura_c,
        ph=estendidos.ph,
        fosforo_mg_l=estendidos.fosforo_mg_l,
        nitrogenio_mg_l=estendidos.nitrogenio_mg_l,
        e_coli_nmp_100ml=estendidos.e_coli_nmp_100ml,
        metais_toxicos_indice=estendidos.metais_toxicos_indice,
        indice_biotico=estendidos.indice_biotico,
    )
