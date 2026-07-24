"""Acesso do dashboard às camadas Silver/Gold produzidas pelo pipeline de ingestão.

Substitui a versão anterior deste módulo, que lia os `.xlsx` originais
diretamente (atalho usado enquanto Bronze/Silver/Gold não existiam). Agora
que `waterweave.ingestion.monthly_job` materializa as tabelas Delta em
`data/bronze|silver|gold`, o dashboard só lê essas tabelas — rode
`python -m waterweave.ingestion.monthly_job` (ou aguarde o agendamento
mensal) antes de abrir o app pela primeira vez.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from waterweave.config import GOLD_DIR, SILVER_DIR
from waterweave.io_delta import read_table
from waterweave.transform.gold_features import qualidade_real_com_fallback_simulado


@st.cache_data(ttl=3600)
def load_estacoes_tiete() -> pd.DataFrame:
    """Estações de monitoramento sobre o eixo do Rio Tietê (`silver.estacoes`)."""
    return read_table(SILVER_DIR / "estacoes")


@st.cache_data(ttl=3600)
def load_qualidade_historica() -> pd.DataFrame:
    """Série histórica de IQA/DBO/OD/metais/pesticidas por trecho, priorizando medição
    REAL da CETESB (`silver.qualidade_cetesb`, 1978-2024) e usando `silver.qualidade`
    (simulado) só como preenchimento de anos sem cobertura real (1940-1977 e lacunas
    pontuais) — ver `transform.gold_features.qualidade_real_com_fallback_simulado` e
    a coluna `fonte_tipo` retornada aqui para a proveniência linha a linha.
    """
    return qualidade_real_com_fallback_simulado()


@st.cache_data(ttl=3600)
def load_sensoriamento() -> pd.DataFrame:
    """Pontos de sensoriamento remoto, nascente -> foz (`silver.sensoriamento`).

    ⚠️ Fonte descrita como "Simulação Consolidada" para o período coberto.
    """
    return read_table(SILVER_DIR / "sensoriamento")


@st.cache_data(ttl=3600)
def load_vazao_mensal(trecho_id: str) -> pd.DataFrame:
    """Vazão média mensal por posto de um trecho, todos os postos disponíveis (`silver.vazao_mensal`)."""
    tabela = read_table(SILVER_DIR / "vazao_mensal")
    tabela = tabela[tabela["trecho_id"] == trecho_id].copy()
    if tabela.empty:
        return tabela
    tabela["data"] = pd.to_datetime(dict(year=tabela["ano"], month=tabela["mes"], day=1))
    return tabela.sort_values(["codigo_posto", "data"])


@st.cache_data(ttl=3600)
def load_chuva_mensal(trecho_id: str) -> pd.DataFrame:
    """Chuva média mensal por posto de um trecho, todos os postos disponíveis (`silver.chuva_mensal`)."""
    tabela = read_table(SILVER_DIR / "chuva_mensal")
    tabela = tabela[tabela["trecho_id"] == trecho_id].copy()
    if tabela.empty:
        return tabela
    tabela["data"] = pd.to_datetime(dict(year=tabela["ano"], month=tabela["mes"], day=1))
    return tabela.sort_values(["codigo_posto", "data"])


@st.cache_data(ttl=3600)
def load_serie_temporal_trecho_mes() -> pd.DataFrame:
    """Série mensal agregada por trecho (vazão + chuva + qualidade), pronta para o dashboard (`gold.serie_temporal_trecho_mes`)."""
    return read_table(GOLD_DIR / "serie_temporal_trecho_mes")


@st.cache_data(ttl=3600)
def load_estado_inicial_abm() -> pd.DataFrame:
    """Snapshot mais recente por trecho, usado para inicializar o ABM (`gold.estado_inicial_abm`)."""
    return read_table(GOLD_DIR / "estado_inicial_abm")
