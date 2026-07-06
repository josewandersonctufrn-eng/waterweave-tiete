"""Ingestão Bronze dos relatórios DAEE de vazão (RELATORIO DE RESUMO DE MEDIÇÃO DE VAZÃO).

Cada arquivo .xlsx contém, por posto fluviométrico:
  - Linhas 0-6: cabeçalho de metadados (POSTO, RIO, LATITUDE/LONGITUDE em GMS,
    DATA DE INSTALACAO, EMISSAO).
  - A partir da linha 7: tabela de medições pontuais de vazão (DATA, HORA
    INICIAL, HORA FINAL, COTA INICIAL, COTA FINAL, VAZÃO m³/s, ÁREA m²).

Esta é uma série de EVENTOS de medição (não um passo de tempo regular) — a
regularização mensal/diária acontece na camada Silver.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from waterweave.config import BRONZE_DIR, FONTE_TIPO_OBSERVADO, MESES_PT, RAW_SOURCES
from waterweave.io_delta import write_table
from waterweave.ingestion._daee_common import linhas_de_proveniencia, listar_arquivos, parse_cabecalho_daee

logger = logging.getLogger(__name__)

_COLUNAS_TABELA = {
    "DATA": "data",
    "COTA INICIAL (m)": "cota_inicial_m",
    "COTA FINAL (m)": "cota_final_m",
    "VAZÃO (m³/s)": "vazao_m3s",
    "ÁREA (m²)": "area_m2",
}


def parse_medicoes(path: Path) -> pd.DataFrame:
    """Extrai a tabela de medições de vazão (a partir da linha 7 do arquivo bruto, formato DAEE por posto)."""
    tabela = pd.read_excel(path, skiprows=7)
    tabela = tabela.rename(columns=_COLUNAS_TABELA)
    colunas_presentes = [c for c in _COLUNAS_TABELA.values() if c in tabela.columns]
    tabela = tabela[colunas_presentes].dropna(subset=["data", "vazao_m3s"])
    tabela["data"] = pd.to_datetime(tabela["data"], errors="coerce")
    return tabela.dropna(subset=["data"])


def parse_consolidado(path: Path) -> pd.DataFrame | None:
    """Formato alternativo já regular (Ano, Mês, Estação, Município, Latitude, Longitude, Vazão Média m³/s).

    Alguns arquivos (ex.: `dados_fluviometricos_*.xlsx`) vêm de uma
    consolidação diferente da exportação padrão DAEE por posto — já em
    granularidade mensal e com coordenadas decimais prontas.
    """
    try:
        tabela = pd.read_excel(path, sheet_name="Série Histórica")
    except ValueError:
        return None
    tabela = tabela.rename(
        columns={
            "Ano": "ano", "Mês": "mes_abrev", "Estação": "codigo_posto",
            "Município": "municipio", "Latitude": "latitude", "Longitude": "longitude",
            "Vazão Média (m³/s)": "vazao_m3s", "Nível Médio (cm)": "nivel_medio_cm",
        }
    )
    obrigatorias = {"ano", "mes_abrev", "codigo_posto", "vazao_m3s"}
    if not obrigatorias.issubset(tabela.columns):
        return None
    tabela["mes"] = tabela["mes_abrev"].str.upper().map(MESES_PT)
    tabela["data"] = pd.to_datetime(dict(year=tabela["ano"], month=tabela["mes"], day=1), errors="coerce")
    return tabela.dropna(subset=["data", "vazao_m3s"]).drop(columns=["mes_abrev"])


def ingest_arquivo(path: Path, trecho_id: str) -> pd.DataFrame | None:
    """Ingere um único arquivo de posto; retorna None (com log) se o arquivo estiver malformado."""
    metadados = {"posto": None, "rio": None, "latitude_gms": None, "longitude_gms": None, "data_instalacao": None}
    try:
        metadados = parse_cabecalho_daee(path)
        medicoes = parse_medicoes(path)
        formato = "daee_posto"
    except Exception:
        medicoes = pd.DataFrame()
    if medicoes.empty:
        medicoes = parse_consolidado(path)
        formato = "consolidado"
        if medicoes is None or medicoes.empty:
            logger.warning("Falha ao ler %s — arquivo pulado (nenhum formato reconhecido).", path.name)
            return None
    if formato == "daee_posto":
        medicoes["codigo_posto"] = metadados["posto"]
        medicoes["rio"] = metadados["rio"]
        medicoes["latitude_gms"] = metadados["latitude_gms"]
        medicoes["longitude_gms"] = metadados["longitude_gms"]
        medicoes["data_instalacao"] = metadados["data_instalacao"]
    medicoes["trecho_id"] = trecho_id
    for coluna, valores in linhas_de_proveniencia(len(medicoes), path, FONTE_TIPO_OBSERVADO).items():
        medicoes[coluna] = valores
    return medicoes


def ingest_trecho(trecho_id: str, pasta: Path) -> pd.DataFrame:
    """Percorre todos os .xlsx de um trecho (Alto/Médio/Baixo) e concatena em um único DataFrame Bronze."""
    partes = [ingest_arquivo(arquivo, trecho_id) for arquivo in listar_arquivos(pasta)]
    partes = [p for p in partes if p is not None]
    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)


def run(trechos: list[str] | None = None) -> pd.DataFrame:
    """Executa a ingestão Bronze de fluviometria para os trechos informados (default: todos) e grava em Delta."""
    trechos = trechos or list(RAW_SOURCES["fluviometria"].keys())
    partes = [ingest_trecho(trecho_id, RAW_SOURCES["fluviometria"][trecho_id]) for trecho_id in trechos]
    tabela = pd.concat([p for p in partes if not p.empty], ignore_index=True)
    write_table(BRONZE_DIR / "fluviometria", tabela, partition_by=["trecho_id"])
    logger.info("Bronze fluviometria: %d linhas de %d postos.", len(tabela), tabela["codigo_posto"].nunique())
    return tabela


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
