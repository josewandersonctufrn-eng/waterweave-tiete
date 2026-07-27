"""Testes de guarda da conectividade espacial no ABM (`RioTieteModel.step` propagando carga
poluidora entre trechos, em ordem hidrológica) — ver ACHADO DE PESQUISA "conectividade
espacial" em `models.abm.model`/`models.hybrid_bridge`. Precisa do pacote `mesa`; a parte de
`executar_passo`/`ordem_hidrologica` que NÃO depende de `mesa` está em
`tests/test_hybrid_bridge_conectividade.py`.

Metodologia: comparar um modelo com propagação normal contra um modelo IDÊNTICO (mesma seed,
mesmo dado sintético) rodado com `FRACAO_CARGA_PROPAGADA_MONTANTE` zerada, em vez de tentar
recalcular manualmente o valor esperado — cada trecho também tem seu próprio crescimento
orgânico de carga industrial (`IndustriaAgent`) no mesmo mês, então a carga total de um trecho
a jusante já não é só a carga-base mais o delta propagado; comparar os dois modelos isola
exatamente o efeito da propagação, sem precisar reproduzir a lógica dos agentes à mão.
"""
from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("mesa")

from waterweave.models import hybrid_bridge
from waterweave.models.abm import model as abm_model
from waterweave.models.abm.model import RioTieteModel


@pytest.fixture
def serie_sintetica_3_trechos(monkeypatch):
    """Mesmos parâmetros históricos (chuva/vazão/DBO) para os 3 trechos — deliberado: isola o
    efeito da propagação entre trechos de qualquer assimetria de calibração histórica."""
    meses = pd.date_range("2000-01-01", periods=24, freq="MS")
    linhas = [
        {
            "trecho_id": trecho, "mes_data": m, "mes": m.month, "ano": m.year,
            "chuva_mm_media": 100.0, "vazao_m3s_medio": 20.0, "dbo_mg_l": 5.0,
            "uso_solo": "Metropolitano / Industrial",
            "pct_natural": None, "pct_agropecuaria": None, "pct_urbano_industrial": None, "pct_agua": None,
        }
        for trecho in ("alto_tiete", "medio_tiete", "baixo_tiete")
        for m in meses
    ]
    serie = pd.DataFrame(linhas)
    monkeypatch.setattr(abm_model, "read_table", lambda path: serie)
    monkeypatch.setattr(hybrid_bridge, "read_table", lambda path: serie)
    yield


def _novo_modelo() -> RioTieteModel:
    hybrid_bridge._fator_conversao_indice_para_vazao.cache_clear()
    hybrid_bridge.carga_base_trecho_kg_dia.cache_clear()
    # trechos passados FORA de ordem hidrológica de propósito — testa que o modelo reordena
    return RioTieteModel(trechos=["baixo_tiete", "alto_tiete", "medio_tiete"], seed=42)


def test_ordem_hidrologica_e_trecho_jusante_calculados_no_init(serie_sintetica_3_trechos):
    modelo = _novo_modelo()
    assert modelo._ordem_hidrologica == ["alto_tiete", "medio_tiete", "baixo_tiete"]
    assert modelo._trecho_jusante == {"alto_tiete": "medio_tiete", "medio_tiete": "baixo_tiete", "baixo_tiete": None}


def test_alto_tiete_nao_e_afetado_pela_propagacao(serie_sintetica_3_trechos, monkeypatch):
    """`alto_tiete` é o trecho mais a montante — não recebe carga de ninguém, então seu
    resultado tem que ser IDÊNTICO com ou sem a conectividade ligada."""
    modelo_com_propagacao = _novo_modelo()
    modelo_com_propagacao.step()

    monkeypatch.setattr(hybrid_bridge, "FRACAO_CARGA_PROPAGADA_MONTANTE", 0.0)
    modelo_sem_propagacao = _novo_modelo()
    modelo_sem_propagacao.step()

    passo_com = next(p for p in modelo_com_propagacao.historico if p.trecho_id == "alto_tiete")
    passo_sem = next(p for p in modelo_sem_propagacao.historico if p.trecho_id == "alto_tiete")
    assert passo_com.carga_total_kg_dia == passo_sem.carga_total_kg_dia


def test_medio_tiete_recebe_exatamente_a_fracao_do_desvio_de_alto(serie_sintetica_3_trechos, monkeypatch):
    modelo_com_propagacao = _novo_modelo()
    modelo_com_propagacao.step()
    passos_com = {p.trecho_id: p for p in modelo_com_propagacao.historico}

    fracao = hybrid_bridge.FRACAO_CARGA_PROPAGADA_MONTANTE
    monkeypatch.setattr(hybrid_bridge, "FRACAO_CARGA_PROPAGADA_MONTANTE", 0.0)
    modelo_sem_propagacao = _novo_modelo()
    modelo_sem_propagacao.step()
    passos_sem = {p.trecho_id: p for p in modelo_sem_propagacao.historico}

    diferenca_medio = passos_com["medio_tiete"].carga_total_kg_dia - passos_sem["medio_tiete"].carga_total_kg_dia
    desvio_alto = passos_com["alto_tiete"].carga_total_kg_dia - hybrid_bridge.carga_base_trecho_kg_dia("alto_tiete")
    assert diferenca_medio == pytest.approx(fracao * desvio_alto)


def test_baixo_tiete_tambem_e_afetado_em_cadeia(serie_sintetica_3_trechos, monkeypatch):
    """O efeito precisa se propagar por DOIS elos (alto -> medio -> baixo), não só um."""
    modelo_com_propagacao = _novo_modelo()
    modelo_com_propagacao.step()
    passos_com = {p.trecho_id: p for p in modelo_com_propagacao.historico}

    monkeypatch.setattr(hybrid_bridge, "FRACAO_CARGA_PROPAGADA_MONTANTE", 0.0)
    modelo_sem_propagacao = _novo_modelo()
    modelo_sem_propagacao.step()
    passos_sem = {p.trecho_id: p for p in modelo_sem_propagacao.historico}

    assert passos_com["baixo_tiete"].carga_total_kg_dia != passos_sem["baixo_tiete"].carga_total_kg_dia


def test_roda_varios_passos_sem_erro(serie_sintetica_3_trechos):
    modelo = _novo_modelo()
    modelo.run_horizonte(6)
    assert len(modelo.historico) == 6 * 3
