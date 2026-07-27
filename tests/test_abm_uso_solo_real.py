"""Testes de guarda da ligação do ABM ao uso do solo REAL (MapBiomas) — ver ACHADO DE PESQUISA
"uso do solo REAL no ABM" em `models.abm.model` e `hybrid_bridge.uso_solo_da_linha`. Antes
desta correção, `models.abm.model._uso_solo_recente` só enxergava a classe simulada de texto
livre, mesmo quando os percentuais reais já estavam disponíveis em
`gold.serie_temporal_trecho_mes` para o mesmo trecho/ano.
"""
from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("mesa")

from waterweave.models import hybrid_bridge
from waterweave.models.abm import model as abm_model


def test_uso_solo_da_linha_prioriza_percentuais_reais_sobre_classe_simulada():
    linha = pd.Series(
        {
            "uso_solo": "Metropolitano / Industrial",
            "pct_natural": 50.0, "pct_agropecuaria": 30.0, "pct_urbano_industrial": 15.0, "pct_agua": 5.0,
        }
    )
    resultado = hybrid_bridge.uso_solo_da_linha(linha)
    assert isinstance(resultado, dict)
    assert resultado["pct_natural"] == 50.0


def test_uso_solo_da_linha_cai_para_classe_simulada_quando_real_ausente():
    """Anos fora da cobertura MapBiomas (antes de 1985/depois de 2023) não têm percentual
    real — a função tem que continuar funcionando com a classe simulada, não retornar None."""
    linha = pd.Series(
        {"uso_solo": "Metropolitano / Industrial", "pct_natural": None, "pct_agropecuaria": None, "pct_urbano_industrial": None, "pct_agua": None}
    )
    assert hybrid_bridge.uso_solo_da_linha(linha) == "Metropolitano / Industrial"


def test_uso_solo_da_linha_retorna_none_sem_nenhuma_das_duas_fontes():
    linha = pd.Series({"uso_solo": None, "pct_natural": None, "pct_agropecuaria": None, "pct_urbano_industrial": None, "pct_agua": None})
    assert hybrid_bridge.uso_solo_da_linha(linha) is None


def test_abm_uso_solo_recente_prioriza_a_linha_mais_recente_com_dado_real(monkeypatch):
    """Regressão do bug fechado nesta correção: uma linha ANTIGA só com classe simulada e uma
    linha MAIS RECENTE só com percentual real — `_uso_solo_recente` tem que pegar a mais
    recente (2021, real), não a mais antiga só porque era a única com a coluna `uso_solo`
    simulada preenchida (comportamento antigo, incorreto)."""
    serie = pd.DataFrame(
        [
            {
                "trecho_id": "alto_tiete", "mes_data": pd.Timestamp("2020-01-01"),
                "uso_solo": "Metropolitano / Industrial",
                "pct_natural": None, "pct_agropecuaria": None, "pct_urbano_industrial": None, "pct_agua": None,
            },
            {
                "trecho_id": "alto_tiete", "mes_data": pd.Timestamp("2021-01-01"),
                "uso_solo": None,
                "pct_natural": 60.0, "pct_agropecuaria": 25.0, "pct_urbano_industrial": 10.0, "pct_agua": 5.0,
            },
        ]
    )
    monkeypatch.setattr(abm_model, "_serie_trecho", lambda trecho_id: serie)
    resultado = abm_model._uso_solo_recente("alto_tiete")
    assert isinstance(resultado, dict)
    assert resultado["pct_natural"] == 60.0


def test_abm_uso_solo_recente_none_quando_serie_vazia(monkeypatch):
    monkeypatch.setattr(abm_model, "_serie_trecho", lambda trecho_id: pd.DataFrame(columns=["mes_data", "uso_solo", *hybrid_bridge.COLUNAS_USO_SOLO]))
    assert abm_model._uso_solo_recente("alto_tiete") is None
