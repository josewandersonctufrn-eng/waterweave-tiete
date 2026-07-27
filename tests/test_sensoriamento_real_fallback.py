"""Testes de `transform.gold_features.sensoriamento_real_com_fallback_ilustrativo` — combina
o sensoriamento remoto HISTÓRICO real (Landsat, `silver.sensoriamento_historico`) com a
planilha ilustrativa (`silver.sensoriamento`) dando prioridade ao dado real, mesmo padrão de
`qualidade_real_com_fallback_simulado` (CETESB vs. simulado)."""
from __future__ import annotations

import pandas as pd
import pytest

from waterweave.transform import gold_features


def _linha(id_regiao, ano, parametro, valor, fonte_tipo, trecho_id="alto_tiete"):
    return {
        "id_regiao": id_regiao,
        "trecho_id": trecho_id,
        "data_coleta": pd.Timestamp(year=ano, month=7, day=1),
        "parametro": parametro,
        "valor": valor,
        "unidade": "unidade-teste",
        "fonte_tipo": fonte_tipo,
    }


@pytest.fixture
def duas_fontes(monkeypatch):
    real = pd.DataFrame(
        [
            _linha("TIE-01", 2020, "NDVI (Mata Ciliar)", 0.65, "observado"),
            _linha("TIE-01", 2026, "NDVI (Mata Ciliar)", 0.70, "observado"),  # mesmo (ponto,ano,parametro) do ilustrativo
        ]
    )
    ilustrativo = pd.DataFrame(
        [
            _linha("TIE-01", 2026, "NDVI (Mata Ciliar)", 0.999, "simulado"),  # deve perder para o real acima
            _linha("TIE-04", 2026, "Clorofila-a", 45.2, "simulado", trecho_id="medio_tiete"),  # sem par real, mantido
        ]
    )
    tabelas = {"sensoriamento": ilustrativo, "sensoriamento_historico": real}
    monkeypatch.setattr(gold_features, "read_table", lambda path: tabelas[path.name])
    return real, ilustrativo


def test_real_tem_prioridade_quando_ha_conflito(duas_fontes):
    combinado = gold_features.sensoriamento_real_com_fallback_ilustrativo()
    linha_2026 = combinado[(combinado["id_regiao"] == "TIE-01") & (combinado["data_coleta"].dt.year == 2026)]
    assert len(linha_2026) == 1
    assert linha_2026.iloc[0]["valor"] == 0.70
    assert linha_2026.iloc[0]["fonte_tipo"] == "observado"


def test_ilustrativo_preenche_onde_nao_ha_par_real(duas_fontes):
    combinado = gold_features.sensoriamento_real_com_fallback_ilustrativo()
    linha_clorofila = combinado[combinado["parametro"] == "Clorofila-a"]
    assert len(linha_clorofila) == 1
    assert linha_clorofila.iloc[0]["fonte_tipo"] == "simulado"


def test_nenhuma_linha_e_perdida(duas_fontes):
    real, ilustrativo = duas_fontes
    combinado = gold_features.sensoriamento_real_com_fallback_ilustrativo()
    # 2 reais (sem conflito) + 1 ilustrativo que sobrevive (Clorofila-a) = 3
    assert len(combinado) == 3


def test_data_coleta_e_sempre_timestamp_mesmo_com_fontes_mistas(monkeypatch):
    """Regressão: `silver.sensoriamento` (ilustrativa) volta de `read_table` com `data_coleta`
    como string (round-trip Excel -> Delta), enquanto o Landsat real já vem como Timestamp —
    sem normalizar os dois lados ANTES do concat, o resultado tinha uma coluna de tipo misto
    que quebrava qualquer `.dt`/`.year` a jusante (ver `webapp/pages/1_Mapa_Interativo.py`)."""
    real = pd.DataFrame([_linha("TIE-01", 2020, "NDVI (Mata Ciliar)", 0.65, "observado")])
    ilustrativo = pd.DataFrame([_linha("TIE-04", 2026, "Clorofila-a", 45.2, "simulado", trecho_id="medio_tiete")])
    ilustrativo["data_coleta"] = ilustrativo["data_coleta"].astype(str)  # simula o round-trip real

    tabelas = {"sensoriamento": ilustrativo, "sensoriamento_historico": real}
    monkeypatch.setattr(gold_features, "read_table", lambda path: tabelas[path.name])

    combinado = gold_features.sensoriamento_real_com_fallback_ilustrativo()
    assert pd.api.types.is_datetime64_any_dtype(combinado["data_coleta"])


def test_sem_tabela_real_retorna_ilustrativo_sem_alteracao(monkeypatch):
    ilustrativo = pd.DataFrame([_linha("TIE-04", 2026, "Clorofila-a", 45.2, "simulado", trecho_id="medio_tiete")])
    tabelas = {"sensoriamento": ilustrativo, "sensoriamento_historico": pd.DataFrame()}
    monkeypatch.setattr(gold_features, "read_table", lambda path: tabelas[path.name])

    combinado = gold_features.sensoriamento_real_com_fallback_ilustrativo()
    pd.testing.assert_frame_equal(combinado.reset_index(drop=True), ilustrativo.reset_index(drop=True))
