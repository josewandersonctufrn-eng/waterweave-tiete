"""Utilidades compartilhadas pelos relatórios DAEE (fluviometria e pluviometria).

Ambos os relatórios (RESUMO DE MEDIÇÃO DE VAZÃO e CONSULTA DE ALTURAS
MENSAIS) compartilham o mesmo bloco de cabeçalho nas primeiras ~7 linhas:
POSTO, RIO, LATITUDE, LONGITUDE, DATA DE INSTALACAO — mas a formatação
exata (espaço antes do ":", coluna onde cada campo aparece) varia de
arquivo para arquivo, então o parser varre todas as células em vez de
assumir posições fixas.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pandas as pd

_HEADER_KEYS = {
    "POSTO": "posto",
    "RIO": "rio",
    "LATITUDE": "latitude_gms",
    "LONGITUDE": "longitude_gms",
    "DATA DE INSTALACAO": "data_instalacao",
}


def listar_arquivos(pasta: Path) -> list[Path]:
    return sorted(pasta.glob("*.xlsx"))


def parse_cabecalho_daee(path: Path) -> dict:
    """Varre as primeiras linhas do relatório em busca dos campos de metadados do posto."""
    bruto = pd.read_excel(path, header=None, nrows=7)
    metadados: dict[str, str | None] = {v: None for v in _HEADER_KEYS.values()}
    for valor in bruto.values.flatten():
        if not isinstance(valor, str) or ":" not in valor:
            continue
        chave_bruta, _, resto = valor.partition(":")
        chave = chave_bruta.strip().upper()
        if chave in _HEADER_KEYS:
            metadados[_HEADER_KEYS[chave]] = resto.strip()
    return metadados


def linhas_de_proveniencia(n_linhas: int, source_file: Path, fonte_tipo: str) -> dict:
    """Colunas técnicas de proveniência anexadas a toda tabela Bronze."""
    agora = _dt.datetime.now().isoformat(timespec="seconds")
    return {
        "_ingested_at": [agora] * n_linhas,
        "_source_file": [source_file.name] * n_linhas,
        "_fonte_tipo": [fonte_tipo] * n_linhas,
    }
