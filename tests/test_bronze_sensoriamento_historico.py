"""Testes de `ingestion.bronze_sensoriamento_historico` — grava o resultado do conector
Landsat/Earth Engine em Bronze, sem depender de rede/autenticação (o conector em si é
mockado — ver `test_sensoriamento_historico.py` para os testes do conector)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from waterweave.ingestion import bronze_sensoriamento_historico


def _serie_falsa(desde, ate, bacias=None, project=None):
    return pd.DataFrame(
        {
            "id_regiao": ["TIE-01", "TIE-01"],
            "trecho_id": ["alto_tiete", "alto_tiete"],
            "data_coleta": pd.to_datetime(["2020-07-01", "2021-07-01"]),
            "sensor": ["Landsat Collection 2 (5/7/8/9 mesclados)"] * 2,
            "parametro": ["NDVI (Mata Ciliar)", "NDVI (Mata Ciliar)"],
            "valor": [0.65, 0.63],
            "unidade": ["Índice (0-1)", "Índice (0-1)"],
            "fonte_dado": ["USGS/NASA via Google Earth Engine"] * 2,
            "_fonte_tipo": ["observado", "observado"],
        }
    )


@pytest.fixture
def conector_mockado(monkeypatch):
    capturado = {}

    def _fetch_capturando(desde, ate, bacias=None, project=None):
        capturado["desde"], capturado["ate"] = desde, ate
        return _serie_falsa(desde, ate, bacias, project)

    monkeypatch.setattr(bronze_sensoriamento_historico.sensoriamento_historico, "fetch_series_historica", _fetch_capturando)
    monkeypatch.setattr(bronze_sensoriamento_historico, "write_table", lambda *a, **k: None)
    return capturado


def test_run_usa_datas_padrao_desde_1984(conector_mockado):
    bronze_sensoriamento_historico.run()
    assert conector_mockado["desde"] == date(1984, 1, 1)
    assert conector_mockado["ate"] == date.today()


def test_run_repassa_datas_explicitas(conector_mockado):
    bronze_sensoriamento_historico.run(desde=date(2000, 1, 1), ate=date(2010, 12, 31))
    assert conector_mockado["desde"] == date(2000, 1, 1)
    assert conector_mockado["ate"] == date(2010, 12, 31)


def test_run_marca_colunas_de_proveniencia(conector_mockado):
    tabela = bronze_sensoriamento_historico.run()
    assert "_ingested_at" in tabela.columns
    assert "_source_file" in tabela.columns
    assert (tabela["_fonte_tipo"] == "observado").all()


def test_run_com_fetch_vazio_nao_quebra(monkeypatch):
    monkeypatch.setattr(
        bronze_sensoriamento_historico.sensoriamento_historico, "fetch_series_historica", lambda *a, **k: pd.DataFrame()
    )
    escritas = []
    monkeypatch.setattr(bronze_sensoriamento_historico, "write_table", lambda *a, **k: escritas.append(a))
    tabela = bronze_sensoriamento_historico.run()
    assert tabela.empty
    assert not escritas  # não grava tabela vazia
