"""Testes de `ingestion.bronze_uso_solo` — monta os pontos reais por trecho a partir de
`bronze.estacoes` (mesma regra de `transform.silver_estacoes`) e grava o resultado do conector
MapBiomas em Bronze, sem depender de rede/autenticação do Earth Engine (o conector em si é
mockado — ver `test_mapbiomas.py` para os testes do conector)."""
from __future__ import annotations

import pandas as pd
import pytest

from waterweave.ingestion import bronze_uso_solo


def _bronze_estacoes() -> pd.DataFrame:
    # "Medio Tiete" sem acento é proposital: `_ugrhi_para_trecho` faz `.upper()` (só troca
    # maiúsculas/minúsculas, não remove acento) e procura o substring exato "MEDIO TIETE" —
    # com acento ("MÉDIO TIETÊ") o `in` não bate. Alto/Baixo não têm esse problema porque o
    # substring checado ("ALTO TI"/"BAIXO TI") não inclui a parte acentuada de "Tietê".
    return pd.DataFrame(
        {
            "CodPonto": ["TIET02100", "TIET02200", "TIBT01900", "OUTRO00100"],
            "UGRHI": ["Alto Tietê", "Medio Tiete", "Baixo Tietê", "Alto Tietê"],
            "LongDecml": [-46.1, -48.0, -50.5, -46.2],
            "LattDecml": [-23.5, -22.5, -21.0, -23.6],
        }
    )


def test_pontos_reais_por_trecho_filtra_e_classifica(monkeypatch):
    monkeypatch.setattr(bronze_uso_solo, "read_table", lambda path: _bronze_estacoes())
    pontos = bronze_uso_solo._pontos_reais_por_trecho()

    assert set(pontos) == {"alto_tiete", "medio_tiete", "baixo_tiete"}
    assert pontos["alto_tiete"] == [(-46.1, -23.5)]
    assert pontos["medio_tiete"] == [(-48.0, -22.5)]
    assert pontos["baixo_tiete"] == [(-50.5, -21.0)]


def test_pontos_reais_por_trecho_ignora_codigos_fora_do_eixo_tiete(monkeypatch):
    """`OUTRO00100` não começa com TIET/TIBT — não é uma estação do eixo do rio, mesmo estando
    classificada como Alto Tietê no cadastro estadual (699 estações em todas as bacias de SP)."""
    monkeypatch.setattr(bronze_uso_solo, "read_table", lambda path: _bronze_estacoes())
    pontos = bronze_uso_solo._pontos_reais_por_trecho()
    assert len(pontos["alto_tiete"]) == 1


@pytest.fixture
def bronze_estacoes_e_conector(monkeypatch):
    monkeypatch.setattr(bronze_uso_solo, "read_table", lambda path: _bronze_estacoes())
    monkeypatch.setattr(bronze_uso_solo, "write_table", lambda *a, **k: None)

    capturado = {}

    def _fetch_falso(pontos_por_trecho):
        capturado["pontos_por_trecho"] = pontos_por_trecho
        return pd.DataFrame(
            {
                "trecho_id": ["alto_tiete"],
                "ano": [2023],
                "classe_mapbiomas": [24],
                "macro_categoria": ["urbano_industrial"],
                "area_m2": [1000.0],
            }
        )

    monkeypatch.setattr(bronze_uso_solo.mapbiomas, "fetch_uso_solo_por_trecho", _fetch_falso)
    return capturado


def test_run_repassa_pontos_reais_para_o_conector(bronze_estacoes_e_conector):
    bronze_uso_solo.run()
    assert bronze_estacoes_e_conector["pontos_por_trecho"]["alto_tiete"] == [(-46.1, -23.5)]


def test_run_marca_colunas_de_proveniencia(bronze_estacoes_e_conector):
    tabela = bronze_uso_solo.run()
    assert (tabela["_fonte_tipo"] == "observado").all()
    assert (tabela["_source_file"] == bronze_uso_solo.mapbiomas.ASSET_ID).all()
    assert "_ingested_at" in tabela.columns
