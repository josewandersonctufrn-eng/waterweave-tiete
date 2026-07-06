"""Silver da dimensão de estações: filtra o cadastro estadual (`bronze.estacoes`,
699 pontos em todas as bacias de SP) para o eixo do Rio Tietê e classifica
cada uma em um trecho (Alto/Médio/Baixo) a partir do código UGRHI da bacia.

Este filtro + classificação é regra de negócio (não transposição mecânica),
por isso vive na Silver e não na Bronze.
"""
from __future__ import annotations

import pandas as pd

from waterweave.config import BRONZE_DIR, SILVER_DIR
from waterweave.io_delta import read_table, write_table


def _ugrhi_para_trecho(ugrhi: str) -> str | None:
    u = str(ugrhi).upper()
    if "ALTO TI" in u:
        return "alto_tiete"
    if "BAIXO TI" in u:
        return "baixo_tiete"
    if "MEDIO TIETE" in u or "JACAR" in u or "BATALHA" in u or "SOROCABA" in u:
        return "medio_tiete"
    return None


def build_silver_estacoes() -> pd.DataFrame:
    """Filtra as estações sobre o eixo do Tietê e grava a dimensão Silver."""
    bronze = read_table(BRONZE_DIR / "estacoes")
    mascara = bronze["CodPonto"].astype(str).str.startswith(("TIET", "TIBT"))
    tabela = bronze.loc[mascara].copy()
    tabela["trecho_id"] = tabela["UGRHI"].apply(_ugrhi_para_trecho)
    tabela = tabela.dropna(subset=["trecho_id", "LongDecml", "LattDecml"])
    tabela = tabela.rename(
        columns={
            "CodPonto": "codigo_posto",
            "SistHidrico": "corpo_hidrico",
            "Municipio": "municipio",
            "Classe": "classe_uso",
            "LongDecml": "longitude",
            "LattDecml": "latitude",
        }
    )[["codigo_posto", "corpo_hidrico", "municipio", "classe_uso", "longitude", "latitude", "trecho_id"]]
    write_table(SILVER_DIR / "estacoes", tabela)
    return tabela


if __name__ == "__main__":
    build_silver_estacoes()
