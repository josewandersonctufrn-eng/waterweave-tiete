"""Testes de guarda de `models.abm.clima_real` — a ponte que lê a calibração de `fator_clima`
via CMIP6 (`ingestion.connectors.era5_cmip6`), com fallback quando ela não existe/está
corrompida. Usa `tmp_path` (via monkeypatch de `FATOR_CLIMA_CALIBRACAO_FILE`) — nunca lê/escreve
o `config.FATOR_CLIMA_CALIBRACAO_FILE` real do repositório durante os testes.
"""
from __future__ import annotations

import json

from waterweave.models.abm import clima_real


def test_fallback_quando_arquivo_nao_existe(tmp_path, monkeypatch):
    monkeypatch.setattr(clima_real, "FATOR_CLIMA_CALIBRACAO_FILE", tmp_path / "nao_existe.json")
    assert clima_real.fator_clima_calibrado("mudanca_climatica_extrema", fallback=0.75) == 0.75


def test_le_fator_calibrado_quando_arquivo_existe(tmp_path, monkeypatch):
    caminho = tmp_path / "fator_clima_cmip6.json"
    caminho.write_text(json.dumps({"fatores_clima": {"mudanca_climatica_extrema": 0.62}}), encoding="utf-8")
    monkeypatch.setattr(clima_real, "FATOR_CLIMA_CALIBRACAO_FILE", caminho)
    assert clima_real.fator_clima_calibrado("mudanca_climatica_extrema", fallback=0.75) == 0.62


def test_fallback_quando_cenario_nao_esta_na_calibracao(tmp_path, monkeypatch):
    caminho = tmp_path / "fator_clima_cmip6.json"
    caminho.write_text(json.dumps({"fatores_clima": {"outro_cenario": 0.5}}), encoding="utf-8")
    monkeypatch.setattr(clima_real, "FATOR_CLIMA_CALIBRACAO_FILE", caminho)
    assert clima_real.fator_clima_calibrado("mudanca_climatica_extrema", fallback=0.75) == 0.75


def test_fallback_quando_json_malformado(tmp_path, monkeypatch, caplog):
    caminho = tmp_path / "fator_clima_cmip6.json"
    caminho.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(clima_real, "FATOR_CLIMA_CALIBRACAO_FILE", caminho)
    assert clima_real.fator_clima_calibrado("mudanca_climatica_extrema", fallback=0.75) == 0.75


def test_fallback_quando_estrutura_inesperada(tmp_path, monkeypatch):
    """`fatores_clima` faltando inteiramente (não só o cenário) — mesmo tratamento defensivo."""
    caminho = tmp_path / "fator_clima_cmip6.json"
    caminho.write_text(json.dumps({"algo_inesperado": True}), encoding="utf-8")
    monkeypatch.setattr(clima_real, "FATOR_CLIMA_CALIBRACAO_FILE", caminho)
    assert clima_real.fator_clima_calibrado("mudanca_climatica_extrema", fallback=0.75) == 0.75
