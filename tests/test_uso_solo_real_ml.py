"""Testes de guarda da integração de uso do solo REAL (MapBiomas) ao ML — ver ACHADO DE
PESQUISA "uso do solo REAL" na docstring de `transform.gold_features` e `models.ml.features`.
Ao contrário do sensoriamento remoto (`test_gold_indicadores_sensoriamento.py`), o uso do solo
real TEM sobreposição temporal com a qualidade da água (1985-2023 vs. 1978-2024), então esta
fonte de fato entra em `feature_store_ml_anual` como preditora — estes testes cobrem o merge e
a imputação bidirecional nas bordas da série.
"""
from __future__ import annotations

import pandas as pd
import pytest

from waterweave.transform import gold_features
from waterweave.models.ml.features import (
    PREDITORAS_DRIVERS_ANUAL,
    PREDITORAS_NUMERICAS_ANUAL,
    montar_matriz_features_anual_por_trecho,
    montar_matriz_features_drivers_por_trecho,
)


def _tabela_mensal(trecho_id: str, anos: list[int], coluna: str, base: float) -> pd.DataFrame:
    linhas = [
        {"trecho_id": trecho_id, "ano": ano, "mes": mes, "codigo_posto": "P1", coluna: base}
        for ano in anos
        for mes in range(1, 13)
    ]
    return pd.DataFrame(linhas)


@pytest.fixture
def gold_sintetico_com_uso_solo(monkeypatch):
    """Qualidade real 1978-2024 (47 anos) para `alto_tiete`; uso do solo real só 1985-2023
    (cobertura MapBiomas) — a lacuna de 7 anos (1978-1984) e 1 ano (2024) é exatamente o que a
    imputação bidirecional (`_LIMITE_PREENCHIMENTO_USO_SOLO_ANOS=10`) precisa cobrir."""
    anos_qualidade = list(range(1978, 2025))
    qualidade_real = pd.DataFrame(
        {
            "trecho_id": "alto_tiete", "ano": anos_qualidade,
            "iqa": [60.0] * len(anos_qualidade), "od_mg_l": [6.0] * len(anos_qualidade),
            "fonte_tipo": "observado",
        }
    )
    simulado_vazio = pd.DataFrame(columns=["trecho_id", "ano", "iqa", "od_mg_l", "fonte_tipo"])
    vazao = _tabela_mensal("alto_tiete", anos_qualidade, "vazao_m3s", 10.0)
    chuva = _tabela_mensal("alto_tiete", anos_qualidade, "altura_mm", 100.0)

    anos_uso_solo = list(range(1985, 2024))
    uso_solo = pd.DataFrame(
        {
            "trecho_id": "alto_tiete", "ano": anos_uso_solo,
            "pct_natural": 50.0, "pct_agropecuaria": 30.0, "pct_urbano_industrial": 15.0, "pct_agua": 5.0,
            "fonte_tipo": "observado",
        }
    )

    tabelas = {
        "qualidade_cetesb": qualidade_real, "qualidade": simulado_vazio,
        "vazao_mensal": vazao, "chuva_mensal": chuva, "uso_solo": uso_solo,
    }
    monkeypatch.setattr(gold_features, "read_table", lambda path: tabelas[path.name])


def test_uso_solo_real_entra_como_preditora_de_producao():
    for coluna in ("pct_natural", "pct_agropecuaria", "pct_urbano_industrial", "pct_agua"):
        assert coluna in PREDITORAS_NUMERICAS_ANUAL


def test_uso_solo_real_entra_como_preditora_drivers():
    """Uso do solo é um driver causal-adjacente de verdade (item 8) — não é lag do alvo, e é
    uma alavanca de política real (diferente de vazão/chuva, que ninguém decide)."""
    for coluna in ("pct_natural", "pct_agropecuaria", "pct_urbano_industrial", "pct_agua"):
        assert coluna in PREDITORAS_DRIVERS_ANUAL


def test_lacuna_antes_de_1985_e_preenchida_por_bfill(gold_sintetico_com_uso_solo):
    tabela = gold_features.build_feature_store_ml_anual().set_index("ano")
    for ano in range(1978, 1985):
        assert not pd.isna(tabela.loc[ano, "pct_natural"]), f"{ano} deveria estar preenchido (bfill)"
        assert bool(tabela.loc[ano, "pct_natural_imputado"])
        assert tabela.loc[ano, "pct_natural"] == 50.0  # valor do ano mais próximo com dado real (1985)


def test_anos_com_cobertura_mapbiomas_nao_sao_marcados_como_imputados(gold_sintetico_com_uso_solo):
    tabela = gold_features.build_feature_store_ml_anual().set_index("ano")
    assert not bool(tabela.loc[1985, "pct_natural_imputado"])
    assert not bool(tabela.loc[2023, "pct_natural_imputado"])


def test_lacuna_depois_de_2023_e_preenchida_por_ffill(gold_sintetico_com_uso_solo):
    tabela = gold_features.build_feature_store_ml_anual().set_index("ano")
    assert not pd.isna(tabela.loc[2024, "pct_natural"])
    assert bool(tabela.loc[2024, "pct_natural_imputado"])


def test_matriz_de_producao_e_drivers_tem_uso_do_solo_apos_pipeline_completo(gold_sintetico_com_uso_solo):
    gold = gold_features.build_feature_store_ml_anual()
    X, y = montar_matriz_features_anual_por_trecho(gold, "iqa", "alto_tiete")
    assert {"pct_natural", "pct_agropecuaria", "pct_urbano_industrial", "pct_agua"} <= set(X.columns)
    assert len(X) == len(y) > 0

    X_drivers, y_drivers = montar_matriz_features_drivers_por_trecho(gold, "iqa", "alto_tiete")
    assert {"pct_natural", "pct_agropecuaria", "pct_urbano_industrial", "pct_agua"} <= set(X_drivers.columns)
    assert not any("lag" in c or "media_movel" in c for c in X_drivers.columns)


def test_serie_temporal_trecho_mes_tambem_recebe_uso_do_solo_real(monkeypatch):
    """`build_serie_temporal_trecho_mes` (consumida pelo ABM/dashboard, não só pelo ML) também
    precisa trazer os percentuais reais — é o que `models.abm.model._uso_solo_recente` passou a
    ler (ver `tests/test_abm_uso_solo_real.py`)."""
    vazao = _tabela_mensal("alto_tiete", [2020], "vazao_m3s", 10.0)
    chuva = _tabela_mensal("alto_tiete", [2020], "altura_mm", 100.0)
    qualidade_real = pd.DataFrame({"trecho_id": ["alto_tiete"], "ano": [2020], "iqa": [60.0], "od_mg_l": [6.0], "fonte_tipo": ["observado"]})
    simulado_vazio = pd.DataFrame(columns=["trecho_id", "ano", "iqa", "od_mg_l", "fonte_tipo"])
    uso_solo = pd.DataFrame({"trecho_id": ["alto_tiete"], "ano": [2020], "pct_natural": [55.0], "pct_agropecuaria": [25.0], "pct_urbano_industrial": [15.0], "pct_agua": [5.0]})
    tabelas = {"qualidade_cetesb": qualidade_real, "qualidade": simulado_vazio, "vazao_mensal": vazao, "chuva_mensal": chuva, "uso_solo": uso_solo}
    monkeypatch.setattr(gold_features, "read_table", lambda path: tabelas[path.name])

    serie = gold_features.build_serie_temporal_trecho_mes()
    assert (serie["pct_natural"] == 55.0).all()
    assert (serie["pct_urbano_industrial"] == 15.0).all()


def test_uso_solo_ausente_nao_quebra_o_pipeline(monkeypatch):
    """Se `silver.uso_solo` ainda não foi materializada (ex.: MapBiomas nunca rodou neste
    ambiente), o pipeline não pode quebrar — as colunas viram NA, tratadas como qualquer outra
    preditora faltante pelo dropna de `montar_matriz_features_anual_por_trecho`."""
    anos = [2020, 2021]
    qualidade_real = pd.DataFrame({"trecho_id": "alto_tiete", "ano": anos, "iqa": [60.0, 61.0], "od_mg_l": [6.0, 6.1], "fonte_tipo": "observado"})
    simulado_vazio = pd.DataFrame(columns=["trecho_id", "ano", "iqa", "od_mg_l", "fonte_tipo"])
    vazao = _tabela_mensal("alto_tiete", anos, "vazao_m3s", 10.0)
    chuva = _tabela_mensal("alto_tiete", anos, "altura_mm", 100.0)
    tabelas = {"qualidade_cetesb": qualidade_real, "qualidade": simulado_vazio, "vazao_mensal": vazao, "chuva_mensal": chuva, "uso_solo": pd.DataFrame()}
    monkeypatch.setattr(gold_features, "read_table", lambda path: tabelas[path.name])

    tabela = gold_features.build_feature_store_ml_anual()
    assert tabela["pct_natural"].isna().all()
