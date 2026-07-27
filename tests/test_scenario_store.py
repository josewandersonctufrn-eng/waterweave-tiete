"""Testes de guarda de `models.abm.scenario_store` — mecanismo de co-criação (item 7 do roadmap
de pesquisa WaterWeave-Water4All): salvar/listar/recarregar propostas de cenário de
stakeholders. Usa `tmp_path` (via monkeypatch de `PROPOSTAS_DIR`) — nunca escreve no
`data/cenarios_propostos/` real do repositório durante os testes.
"""
from __future__ import annotations

import json

import pytest

from waterweave.models.abm import scenario_store


@pytest.fixture
def pasta_propostas_isolada(tmp_path, monkeypatch):
    pasta = tmp_path / "cenarios_propostos"
    monkeypatch.setattr(scenario_store, "PROPOSTAS_DIR", pasta)
    return pasta


def test_salvar_proposta_grava_json_com_todos_os_campos(pasta_propostas_isolada):
    parametros = {"fator_clima": 0.9, "piso_fator_outorga": 0.7}
    proposta = scenario_store.salvar_proposta(
        nome="Mais fiscalização no Alto Tietê",
        autor="Comitê de Bacia PCJ",
        justificativa="Reduzir carga industrial antes da expansão urbana projetada.",
        trecho_id="alto_tiete",
        horizonte_anos=15,
        parametros=parametros,
        resumo_metricas={"iqa_final": 62.0},
    )
    assert proposta.id
    arquivos = list(pasta_propostas_isolada.glob("*.json"))
    assert len(arquivos) == 1

    dados = json.loads(arquivos[0].read_text(encoding="utf-8"))
    assert dados["nome"] == "Mais fiscalização no Alto Tietê"
    assert dados["autor"] == "Comitê de Bacia PCJ"
    assert dados["trecho_id"] == "alto_tiete"
    assert dados["horizonte_anos"] == 15
    assert dados["parametros"] == parametros
    assert dados["resumo_metricas"] == {"iqa_final": 62.0}
    assert dados["criado_em"]


def test_nomes_com_acento_e_espaco_viram_slug_valido_no_arquivo(pasta_propostas_isolada):
    scenario_store.salvar_proposta(
        nome="Restrição Agrícola & Saneamento!!",
        autor="ONG Rio Vivo",
        justificativa="x",
        trecho_id="medio_tiete",
        horizonte_anos=5,
        parametros={},
    )
    arquivo = next(pasta_propostas_isolada.glob("*.json"))
    assert "restricao-agricola" in arquivo.stem
    assert " " not in arquivo.stem


def test_listar_propostas_ordena_mais_recente_primeiro(pasta_propostas_isolada):
    primeira = scenario_store.salvar_proposta("Primeira", "A", "x", "alto_tiete", 5, {})
    segunda = scenario_store.salvar_proposta("Segunda", "B", "x", "alto_tiete", 5, {})

    listadas = scenario_store.listar_propostas()
    assert [p.id for p in listadas] == sorted([primeira.id, segunda.id], reverse=True)


def test_carregar_proposta_recupera_pelos_id(pasta_propostas_isolada):
    salva = scenario_store.salvar_proposta(
        "Cenário X", "Autor Y", "justificativa", "baixo_tiete", 20, {"fator_clima": 1.1}
    )
    recarregada = scenario_store.carregar_proposta(salva.id)
    assert recarregada == salva


def test_carregar_proposta_inexistente_levanta_erro_claro(pasta_propostas_isolada):
    with pytest.raises(FileNotFoundError, match="não encontrada"):
        scenario_store.carregar_proposta("id-que-nao-existe")


def test_listar_propostas_pasta_inexistente_retorna_lista_vazia(pasta_propostas_isolada):
    assert not pasta_propostas_isolada.exists()
    assert scenario_store.listar_propostas() == []


def test_controles_ui_salvos_e_recarregados_junto_com_parametros(pasta_propostas_isolada):
    controles_ui = {"esforco_fisico": 70, "controlar_fisico": True, "clima_pct": 85}
    salva = scenario_store.salvar_proposta(
        "Cenário Y", "Autor Z", "x", "alto_tiete", 10, {"fator_clima": 0.85}, controles_ui=controles_ui
    )
    assert salva.controles_ui == controles_ui
    recarregada = scenario_store.carregar_proposta(salva.id)
    assert recarregada.controles_ui == controles_ui


def test_controles_ui_default_vazio_quando_nao_informado(pasta_propostas_isolada):
    salva = scenario_store.salvar_proposta("Cenário Z", "Autor W", "x", "alto_tiete", 10, {})
    assert salva.controles_ui == {}


def test_listar_propostas_ignora_arquivo_json_malformado(pasta_propostas_isolada, caplog):
    pasta_propostas_isolada.mkdir(parents=True)
    (pasta_propostas_isolada / "corrompido.json").write_text("{not valid json", encoding="utf-8")
    scenario_store.salvar_proposta("Válida", "A", "x", "alto_tiete", 5, {})

    listadas = scenario_store.listar_propostas()
    assert len(listadas) == 1
    assert listadas[0].nome == "Válida"
