"""Ingestão Bronze de `base_de_dados_pontos.xlsx` (rede estadual de qualidade da água CETESB).

Fonte REAL (não simulada): 3 abas por período (1978_2005, 2006_2016, 2017_2024),
mesmo schema nas três — formato EAV (uma linha por medição pontual: CodPonto x
Coleta_Data x Parametro), não uma tabela larga. Bronze mantém o mirror completo
(699 pontos em todo o Estado de SP, ~2,4 milhões de medições, 1978-2024); o
filtro para o eixo do Rio Tietê, a pivotagem para colunas (od_mg_l, dbo_mg_l,
turbidez_ntu...) e o tratamento de censura analítica (coluna Sinal) são regra
de negócio e ficam em `transform.silver_qualidade_cetesb`.

ACHADO DE AUDITORIA (ver docs/Auditoria_Engenharia_Dados_WaterWeave_Tiete.docx):
esta fonte estava registrada em `RAW_SOURCES["pontos_consolidados"]` desde o
início do projeto, mas nenhum módulo bronze a lia — o pipeline rodava 100%
sobre a série simulada de `bronze_qualidade_solo`. Este módulo fecha essa
lacuna.
"""
from __future__ import annotations

import logging

import pandas as pd

from waterweave.config import BRONZE_DIR, FONTE_TIPO_OBSERVADO, RAW_SOURCES
from waterweave.io_delta import write_table
from waterweave.ingestion._daee_common import linhas_de_proveniencia

logger = logging.getLogger(__name__)

_ABAS = ("1978_2005", "2006_2016", "2017_2024")

_RENOMEIA = {
    "SEQID": "seq_id",  # NÃO é chave única de linha (só 699 valores distintos, um por ponto) — ver auditoria
    "TipoRede": "tipo_rede",
    "UGRHI": "ugrhi",
    "CodPonto": "codigo_ponto",
    "Coleta_Data": "data",
    "Coleta_Hora": "hora",
    "Parametro": "parametro",
    "Resultado_Texto": "resultado_texto",
    "Sinal": "sinal_censura",  # '<' = abaixo do limite de detecção, '>' = acima da faixa medida
    "Resultado_numerico": "resultado_numerico",
    "SiglaUniMedda": "unidade",
    "SistHidrico": "sist_hidrico",
    "Municipio": "municipio",
    "UF": "uf",
}


def run() -> pd.DataFrame:
    """Lê as 3 abas (períodos) de base_de_dados_pontos.xlsx e grava o mirror completo em Bronze."""
    caminho = RAW_SOURCES["pontos_consolidados"]
    partes = [pd.read_excel(caminho, sheet_name=aba) for aba in _ABAS]
    tabela = pd.concat(partes, ignore_index=True)
    tabela = tabela.rename(columns=_RENOMEIA)

    # Excel guarda Coleta_Hora como hora-do-dia -> pandas le como datetime.time -> pyarrow
    # infere Time64, tipo que o writer Rust do Delta Lake nao suporta ("Invalid data type
    # for Delta Lake: Time64(us)", erro real encontrado ao gravar). Guardamos como texto
    # "HH:MM:SS", que e' o suficiente para compor a chave de medicao abaixo.
    tabela["hora"] = tabela["hora"].astype(str)

    # Chave real de uma medição individual — SEQID não serve para isso (ver _RENOMEIA acima).
    tabela["medicao_id"] = (
        tabela["codigo_ponto"].astype(str) + "|"
        + tabela["data"].astype(str) + "|"
        + tabela["hora"].astype(str) + "|"
        + tabela["parametro"].astype(str)
    )

    for coluna, valores in linhas_de_proveniencia(len(tabela), caminho, FONTE_TIPO_OBSERVADO).items():
        tabela[coluna] = valores

    write_table(BRONZE_DIR / "cetesb", tabela)
    logger.info(
        "Bronze cetesb: %d linhas de %d pontos (%s a %s).",
        len(tabela), tabela["codigo_ponto"].nunique(),
        tabela["data"].min(), tabela["data"].max(),
    )
    return tabela


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
