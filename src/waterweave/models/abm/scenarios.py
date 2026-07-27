"""Definição dos cenários comparativos exibidos no dashboard.

Cada cenário configura os parâmetros iniciais/estruturais do `RioTieteModel`:
  - "atual": clima e regras de decisão sem alteração.
  - "alta_restricao_outorga": piso de outorga mais alto (menos captação
    permitida) e agricultores sob pressão regulatória ativa.
  - "mudanca_climatica_extrema": chuva reduzida segundo `fator_clima` — ver ATUALIZAÇÃO abaixo.

ATUALIZAÇÃO (2026-07, CMIP6 -> `fator_clima`): o `fator_clima` de `"mudanca_climatica_extrema"`
deixou de ser um proxy fixo de -25% — agora vem de `models.abm.clima_real.fator_clima_calibrado`,
que lê uma calibração real feita a partir de projeções CMIP6 (cenário SSP5-8.5, ver
`ingestion.connectors.era5_cmip6.calibrar_fatores_clima_cenarios`) quando ela existe
(`config.FATOR_CLIMA_CALIBRACAO_FILE`), e cai de volta no mesmo -25% fixo de antes quando não
(checkout novo, calibração nunca rodada) — ver docstring de `models.abm.clima_real` para o
racional completo do porquê a calibração é um passo em lote, não uma chamada ao vivo aqui.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from waterweave.models.abm import clima_real
from waterweave.models.abm.model import RioTieteModel

# Valor fixo pré-CMIP6 — mantido como `fallback` de `clima_real.fator_clima_calibrado` (ver
# ATUALIZAÇÃO na docstring do módulo), não como o valor efetivamente usado quando a calibração
# real está disponível.
_FATOR_CLIMA_EXTREMA_FALLBACK = 0.75


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
        "Chuva reduzida em relação à climatologia histórica, segundo cenário CMIP6 SSP5-8.5 "
        "(calibrado de projeção real quando disponível — ver ATUALIZAÇÃO na docstring do módulo; "
        "proxy fixo de -25% como piso quando não).",
    ),
}

PARAMETROS_CENARIO = {
    "atual": {"fator_clima": 1.0, "piso_fator_outorga": 0.5, "restricao_ambiental": False},
    "alta_restricao_outorga": {"fator_clima": 1.0, "piso_fator_outorga": 0.80, "restricao_ambiental": True},
    "mudanca_climatica_extrema": {
        "fator_clima": clima_real.fator_clima_calibrado(
            "mudanca_climatica_extrema", fallback=_FATOR_CLIMA_EXTREMA_FALLBACK
        ),
        "piso_fator_outorga": 0.5,
        "restricao_ambiental": False,
    },
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
            "turbidez_ntu": passo.turbidez_ntu,
            "solidos_totais_mg_l": passo.solidos_totais_mg_l,
            "temperatura_c": passo.temperatura_c,
            "ph": passo.ph,
            "fosforo_mg_l": passo.fosforo_mg_l,
            "nitrogenio_mg_l": passo.nitrogenio_mg_l,
            "e_coli_nmp_100ml": passo.e_coli_nmp_100ml,
            "metais_toxicos_indice": passo.metais_toxicos_indice,
            "indice_biotico": passo.indice_biotico,
            "indice_escoamento_mm": passo.estado_hidrologico.indice_escoamento_mm,
        }
        for i, passo in enumerate(modelo.historico)
    ]
    tabela = pd.DataFrame(linhas)
    tabela["multas_acumuladas"] = tabela["trecho_id"].map(modelo.multas_por_trecho)
    # Necessária para o serviço ecossistêmico de PROVISÃO HÍDRICA (`models.servicos_ecossistemicos`,
    # item 5 do roadmap de pesquisa) — mesmo valor repetido em todas as linhas do trecho (não
    # muda passo a passo, ver `RioTieteModel.captacao_necessaria_m3s`).
    tabela["captacao_necessaria_m3s"] = tabela["trecho_id"].map(modelo.captacao_necessaria_m3s)
    return tabela
