"""Leitura/escrita de tabelas Delta Lake usadas por Bronze, Silver e Gold.

Usa `deltalake` (bindings Python do delta-rs) em vez de PySpark: mesmo
formato de tabela (log de transações, ACID, schema), sem exigir JVM/Hadoop —
adequado para rodar o pipeline inteiro em uma única máquina Windows. Se o
projeto crescer para processamento distribuído, o mesmo diretório de tabelas
Delta pode ser lido por um cluster Spark real sem migração de dado.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from deltalake import DeltaTable, write_deltalake


def write_table(path: Path, df: pd.DataFrame, *, mode: str = "overwrite", partition_by: list[str] | None = None) -> None:
    """Grava (ou substitui) uma tabela Delta em `path`.

    Para `mode="overwrite"`, `schema_mode="overwrite"` permite que o schema
    evolua entre execuções (ex.: um novo formato de arquivo trazendo colunas
    extras) — o job mensal reprocessa a fonte inteira a cada rodada (ver
    `monthly_job`), então não faz sentido travar nesse caso. Para
    `mode="append"`, `schema_mode="merge"` permite unir colunas de uma fonte
    com schema diferente (ex.: conector ANA anexado a um Bronze DAEE) sem
    forçar as duas fontes a terem exatamente as mesmas colunas.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    schema_mode = {"overwrite": "overwrite", "append": "merge"}.get(mode)
    write_deltalake(str(path), df, mode=mode, partition_by=partition_by, schema_mode=schema_mode)


def read_table(path: Path) -> pd.DataFrame:
    """Lê uma tabela Delta em `path`; retorna DataFrame vazio se a tabela ainda não existe."""
    try:
        return DeltaTable(str(path)).to_pandas()
    except Exception:
        return pd.DataFrame()
