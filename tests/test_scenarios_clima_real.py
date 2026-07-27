"""Testes de guarda de que `models.abm.scenarios.PARAMETROS_CENARIO["mudanca_climatica_extrema"]`
usa `models.abm.clima_real.fator_clima_calibrado` (item "ligar ERA5/CMIP6 ao fator_clima do
ABM"). `PARAMETROS_CENARIO` é construído no NÍVEL DO MÓDULO (uma vez, no import) — para testar
os dois caminhos (com/sem calibração real) é preciso `importlib.reload` depois de mudar
`clima_real.FATOR_CLIMA_CALIBRACAO_FILE`, não dá para só monkeypatchar depois do import (o dict
já estaria fixo). Precisa do pacote `mesa` (`scenarios.py` importa `models.abm.model`).
"""
from __future__ import annotations

import importlib
import json

import pytest

pytest.importorskip("mesa")

from waterweave.models.abm import clima_real
from waterweave.models.abm import scenarios as scenarios_module

# Cada teste recarrega `scenarios_module` depois de mudar `clima_real.FATOR_CLIMA_CALIBRACAO_FILE`
# (é a única forma de exercitar os dois caminhos, já que `PARAMETROS_CENARIO` é construído uma
# vez no nível do módulo) e recarrega de NOVO ao final (sem a calibração de teste) para não
# deixar `scenarios_module.PARAMETROS_CENARIO` calibrado com um valor de teste vazando para
# outros arquivos de teste que importem `scenarios` depois.


def test_fallback_fixo_quando_sem_calibracao(tmp_path, monkeypatch):
    monkeypatch.setattr(clima_real, "FATOR_CLIMA_CALIBRACAO_FILE", tmp_path / "nao_existe.json")
    modulo = importlib.reload(scenarios_module)
    assert modulo.PARAMETROS_CENARIO["mudanca_climatica_extrema"]["fator_clima"] == pytest.approx(
        modulo._FATOR_CLIMA_EXTREMA_FALLBACK
    )
    importlib.reload(scenarios_module)  # restaura para os demais testes do módulo/sessão


def test_usa_fator_calibrado_quando_disponivel(tmp_path, monkeypatch):
    caminho = tmp_path / "fator_clima_cmip6.json"
    caminho.write_text(json.dumps({"fatores_clima": {"mudanca_climatica_extrema": 0.63}}), encoding="utf-8")
    monkeypatch.setattr(clima_real, "FATOR_CLIMA_CALIBRACAO_FILE", caminho)

    modulo = importlib.reload(scenarios_module)
    assert modulo.PARAMETROS_CENARIO["mudanca_climatica_extrema"]["fator_clima"] == pytest.approx(0.63)

    importlib.reload(scenarios_module)  # restaura para os demais testes do módulo/sessão


def test_outros_cenarios_nao_sao_afetados_pela_calibracao(tmp_path, monkeypatch):
    caminho = tmp_path / "fator_clima_cmip6.json"
    caminho.write_text(json.dumps({"fatores_clima": {"mudanca_climatica_extrema": 0.5}}), encoding="utf-8")
    monkeypatch.setattr(clima_real, "FATOR_CLIMA_CALIBRACAO_FILE", caminho)

    modulo = importlib.reload(scenarios_module)
    assert modulo.PARAMETROS_CENARIO["atual"]["fator_clima"] == 1.0
    assert modulo.PARAMETROS_CENARIO["alta_restricao_outorga"]["fator_clima"] == 1.0

    importlib.reload(scenarios_module)  # restaura para os demais testes do módulo/sessão
