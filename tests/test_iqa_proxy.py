"""Teste de guarda para `models.hybrid_bridge.iqa_proxy` — cobre o achado de 2026-09: a
fórmula anterior (`20×OD - 2×DBO + 40`) saturava em 100 para praticamente qualquer OD/DBO
alcançável pelo balanço hídrico + Streeter-Phelps (OD nunca passa de ~9,08 mg/L, o que já dá
20×9,08+40=221,6 sozinho), fazendo a página "Comparativo de Cenários" mostrar IQA = 100,00 para
todo trecho, cenário e horizonte temporal — o oposto do propósito da página. Corrigido
reaproveitando a mesma fórmula já usada para o dado REAL em
`transform.silver_qualidade_cetesb.build_silver_qualidade_cetesb`."""
from __future__ import annotations

import pytest

from waterweave.models import hybrid_bridge


def test_iqa_proxy_nao_satura_para_od_dbo_tipicos_do_streeter_phelps():
    """OD/DBO reais observados via `rodar_cenario` (Alto Tietê, cenários "atual" e "alta
    restrição de outorga") precisam produzir valores DIFERENTES e abaixo de 100 — antes desta
    correção, ambos davam exatamente 100,00."""
    atual = hybrid_bridge.iqa_proxy(od_mg_l=5.74, dbo_mg_l=11.84)
    alta_restricao = hybrid_bridge.iqa_proxy(od_mg_l=6.25, dbo_mg_l=10.21)
    assert atual < 100.0
    assert alta_restricao < 100.0
    assert alta_restricao > atual  # menos DBO e mais OD -> cenário melhor


def test_iqa_proxy_extremos():
    assert hybrid_bridge.iqa_proxy(od_mg_l=hybrid_bridge.IQA_OD_REFERENCIA_MG_L, dbo_mg_l=0.0) == pytest.approx(100.0)
    assert hybrid_bridge.iqa_proxy(od_mg_l=0.0, dbo_mg_l=hybrid_bridge.IQA_DBO_REFERENCIA_MG_L) == pytest.approx(0.0)


def test_iqa_proxy_usa_a_mesma_formula_do_dado_real():
    """Mesma fórmula de `silver_qualidade_cetesb.build_silver_qualidade_cetesb`, para o ABM e o
    dado observado falarem a mesma língua (não duas fórmulas divergentes para "IQA")."""
    od, dbo = 6.5, 8.0
    od_normalizado = min(100.0, (od / 8.0) * 100.0)
    dbo_normalizado = max(0.0, 100.0 - (dbo / 10.0) * 100.0)
    esperado = 0.6 * od_normalizado + 0.4 * dbo_normalizado
    assert hybrid_bridge.iqa_proxy(od, dbo) == pytest.approx(esperado)
