"""Testes de guarda de `transform.gold_features.build_indicadores_sensoriamento_anual` — a
primeira metade da integração de sensoriamento remoto pedida pela pesquisa de pós-doutorado
(ver ACHADO DE PESQUISA na docstring de `gold_features`). Cobrem o pivot (longo -> uma linha
por trecho/ano), a média quando há mais de uma leitura no mesmo ano, o fallback de nome de
coluna para parâmetros sem mapeamento conhecido, e o caso de tabela fonte vazia.
"""
from __future__ import annotations

import pandas as pd
import pytest

from waterweave.transform import gold_features


def _silver_sensoriamento_sintetico() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("alto_tiete", "2026-05-12", "NDVI (Mata Ciliar)", 0.78, "simulado"),
            ("alto_tiete", "2026-05-12", "Turbidez", 4.2, "simulado"),
            ("alto_tiete", "2026-06-01", "NDVI (Mata Ciliar)", 0.80, "simulado"),  # 2ª leitura no mesmo ano
            ("medio_tiete", "2026-05-20", "Clorofila-a", 45.2, "simulado"),
            ("medio_tiete", "2026-05-25", "Nível da Água Altimetria", 442.15, "simulado"),
            ("baixo_tiete", "2026-06-10", "Temperatura da Superfície", 24.1, "simulado"),
            ("baixo_tiete", "2026-06-10", "Parâmetro Desconhecido XYZ", 99.0, "simulado"),
        ],
        columns=["trecho_id", "data_coleta", "parametro", "valor", "fonte_tipo"],
    )


@pytest.fixture
def sensoriamento_sintetico(monkeypatch):
    """Só a planilha ilustrativa: mockar `sensoriamento_historico` vazia mantém
    `sensoriamento_real_com_fallback_ilustrativo` no caminho "sem dado real" (early-return),
    então `build_indicadores_sensoriamento_anual` continua vendo exatamente esta tabela — ver
    `test_sensoriamento_real_fallback.py` para os testes do merge real+ilustrativo em si."""
    tabela = _silver_sensoriamento_sintetico()
    monkeypatch.setattr(gold_features, "read_table", lambda path: tabela if path.name == "sensoriamento" else pd.DataFrame())


def test_uma_linha_por_trecho_ano(sensoriamento_sintetico):
    tabela = gold_features.build_indicadores_sensoriamento_anual()
    assert len(tabela) == tabela[["trecho_id", "ano"]].drop_duplicates().shape[0]
    assert set(tabela["trecho_id"]) == {"alto_tiete", "medio_tiete", "baixo_tiete"}
    assert (tabela["ano"] == 2026).all()


def test_parametros_conhecidos_viram_colunas_com_nome_estavel(sensoriamento_sintetico):
    tabela = gold_features.build_indicadores_sensoriamento_anual().set_index("trecho_id")
    assert tabela.loc["medio_tiete", "clorofila_a_mg_m3"] == 45.2
    assert tabela.loc["medio_tiete", "nivel_agua_m"] == 442.15
    assert tabela.loc["baixo_tiete", "temperatura_superficie_c"] == 24.1
    assert tabela.loc["alto_tiete", "turbidez_ntu_sensoriamento"] == 4.2


def test_duas_leituras_no_mesmo_ano_viram_media(sensoriamento_sintetico):
    tabela = gold_features.build_indicadores_sensoriamento_anual().set_index("trecho_id")
    assert tabela.loc["alto_tiete", "ndvi_mata_ciliar"] == pytest.approx((0.78 + 0.80) / 2)
    assert tabela.loc["alto_tiete", "n_observacoes_sensoriamento"] == 3


def test_parametro_sem_mapeamento_usa_fallback_normalizado_em_vez_de_sumir(sensoriamento_sintetico):
    """Um parâmetro novo na planilha fonte (ex.: um índice espectral adicional) não pode ser
    descartado silenciosamente — vira uma coluna com nome normalizado, e o teste falha se
    algum dia essa linha for perdida por engano numa refatoração."""
    tabela = gold_features.build_indicadores_sensoriamento_anual().set_index("trecho_id")
    assert tabela.loc["baixo_tiete", "parametro_desconhecido_xyz"] == 99.0


def test_proxy_ndti_do_landsat_real_tem_coluna_propria_distinta_da_turbidez_ntu():
    """A "Turbidez" da planilha ilustrativa (NTU) e a "Turbidez (proxy NDTI, não calibrado)" do
    Landsat real (`connectors.sensoriamento_historico`) são grandezas DIFERENTES — não podem
    cair na mesma coluna, ou o merge por prioridade misturaria um índice espectral não
    calibrado com uma medição NTU real sem nenhum aviso."""
    mapa = gold_features._PARAMETRO_SENSORIAMENTO_PARA_COLUNA
    assert mapa["Turbidez"] == "turbidez_ntu_sensoriamento"
    assert mapa["Turbidez (proxy NDTI, não calibrado)"] == "turbidez_proxy_ndti_sensoriamento"
    assert mapa["Turbidez"] != mapa["Turbidez (proxy NDTI, não calibrado)"]


def test_tabela_fonte_vazia_retorna_vazio_sem_erro(monkeypatch):
    monkeypatch.setattr(gold_features, "read_table", lambda path: pd.DataFrame())
    tabela = gold_features.build_indicadores_sensoriamento_anual()
    assert tabela.empty


def test_fonte_tipo_agregada_e_simulado_quando_so_ha_ilustrativo(sensoriamento_sintetico):
    """Sem `silver.sensoriamento_historico` (real), a proveniência agregada de todo
    (trecho, ano) tem que ser "simulado" — nenhuma linha veio do Landsat."""
    tabela = gold_features.build_indicadores_sensoriamento_anual().set_index("trecho_id")
    assert (tabela["sensoriamento_fonte_tipo"] == "simulado").all()


def test_sem_sobreposicao_de_ano_com_qualidade_real():
    """Documenta em teste a própria ressalva da docstring do módulo: a planilha ILUSTRATIVA
    (2026) isolada não tem nenhum ano em comum com o histórico real da CETESB (até 2024). Isto
    NÃO é mais o motivo de `gold.sensoriamento_trecho_ano` ficar fora de `feature_store_ml_anual`
    — desde que `silver.sensoriamento_historico` (Landsat real, 1984-presente) existe, HÁ
    sobreposição real (ver `test_sensoriamento_real_fallback.py`); o motivo atual é a falta de
    calibração dos índices espectrais contra medição in situ (ver ATUALIZAÇÃO 2026-07 na
    docstring do módulo)."""
    anos_sensoriamento_sintetico = {2026}
    ultimo_ano_cetesb_real_documentado = 2024
    assert min(anos_sensoriamento_sintetico) > ultimo_ano_cetesb_real_documentado
