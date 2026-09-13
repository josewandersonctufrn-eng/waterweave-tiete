"""Teste de guarda para `models.biofisico.iqa_oficial_cetesb` — o modelo OFICIAL CETESB/NSF
(9 parâmetros, produtório ponderado), adotado a pedido do usuário para o IQA exibido na página
"Cenários Futuros" (distinto do proxy de 2 parâmetros OD/DBO usado no restante do projeto —
ver `models.hybrid_bridge.iqa_proxy`). Cobre os pontos EXATOS publicados pela CETESB (2007,
Anexo III, Figura V.1) e propriedades gerais da agregação."""
from __future__ import annotations

import pytest

from waterweave.models.biofisico import iqa_oficial_cetesb as m


def test_pesos_somam_um():
    assert sum(m.PESOS.values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "funcao, x, q_esperado",
    [
        (m.q_od, 140.0, 47.0),
        (m.q_od, 200.0, 47.0),  # constante além do ponto publicado
        (m.q_ph, 2.0, 2.0),
        (m.q_ph, 1.0, 2.0),  # constante abaixo do ponto publicado
        (m.q_ph, 12.0, 3.0),
        (m.q_ph, 20.0, 3.0),
        (m.q_dbo, 30.0, 2.0),
        (m.q_dbo, 50.0, 2.0),
        (m.q_nitrogenio, 100.0, 1.0),
        (m.q_fosforo, 10.0, 1.0),
        (m.q_turbidez, 100.0, 5.0),
        (m.q_solidos_totais, 500.0, 32.0),
    ],
)
def test_pontos_exatos_publicados_pela_cetesb_2007(funcao, x, q_esperado):
    """Cada um destes é um valor que a própria CETESB (2007, Fig. V.1) escreve por extenso
    como nota (ex.: "se OD %sat. > 140, q9 = 47,0") — não uma aproximação nossa."""
    assert funcao(x) == pytest.approx(q_esperado)


def test_q_coliformes_ponto_exato_10_elevado_a_5():
    assert m.q_coliformes(1e5) == pytest.approx(3.0)
    assert m.q_coliformes(1e7) == pytest.approx(3.0)  # constante além do ponto publicado


def test_todas_as_curvas_ficam_no_intervalo_0_100():
    amostras = {
        m.q_od: [0, 50, 100, 150, 300],
        m.q_coliformes: [0, 1, 100, 10_000, 1e6],
        m.q_ph: [0, 4, 7, 9, 14],
        m.q_dbo: [0, 10, 30, 100],
        m.q_nitrogenio: [0, 20, 100, 200],
        m.q_fosforo: [0, 1, 10, 20],
        m.q_temperatura: [-10, -5, 0, 10, 15, 30],
        m.q_turbidez: [0, 30, 100, 200],
        m.q_solidos_totais: [0, 100, 500, 1000],
    }
    for funcao, valores in amostras.items():
        for x in valores:
            q = funcao(x)
            assert 0.0 <= q <= 100.0, f"{funcao.__name__}({x}) = {q} fora de [0, 100]"


def test_iqa_oficial_fica_no_intervalo_0_100_e_e_sensivel_a_cada_parametro():
    condicoes_boas = dict(
        od_mg_l=8.5, dbo_mg_l=1.0, coliformes_termotolerantes_nmp_100ml=1.0, ph=7.2,
        nitrogenio_total_mg_l=1.0, fosforo_total_mg_l=0.1, turbidez_ntu=2.0, solidos_totais_mg_l=60.0,
    )
    condicoes_ruins = dict(
        od_mg_l=0.5, dbo_mg_l=40.0, coliformes_termotolerantes_nmp_100ml=1_000_000.0, ph=3.0,
        nitrogenio_total_mg_l=150.0, fosforo_total_mg_l=15.0, turbidez_ntu=150.0, solidos_totais_mg_l=800.0,
    )
    iqa_bom = m.iqa_oficial_cetesb(**condicoes_boas)
    iqa_ruim = m.iqa_oficial_cetesb(**condicoes_ruins)
    assert 0.0 <= iqa_ruim < iqa_bom <= 100.0


def test_iqa_oficial_converte_od_mg_l_para_percentual_de_saturacao():
    """OD em mg/L precisa ser convertido para % de saturação antes de entrar na curva de OD
    (definida em % de saturação, não em mg/L) — usando a mesma referência de
    `qualidade_agua.OD_SATURACAO_MG_L`."""
    od_no_ponto_de_saturacao = m.OD_SATURACAO_REFERENCIA_MG_L  # 100% de saturação
    base = dict(
        dbo_mg_l=5.0, coliformes_termotolerantes_nmp_100ml=10.0, ph=7.0,
        nitrogenio_total_mg_l=5.0, fosforo_total_mg_l=0.5, turbidez_ntu=10.0, solidos_totais_mg_l=100.0,
    )
    iqa_saturado = m.iqa_oficial_cetesb(od_mg_l=od_no_ponto_de_saturacao, **base)
    iqa_metade = m.iqa_oficial_cetesb(od_mg_l=od_no_ponto_de_saturacao / 2, **base)
    assert iqa_saturado > iqa_metade
