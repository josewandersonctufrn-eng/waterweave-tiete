"""Testes de guarda do pipeline de ingestão: garantem que toda fonte declarada em
`config.RAW_SOURCES` tem uma ingestão Bronze de fato executada pelo job mensal.

Existem para não repetir o gap encontrado na auditoria de 2026-07 (ver
docs/Auditoria_Engenharia_Dados_WaterWeave_Tiete.docx): `base_de_dados_pontos.xlsx`
ficou registrado em `RAW_SOURCES` desde o início do projeto sem que nenhum módulo
`bronze_*.py` o lesse — 2,4 milhões de medições reais da CETESB nunca chegaram ao
pipeline, e nada acusava essa lacuna.
"""
from __future__ import annotations

import ast
import inspect
import textwrap

from waterweave.config import RAW_SOURCES
from waterweave.ingestion import monthly_job

# Mapa explícito: toda chave nova em RAW_SOURCES precisa ganhar uma entrada aqui — esse
# é o próprio ponto do teste, forçar uma decisão consciente em vez de deixar uma fonte
# "configurada mas nunca lida" passar despercebida por meses.
_FONTE_PARA_MODULO_BRONZE = {
    "fluviometria": "bronze_daee_fluviometria",
    "pluviometria": "bronze_daee_pluviometria",
    "estacoes": "bronze_estacoes",
    "pontos_consolidados": "bronze_cetesb",
    "qualidade_solo_sedimentos": "bronze_qualidade_solo",
    "sensoriamento_remoto": "bronze_sensoriamento",
}


def test_toda_fonte_declarada_tem_modulo_bronze_mapeado():
    """Toda chave de `RAW_SOURCES` precisa aparecer em `_FONTE_PARA_MODULO_BRONZE` — se uma
    fonte nova for adicionada em `config.py` sem decidir seu módulo de ingestão, este teste
    falha em vez de deixar a fonte órfã silenciosamente (a causa raiz real do gap auditado)."""
    faltando = set(RAW_SOURCES) - set(_FONTE_PARA_MODULO_BRONZE)
    assert not faltando, (
        f"Fonte(s) declarada(s) em RAW_SOURCES sem módulo bronze mapeado: {faltando}. "
        "Adicione uma entrada em _FONTE_PARA_MODULO_BRONZE (tests/test_pipeline_paridade.py) "
        "apontando para o módulo bronze_*.py responsável, ou implemente um novo."
    )


def _modulos_run_chamados(funcao) -> list[str]:
    """Extrai, via AST (não substring — comentários/docstrings não enganam isto), os nomes
    de módulo de toda chamada `<modulo>.run()` no corpo de `funcao`."""
    arvore = ast.parse(textwrap.dedent(inspect.getsource(funcao)))
    chamados = []
    for node in ast.walk(arvore):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
        ):
            chamados.append(node.func.value.id)
    return chamados


def test_todo_modulo_bronze_mapeado_e_realmente_executado():
    """Todo módulo listado em `_FONTE_PARA_MODULO_BRONZE` precisa ser chamado dentro de
    `monthly_job.run_bronze_static_sources` — senão a fonte fica 'configurada' mas nunca é
    lida, que foi exatamente o gap real encontrado nesta auditoria. Usa AST (não checagem de
    texto): um `.run()` comentado ou dentro de uma docstring não passa neste teste."""
    chamados = set(_modulos_run_chamados(monthly_job.run_bronze_static_sources))
    nao_executados = [modulo for modulo in _FONTE_PARA_MODULO_BRONZE.values() if modulo not in chamados]
    assert not nao_executados, (
        f"Módulo(s) bronze mapeado(s) em _FONTE_PARA_MODULO_BRONZE mas NÃO chamado(s) dentro "
        f"de monthly_job.run_bronze_static_sources: {nao_executados}"
    )


def test_run_bronze_static_sources_nao_tem_chamada_duplicada_ou_a_mais():
    """Sanidade adicional: o número de chamadas `.run()` reais (via AST) dentro da função deve
    bater exatamente com o número de fontes mapeadas — pega duplicação ou chamada residual de
    um módulo já removido de `_FONTE_PARA_MODULO_BRONZE`."""
    chamados = _modulos_run_chamados(monthly_job.run_bronze_static_sources)
    assert len(chamados) == len(_FONTE_PARA_MODULO_BRONZE), (
        f"Esperava {len(_FONTE_PARA_MODULO_BRONZE)} chamadas .run() em "
        f"run_bronze_static_sources (uma por fonte mapeada), encontrei {len(chamados)}: {chamados}."
    )
