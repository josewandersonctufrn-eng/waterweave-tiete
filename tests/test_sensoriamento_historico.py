"""Testes de `connectors.sensoriamento_historico` — dois grupos, mesma separação de
`tests/test_mapbiomas.py`:

1. `_formatar_para_schema_bronze` — reshape puro de pandas, sem `ee`, cobre o contrato de
   schema que o resto do pipeline (`transform.silver_sensoriamento`,
   `transform.gold_features.build_indicadores_sensoriamento_anual`) espera receber.
2. `fetch_series_historica` — a ORQUESTRAÇÃO (filtro por `bacias`, tratamento de erro por
   ponto, projeto obrigatório), com `ee.Initialize`/`_serie_ponto` mockados — mesma técnica de
   `test_mapbiomas.py`. NÃO testa o cálculo espectral em si (`_serie_ponto`,
   `_preparar_colecao`, reduceRegion do Earth Engine) — isso nunca foi executado contra o
   Earth Engine de verdade (ver STATUS DE IMPLEMENTAÇÃO na docstring do módulo), só a
   orquestração ao redor dele.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from waterweave.ingestion.connectors import sensoriamento_historico as sh
from waterweave.ingestion.connectors.sensoriamento_historico import _formatar_para_schema_bronze


def _serie_anual_larga_sintetica() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ano": 2020, "ndvi": 0.75, "ndti_proxy_turbidez": -0.10, "temp_superficie_c": 22.0, "ponto_id": "TIE-01", "trecho_id": "alto_tiete"},
            {"ano": 2021, "ndvi": 0.70, "ndti_proxy_turbidez": None, "temp_superficie_c": 23.0, "ponto_id": "TIE-01", "trecho_id": "alto_tiete"},
            {"ano": 2020, "ndvi": 0.30, "ndti_proxy_turbidez": 0.20, "temp_superficie_c": 25.0, "ponto_id": "TIE-04", "trecho_id": "medio_tiete"},
        ]
    )


def test_formato_de_saida_bate_com_schema_bronze_sensoriamento():
    """O restante do pipeline (`silver_sensoriamento.py`) espera exatamente estas colunas —
    ver `_RENOMEIA` naquele módulo. Se esta lista divergir, a ingestão quebra silenciosamente
    (colunas renomeadas para NaN em vez de erro)."""
    longo = _formatar_para_schema_bronze(_serie_anual_larga_sintetica())
    esperado = {"id_regiao", "trecho_id", "data_coleta", "sensor", "parametro", "valor", "unidade", "fonte_dado", "_fonte_tipo"}
    assert set(longo.columns) == esperado


def test_uma_linha_por_ponto_data_parametro_pulando_valores_nulos():
    longo = _formatar_para_schema_bronze(_serie_anual_larga_sintetica())
    # TIE-01/2021 tem ndti nulo -> só 2 parâmetros (não 3); os outros 2 pontos-ano têm os 3
    assert len(longo) == 3 + 3 + 2
    tie01_2021 = longo[(longo["id_regiao"] == "TIE-01") & (longo["data_coleta"] == pd.Timestamp("2021-07-01"))]
    assert set(tie01_2021["parametro"]) == {"NDVI (Mata Ciliar)", "Temperatura da Superfície"}


def test_todas_as_linhas_marcadas_como_fonte_observada():
    """Diferente da planilha ilustrativa (`fonte_tipo=simulado`), dado extraído de satélite
    real é observação real — mesmo que indireta/remota, não pode ser confundido com o
    fallback simulado a jusante (ver `transform.gold_features.qualidade_real_com_fallback_simulado`
    para o mesmo tipo de distinção aplicada à qualidade da água)."""
    longo = _formatar_para_schema_bronze(_serie_anual_larga_sintetica())
    assert (longo["_fonte_tipo"] == "observado").all()


def test_data_coleta_representa_o_ano_inteiro():
    """A mediana anual não tem uma data real única — 1º de julho é usado como data
    representativa. Regressão simples: garante que ninguém troca isso por uma data arbitrária
    diferente sem querer."""
    longo = _formatar_para_schema_bronze(_serie_anual_larga_sintetica())
    assert (longo["data_coleta"].dt.month == 7).all()
    assert (longo["data_coleta"].dt.day == 1).all()


def test_entrada_vazia_retorna_vazio_sem_erro():
    resultado = _formatar_para_schema_bronze(pd.DataFrame())
    assert resultado.empty


# ---------------------------------------------------------------------------------------------
# Grupo 2: `fetch_series_historica` — orquestração, com `ee.Initialize`/`_serie_ponto` mockados
# (mesma técnica de `test_mapbiomas.py`'s `ee_mockado`). Não exercita `_serie_ponto`/
# `_preparar_colecao` de verdade — ver docstring do módulo no topo deste arquivo.
# ---------------------------------------------------------------------------------------------

_PROJETO_TESTE = "projeto-teste-falso"


@pytest.fixture
def ee_mockado(monkeypatch):
    monkeypatch.setattr(sh.ee, "Initialize", lambda project=None: None)


def _serie_ponto_falsa(ponto_id: str, metadados: dict, data_inicio, data_fim) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ano": 2020,
                "ndvi": 0.7,
                "ndti_proxy_turbidez": 0.1,
                "temp_superficie_c": 22.0,
                "ponto_id": ponto_id,
                "trecho_id": metadados["trecho_id"],
            }
        ]
    )


def test_fetch_processa_todos_os_pontos(ee_mockado, monkeypatch):
    monkeypatch.setattr(sh, "_serie_ponto", _serie_ponto_falsa)
    resultado = sh.fetch_series_historica(date(2020, 1, 1), date(2021, 1, 1), project=_PROJETO_TESTE)
    assert set(resultado["id_regiao"]) == set(sh.PONTOS_MONITORAMENTO)
    assert set(resultado["trecho_id"]) == {"alto_tiete", "medio_tiete", "baixo_tiete"}


def test_fetch_filtro_por_bacias(ee_mockado, monkeypatch):
    monkeypatch.setattr(sh, "_serie_ponto", _serie_ponto_falsa)
    resultado = sh.fetch_series_historica(
        date(2020, 1, 1), date(2021, 1, 1), bacias=["alto_tiete"], project=_PROJETO_TESTE
    )
    assert set(resultado["trecho_id"]) == {"alto_tiete"}
    pontos_alto = {k for k, v in sh.PONTOS_MONITORAMENTO.items() if v["trecho_id"] == "alto_tiete"}
    assert set(resultado["id_regiao"]) == pontos_alto


def test_fetch_falha_em_um_ponto_nao_derruba_os_demais(ee_mockado, monkeypatch):
    """Um ponto com erro (ex.: falha transitória de rede/`getInfo`) é pulado e logado — não
    interrompe a extração dos demais pontos (ver `logger.warning(..., exc_info=True)` em
    `fetch_series_historica`)."""

    def _serie_com_uma_falha(ponto_id, metadados, data_inicio, data_fim):
        if ponto_id == "TIE-02":
            raise RuntimeError("falha simulada de Earth Engine")
        return _serie_ponto_falsa(ponto_id, metadados, data_inicio, data_fim)

    monkeypatch.setattr(sh, "_serie_ponto", _serie_com_uma_falha)
    resultado = sh.fetch_series_historica(date(2020, 1, 1), date(2021, 1, 1), project=_PROJETO_TESTE)
    assert "TIE-02" not in set(resultado["id_regiao"])
    assert set(resultado["id_regiao"]) == set(sh.PONTOS_MONITORAMENTO) - {"TIE-02"}


def test_fetch_sem_projeto_levanta_erro_claro(ee_mockado):
    with pytest.raises(RuntimeError, match="WATERWEAVE_EE_PROJECT"):
        sh.fetch_series_historica(date(2020, 1, 1), date(2021, 1, 1), project=None)
