"""Configuração central do WaterWeave-Tietê: paths, trechos e constantes de domínio.

Mantém em um único lugar o mapeamento entre a estrutura de pastas real do
projeto (exports brutos DAEE, planilhas sintéticas) e os nomes lógicos usados
pelo restante do pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DATA_DIR = PROJECT_ROOT
BRONZE_DIR = PROJECT_ROOT / "data" / "bronze"
SILVER_DIR = PROJECT_ROOT / "data" / "silver"
GOLD_DIR = PROJECT_ROOT / "data" / "gold"

# Fontes brutas conhecidas hoje (ver DIRETRIZES DA ARQUITETURA). Cada entrada
# aponta para pastas/arquivos que já existem no diretório do projeto.
RAW_SOURCES = {
    "fluviometria": {
        "alto_tiete": RAW_DATA_DIR / "ALTO TIETE_FLUV",
        "medio_tiete": RAW_DATA_DIR / "MEDIO TIETE_FLUV",
        "baixo_tiete": RAW_DATA_DIR / "BAIXO TIETE_FLUV",
    },
    "pluviometria": {
        "alto_tiete": RAW_DATA_DIR / "ALTO TIETE_PLUV",
        "medio_tiete": RAW_DATA_DIR / "MEDIO TIETE_PLUV",
        "baixo_tiete": RAW_DATA_DIR / "BAIXO TIETE_PLUV",
    },
    "estacoes": RAW_DATA_DIR / "cod_latlong.xlsx",
    "pontos_consolidados": RAW_DATA_DIR / "base_de_dados_pontos.xlsx",
    "qualidade_solo_sedimentos": RAW_DATA_DIR / "Planilha_Historica_Solo_Sedimentos_Rio_Tiete_1940_2025.xlsx",
    "sensoriamento_remoto": RAW_DATA_DIR / "Sensoriamento_Remoto_Rio_Tiete.xlsx",
}

# ---------------------------------------------------------------------------
# Domínio: trechos do Rio Tietê (nascente -> foz)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Trecho:
    id: str
    nome: str
    municipio_referencia: str
    km_aproximado: float  # distância aproximada da nascente, em km


TRECHOS: dict[str, Trecho] = {
    "alto_tiete": Trecho("alto_tiete", "Alto Tietê", "Salesópolis", 0),
    "medio_tiete": Trecho("medio_tiete", "Médio Tietê", "Barra Bonita", 350),
    "baixo_tiete": Trecho("baixo_tiete", "Baixo Tietê", "Itapura (foz no Rio Paraná)", 1100),
}

# Proveniência dos dados: distingue séries observadas (agências) de séries
# sintéticas/simuladas usadas como ponte para períodos sem telemetria digital.
FONTE_TIPO_OBSERVADO = "observado"
FONTE_TIPO_SIMULADO = "simulado"

HISTORICO_INICIO = 1940
HISTORICO_FIM_INICIAL = 2025  # atualizado mensalmente pelo job de automação

MESES_PT = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
}

# ---------------------------------------------------------------------------
# Controle de execução do job mensal
# ---------------------------------------------------------------------------

PIPELINE_CONTROL_FILE = PROJECT_ROOT / "data" / "_pipeline_runs.json"
