"""Submodelos simplificados para os parâmetros físicos/químicos/biológicos além de OD/DBO.

`qualidade_agua.simular_od_dbo` cobre apenas Streeter-Phelps clássico (OD/DBO).
Este módulo estende a simulação para os demais parâmetros que a análise de
poluição do Tietê identificou como relevantes (ver docs/Analise_Poluicao_Rio_Tiete.docx):

  Físicos:    Turbidez, Temperatura da Água, Sólidos Totais
  Químicos:   pH, Fósforo Total, Nitrogênio (amoniacal + nitrato)
  Biológicos: E. coli (sucessora de Coliformes Termotolerantes desde a
              CONAMA 430/2011 — mesmo indicador de contaminação fecal)

Cada parâmetro usa a MESMA lógica de ancoragem em dado real já empregada por
`hybrid_bridge.carga_base_trecho_kg_dia`: um valor-base é fixado a partir da
média real observada (CETESB, `base_de_dados_pontos.xlsx`, período 2012-2024,
extraída diretamente do arquivo bruto nesta sessão de análise — ver
docs/Analise_Poluicao_Rio_Tiete.docx, seção 8), e a simulação futura escala
esse valor pelos MESMOS fatores de decisão que os agentes do ABM já ajustam
(`fator_carga_industria`, `fator_carga_difusa`, `fator_outorga`) e pelo índice
de escoamento do balanço hídrico (para os parâmetros ligados a erosão/sedimento).

IMPORTANTE — nível de simplificação: assim como o Streeter-Phelps e o balanço
hídrico do restante do projeto, estas são relações simplificadas de literatura
combinadas com um único ponto de ancoragem real, NÃO modelos calibrados com
série temporal completa (o projeto ainda não ingeriu `base_de_dados_pontos.xlsx`
formalmente no pipeline — ver "Próximos passos" do README). pH e Temperatura
não seguem diluição de massa simples (não são cargas em kg/dia); usam uma
resposta proporcional documentada em cada função.
"""
from __future__ import annotations

from dataclasses import dataclass

# Médias reais 2012-2024 por trecho, extraídas de `base_de_dados_pontos.xlsx`
# (CETESB, pontos do eixo principal do Tietê) — ver docs/Analise_Poluicao_Rio_Tiete.docx.
ANCORA_TURBIDEZ_NTU = {"alto_tiete": 33.14, "medio_tiete": 32.06, "baixo_tiete": 3.50}
ANCORA_SOLIDOS_TOTAIS_MG_L = {"alto_tiete": 309.79, "medio_tiete": 251.93, "baixo_tiete": 127.60}
ANCORA_TEMPERATURA_C = {"alto_tiete": 22.07, "medio_tiete": 24.24, "baixo_tiete": 25.19}
ANCORA_PH = {"alto_tiete": 6.93, "medio_tiete": 7.32, "baixo_tiete": 7.62}
ANCORA_FOSFORO_MG_L = {"alto_tiete": 1.08, "medio_tiete": 0.76, "baixo_tiete": 0.02}
ANCORA_NITROGENIO_MG_L = {"alto_tiete": 9.44, "medio_tiete": 9.53, "baixo_tiete": 0.80}  # amoniacal + nitrato
ANCORA_ECOLI_NMP_100ML = {"alto_tiete": 1_091_191.0, "medio_tiete": 17_395.0, "baixo_tiete": 6.8}

# Fração da carga de nutrientes/patógenos atribuída a fonte industrial/doméstica
# (esgoto) vs. difusa/agrícola (fertilizante) — mesma lógica de
# `hybrid_bridge.FRACAO_CARGA_INDUSTRIAL/DIFUSA`, com pesos ajustados: E. coli é
# quase inteiramente esgoto; Nitrogênio é mais equilibrado (esgoto + fertilizante).
FRACAO_INDUSTRIAL_ECOLI = 0.95
FRACAO_DIFUSA_ECOLI = 0.05
FRACAO_INDUSTRIAL_NUTRIENTE = 0.45
FRACAO_DIFUSA_NUTRIENTE = 0.55

INDICE_ESCOAMENTO_REFERENCIA_MM = 90.0  # ~ET_POTENCIAL_MM do balanço hídrico, usado só como escala


@dataclass
class ParametrosEstendidos:
    turbidez_ntu: float
    solidos_totais_mg_l: float
    temperatura_c: float
    ph: float
    fosforo_mg_l: float
    nitrogenio_mg_l: float
    e_coli_nmp_100ml: float


def carga_base_kg_dia(ancora_concentracao_mg_l: float, vazao_media_historica_m3s: float) -> float:
    """Back-calcula uma carga-base (kg/dia) a partir de uma concentração-âncora real e da vazão média
    histórica do trecho — mesmo procedimento de `hybrid_bridge.carga_base_trecho_kg_dia`, generalizado
    para qualquer parâmetro que se comporte como massa diluída (Fósforo, Nitrogênio, E. coli-equivalente).
    """
    return ancora_concentracao_mg_l * max(vazao_media_historica_m3s, 0.01) * 86.4


def _diluir(carga_base_kg_dia_: float, fator_carga: float, vazao_diluicao_m3s: float) -> float:
    """Mesma fórmula de diluição de `qualidade_agua`/`hybrid_bridge`: kg/dia -> concentração (mg/L ou análogo)."""
    vazao = max(vazao_diluicao_m3s, 0.01)
    return (carga_base_kg_dia_ * fator_carga * 1_000_000) / (vazao * 86_400 * 1000)


def simular_parametros_estendidos(
    trecho_id: str,
    fator_carga_industria: float,
    fator_carga_difusa: float,
    vazao_diluicao_m3s: float,
    indice_escoamento_mm: float,
    dbo_simulado_mg_l: float,
    fator_clima: float,
    carga_base_fosforo_kg_dia: float,
    carga_base_nitrogenio_kg_dia: float,
    carga_base_ecoli_kg_dia: float,
) -> ParametrosEstendidos:
    """Deriva os parâmetros físicos/químicos/biológicos adicionais para o passo mensal corrente.

    `carga_base_*_kg_dia` já vêm back-calculados (via `carga_base_kg_dia`) da
    concentração-âncora real × vazão média histórica do trecho — calculados uma
    vez em `hybrid_bridge` (cache) e passados prontos aqui, seguindo o mesmo
    padrão de `carga_base_trecho_kg_dia`.
    """
    fator_nutriente = FRACAO_INDUSTRIAL_NUTRIENTE * fator_carga_industria + FRACAO_DIFUSA_NUTRIENTE * fator_carga_difusa
    fator_ecoli = FRACAO_INDUSTRIAL_ECOLI * fator_carga_industria + FRACAO_DIFUSA_ECOLI * fator_carga_difusa

    fosforo = _diluir(carga_base_fosforo_kg_dia, fator_nutriente, vazao_diluicao_m3s)
    nitrogenio = _diluir(carga_base_nitrogenio_kg_dia, fator_nutriente, vazao_diluicao_m3s)
    e_coli = _diluir(carga_base_ecoli_kg_dia, fator_ecoli, vazao_diluicao_m3s)

    # Turbidez e sólidos totais: ligados a erosão/sedimento (carga difusa +
    # intensidade do escoamento do mês) e a matéria orgânica em suspensão (DBO).
    intensidade_escoamento = indice_escoamento_mm / INDICE_ESCOAMENTO_REFERENCIA_MM
    turbidez = ANCORA_TURBIDEZ_NTU[trecho_id] * fator_carga_difusa * (0.4 + 0.6 * intensidade_escoamento)
    solidos_totais = ANCORA_SOLIDOS_TOTAIS_MG_L[trecho_id] * (
        0.5 * fator_carga_industria + 0.5 * fator_carga_difusa * (0.4 + 0.6 * intensidade_escoamento)
    )

    # pH: depressão proporcional ao excesso de carga industrial e à DBO (ácidos
    # orgânicos da decomposição), puxando de volta a neutro (7,2) quando a carga cai.
    ph_base = ANCORA_PH[trecho_id]
    ph = 7.2 - (7.2 - ph_base) * fator_carga_industria - 0.01 * max(0.0, dbo_simulado_mg_l - 5.0)
    ph = max(6.0, min(8.5, ph))

    # Temperatura: não é controlada pelas alavancas de gestão da bacia — reflete
    # apenas o cenário climático (mais seco/quente com `fator_clima` menor).
    temperatura = ANCORA_TEMPERATURA_C[trecho_id] + 3.0 * (1.0 - fator_clima)

    return ParametrosEstendidos(
        turbidez_ntu=turbidez,
        solidos_totais_mg_l=solidos_totais,
        temperatura_c=temperatura,
        ph=ph,
        fosforo_mg_l=fosforo,
        nitrogenio_mg_l=nitrogenio,
        e_coli_nmp_100ml=e_coli,
    )
