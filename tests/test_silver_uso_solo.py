"""Testes de `transform.silver_uso_solo` — agregação de área por classe MapBiomas
(`bronze.uso_solo`) em percentual por macro-categoria, uma linha por (trecho, ano)."""
from __future__ import annotations

import pandas as pd
import pytest

from waterweave.transform import silver_uso_solo


def _bronze_uso_solo() -> pd.DataFrame:
    """Um trecho, dois anos: 2020 com 3 classes (natural/agropecuaria/urbano_industrial),
    2021 só com 2 classes (sem urbano_industrial) — para checar o fill_value=0 na pivot."""
    return pd.DataFrame(
        {
            "trecho_id": ["alto_tiete"] * 5,
            "ano": [2020, 2020, 2020, 2021, 2021],
            "classe_mapbiomas": [3, 15, 24, 3, 15],
            "macro_categoria": ["natural", "agropecuaria", "urbano_industrial", "natural", "agropecuaria"],
            "area_m2": [100.0, 300.0, 600.0, 400.0, 600.0],
        }
    )


@pytest.fixture
def bronze_sintetico(monkeypatch):
    monkeypatch.setattr(silver_uso_solo, "read_table", lambda path: _bronze_uso_solo())
    monkeypatch.setattr(silver_uso_solo, "write_table", lambda *a, **k: None)


def test_uma_linha_por_trecho_ano(bronze_sintetico):
    tabela = silver_uso_solo.build_silver_uso_solo()
    assert len(tabela) == 2
    assert set(tabela["ano"]) == {2020, 2021}


def test_percentuais_somam_cem_por_ano(bronze_sintetico):
    tabela = silver_uso_solo.build_silver_uso_solo().set_index("ano")
    colunas_pct = [c for c in tabela.columns if c.startswith("pct_")]
    for ano in (2020, 2021):
        assert tabela.loc[ano, colunas_pct].sum() == pytest.approx(100.0)


def test_classe_ausente_no_ano_vira_zero_nao_erro(bronze_sintetico):
    """2021 não tem nenhum pixel de `urbano_industrial` — a pivot precisa preencher 0,0, não
    NaN nem derrubar a coluna inteira (ver `fill_value=0.0` em `build_silver_uso_solo`)."""
    tabela = silver_uso_solo.build_silver_uso_solo().set_index("ano")
    assert tabela.loc[2021, "pct_urbano_industrial"] == 0.0
    assert tabela.loc[2020, "pct_urbano_industrial"] == pytest.approx(60.0)


def test_todas_macro_categorias_conhecidas_viram_colunas(bronze_sintetico):
    tabela = silver_uso_solo.build_silver_uso_solo()
    for categoria in silver_uso_solo.MACRO_CATEGORIAS:
        assert f"pct_{categoria}" in tabela.columns


def test_marca_fonte_tipo_observado(bronze_sintetico):
    tabela = silver_uso_solo.build_silver_uso_solo()
    assert (tabela["fonte_tipo"] == "observado").all()
