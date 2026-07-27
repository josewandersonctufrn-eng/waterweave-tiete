"""Camada de uso e cobertura do solo: converte classes de uso do solo em parâmetros biofísicos.

Coeficientes de escoamento (fração da precipitação que vira escoamento direto — lógica tipo
Curve Number, simplificada). Duas fontes de uso do solo coexistem hoje, e cada uma tem sua
própria função de conversão para coeficiente:

  - `classe_para_coeficiente_escoamento` (legado): classes de TEXTO LIVRE simuladas, que
    aparecem em `silver.qualidade` (coluna `uso_solo`) — é o que `models.abm.model` ainda
    alimenta em `models.hybrid_bridge`/`balanco_hidrico.simular_passo_mensal` hoje (ver ACHADO
    DE PESQUISA abaixo: a ligação ao dado REAL ainda não foi feita nesse ponto específico).
  - `coeficiente_de_percentuais_reais` (2026-07): percentual de área por MACRO-CATEGORIA real
    do MapBiomas (`transform.gold_features.COLUNAS_USO_SOLO` — `pct_natural`/
    `pct_agropecuaria`/`pct_urbano_industrial`/`pct_agua`), já usado como preditora do ML (ver
    `models.ml.features`). `balanco_hidrico.simular_passo_mensal` aceita as DUAS formas (ver
    docstring daquele módulo) — string legada ou dict de percentuais — mas nenhum chamador
    real (`models.abm.model`) foi migrado para passar o dict ainda: isso exigiria trazer
    `silver.uso_solo` para dentro de `gold.serie_temporal_trecho_mes`/`estado_inicial_abm`,
    que hoje só carregam a coluna `uso_solo` de texto simulado — mudança de escopo maior,
    fora deste commit, documentada aqui para o próximo passo.

ACHADO DE PESQUISA (2026-07, mesmo racional do ACHADO em `transform.gold_features`): os
coeficientes por macro-categoria abaixo (`_COEFICIENTE_POR_MACRO_CATEGORIA`) são uma média
aproximada dos coeficientes por classe fina já usados no dicionário legado — não uma
calibração nova. Refinar isso com literatura específica de Curve Number por classe MapBiomas é
um passo de qualidade futuro, não bloqueante para o dado começar a fluir.
"""
from __future__ import annotations

_COEFICIENTE_POR_CLASSE = {
    "Agrícola / Vegetação Natural": 0.20,
    "Pecuária e Vegetação": 0.25,
    "Agrícola Tradicional": 0.35,
    "Hidrovia e Agropecuária": 0.35,
    "Agroindustrial (Cana / Citros)": 0.45,
    "Metropolitano / Industrial": 0.70,
    "Urbano Intenso / Industrial": 0.80,
}

_COEFICIENTE_PADRAO = 0.35  # fallback para classes não catalogadas


def classe_para_coeficiente_escoamento(classe_uso_solo: str | None) -> float:
    """Retorna o coeficiente de escoamento superficial associado à classe de uso do solo
    (fonte simulada, texto livre — ver docstring do módulo para a fonte real)."""
    if classe_uso_solo is None:
        return _COEFICIENTE_PADRAO
    return _COEFICIENTE_POR_CLASSE.get(classe_uso_solo, _COEFICIENTE_PADRAO)


# Coeficiente por macro-categoria REAL do MapBiomas — aproximadamente a média dos coeficientes
# por classe fina já usados acima (ver ACHADO DE PESQUISA na docstring do módulo).
# "agua": praticamente toda precipitação sobre o espelho d'água conta como "escoamento" no
# sentido deste balanço simplificado (não infiltra) — por isso o coeficiente mais alto do mapa,
# não porque a água "escoa mais rápido" no sentido hidrológico usual.
_COEFICIENTE_POR_MACRO_CATEGORIA: dict[str, float] = {
    "natural": 0.20,
    "agropecuaria": 0.35,
    "urbano_industrial": 0.75,
    "agua": 0.95,
    "nao_vegetado_outro": _COEFICIENTE_PADRAO,
    "nao_observado": _COEFICIENTE_PADRAO,
}


def coeficiente_de_percentuais_reais(percentuais: dict[str, float]) -> float:
    """Coeficiente de escoamento ponderado pelo percentual de área de cada macro-categoria
    REAL (MapBiomas) — ver ACHADO DE PESQUISA na docstring do módulo.

    `percentuais`: dict com chaves como `transform.gold_features.COLUNAS_USO_SOLO`
    (`pct_natural`, `pct_agropecuaria`, `pct_urbano_industrial`, `pct_agua`, prefixo `pct_`
    opcional — aceita tanto `{"natural": 50.0, ...}` quanto `{"pct_natural": 50.0, ...}`) e
    valores em PERCENTUAL (0-100, não fração 0-1) — mesma unidade de `silver.uso_solo`.

    Retorna `_COEFICIENTE_PADRAO` se `percentuais` estiver vazio ou todos os valores forem
    nulos/zero (ex.: trecho/ano sem cobertura MapBiomas e fora da janela de imputação de
    `transform.gold_features._LIMITE_PREENCHIMENTO_USO_SOLO_ANOS`) — nunca lança exceção por
    dado faltante, no mesmo espírito de `classe_para_coeficiente_escoamento(None)`."""
    normalizado = {chave.removeprefix("pct_"): valor for chave, valor in percentuais.items() if valor is not None}
    total = sum(v for v in normalizado.values() if v == v)  # `v == v` descarta NaN sem precisar de pandas/math aqui
    if not normalizado or not total:
        return _COEFICIENTE_PADRAO

    soma_ponderada = sum(
        valor * _COEFICIENTE_POR_MACRO_CATEGORIA.get(categoria, _COEFICIENTE_PADRAO)
        for categoria, valor in normalizado.items()
        if valor == valor
    )
    return soma_ponderada / total
