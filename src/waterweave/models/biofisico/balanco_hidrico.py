"""Modelo biofísico determinístico de balanço hídrico mensal (P = ET + Q + ΔS), simplificado.

Produz um ÍNDICE de escoamento (mm/mês equivalente), não uma vazão
absoluta em m³/s: estimar vazão absoluta exigiria a área de drenagem real
de cada trecho (delimitação de bacia via shapefile ANA/ottobacias — não
disponível neste projeto ainda). Em vez de inventar uma área aproximada e
apresentar uma vazão "de mentirinha" como se fosse calibrada, o índice é
combinado com a média histórica real (`gold.serie_temporal_trecho_mes`) em
`models.hybrid_bridge`, que converte a resposta relativa do balanço hídrico
em uma vazão simulada ancorada em magnitudes observadas.

Simplificações assumidas (documentadas para revisão futura):
  - Evapotranspiração potencial mensal fixa (`ET_POTENCIAL_MM`), por não
    haver série de temperatura na Gold atual — substituir por ETo real
    (Penman-Monteith com dado ERA5) quando o conector climático existir.
  - Recessão de vazão de base como reservatório linear simples.

ACHADO DE PESQUISA (2026-07, uso do solo real): `simular_passo_mensal` aceita `uso_solo` em
DUAS formas — `str | None` (classe de texto simulada, legado) ou `dict[str, float]`
(percentual de área por macro-categoria REAL do MapBiomas, ver
`models.biofisico.uso_solo.coeficiente_de_percentuais_reais`) — para o chamador poder migrar
gradualmente sem quebrar quem ainda passa a forma antiga. Hoje (2026-07) `models.abm.model`
ainda só passa a forma antiga (string simulada); religar o ABM à forma real exigiria trazer
`silver.uso_solo` para `gold.serie_temporal_trecho_mes`/`estado_inicial_abm`, que é um passo
de escopo maior — ver docstring de `models.biofisico.uso_solo` para o detalhe.
"""
from __future__ import annotations

from dataclasses import dataclass

from waterweave.models.biofisico.uso_solo import classe_para_coeficiente_escoamento, coeficiente_de_percentuais_reais

K_RECESSAO = 0.35  # fração do armazenamento que vira escoamento de base por mês
ET_POTENCIAL_MM = 90.0  # evapotranspiração potencial mensal aproximada (SP, clima tropical/subtropical úmido)


@dataclass
class EstadoHidrologico:
    trecho_id: str
    armazenamento_mm: float
    indice_escoamento_mm: float


def simular_passo_mensal(
    estado_anterior: EstadoHidrologico, precipitacao_mm: float, uso_solo: str | dict[str, float] | None
) -> EstadoHidrologico:
    """Avança o balanço hídrico em um passo mensal para um trecho.

    `uso_solo` aceita `str | None` (classe simulada, legado —
    `models.biofisico.uso_solo.classe_para_coeficiente_escoamento`) OU `dict[str, float]`
    (percentual real por macro-categoria MapBiomas —
    `models.biofisico.uso_solo.coeficiente_de_percentuais_reais`) — ver ACHADO DE PESQUISA na
    docstring do módulo.

    Retorna o novo estado com `indice_escoamento_mm` (escoamento direto +
    de base do mês) e `armazenamento_mm` atualizado.
    """
    coeficiente = (
        coeficiente_de_percentuais_reais(uso_solo) if isinstance(uso_solo, dict) else classe_para_coeficiente_escoamento(uso_solo)
    )
    escoamento_direto_mm = coeficiente * precipitacao_mm
    infiltracao_mm = precipitacao_mm - escoamento_direto_mm

    armazenamento_disponivel = estado_anterior.armazenamento_mm + infiltracao_mm
    et_real_mm = min(ET_POTENCIAL_MM, armazenamento_disponivel)
    armazenamento_pos_et = armazenamento_disponivel - et_real_mm

    escoamento_base_mm = K_RECESSAO * armazenamento_pos_et
    novo_armazenamento = armazenamento_pos_et - escoamento_base_mm

    indice_escoamento_mm = escoamento_direto_mm + escoamento_base_mm
    return EstadoHidrologico(
        trecho_id=estado_anterior.trecho_id,
        armazenamento_mm=novo_armazenamento,
        indice_escoamento_mm=indice_escoamento_mm,
    )


def estado_inicial(trecho_id: str, armazenamento_mm: float = 50.0) -> EstadoHidrologico:
    """Estado de partida neutro para iniciar uma simulação (ex.: um cenário do ABM)."""
    return EstadoHidrologico(trecho_id=trecho_id, armazenamento_mm=armazenamento_mm, indice_escoamento_mm=0.0)
