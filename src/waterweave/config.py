"""Configuração central do WaterWeave-Tietê: paths, trechos e constantes de domínio.

Mantém em um único lugar o mapeamento entre a estrutura de pastas real do
projeto (exports brutos DAEE, planilhas sintéticas) e os nomes lógicos usados
pelo restante do pipeline.
"""
from __future__ import annotations

import os
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
    # 2.397.437 medições REAIS da rede CETESB (1978-2024), ingeridas por
    # `ingestion.bronze_cetesb` / `transform.silver_qualidade_cetesb` — fonte
    # primária de iqa/od_mg_l/dbo_mg_l/metais_pesados_ppm (ver ACHADO DE
    # AUDITORIA em `ingestion.monthly_job`: até 2026-07 esta fonte estava
    # declarada aqui mas nunca era lida).
    "pontos_consolidados": RAW_DATA_DIR / "base_de_dados_pontos.xlsx",
    # Reclassificada (2026-07): NÃO é mais fonte de produção para
    # iqa/od_mg_l/dbo_mg_l/metais_pesados_ppm — `transform.gold_features.
    # qualidade_real_com_fallback_simulado` só usa esta série (via
    # `silver_qualidade.build_silver_qualidade`) para preencher anos sem
    # cobertura real da CETESB (1940-1977 e lacunas pontuais). Continua sendo
    # a única fonte para uso_solo/pesticidas_ppm/materia_organica_pct, que a
    # CETESB não mede.
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

# ---------------------------------------------------------------------------
# Co-criação com stakeholders (item 7 do roadmap de pesquisa WaterWeave-Water4All) —
# ver models.abm.scenario_store
# ---------------------------------------------------------------------------
# Propostas de cenário salvas por gestores/tomadores de decisão/representantes de comunidades
# na página "Cenários Futuros" (nome, autor, justificativa, parâmetros) — um arquivo JSON por
# proposta. VERSIONADO (não é gitignored, ao contrário de `data/bronze/`): diferente de dado
# reprocessável a partir da fonte bruta, uma proposta de stakeholder é conteúdo original que só
# existe aqui — perder isso ao limpar `data/` apagaria contribuição real de co-criação.
PROPOSTAS_DIR = PROJECT_ROOT / "data" / "cenarios_propostos"

# ---------------------------------------------------------------------------
# Google Earth Engine (uso do solo real — ingestion.connectors.mapbiomas)
# ---------------------------------------------------------------------------
# Projeto Google Cloud com a API do Earth Engine habilitada e registrada para
# uso não-comercial/acadêmico (ver docstring de connectors.mapbiomas). Exigido
# por `ee.Initialize(project=...)` desde que o Earth Engine passou a recusar
# inicialização sem projeto explícito.
#
# Lido de variável de ambiente, não hardcoded: não é uma credencial (sozinho
# não dá acesso a nada — ainda precisa do token OAuth de `earthengine
# authenticate`, que fica fora do repositório, em `~/.config/earthengine/`),
# mas é um identificador específico da conta Google do usuário, então não faz
# sentido fixo no código de um repositório público. Configure antes de rodar
# `bronze_uso_solo.py` (ver README):
#   PowerShell:  $env:WATERWEAVE_EE_PROJECT = "seu-project-id"
#   bash:        export WATERWEAVE_EE_PROJECT=seu-project-id
#
# Fica `None` se a variável não estiver definida — `connectors.mapbiomas`
# levanta um erro claro nesse caso (ver `fetch_uso_solo_por_trecho`), em vez
# do erro genérico do Earth Engine sobre projeto ausente.
EARTH_ENGINE_PROJECT = os.environ.get("WATERWEAVE_EE_PROJECT")

# ---------------------------------------------------------------------------
# Copernicus Climate Data Store (ERA5 reanálise + CMIP6 projeções — item 4 do
# roadmap de pesquisa, ver ingestion.connectors.era5_cmip6)
# ---------------------------------------------------------------------------
# Token de acesso pessoal da CDS (registro gratuito em https://cds.climate.copernicus.eu,
# depois copiar o valor de "key" em https://cds.climate.copernicus.eu/how-to-api). O padrão
# oficial da biblioteca `cdsapi` é gravar isso em `~/.cdsapirc`; aqui lemos de variável de
# ambiente (mesmo raciocínio de `EARTH_ENGINE_PROJECT`: consistente com o resto do projeto, não
# obriga a mexer em arquivos de configuração fora do repo) e passamos explicitamente para
# `cdsapi.Client(url=..., key=...)`, que aceita essa forma tão bem quanto o arquivo:
#   PowerShell:  $env:WATERWEAVE_CDS_API_KEY = "seu-token-pessoal"
#   bash:        export WATERWEAVE_CDS_API_KEY=seu-token-pessoal
# Fica `None` se a variável não estiver definida — `connectors.era5_cmip6` levanta um erro claro
# nesse caso, no mesmo padrão de `EARTH_ENGINE_PROJECT`/`connectors.mapbiomas`.
CDS_API_URL = "https://cds.climate.copernicus.eu/api"
CDS_API_KEY = os.environ.get("WATERWEAVE_CDS_API_KEY")

# Bounding box aproximado da bacia do Tietê (todos os 3 trechos, com margem), no formato
# (lat_min, lon_min, lat_max, lon_max) — cobre da nascente em Salesópolis (23.53°S, 45.84°W) até
# a foz em Itapura/Rio Paraná (20.67°S, 51.45°W), mesmos pontos de referência de
# `connectors.sensoriamento_historico.PONTOS_MONITORAMENTO`. Usado como área de consulta do
# ERA5/CMIP6 (clima é um sinal de escala muito maior que o buffer de 300m usado no sensoriamento
# óptico — não faz sentido, nem é preciso o suficiente na resolução do ERA5 (~28km) para pedir
# recorte por trecho individual).
BBOX_BACIA_TIETE = (-24.0, -52.0, -20.0, -45.5)
