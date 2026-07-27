"""Testes de `transform.silver_sensoriamento_historico` — anexa latitude/longitude/nome do
ponto a partir de `connectors.sensoriamento_historico.PONTOS_MONITORAMENTO`, sem precisar
separar uma coluna "Coordenadas (Lat/Long)" (diferente da planilha ilustrativa, ver
`transform.silver_sensoriamento`)."""
from __future__ import annotations

import pandas as pd

from waterweave.transform import silver_sensoriamento_historico as ssh


def _bronze_sensoriamento_historico() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id_regiao": ["TIE-01", "TIE-04"],
            "trecho_id": ["alto_tiete", "medio_tiete"],
            "data_coleta": pd.to_datetime(["2020-07-01", "2021-07-01"]),
            "sensor": ["Landsat Collection 2 (5/7/8/9 mesclados)"] * 2,
            "parametro": ["NDVI (Mata Ciliar)", "Temperatura da Superfície"],
            "valor": [0.65, 28.4],
            "unidade": ["Índice (0-1)", "°C"],
            "fonte_dado": ["USGS/NASA via Google Earth Engine"] * 2,
            "_fonte_tipo": ["observado", "observado"],
        }
    )


def test_anexa_coordenadas_reais_dos_pontos(monkeypatch):
    monkeypatch.setattr(ssh, "read_table", lambda path: _bronze_sensoriamento_historico())
    monkeypatch.setattr(ssh, "write_table", lambda *a, **k: None)

    tabela = ssh.build_silver_sensoriamento_historico().set_index("id_regiao")
    assert tabela.loc["TIE-01", "latitude"] == ssh.PONTOS_MONITORAMENTO["TIE-01"]["lat"]
    assert tabela.loc["TIE-01", "longitude"] == ssh.PONTOS_MONITORAMENTO["TIE-01"]["lon"]
    assert tabela.loc["TIE-04", "trecho_nome"] == ssh.PONTOS_MONITORAMENTO["TIE-04"]["nome"]


def test_renomeia_fonte_tipo(monkeypatch):
    monkeypatch.setattr(ssh, "read_table", lambda path: _bronze_sensoriamento_historico())
    monkeypatch.setattr(ssh, "write_table", lambda *a, **k: None)

    tabela = ssh.build_silver_sensoriamento_historico()
    assert "fonte_tipo" in tabela.columns
    assert "_fonte_tipo" not in tabela.columns
    assert (tabela["fonte_tipo"] == "observado").all()


def test_bronze_vazia_retorna_vazio_sem_erro(monkeypatch):
    monkeypatch.setattr(ssh, "read_table", lambda path: pd.DataFrame())
    tabela = ssh.build_silver_sensoriamento_historico()
    assert tabela.empty
