"""Testes de guarda de `coeficiente_de_percentuais_reais` (uso do solo real, MapBiomas) e do
dispatch `str | dict | None` em `balanco_hidrico.simular_passo_mensal` — ver ACHADO DE
PESQUISA em `models.biofisico.uso_solo`/`models.biofisico.balanco_hidrico`.
"""
from __future__ import annotations

import math

import pytest

from waterweave.models.biofisico.balanco_hidrico import estado_inicial, simular_passo_mensal
from waterweave.models.biofisico.uso_solo import (
    _COEFICIENTE_PADRAO,
    classe_para_coeficiente_escoamento,
    coeficiente_de_percentuais_reais,
)


def test_cem_por_cento_de_uma_categoria_usa_o_coeficiente_dela_direto():
    assert coeficiente_de_percentuais_reais({"pct_natural": 100.0}) == 0.20
    assert coeficiente_de_percentuais_reais({"pct_urbano_industrial": 100.0}) == 0.75


def test_mistura_e_media_ponderada_pelo_percentual():
    coeficiente = coeficiente_de_percentuais_reais({"pct_natural": 50.0, "pct_urbano_industrial": 50.0})
    assert coeficiente == pytest.approx((0.20 + 0.75) / 2)


def test_aceita_chaves_com_ou_sem_prefixo_pct():
    com_prefixo = coeficiente_de_percentuais_reais({"pct_natural": 50.0, "pct_urbano_industrial": 50.0})
    sem_prefixo = coeficiente_de_percentuais_reais({"natural": 50.0, "urbano_industrial": 50.0})
    assert com_prefixo == sem_prefixo


def test_percentuais_vazios_ou_nulos_caem_no_fallback_padrao():
    assert coeficiente_de_percentuais_reais({}) == _COEFICIENTE_PADRAO
    assert coeficiente_de_percentuais_reais({"pct_natural": None}) == _COEFICIENTE_PADRAO
    assert coeficiente_de_percentuais_reais({"pct_natural": math.nan, "pct_agua": math.nan}) == _COEFICIENTE_PADRAO


def test_simular_passo_mensal_aceita_string_legada_e_dict_real_sem_erro():
    """Regressão de compatibilidade: `models.abm.model` ainda passa string simulada hoje —
    isso NÃO pode quebrar quando o dict real também é um caminho válido. Com
    `armazenamento_mm=50.0` (padrão de `estado_inicial`) e `precipitacao_mm=100.0`, o
    armazenamento disponível (80mm) fica todo consumido pela ET potencial (90mm) — o
    escoamento de base zera, e `indice_escoamento_mm` vira exatamente `coeficiente * 100`,
    o que dá um valor exato e fácil de conferir para os dois caminhos (string e dict)."""
    estado0 = estado_inicial("alto_tiete")

    novo_str = simular_passo_mensal(estado0, 100.0, "Metropolitano / Industrial")
    coef_str_esperado = classe_para_coeficiente_escoamento("Metropolitano / Industrial")
    assert coef_str_esperado == 0.70
    assert novo_str.indice_escoamento_mm == pytest.approx(70.0)

    novo_dict = simular_passo_mensal(estado0, 100.0, {"pct_urbano_industrial": 100.0})
    assert novo_dict.indice_escoamento_mm == pytest.approx(75.0)  # coeficiente real (0.75) != coeficiente simulado (0.70), de propósito
    assert novo_dict.indice_escoamento_mm != novo_str.indice_escoamento_mm

    # None -> coeficiente padrão (0.35): aqui a infiltração (65mm) supera a ET potencial
    # (90mm > armazenamento disponível de 115mm? não — sobra 25mm), então o escoamento de
    # base NÃO zera como nos casos acima (valor calculado e conferido à mão: 43.75mm).
    novo_none = simular_passo_mensal(estado0, 100.0, None)
    assert novo_none.indice_escoamento_mm == pytest.approx(43.75)  # fallback, não lança exceção
