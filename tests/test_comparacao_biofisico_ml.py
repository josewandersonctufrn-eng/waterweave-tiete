"""Testes de guarda de `models.ml.comparacao_biofisico_ml.comparar_ml_vs_biofisico` — item 6 do
roadmap de pesquisa WaterWeave-Water4All ("acoplar" ML e biofísico). Mocka as duas fontes
(`prever_iqa`, `rodar_cenario_customizado`) inteiras — não depende de `sklearn`/`mesa`/`joblib`
nem de modelos treinados em disco, só da lógica de junção/comparação deste módulo. Mesma técnica
de mockar pelo NOME LIGADO NESTE MÓDULO (não no módulo original) já documentada em
`tests/test_abm_conectividade_espacial.py` (ver ERRO CONHECIDO ali: `from x import y` cria um
binding próprio, `monkeypatch.setattr(modulo_original, "y", ...)` não teria efeito aqui).
"""
from __future__ import annotations

import pandas as pd
import pytest

from waterweave.models.ml import comparacao_biofisico_ml as cbm


def _previsao_ml_falsa(trecho_id: str, horizonte_anos: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trecho_id": trecho_id, "ano": 2025 + i, "iqa_previsto": 70.0 - 5 * i, "od_previsto": 6.0}
            for i in range(horizonte_anos)
        ]
    )


def _historico_biofisico_falso(parametros: dict, trechos: list[str], horizonte_meses: int) -> pd.DataFrame:
    trecho_id = trechos[0]
    linhas = []
    for mes_idx in range(horizonte_meses):
        ano_relativo = mes_idx // 12 + 1
        linhas.append(
            {
                "trecho_id": trecho_id,
                "mes_data": pd.Timestamp("2026-01-01") + pd.DateOffset(months=mes_idx),
                "ano_relativo": ano_relativo,
                # IQA biofísico deliberadamente BEM diferente do ML no ano 2 (ano_relativo=2),
                # para exercitar a flag `divergem`.
                "iqa": {1: 68.0, 2: 20.0, 3: 55.0}[ano_relativo],
            }
        )
    return pd.DataFrame(linhas)


@pytest.fixture
def fontes_mockadas(monkeypatch):
    monkeypatch.setattr(cbm, "prever_iqa", _previsao_ml_falsa)
    monkeypatch.setattr(cbm, "rodar_cenario_customizado", _historico_biofisico_falso)


def test_compara_por_passo_nao_por_ano_civil(fontes_mockadas):
    resultado = cbm.comparar_ml_vs_biofisico("alto_tiete", horizonte_anos=3)

    assert list(resultado["passo"]) == [1, 2, 3]
    assert list(resultado["ano_civil_ml"]) == [2025, 2026, 2027]
    # ano civil do biofísico é ancorado em "hoje" (mockado aqui a partir de 2026-01), não no
    # último ano real de qualidade da água (2025 no ML falso) — os dois NÃO coincidem em ano
    # civil no mesmo `passo`, exatamente a ressalva documentada no módulo.
    assert list(resultado["ano_civil_biofisico"]) == [2026, 2027, 2028]
    assert resultado["ano_civil_ml"].tolist() != resultado["ano_civil_biofisico"].tolist()


def test_diferenca_absoluta_calculada_corretamente(fontes_mockadas):
    resultado = cbm.comparar_ml_vs_biofisico("alto_tiete", horizonte_anos=3).set_index("passo")
    assert resultado.loc[1, "iqa_ml"] == pytest.approx(70.0)
    assert resultado.loc[1, "iqa_biofisico"] == pytest.approx(68.0)
    assert resultado.loc[1, "diferenca_abs_iqa"] == pytest.approx(2.0)
    assert resultado.loc[2, "iqa_ml"] == pytest.approx(65.0)
    assert resultado.loc[2, "iqa_biofisico"] == pytest.approx(20.0)
    assert resultado.loc[2, "diferenca_abs_iqa"] == pytest.approx(45.0)


def test_flag_divergem_usa_o_limiar_documentado(fontes_mockadas):
    resultado = cbm.comparar_ml_vs_biofisico("alto_tiete", horizonte_anos=3).set_index("passo")
    assert resultado.loc[1, "diferenca_abs_iqa"] < cbm.LIMIAR_DIVERGENCIA_IQA
    assert not resultado.loc[1, "divergem"]
    assert resultado.loc[2, "diferenca_abs_iqa"] > cbm.LIMIAR_DIVERGENCIA_IQA
    assert resultado.loc[2, "divergem"]


def test_cenario_biofisico_customizado_e_registrado_na_saida(fontes_mockadas):
    resultado = cbm.comparar_ml_vs_biofisico("alto_tiete", horizonte_anos=2, cenario_biofisico="alta_restricao_outorga")
    assert (resultado["cenario_biofisico"] == "alta_restricao_outorga").all()
