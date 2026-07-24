"""Silver de qualidade da água a partir da CETESB real (`bronze.cetesb`).

Pivota o formato EAV de `bronze.cetesb` (uma linha por CodPonto x Data x
Parametro) para o MESMO schema largo de `silver.qualidade` (hoje alimentado
pela planilha simulada) — trecho_id, ano, uso_solo, iqa, dbo_mg_l, od_mg_l,
metais_pesados_ppm, pesticidas_ppm, materia_organica_pct, fonte_tipo —
agregando por (trecho_id, ano) para bater com a granularidade anual já usada
no resto do pipeline (`gold_features.build_serie_temporal_trecho_mes`).

Reaproveita `silver.estacoes` para o filtro do eixo do Tietê (não reimplementa
a classificação por trecho): o merge por codigo_ponto já restringe aos 32
pontos do eixo, porque `silver.estacoes` só tem esses 32
(`silver_estacoes.build_silver_estacoes`).

Limitações desta primeira versão (documentadas, não escondidas):
  - `uso_solo`, `pesticidas_ppm` e `materia_organica_pct` continuam nulos —
    a CETESB não mede uso do solo nem matéria orgânica de sedimento na coluna
    d'água, e a cobertura de agrotóxicos individuais é esparsa demais para um
    composto confiável nesta rodada. `gold_features` já tolera nulos nessas
    colunas (ver `gold.feature_store_ml`), então isso não quebra o pipeline —
    só significa que, para essas 3 colunas específicas, o fallback simulado
    de `silver.qualidade` continua sendo a única fonte disponível.
  - `iqa` é um proxy simplificado a partir de OD/DBO reais — MESMA
    simplificação já documentada no projeto (`webapp/i18n.py`, chaves
    `cn.nota`/`rel.nota_proveniencia`: "IQA é um proxy simplificado de
    OD/DBO, não o índice oficial CETESB de 9 parâmetros"), agora alimentada
    por medições reais em vez de série simulada.
"""
from __future__ import annotations

import pandas as pd

from waterweave.config import BRONZE_DIR, FONTE_TIPO_OBSERVADO, SILVER_DIR
from waterweave.io_delta import read_table, write_table

# Parametro (nome exato na fonte CETESB) -> coluna larga de saída.
_PARAMETROS_DIRETOS = {
    "Oxigênio Dissolvido": "od_mg_l",
    "DBO (5, 20)": "dbo_mg_l",
}

# 6 metais pesados reais somados (mg/L ~ ppm em solução aquosa diluída) para compor
# metais_pesados_ppm — substitui o "julgamento documentado" usado no proxy simulado
# (`parametros_estendidos.ANCORA_METAIS_TOXICOS_INDICE`) por uma soma de concentrações
# reais medidas. Cobertura real no eixo do Tietê (1978-2024): 2.374 a 3.428 medições
# por metal — boa o bastante para uma média anual por trecho.
_METAIS_PESADOS = ("Chumbo Total", "Cádmio Total", "Mercúrio Total", "Níquel Total", "Crômio Total", "Zinco Total")


def _aplicar_censura(bronze: pd.DataFrame) -> pd.DataFrame:
    """Trata a coluna Sinal (censura analítica): '<' = resultado abaixo do limite de
    detecção — convenção padrão em química analítica é usar metade do valor reportado
    (que, nesses casos, é o próprio limite de detecção do método); '>' = resultado acima
    da faixa medida pelo método — mantém o valor como limite inferior conhecido, sem
    ajuste (subestimar levemente é mais seguro do que inflar arbitrariamente)."""
    bronze = bronze.copy()
    abaixo_do_limite = bronze["sinal_censura"] == "<"
    bronze.loc[abaixo_do_limite, "resultado_numerico"] = bronze.loc[abaixo_do_limite, "resultado_numerico"] / 2.0
    return bronze


def _media_anual_por_trecho(bronze_tiete: pd.DataFrame, nome_parametro: str) -> pd.Series:
    """Média anual por trecho de um único parâmetro, já filtrado ao eixo do Tietê e com
    censura analítica tratada. Índice: (trecho_id, ano)."""
    sub = bronze_tiete[bronze_tiete["parametro"] == nome_parametro]
    return sub.groupby(["trecho_id", "ano"])["resultado_numerico"].mean()


def build_silver_qualidade_cetesb() -> pd.DataFrame:
    """Constrói a série anual REAL de qualidade da água (CETESB) por trecho do Rio Tietê."""
    bronze = read_table(BRONZE_DIR / "cetesb")
    estacoes_tiete = read_table(SILVER_DIR / "estacoes")[["codigo_posto", "trecho_id"]]

    bronze_tiete = bronze.merge(estacoes_tiete, left_on="codigo_ponto", right_on="codigo_posto", how="inner")
    bronze_tiete = _aplicar_censura(bronze_tiete)
    bronze_tiete["ano"] = bronze_tiete["data"].dt.year

    colunas: dict[str, pd.Series] = {}
    for nome_parametro, coluna in _PARAMETROS_DIRETOS.items():
        colunas[coluna] = _media_anual_por_trecho(bronze_tiete, nome_parametro)

    metais_por_composto = [_media_anual_por_trecho(bronze_tiete, p) for p in _METAIS_PESADOS]
    colunas["metais_pesados_ppm"] = pd.concat(metais_por_composto, axis=1).sum(axis=1, min_count=1)

    tabela = pd.DataFrame(colunas).reset_index()

    # IQA: proxy simplificado a partir de OD/DBO reais (ver docstring do módulo). Escalas de
    # referência: OD/8mg/L (mesma convenção já usada em
    # `parametros_estendidos.simular_parametros_estendidos` para od_normalizado) e
    # DBO/10mg/L (limite CONAMA 357/2005 Classe 3) — escolha de engenharia documentada,
    # não o cálculo oficial NSF-WQI de 9 parâmetros (que usa curvas de peso não lineares).
    od_normalizado = (tabela["od_mg_l"] / 8.0 * 100).clip(lower=0, upper=100)
    dbo_normalizado = (100 - tabela["dbo_mg_l"] / 10.0 * 100).clip(lower=0, upper=100)
    tabela["iqa"] = 0.6 * od_normalizado + 0.4 * dbo_normalizado

    # `pd.NA`/`None` puro faz o pyarrow inferir tipo Null (Delta Lake nao aceita) --
    # precisamos de um dtype concreto mesmo estando 100% vazio nesta rodada (ver
    # limitacoes documentadas no topo do modulo).
    tabela["uso_solo"] = pd.Series([pd.NA] * len(tabela), dtype="string")
    tabela["pesticidas_ppm"] = float("nan")
    tabela["materia_organica_pct"] = float("nan")
    tabela["fonte_tipo"] = FONTE_TIPO_OBSERVADO

    colunas_finais = [
        "trecho_id", "ano", "uso_solo", "iqa", "dbo_mg_l", "od_mg_l",
        "metais_pesados_ppm", "pesticidas_ppm", "materia_organica_pct", "fonte_tipo",
    ]
    tabela = tabela[colunas_finais].dropna(subset=["iqa"]).sort_values(["trecho_id", "ano"]).reset_index(drop=True)
    write_table(SILVER_DIR / "qualidade_cetesb", tabela, partition_by=["trecho_id"])
    return tabela


if __name__ == "__main__":
    build_silver_qualidade_cetesb()
