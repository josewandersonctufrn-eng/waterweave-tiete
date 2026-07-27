"""Testes de guarda de `transform.gold_features.build_feature_store_ml_anual` — protegem a
correção do vazamento de granularidade (ACHADO DE AUDITORIA DE ML item 1, ver docstring do
módulo): uma linha por (trecho, ano), sem repetir o valor anual em 12 meses. Também cobrem o
fallback real/simulado (item 2) e a imputação limitada de vazão/chuva (item 6).
"""
from __future__ import annotations

import pandas as pd
import pytest

from waterweave.transform import gold_features


def _tabela_qualidade(trecho_id: str, anos: list[int], fonte_tipo: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trecho_id": trecho_id,
            "ano": anos,
            "iqa": [60.0 + i for i in range(len(anos))],
            "od_mg_l": [6.0 + i * 0.1 for i in range(len(anos))],
            "fonte_tipo": fonte_tipo,
        }
    )


def _tabela_mensal(trecho_id: str, anos: list[int], coluna: str, base: float) -> pd.DataFrame:
    linhas = [
        {"trecho_id": trecho_id, "ano": ano, "mes": mes, "codigo_posto": "P1", coluna: base}
        for ano in anos
        for mes in range(1, 13)
    ]
    return pd.DataFrame(linhas)


@pytest.fixture
def gold_sintetico(monkeypatch):
    """Substitui `read_table` por dados sintéticos para `alto_tiete`: 8 anos reais
    (2013-2020) + 2 anos só com fallback simulado (2011-2012, para checar o fallback do item
    2); vazão com um buraco de 1 ano (2016, dentro do limite de preenchimento) e outro de 2
    anos (2018-2019, NO limite `_LIMITE_PREENCHIMENTO_ANOS`)."""
    real = _tabela_qualidade("alto_tiete", list(range(2013, 2021)), "observado")
    simulado = _tabela_qualidade("alto_tiete", [2011, 2012], "simulado")

    anos_vazao = [a for a in range(2011, 2021) if a not in (2016, 2018, 2019)]
    vazao = _tabela_mensal("alto_tiete", anos_vazao, "vazao_m3s", 10.0)
    chuva = _tabela_mensal("alto_tiete", list(range(2011, 2021)), "altura_mm", 100.0)

    # Vazia de propósito: estes testes cobrem vazamento de granularidade/fallback/imputação de
    # vazão, não uso do solo — `build_feature_store_ml_anual` trata `uso_solo` vazio preenchendo
    # as colunas `pct_*` com NA (ver `else` no bloco de merge), sem afetar o resto da tabela.
    uso_solo = pd.DataFrame()

    tabelas = {
        "qualidade_cetesb": real, "qualidade": simulado,
        "vazao_mensal": vazao, "chuva_mensal": chuva, "uso_solo": uso_solo,
    }
    monkeypatch.setattr(gold_features, "read_table", lambda path: tabelas[path.name])


def test_uma_linha_por_trecho_ano_sem_repeticao_mensal(gold_sintetico):
    """Regressão do item 1: a versão antiga (`build_feature_store_ml`, mensal) repetia o valor
    anual 12x; a versão anual não pode ter linhas duplicadas por (trecho, ano)."""
    tabela = gold_features.build_feature_store_ml_anual()
    assert len(tabela) == tabela[["trecho_id", "ano"]].drop_duplicates().shape[0]
    assert len(tabela) == 10  # 8 anos reais (2013-2020) + 2 simulados de fallback (2011-2012)


def test_fallback_simulado_preenche_so_os_anos_sem_medicao_real(gold_sintetico):
    """`qualidade_real_com_fallback_simulado` só deve usar o simulado onde não existe medição
    real — nunca sobrescrever um ano que já tem dado da CETESB."""
    tabela = gold_features.build_feature_store_ml_anual().set_index("ano")
    assert tabela.loc[2011, "fonte_tipo"] == "simulado"
    assert tabela.loc[2012, "fonte_tipo"] == "simulado"
    assert tabela.loc[2013, "fonte_tipo"] == "observado"
    assert tabela.loc[2020, "fonte_tipo"] == "observado"


def test_imputacao_de_vazao_respeita_limite_de_anos(gold_sintetico):
    """ACHADO item 6: buraco de 1 ano (2016) e buraco de 2 anos (2018-2019, no limite) devem
    ser preenchidos por ffill e marcados com o flag `_imputado` — para não confundir dado real
    com dado inventado a jusante (ex.: análise hidrológica, dashboard)."""
    tabela = gold_features.build_feature_store_ml_anual().set_index("ano")
    for ano in (2016, 2018, 2019):
        assert bool(tabela.loc[ano, "vazao_m3s_medio_imputado"]), f"{ano} deveria estar imputado"
        assert not pd.isna(tabela.loc[ano, "vazao_m3s_medio"]), f"{ano} deveria ter valor preenchido"
    for ano in (2013, 2014, 2015, 2017, 2020):
        assert not bool(tabela.loc[ano, "vazao_m3s_medio_imputado"]), f"{ano} não deveria estar imputado"


def test_lags_de_iqa_nao_sao_imputados_como_vazao_e_chuva_sao(gold_sintetico):
    """Ressalva do item 6: só vazão/chuva (preditoras exógenas) são preenchidas por ffill — um
    buraco real no próprio alvo (iqa/od_mg_l) não pode ser inventado. O primeiro ano da série
    (2011) não tem histórico anterior para `iqa_lag1a/2a/3a`: se alguém "corrigisse" isso com
    ffill (mesmo erro que a imputação de vazão faz de propósito), este teste falha — é
    exatamente essa distinção que a docstring do módulo documenta como deliberada."""
    tabela = gold_features.build_feature_store_ml_anual().set_index("ano")
    assert pd.isna(tabela.loc[2011, "iqa_lag1a"])
    assert pd.isna(tabela.loc[2011, "iqa_lag3a"])
    assert pd.isna(tabela.loc[2011, "od_mg_l_lag1a"])
    # em contraste: vazão do mesmo ano (2011) TEM valor (não é o primeiro buraco testado aqui,
    # só confirma que a ausência de lag em iqa não é um efeito colateral de dado geral faltando)
    assert not pd.isna(tabela.loc[2011, "vazao_m3s_medio"])
