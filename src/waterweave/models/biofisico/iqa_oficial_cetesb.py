"""IQA oficial CETESB/NSF (9 parâmetros, produtório ponderado) — ver ACHADO na docstring do
módulo para o porquê deste módulo existir ao lado do proxy simplificado já usado no resto do
projeto (`models.hybrid_bridge.iqa_proxy`, 2 parâmetros, OD/DBO).

Fórmula oficial (CETESB, 2007, "Qualidade das Águas Interiores no Estado de São Paulo — Anexo
III — Índices de Qualidade das Águas", seção 3):

    IQA = Π(i=1..9) qi ^ wi,   Σ wi = 1

onde qi é a "qualidade do i-ésimo parâmetro" (0-100), lida da respectiva curva média de
variação de qualidade (CETESB 2007, Figura V.1), e wi o peso oficial de cada parâmetro:

    OD (% saturação)              wi = 0,17
    Coliformes termotolerantes    wi = 0,15
    pH                            wi = 0,12
    DBO5,20                       wi = 0,10
    Nitrogênio total              wi = 0,10
    Fósforo total                 wi = 0,10
    Temperatura (Δt equilíbrio)   wi = 0,10
    Turbidez                      wi = 0,08
    Resíduo total (sólidos)       wi = 0,08

ACHADO (2026-09, pedido do usuário: "quero que o IQA seja calculado no modelo que a CETESB
calcula" na página "Cenários Futuros"): a CETESB NUNCA publicou as 9 curvas como equações
fechadas — são gráficos (Figura V.1 do documento acima). Sem acesso ao dado bruto usado para
desenhá-las, a única forma honesta de reproduzi-las em código é digitalizar pontos de controle
do próprio gráfico oficial e interpolar linearmente por partes entre eles — método padrão
nesta situação (usado, por ex., por diversas ferramentas de cálculo de IQA no Brasil). Os
pontos de controle usados aqui vêm de três fontes, priorizadas nesta ordem:
  1. Valores de contorno/assintóticos que a própria CETESB (2007) publica por extenso nas
     notas da Figura V.1 (ex.: "se OD %sat. > 140, q9 = 47,0") — estes são EXATOS, não
     aproximados.
  2. O formato visual de cada curva (crescente/decrescente, posição do pico, etc.), lido
     diretamente da Figura V.1.
  3. Pontos de transição entre faixas de qualidade (excelente/boa/média), calibrados contra
     Pereira et al. (2013, XX Simpósio Brasileiro de Recursos Hídricos, "Análise de
     Sensibilidade dos Parâmetros do IQA") — equações do SCQA (Instituto Mineiro de Gestão das
     Águas), derivadas independentemente das mesmas curvas NSF por regressão polinomial e
     "comparadas com curvas já existentes na literatura, mostrando-se satisfatórias" (idem).
     Usadas só como calibração adicional dos pontos INTERNOS da curva, nunca no lugar dos
     valores exatos do item 1.

Isto é uma aproximação documentada da curva oficial, não uma cópia pixel-a-pixel — mais fiel
ao gráfico publicado pela CETESB do que reaproveitar a fórmula alternativa do SCQA (que é de
outra agência, com curvas próprias). Ver `tests/test_iqa_oficial_cetesb.py` para os casos de
verificação usados (pontos exatos das notas da CETESB, extremos 0/100, monotonicidade)."""
from __future__ import annotations

PESOS = {
    "od": 0.17,
    "coliformes": 0.15,
    "ph": 0.12,
    "dbo": 0.10,
    "nitrogenio": 0.10,
    "fosforo": 0.10,
    "temperatura": 0.10,
    "turbidez": 0.08,
    "solidos_totais": 0.08,
}
assert abs(sum(PESOS.values()) - 1.0) < 1e-9

OD_SATURACAO_REFERENCIA_MG_L = 9.08  # mesma referência de qualidade_agua.OD_SATURACAO_MG_L


def _interp_linear_por_partes(x: float, pontos: list[tuple[float, float]]) -> float:
    """Interpola `x` nos `pontos` (lista (x, q) ordenada por x crescente), mantendo constante
    fora do intervalo (clamp nas pontas) — mesmo comportamento das notas da CETESB ("se X >
    limite, q = valor fixo")."""
    if x <= pontos[0][0]:
        return pontos[0][1]
    if x >= pontos[-1][0]:
        return pontos[-1][1]
    for (x0, q0), (x1, q1) in zip(pontos, pontos[1:]):
        if x0 <= x <= x1:
            fracao = (x - x0) / (x1 - x0)
            return q0 + fracao * (q1 - q0)
    return pontos[-1][1]  # inatingível (loop acima cobre todo o intervalo [pontos[0], pontos[-1]])


def q_od(od_pct_saturacao: float) -> float:
    """Curva de qualidade do Oxigênio Dissolvido (% de saturação) — CETESB 2007, Fig. V.1,
    i=9. Ponto exato publicado: OD %sat. > 140 -> q9 = 47,0."""
    pontos = [(0, 2), (20, 8), (40, 21), (60, 50), (80, 89), (90, 96), (100, 98), (110, 94), (120, 80), (140, 47)]
    return _interp_linear_por_partes(od_pct_saturacao, pontos)


def q_coliformes(coliformes_termotolerantes_nmp_100ml: float) -> float:
    """Curva de qualidade de Coliformes Termotolerantes (NMP/100mL, escala logarítmica no
    eixo x) — CETESB 2007, Fig. V.1, i=1. Ponto exato publicado: C.F. > 10^5 -> q1 = 3,0."""
    import math

    cf = max(coliformes_termotolerantes_nmp_100ml, 1.0)
    log_cf = math.log10(cf)
    pontos = [(0, 100), (1, 85), (2, 65), (3, 48), (4, 25), (5, 3)]  # log10(NMP/100mL)
    return _interp_linear_por_partes(log_cf, pontos)


def q_ph(ph: float) -> float:
    """Curva de qualidade do pH — CETESB 2007, Fig. V.1, i=2. Pontos exatos publicados:
    pH < 2,0 -> q2 = 2,0; pH > 12,0 -> q2 = 3,0."""
    pontos = [(2, 2), (3, 10), (4, 35), (5, 60), (5.87, 75), (7, 90), (7.44, 93), (8.5, 88), (9.12, 75), (10, 55), (11.10, 42), (12, 3)]
    return _interp_linear_por_partes(ph, pontos)


def q_dbo(dbo_mg_l: float) -> float:
    """Curva de qualidade da DBO5,20 (mg/L) — CETESB 2007, Fig. V.1, i=3. Ponto exato
    publicado: DBO5 > 30,0 -> q3 = 2,0."""
    pontos = [(0, 99), (5, 90), (7.11, 85), (10, 70), (15, 55), (20, 40), (25, 25), (30, 2)]
    return _interp_linear_por_partes(dbo_mg_l, pontos)


def q_nitrogenio(nitrogenio_total_mg_l: float) -> float:
    """Curva de qualidade do Nitrogênio Total (mg/L) — CETESB 2007, Fig. V.1, i=4. Ponto
    exato publicado: N.T. > 100,0 -> q4 = 1,0."""
    pontos = [(0, 95), (10, 80), (11.33, 78), (30, 55), (50, 35), (69.74, 20), (100, 1)]
    return _interp_linear_por_partes(nitrogenio_total_mg_l, pontos)


def q_fosforo(fosforo_total_mg_l: float) -> float:
    """Curva de qualidade do Fósforo Total (mg/L) — CETESB 2007, Fig. V.1, i=5. Ponto exato
    publicado: PO4-T > 10,0 -> q5 = 1,0."""
    pontos = [(0, 95), (0.801, 85), (2, 60), (4, 40), (6, 25), (8, 15), (10, 1)]
    return _interp_linear_por_partes(fosforo_total_mg_l, pontos)


def q_temperatura(delta_t_c: float = 0.0) -> float:
    """Curva de qualidade da Temperatura, em função de Δt (afastamento da temperatura de
    equilíbrio, °C) — CETESB 2007, Fig. V.1, i=6. Pontos exatos publicados: Δt < -5,0 -> q6
    indefinido (aqui tratado como o mesmo piso de Δt=-5); Δt > 15,0 -> q6 = 9,0.

    `delta_t_c` default 0,0: o ABM não modela lançamento térmico industrial (descarga de água
    de resfriamento) como um desvio explícito da temperatura natural de equilíbrio — apenas
    uma temperatura absoluta ancorada por trecho. Mananciais brasileiros tipicamente não
    recebem cargas térmicas elevadas (ver Pereira et al., 2013, que adota a mesma convenção:
    "considera-se a variação da temperatura de equilíbrio próxima a zero, com qs = 93")."""
    pontos = [(-5, 10), (0, 93), (5, 80), (10, 55), (15, 9), (20, 9)]
    return _interp_linear_por_partes(delta_t_c, pontos)


def q_turbidez(turbidez_ntu: float) -> float:
    """Curva de qualidade da Turbidez (UNT) — CETESB 2007, Fig. V.1, i=7. Ponto exato
    publicado: turbidez > 100 -> q7 = 5,0."""
    pontos = [(0, 95), (27.85, 80), (50, 55), (70, 40), (100, 5)]
    return _interp_linear_por_partes(turbidez_ntu, pontos)


def q_solidos_totais(solidos_totais_mg_l: float) -> float:
    """Curva de qualidade do Resíduo Total / Sólidos Totais (mg/L) — CETESB 2007, Fig. V.1,
    i=8. Ponto exato publicado: R.T. > 500 -> q8 = 32,0."""
    pontos = [(0, 85), (55.864, 87), (100, 85), (200, 70), (300, 60), (400, 45), (500, 32)]
    return _interp_linear_por_partes(solidos_totais_mg_l, pontos)


def iqa_oficial_cetesb(
    od_mg_l: float,
    dbo_mg_l: float,
    coliformes_termotolerantes_nmp_100ml: float,
    ph: float,
    nitrogenio_total_mg_l: float,
    fosforo_total_mg_l: float,
    turbidez_ntu: float,
    solidos_totais_mg_l: float,
    delta_temperatura_c: float = 0.0,
    od_saturacao_referencia_mg_l: float = OD_SATURACAO_REFERENCIA_MG_L,
) -> float:
    """IQA pelo modelo oficial CETESB/NSF (9 parâmetros, produtório ponderado) — ver docstring
    do módulo para a fórmula, os pesos e a proveniência de cada curva de qualidade.

    `od_mg_l` é convertido para % de saturação usando `od_saturacao_referencia_mg_l` (mesma
    referência de `models.biofisico.qualidade_agua.OD_SATURACAO_MG_L`) antes de entrar na
    curva de OD, que é definida em % de saturação, não em mg/L.
    """
    od_pct_sat = 100.0 * od_mg_l / od_saturacao_referencia_mg_l

    qs = {
        "od": q_od(od_pct_sat),
        "coliformes": q_coliformes(coliformes_termotolerantes_nmp_100ml),
        "ph": q_ph(ph),
        "dbo": q_dbo(dbo_mg_l),
        "nitrogenio": q_nitrogenio(nitrogenio_total_mg_l),
        "fosforo": q_fosforo(fosforo_total_mg_l),
        "temperatura": q_temperatura(delta_temperatura_c),
        "turbidez": q_turbidez(turbidez_ntu),
        "solidos_totais": q_solidos_totais(solidos_totais_mg_l),
    }

    iqa = 1.0
    for chave, peso in PESOS.items():
        iqa *= qs[chave] ** peso
    return iqa
