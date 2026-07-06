"""Ingestão Bronze dos relatórios DAEE de chuva (RELATORIO DE CONSULTA DE ALTURAS MENSAIS).

Cada arquivo .xlsx contém, por posto pluviométrico, uma matriz ANO x MÊS
(JAN..DEZ) de alturas de chuva mensais (mm), com o mesmo bloco de metadados
de cabeçalho dos relatórios de vazão. Aqui já convertemos a matriz larga em
série longa (ano, mes) — é uma transposição mecânica, não uma decisão de
limpeza/negócio, então cabe em Bronze (mantendo o valor exatamente como
está na fonte).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from waterweave.config import BRONZE_DIR, FONTE_TIPO_OBSERVADO, MESES_PT, RAW_SOURCES
from waterweave.io_delta import write_table
from waterweave.ingestion._daee_common import linhas_de_proveniencia, listar_arquivos, parse_cabecalho_daee

logger = logging.getLogger(__name__)


def parse_matriz_mensal(path: Path) -> pd.DataFrame:
    """Converte a matriz ANO x MÊS (a partir da linha 8 do arquivo bruto) em formato longo (ano, mes, altura_mm)."""
    tabela = pd.read_excel(path, skiprows=8)
    tabela = tabela.rename(columns={"ANO": "ano"})
    tabela["ano"] = pd.to_numeric(tabela["ano"], errors="coerce")
    tabela = tabela.dropna(subset=["ano"])
    meses_presentes = [m for m in MESES_PT if m in tabela.columns]
    longo = tabela.melt(id_vars=["ano"], value_vars=meses_presentes, var_name="mes_abrev", value_name="altura_mm")
    longo["altura_mm"] = pd.to_numeric(longo["altura_mm"], errors="coerce")
    longo = longo.dropna(subset=["altura_mm"])
    longo["mes"] = longo["mes_abrev"].map(MESES_PT)
    longo["ano"] = longo["ano"].astype(int)
    return longo.drop(columns=["mes_abrev"])


def parse_consolidado(path: Path) -> pd.DataFrame | None:
    """Formato alternativo já regular (Ano, Mês, Posto Pluviométrico, Município, Latitude, Longitude, Precipitação Mensal).

    Ver `bronze_daee_fluviometria.parse_consolidado` — mesma origem alternativa de consolidação.
    """
    try:
        tabela = pd.read_excel(path, sheet_name="Série Histórica")
    except ValueError:
        return None
    tabela = tabela.rename(
        columns={
            "Ano": "ano", "Mês": "mes_abrev", "Posto Pluviométrico": "codigo_posto",
            "Município": "municipio", "Latitude": "latitude", "Longitude": "longitude",
            "Precipitação Mensal (mm)": "altura_mm",
        }
    )
    obrigatorias = {"ano", "mes_abrev", "codigo_posto", "altura_mm"}
    if not obrigatorias.issubset(tabela.columns):
        return None
    tabela["mes"] = tabela["mes_abrev"].str.upper().map(MESES_PT)
    tabela["ano"] = tabela["ano"].astype(int)
    return tabela.dropna(subset=["altura_mm"]).drop(columns=["mes_abrev"])


def ingest_arquivo(path: Path, trecho_id: str) -> pd.DataFrame | None:
    """Ingere um único arquivo de posto; retorna None (com log) se o arquivo estiver malformado."""
    metadados = {"posto": None, "rio": None, "latitude_gms": None, "longitude_gms": None, "data_instalacao": None}
    try:
        metadados = parse_cabecalho_daee(path)
        longo = parse_matriz_mensal(path)
        formato = "daee_posto"
    except Exception:
        longo = pd.DataFrame()
    if longo.empty:
        longo = parse_consolidado(path)
        formato = "consolidado"
        if longo is None or longo.empty:
            logger.warning("Falha ao ler %s — arquivo pulado (nenhum formato reconhecido).", path.name)
            return None
    if formato == "daee_posto":
        longo["codigo_posto"] = metadados["posto"]
        longo["rio"] = metadados["rio"]
        longo["latitude_gms"] = metadados["latitude_gms"]
        longo["longitude_gms"] = metadados["longitude_gms"]
        longo["data_instalacao"] = metadados["data_instalacao"]
    longo["trecho_id"] = trecho_id
    for coluna, valores in linhas_de_proveniencia(len(longo), path, FONTE_TIPO_OBSERVADO).items():
        longo[coluna] = valores
    return longo


def ingest_trecho(trecho_id: str, pasta: Path) -> pd.DataFrame:
    """Percorre todos os .xlsx de um trecho e concatena em um único DataFrame Bronze."""
    partes = [ingest_arquivo(arquivo, trecho_id) for arquivo in listar_arquivos(pasta)]
    partes = [p for p in partes if p is not None]
    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)


def run(trechos: list[str] | None = None) -> pd.DataFrame:
    """Executa a ingestão Bronze de pluviometria para os trechos informados e grava em Delta."""
    trechos = trechos or list(RAW_SOURCES["pluviometria"].keys())
    partes = [ingest_trecho(trecho_id, RAW_SOURCES["pluviometria"][trecho_id]) for trecho_id in trechos]
    tabela = pd.concat([p for p in partes if not p.empty], ignore_index=True)
    write_table(BRONZE_DIR / "pluviometria", tabela, partition_by=["trecho_id"])
    logger.info("Bronze pluviometria: %d linhas de %d postos.", len(tabela), tabela["codigo_posto"].nunique())
    return tabela


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
