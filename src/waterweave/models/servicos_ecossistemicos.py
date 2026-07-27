"""Indicadores de SERVIÇOS ECOSSISTÊMICOS do Rio Tietê — item 5 do roadmap de pesquisa
WaterWeave-Water4All.

ACHADO DE PESQUISA (2026-07): a pesquisa de pós-doutorado fala em "extrair relações entre o
estado dos ecossistemas e a PROVISÃO DE SERVIÇOS ECOSSISTÊMICOS", não só em qualidade da água
isolada. Até esta correção, o pipeline produzia vários indicadores de estado do ecossistema
(IQA, vazão, índice biótico, uso do solo real, sensoriamento remoto...) mas nenhum deles tinha
sido formalizado como SERVIÇO — a diferença importa: "estado" descreve o rio, "serviço" descreve
o BENEFÍCIO que esse estado entrega a quem depende dele (abastecimento, saúde pública,
biodiversidade), que é o que interessa para um exercício de gestão com stakeholders.

Decisão (usuário, 2026-07): formalizar os 3 serviços a seguir, SEPARADOS (não um índice
composto único) — para não esconder trade-offs entre eles nas telas de cenário:

  1. `regulacao_qualidade_agua`: capacidade do rio de se autodepurar/diluir poluição, a partir
     do IQA já calculado em todo o pipeline (real CETESB ou proxy simulado do ABM).
  2. `provisao_hidrica`: capacidade de atender à demanda de captação de água a partir da vazão
     disponível.
  3. `suporte_biodiversidade`: capacidade de sustentar vida aquática sensível, a partir do
     índice biótico já usado no biofísico (`models.biofisico.parametros_estendidos.indice_biotico`).

Todos os 3 são reescalados para FRAÇÃO 0-1 ("quanto da capacidade máxima do serviço está sendo
entregue"), não um índice 0-100 arbitrário — isso deixa os 3 na mesma escala para comparação
lado a lado (ex.: um gráfico de radar/barras nas telas de cenário), sem precisar renormalizar.
Deliberadamente NÃO fazemos a média dos 3 num índice único aqui — ver decisão acima.

LIMITAÇÃO (cobertura histórica REAL): dos 3, só `regulacao_qualidade_agua` e `provisao_hidrica`
têm série histórica REAL longa disponível (`transform.gold_features.build_feature_store_ml_anual`,
IQA e vazão desde 1978/1940) — por isso só esses dois entram em
`transform.gold_features.build_servicos_ecossistemicos_historico` (nova tabela Gold
`servicos_ecossistemicos_trecho_ano`). `suporte_biodiversidade` depende de turbidez e de um
índice de toxicidade (`metais_toxicos_indice`) que hoje só existem no braço SIMULADO do
biofísico (`models.biofisico.parametros_estendidos`, ver `ANCORA_TURBIDEZ_NTU`/
`ANCORA_METAIS_TOXICOS_INDICE`) — a série real de qualidade da água (`silver.qualidade_cetesb`)
tem `metais_pesados_ppm` real, mas numa unidade/escala diferente do índice de toxicidade 0-100
usado aqui, e NÃO tem turbidez real como série histórica (a única fonte de turbidez real do
projeto é o sensoriamento remoto via Earth Engine, `ingestion.connectors.sensoriamento_historico`,
que nunca foi executado contra o Earth Engine de verdade — ver docstring daquele módulo).
Por isso `suporte_biodiversidade` só é calculado no contexto do ABM/"Cenários Futuros"
(`calcular_servicos_do_passo`), não como série histórica real — reconciliar essas duas fontes de
turbidez/toxicidade (ancorar o índice biótico simulado em dado real de metais + um proxy real de
turbidez) é uma extensão futura, não feita aqui.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from waterweave.models.biofisico.parametros_estendidos import indice_biotico as _formula_indice_biotico

if TYPE_CHECKING:
    from waterweave.models.hybrid_bridge import PassoHibrido


@dataclass(frozen=True)
class ServicosEcossistemicos:
    """Os 3 serviços, cada um em fração 0-1 (1.0 = capacidade máxima entregue). `suporte_biodiversidade`
    é `None` quando não computável (ver LIMITAÇÃO na docstring do módulo — histórico real, por
    exemplo, nunca preenche este campo)."""

    regulacao_qualidade_agua: float
    provisao_hidrica: float
    suporte_biodiversidade: float | None


def regulacao_qualidade_agua(iqa: float) -> float:
    """Fração 0-1 do serviço de regulação/purificação da água, a partir do IQA (0-100, real ou
    proxy simulado — ver `models.hybrid_bridge.iqa_proxy` e `silver.qualidade_cetesb`). Simples
    reescala linear: o IQA já É, por definição, uma nota de 0 a 100 da qualidade da água, então
    dividir por 100 já expressa "fração da qualidade máxima possível entregue" sem introduzir
    uma nova curva/ponderação."""
    if iqa is None or iqa != iqa:  # NaN
        return float("nan")
    return max(0.0, min(1.0, iqa / 100.0))


def provisao_hidrica(vazao_m3s: float, captacao_necessaria_m3s: float | None) -> float:
    """Fração 0-1 do serviço de provisão hídrica: quanto da necessidade de captação a vazão
    disponível consegue atender (capado em 1.0 — vazão excedente não conta como "mais serviço",
    só como folga). `captacao_necessaria_m3s` ausente/não-positiva é tratada como "sem
    necessidade conhecida para este trecho" -> serviço plenamente provido por definição (1.0),
    não por uma vazão infinita — evita `ZeroDivisionError`/`inf` silencioso quando o chamador
    não tiver esse dado."""
    if vazao_m3s is None or vazao_m3s != vazao_m3s:  # NaN
        return float("nan")
    if not captacao_necessaria_m3s or captacao_necessaria_m3s <= 0:
        return 1.0
    return max(0.0, min(1.0, vazao_m3s / captacao_necessaria_m3s))


def suporte_biodiversidade(od_mg_l: float, turbidez_ntu: float, metais_toxicos_indice: float) -> float:
    """Fração 0-1 do serviço de suporte à biodiversidade aquática — reaproveita a MESMA fórmula
    de `models.biofisico.parametros_estendidos.indice_biotico` (0-100, sem duplicar a lógica),
    convertida para fração. Ver LIMITAÇÃO na docstring do módulo: só computável onde
    turbidez/toxicidade estão disponíveis (hoje, só no braço simulado do biofísico)."""
    return _formula_indice_biotico(od_mg_l, turbidez_ntu, metais_toxicos_indice) / 100.0


def calcular_servicos_do_passo(passo: "PassoHibrido", captacao_necessaria_m3s: float | None) -> ServicosEcossistemicos:
    """Calcula os 3 serviços a partir de um `PassoHibrido` (saída de
    `models.hybrid_bridge.executar_passo`, usado pelo ABM/"Cenários Futuros") — único ponto que
    consegue calcular os 3, porque só o braço simulado do biofísico produz turbidez e índice de
    toxicidade junto com IQA e vazão no mesmo passo."""
    return ServicosEcossistemicos(
        regulacao_qualidade_agua=regulacao_qualidade_agua(passo.iqa_simulado),
        provisao_hidrica=provisao_hidrica(passo.vazao_simulada_m3s, captacao_necessaria_m3s),
        suporte_biodiversidade=suporte_biodiversidade(
            passo.od_simulado_mg_l, passo.turbidez_ntu, passo.metais_toxicos_indice
        ),
    )
