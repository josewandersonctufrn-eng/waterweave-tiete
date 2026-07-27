"""Testes de guarda para os indicadores de serviços ecossistêmicos (item 5 do roadmap de
pesquisa WaterWeave-Water4All) — ver ACHADO DE PESQUISA em `models.servicos_ecossistemicos`.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from waterweave.models import servicos_ecossistemicos as se
from waterweave.models.biofisico import parametros_estendidos
from waterweave.transform import gold_features


def test_regulacao_qualidade_agua_reescala_iqa_para_fracao():
    assert se.regulacao_qualidade_agua(100.0) == pytest.approx(1.0)
    assert se.regulacao_qualidade_agua(0.0) == pytest.approx(0.0)
    assert se.regulacao_qualidade_agua(50.0) == pytest.approx(0.5)


def test_regulacao_qualidade_agua_propaga_nan():
    assert math.isnan(se.regulacao_qualidade_agua(float("nan")))


def test_provisao_hidrica_capada_em_1_quando_vazao_excede_necessidade():
    assert se.provisao_hidrica(vazao_m3s=20.0, captacao_necessaria_m3s=5.0) == pytest.approx(1.0)


def test_provisao_hidrica_proporcional_quando_vazao_insuficiente():
    assert se.provisao_hidrica(vazao_m3s=2.5, captacao_necessaria_m3s=5.0) == pytest.approx(0.5)


def test_provisao_hidrica_sem_necessidade_conhecida_retorna_1():
    assert se.provisao_hidrica(vazao_m3s=10.0, captacao_necessaria_m3s=0.0) == pytest.approx(1.0)
    assert se.provisao_hidrica(vazao_m3s=10.0, captacao_necessaria_m3s=None) == pytest.approx(1.0)


def test_suporte_biodiversidade_bate_com_indice_biotico_do_biofisico():
    """`suporte_biodiversidade` é `indice_biotico/100` — mesma fórmula, sem duplicação."""
    od, turbidez, metais = 6.0, 20.0, 30.0
    esperado = parametros_estendidos.indice_biotico(od, turbidez, metais) / 100.0
    assert se.suporte_biodiversidade(od, turbidez, metais) == pytest.approx(esperado)


def test_indice_biotico_extraido_reproduz_valores_conhecidos():
    """Regressão: valores calculados à mão para o formato antigo (inline em
    `simular_parametros_estendidos`), antes da extração para função standalone."""
    # OD=8 (normalizado=100), turbidez=0 (normalizada=0 -> 100-0=100), metais=0 -> 100-0=100
    assert parametros_estendidos.indice_biotico(8.0, 0.0, 0.0) == pytest.approx(100.0)
    # OD=0, turbidez=60 (normalizada=100 -> 0), metais=100 -> 0
    assert parametros_estendidos.indice_biotico(0.0, 60.0, 100.0) == pytest.approx(0.0)
    # meio-termo: OD=4 (normalizado=50), turbidez=30 (normalizada=50 -> 50), metais=50 -> 50
    assert parametros_estendidos.indice_biotico(4.0, 30.0, 50.0) == pytest.approx(50.0)


def test_calcular_servicos_do_passo_usa_os_3_campos_certos():
    class PassoFalso:
        iqa_simulado = 80.0
        vazao_simulada_m3s = 10.0
        od_simulado_mg_l = 7.0
        turbidez_ntu = 10.0
        metais_toxicos_indice = 20.0

    resultado = se.calcular_servicos_do_passo(PassoFalso(), captacao_necessaria_m3s=2.0)
    assert resultado.regulacao_qualidade_agua == pytest.approx(0.8)
    assert resultado.provisao_hidrica == pytest.approx(1.0)  # vazão (10) > necessidade (2)
    assert resultado.suporte_biodiversidade == pytest.approx(
        parametros_estendidos.indice_biotico(7.0, 10.0, 20.0) / 100.0
    )


# ---------------------------------------------------------------------------------------------
# `transform.gold_features.build_servicos_ecossistemicos_historico` — regulação + provisão
# sobre o histórico REAL (não depende de `read_table`, recebe `features_anual` já pronto).
# ---------------------------------------------------------------------------------------------


def _features_anual_sintetico() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trecho_id": "alto_tiete", "ano": 2020, "iqa": 80.0, "vazao_m3s_medio": 20.0, "fonte_tipo": "observado"},
            {"trecho_id": "alto_tiete", "ano": 2021, "iqa": 40.0, "vazao_m3s_medio": 2.0, "fonte_tipo": "observado"},
            {"trecho_id": "medio_tiete", "ano": 2020, "iqa": 60.0, "vazao_m3s_medio": None, "fonte_tipo": "simulado"},
        ]
    )


def test_regulacao_e_provisao_calculadas_por_trecho_ano():
    resultado = gold_features.build_servicos_ecossistemicos_historico(_features_anual_sintetico())

    alto = resultado[resultado.trecho_id == "alto_tiete"].sort_values("ano").reset_index(drop=True)
    necessidade_esperada = ((20.0 + 2.0) / 2) * gold_features.FRACAO_VAZAO_CAPTACAO_NECESSARIA
    assert alto.loc[0, "captacao_necessaria_m3s"] == pytest.approx(necessidade_esperada)
    assert alto.loc[0, "regulacao_qualidade_agua"] == pytest.approx(0.8)
    assert alto.loc[1, "regulacao_qualidade_agua"] == pytest.approx(0.4)
    # os dois trechos/anos usam a MESMA `captacao_necessaria_m3s` (é uma média por trecho, não por ano)
    assert alto.loc[0, "captacao_necessaria_m3s"] == pytest.approx(alto.loc[1, "captacao_necessaria_m3s"])


def test_provisao_hidrica_propaga_nan_quando_vazao_ausente():
    resultado = gold_features.build_servicos_ecossistemicos_historico(_features_anual_sintetico())
    medio = resultado[resultado.trecho_id == "medio_tiete"].iloc[0]
    assert math.isnan(medio["provisao_hidrica"])
    assert medio["regulacao_qualidade_agua"] == pytest.approx(0.6)  # IQA não depende de vazão


def test_biodiversidade_nao_entra_na_tabela_historica():
    """Só regulação e provisão têm série real — ver ACHADO DE PESQUISA (limitação de cobertura
    histórica) em `models.servicos_ecossistemicos`."""
    resultado = gold_features.build_servicos_ecossistemicos_historico(_features_anual_sintetico())
    assert "suporte_biodiversidade" not in resultado.columns


def test_entrada_vazia_retorna_vazio_sem_erro():
    vazia = pd.DataFrame(columns=["trecho_id", "ano", "iqa", "vazao_m3s_medio"])
    resultado = gold_features.build_servicos_ecossistemicos_historico(vazia)
    assert resultado.empty
