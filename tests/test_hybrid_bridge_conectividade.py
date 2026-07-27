"""Testes de guarda da conectividade espacial entre trechos — ver ACHADO DE PESQUISA
"conectividade espacial" em `models.hybrid_bridge` e `models.abm.model`. Cobrem
`ordem_hidrologica` e o efeito de `carga_delta_montante_kg_dia` em `executar_passo`; a
orquestração completa (`RioTieteModel.step` propagando entre trechos reais) fica em
`tests/test_abm_conectividade_espacial.py`, que precisa do pacote `mesa`.
"""
from __future__ import annotations

import pandas as pd
import pytest

from waterweave.models import hybrid_bridge


@pytest.fixture
def serie_sintetica_alto_tiete(monkeypatch):
    """Série mensal sintética de 2 anos para `alto_tiete` — suficiente para calibrar
    `_fator_conversao_indice_para_vazao` e `carga_base_trecho_kg_dia` sem depender de dado
    real. Limpa os `lru_cache` dessas funções antes/depois para não vazar estado entre testes."""
    meses = pd.date_range("2000-01-01", periods=24, freq="MS")
    serie = pd.DataFrame(
        {
            "trecho_id": "alto_tiete", "mes_data": meses,
            "chuva_mm_media": 100.0, "vazao_m3s_medio": 20.0, "dbo_mg_l": 5.0,
            "uso_solo": "Metropolitano / Industrial",
            "pct_natural": None, "pct_agropecuaria": None, "pct_urbano_industrial": None, "pct_agua": None,
        }
    )
    monkeypatch.setattr(hybrid_bridge, "read_table", lambda path: serie)
    hybrid_bridge._fator_conversao_indice_para_vazao.cache_clear()
    hybrid_bridge.carga_base_trecho_kg_dia.cache_clear()
    yield meses
    hybrid_bridge._fator_conversao_indice_para_vazao.cache_clear()
    hybrid_bridge.carga_base_trecho_kg_dia.cache_clear()


def test_ordem_hidrologica_vai_de_montante_para_jusante():
    assert hybrid_bridge.ordem_hidrologica(["baixo_tiete", "alto_tiete", "medio_tiete"]) == [
        "alto_tiete", "medio_tiete", "baixo_tiete",
    ]


def test_ordem_hidrologica_com_subconjunto_de_trechos():
    """Se só 2 dos 3 trechos estiverem numa simulação, a ordem relativa entre eles continua
    correta — o cenário mais comum são simulações com todos os 3, mas nada impede um
    subconjunto."""
    assert hybrid_bridge.ordem_hidrologica(["baixo_tiete", "alto_tiete"]) == ["alto_tiete", "baixo_tiete"]


def test_carga_delta_montante_positivo_aumenta_carga_total_e_piora_dbo(serie_sintetica_alto_tiete):
    meses = serie_sintetica_alto_tiete
    estado0 = hybrid_bridge.estado_hidrologico_inicial("alto_tiete")
    params = hybrid_bridge.ParametrosAgentes()

    sem_montante = hybrid_bridge.executar_passo("alto_tiete", meses[0], estado0, params, 100.0, "Metropolitano / Industrial")
    com_montante = hybrid_bridge.executar_passo(
        "alto_tiete", meses[0], estado0, params, 100.0, "Metropolitano / Industrial", carga_delta_montante_kg_dia=1000.0
    )

    assert com_montante.carga_total_kg_dia == pytest.approx(sem_montante.carga_total_kg_dia + 1000.0)
    assert com_montante.dbo_simulado_mg_l > sem_montante.dbo_simulado_mg_l
    assert com_montante.od_simulado_mg_l < sem_montante.od_simulado_mg_l


def test_carga_delta_montante_grande_o_bastante_piora_iqa(serie_sintetica_alto_tiete):
    """Com um desvio pequeno o IQA proxy pode ficar saturado em 100 (ver `iqa_proxy`) — um
    desvio grande o suficiente precisa mover o IQA para baixo de verdade, não só DBO/OD."""
    meses = serie_sintetica_alto_tiete
    estado0 = hybrid_bridge.estado_hidrologico_inicial("alto_tiete")
    params = hybrid_bridge.ParametrosAgentes()

    sem_montante = hybrid_bridge.executar_passo("alto_tiete", meses[0], estado0, params, 100.0, "Metropolitano / Industrial")
    com_muito_montante = hybrid_bridge.executar_passo(
        "alto_tiete", meses[0], estado0, params, 100.0, "Metropolitano / Industrial", carga_delta_montante_kg_dia=1_000_000.0
    )
    assert com_muito_montante.iqa_simulado < sem_montante.iqa_simulado


def test_carga_delta_montante_negativo_reduz_carga_total(serie_sintetica_alto_tiete):
    meses = serie_sintetica_alto_tiete
    estado0 = hybrid_bridge.estado_hidrologico_inicial("alto_tiete")
    params = hybrid_bridge.ParametrosAgentes()

    sem_montante = hybrid_bridge.executar_passo("alto_tiete", meses[0], estado0, params, 100.0, "Metropolitano / Industrial")
    com_reducao_montante = hybrid_bridge.executar_passo(
        "alto_tiete", meses[0], estado0, params, 100.0, "Metropolitano / Industrial", carga_delta_montante_kg_dia=-1000.0
    )
    assert com_reducao_montante.carga_total_kg_dia < sem_montante.carga_total_kg_dia
    assert com_reducao_montante.dbo_simulado_mg_l < sem_montante.dbo_simulado_mg_l


def test_carga_total_nunca_fica_negativa_mesmo_com_desvio_absurdo(serie_sintetica_alto_tiete):
    meses = serie_sintetica_alto_tiete
    estado0 = hybrid_bridge.estado_hidrologico_inicial("alto_tiete")
    params = hybrid_bridge.ParametrosAgentes()
    passo = hybrid_bridge.executar_passo(
        "alto_tiete", meses[0], estado0, params, 100.0, "Metropolitano / Industrial", carga_delta_montante_kg_dia=-1e9
    )
    assert passo.carga_total_kg_dia == 0.0


def test_sem_o_parametro_comportamento_e_identico_ao_anterior(serie_sintetica_alto_tiete):
    """Regressão de compatibilidade: quem chama `executar_passo` sem `carga_delta_montante_kg_dia`
    (código antigo, ou o trecho mais a montante que não recebe nada) tem que ter exatamente o
    mesmo resultado de antes desta correção."""
    meses = serie_sintetica_alto_tiete
    estado0 = hybrid_bridge.estado_hidrologico_inicial("alto_tiete")
    params = hybrid_bridge.ParametrosAgentes()
    com_default_explicito = hybrid_bridge.executar_passo(
        "alto_tiete", meses[0], estado0, params, 100.0, "Metropolitano / Industrial", carga_delta_montante_kg_dia=0.0
    )
    sem_passar_o_parametro = hybrid_bridge.executar_passo("alto_tiete", meses[0], estado0, params, 100.0, "Metropolitano / Industrial")
    assert com_default_explicito.carga_total_kg_dia == sem_passar_o_parametro.carga_total_kg_dia
