"""Definição dos cenários comparativos exibidos no dashboard.

Cada cenário configura os parâmetros iniciais/estruturais do `RioTieteModel`:
  - "atual": clima e regras de decisão sem alteração.
  - "alta_restricao_outorga": piso de outorga mais alto (menos captação
    permitida) e agricultores sob pressão regulatória ativa.
  - "mudanca_climatica_extrema": chuva reduzida em 25% — proxy simplificado
    para um cenário de aquecimento tipo CMIP6 SSP5-8.5, até que
    `ingestion.connectors.era5_cmip6` forneça a projeção real.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from waterweave.models.abm.model import RioTieteModel


@dataclass(frozen=True)
class Cenario:
    id: str
    nome: str
    descricao: str


CENARIOS = {
    "atual": Cenario("atual", "Cenário Atual", "Regras de decisão e clima observado/climatológico sem alteração."),
    "alta_restricao_outorga": Cenario(
        "alta_restricao_outorga",
        "Alta Restrição de Outorga",
        "Piso de outorga elevado (menos captação permitida) e restrição ambiental ativa sobre uso agrícola.",
    ),
    "mudanca_climatica_extrema": Cenario(
        "mudanca_climatica_extrema",
        "Mudança Climática Extrema",
        "Chuva reduzida em 25% em relação à climatologia histórica (proxy simplificado de cenário CMIP6 severo).",
    ),
}

PARAMETROS_CENARIO = {
    "atual": {"fator_clima": 1.0, "piso_fator_outorga": 0.5, "restricao_ambiental": False},
    "alta_restricao_outorga": {"fator_clima": 1.0, "piso_fator_outorga": 0.80, "restricao_ambiental": True},
    "mudanca_climatica_extrema": {"fator_clima": 0.75, "piso_fator_outorga": 0.5, "restricao_ambiental": False},
}

HORIZONTE_MESES = {"curto_prazo": 60, "medio_prazo": 180, "longo_prazo": 360}


def rodar_cenario(cenario_id: str, trechos: list[str], horizonte_meses: int) -> pd.DataFrame:
    """Instancia e roda `RioTieteModel` com os parâmetros do cenário informado.

    Retorna uma linha por trecho com o estado simulado ao FIM do horizonte
    (`horizonte_meses` passos mensais a partir de hoje).
    """
    parametros = PARAMETROS_CENARIO[cenario_id]
    modelo = RioTieteModel(trechos, cenario_id=cenario_id, seed=42, **parametros)
    modelo.run_horizonte(horizonte_meses)

    linhas = []
    for trecho_id in trechos:
        passo = modelo.ultimo_passo_por_trecho[trecho_id]
        linhas.append(
            {
                "trecho_id": trecho_id,
                "cenario_id": cenario_id,
                "mes_data": passo.mes_data,
                "vazao_m3s_medio": passo.vazao_simulada_m3s,
                "iqa": passo.iqa_simulado,
                "od_mg_l": passo.od_simulado_mg_l,
                "dbo_mg_l": passo.dbo_simulado_mg_l,
                "multas_acumuladas": modelo.multas_por_trecho[trecho_id],
                "estresse_hidrico": modelo.estresse_hidrico_por_trecho[trecho_id],
            }
        )
    return pd.DataFrame(linhas)


def rodar_cenario_customizado(
    parametros_modelo: dict, trechos: list[str], horizonte_meses: int, seed: int = 42
) -> pd.DataFrame:
    """Roda `RioTieteModel` com parâmetros arbitrários (não só os `CENARIOS` pré-definidos)
    e retorna a trajetória MÊS A MÊS completa (não só o estado final).

    Usada pela página "Cenários Futuros", onde o usuário define os parâmetros
    via sliders em vez de escolher entre os 3 cenários fixos de
    `CENARIOS`/`PARAMETROS_CENARIO` — `rodar_cenario` continua servindo
    exclusivamente `3_Comparativo_Cenarios.py`.
    """
    modelo = RioTieteModel(trechos, seed=seed, **parametros_modelo)
    modelo.run_horizonte(horizonte_meses)

    linhas = [
        {
            "trecho_id": passo.trecho_id,
            "mes_data": passo.mes_data,
            "ano_relativo": i // (12 * len(trechos)) + 1,
            "vazao_m3s_medio": passo.vazao_simulada_m3s,
            "iqa": passo.iqa_simulado,
            "od_mg_l": passo.od_simulado_mg_l,
            "dbo_mg_l": passo.dbo_simulado_mg_l,
        }
        for i, passo in enumerate(modelo.historico)
    ]
    tabela = pd.DataFrame(linhas)
    tabela["multas_acumuladas"] = tabela["trecho_id"].map(modelo.multas_por_trecho)
    return tabela
