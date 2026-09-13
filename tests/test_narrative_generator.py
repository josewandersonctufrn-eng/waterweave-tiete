"""Teste de guarda para `reports.narrative_generator` — cobre o achado de 2026-09: o Relatório
Automático (Modelo Completo) reaproveitava, por engano, o texto de metodologia do relatório de
Cenário ("Simulação via modelo de agentes (Mesa) + balanço hídrico + Streeter-Phelps..."),
mesmo operando sobre `load_qualidade_historica()` (medição REAL da CETESB + fallback simulado,
nunca o ABM) — ver docstring do módulo. A tela "Relatório Automático" e o PDF gerado
descreviam incorretamente a própria metodologia."""
from __future__ import annotations

import pandas as pd
import pytest

from waterweave.reports.narrative_generator import gerar_relatorio_trecho_completo
from waterweave.webapp import i18n


@pytest.fixture
def qualidade_sintetica():
    return pd.DataFrame(
        {
            "trecho_id": ["alto_tiete"] * 3,
            "ano": [2013, 2023, 2024],
            "iqa": [50.0, 40.0, 45.0],
            "od_mg_l": [5.0, 4.0, 4.5],
            "dbo_mg_l": [10.0, 12.0, 11.0],
            "uso_solo": ["Metropolitano / Industrial"] * 3,
        }
    )


def test_metodologia_corpo_nao_e_a_do_relatorio_de_cenario_abm(qualidade_sintetica):
    narrativa = gerar_relatorio_trecho_completo(qualidade_sintetica, "alto_tiete", 2024)
    assert narrativa is not None
    assert narrativa.metodologia_corpo != i18n.t("cn.nota")
    assert "Mesa" not in narrativa.metodologia_corpo
    assert "Streeter-Phelps" not in narrativa.metodologia_corpo


def test_metodologia_corpo_descreve_medicao_real_da_cetesb(qualidade_sintetica):
    narrativa = gerar_relatorio_trecho_completo(qualidade_sintetica, "alto_tiete", 2024)
    assert narrativa is not None
    assert "CETESB" in narrativa.metodologia_corpo
    assert "reais" in narrativa.metodologia_corpo


def test_resumo_e_objetivo_nao_alegam_simulacao_hidrobiogeoquimica(qualidade_sintetica):
    """As chaves rel.b.resumo_texto/objetivo_geral_texto não podem mais afirmar que o
    relatório se baseia na simulação do ABM (elas descrevem dado REAL da CETESB)."""
    narrativa = gerar_relatorio_trecho_completo(qualidade_sintetica, "alto_tiete", 2024)
    assert narrativa is not None
    for texto in (narrativa.resumo, narrativa.objetivo_geral):
        assert "hidrobiogeoquímica" not in texto
        assert "modelo baseado em agentes" not in texto
