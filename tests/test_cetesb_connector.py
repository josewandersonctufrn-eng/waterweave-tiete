"""Testes de guarda da decisão sobre `connectors.cetesb` (ver docstring do módulo e
README, seção "Conector CETESB — decisão formalizada"): CETESB não tem API pública
estruturada para boletins pós-2024 (só portal de download manual no INFOÁGUAS), então
`fetch_new_records` é um `NotImplementedError` DELIBERADO, não uma lacuna esquecida —
diferente do histórico 1978-2024, que já é real via `ingestion.bronze_cetesb`
(`base_de_dados_pontos.xlsx`, um export local, não uma API).

Estes testes travam as duas metades dessa decisão para que uma regressão futura
(alguém "arrumando" o stub sem querer, ou o job mensal passando a derrubar por causa
dele) seja pega automaticamente:
  1. `fetch_new_records` continua levantando `NotImplementedError` com uma mensagem
     clara (não um erro genérico/silencioso).
  2. `ingestion.monthly_job.run_live_connectors` continua pulando esse erro
     especificamente (log e segue), sem derrubar o job mensal.
"""
from __future__ import annotations

import sys
import types
from datetime import date

import pytest

from waterweave.ingestion.connectors import cetesb


def test_fetch_new_records_levanta_not_implemented_com_mensagem_clara():
    with pytest.raises(NotImplementedError, match="API pública"):
        cetesb.fetch_new_records(since=date(2024, 1, 1))


def test_fetch_new_records_mesmo_comportamento_com_pontos_monitoramento():
    """O parâmetro opcional `pontos_monitoramento` não muda a decisão — continua
    sem rota de API para filtrar por ele."""
    with pytest.raises(NotImplementedError, match="API pública"):
        cetesb.fetch_new_records(since=date(2024, 1, 1), pontos_monitoramento=["TIET02900"])


def _modulo_falso(nome: str, **atributos) -> types.ModuleType:
    modulo = types.ModuleType(nome)
    for chave, valor in atributos.items():
        setattr(modulo, chave, valor)
    return modulo


@pytest.fixture
def _dependencias_pesadas_falsas(monkeypatch):
    """`ingestion.monthly_job` importa toda a cadeia Bronze/Silver/Gold no nível do
    módulo, e essa cadeia importa `deltalake` (via `io_delta`) e `ee`/Earth Engine
    (via `bronze_uso_solo`/`bronze_sensoriamento_historico`) — nenhum dos dois é
    necessário de verdade para o que este teste cobre (só o CAMINHO de
    `run_live_connectors` que trata `cetesb`). Se o ambiente já os tem instalados
    (caso normal do projeto), não mexe em nada.
    """
    fakes = {
        "deltalake": _modulo_falso("deltalake", DeltaTable=object, write_deltalake=lambda *a, **k: None),
        "ee": _modulo_falso("ee", Initialize=lambda *a, **k: None, Authenticate=lambda *a, **k: None),
    }
    for nome, modulo_falso in fakes.items():
        if nome not in sys.modules:
            monkeypatch.setitem(sys.modules, nome, modulo_falso)
    yield


def test_run_live_connectors_pula_cetesb_sem_derrubar_job(monkeypatch, caplog, _dependencias_pesadas_falsas):
    from waterweave.ingestion import monthly_job

    # Isola o teste da API real da ANA (já coberta à parte) — só o comportamento do
    # stub CETESB dentro de `run_live_connectors` está em questão aqui.
    monkeypatch.setattr(monthly_job.ana_snirh, "fetch_new_records", lambda since: {})

    with caplog.at_level("INFO"):
        monthly_job.run_live_connectors(since=date(2024, 1, 1))  # não deve levantar

    assert any(
        "cetesb" in registro.message and "não implementado" in registro.message
        for registro in caplog.records
    )
