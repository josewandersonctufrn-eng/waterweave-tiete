"""Silver de uso do solo real: agrega `bronze.uso_solo` (área por classe MapBiomas) em
percentuais por macro-categoria, uma linha por (trecho, ano).

Substitui, para os anos com cobertura MapBiomas (1985-2023), o campo `uso_solo` de texto
livre simulado em `silver.qualidade` (ex.: "Metropolitano/Industrial") por um percentual real
e quantitativo de área — ver `ingestion.bronze_uso_solo`/`ingestion.connectors.mapbiomas` para
a proveniência e as limitações (buffer de 5 km ao redor das estações, não uma bacia
hidrográfica real). Ainda NÃO está plugada em `transform.gold_features`/`models.ml` como
preditora — esta é a camada Silver isolada; integrá-la ao feature store de ML é uma decisão
separada (ver Seção 25 do relatório de EDA sobre a lacuna que este módulo fecha)."""
from __future__ import annotations

import pandas as pd

from waterweave.config import BRONZE_DIR, SILVER_DIR
from waterweave.io_delta import read_table, write_table

MACRO_CATEGORIAS = ["natural", "agropecuaria", "urbano_industrial", "agua", "nao_vegetado_outro", "nao_observado"]


def build_silver_uso_solo() -> pd.DataFrame:
    """Pivota `bronze.uso_solo` (uma linha por trecho/ano/classe) em percentual de área por
    macro-categoria, uma linha por (trecho, ano)."""
    bronze = read_table(BRONZE_DIR / "uso_solo")

    total_por_trecho_ano = bronze.groupby(["trecho_id", "ano"])["area_m2"].transform("sum")
    bronze = bronze.assign(pct_area=bronze["area_m2"] / total_por_trecho_ano * 100)

    tabela = bronze.pivot_table(
        index=["trecho_id", "ano"], columns="macro_categoria", values="pct_area", aggfunc="sum", fill_value=0.0
    )
    for categoria in MACRO_CATEGORIAS:
        if categoria not in tabela.columns:
            tabela[categoria] = 0.0
    tabela = tabela[MACRO_CATEGORIAS].add_prefix("pct_").reset_index()

    tabela["fonte_tipo"] = "observado"
    tabela = tabela.sort_values(["trecho_id", "ano"]).reset_index(drop=True)
    write_table(SILVER_DIR / "uso_solo", tabela, partition_by=["trecho_id"])
    return tabela


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    df = build_silver_uso_solo()
    print(f"silver.uso_solo: {len(df)} linhas ({df['trecho_id'].nunique()} trechos)")
