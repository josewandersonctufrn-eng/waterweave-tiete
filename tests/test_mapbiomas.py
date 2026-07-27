"""Testes de `ingestion.connectors.mapbiomas` — a legenda de classes e a montagem da tabela
final de `fetch_uso_solo_por_trecho`. NÃO faz nenhuma chamada real ao Earth Engine (rede/
autenticação): `ee.Initialize` e a busca por ano (`_area_por_classe_um_ano`) são mockados —
ver `test_bronze_uso_solo.py` para o restante do pipeline com o conector também mockado."""
from __future__ import annotations

import pandas as pd
import pytest

from waterweave.ingestion.connectors import mapbiomas

_MACRO_CATEGORIAS_VALIDAS = {
    "natural", "agropecuaria", "urbano_industrial", "agua", "nao_vegetado_outro", "nao_observado",
}


def test_todas_as_classes_mapeadas_tem_macro_categoria_valida():
    assert set(mapbiomas.CLASSE_PARA_MACRO.values()) <= _MACRO_CATEGORIAS_VALIDAS


def test_classes_conhecidas_chave_e_valor_esperados():
    """Amostra de códigos MapBiomas realmente observados no eixo do Tietê (ver histórico de
    execução real do conector) — trava a legenda contra uma reordenação/erro de digitação
    silencioso."""
    assert mapbiomas.CLASSE_PARA_MACRO[3] == "natural"  # Formação Florestal
    assert mapbiomas.CLASSE_PARA_MACRO[15] == "agropecuaria"  # Pastagem
    assert mapbiomas.CLASSE_PARA_MACRO[24] == "urbano_industrial"  # Área Urbanizada
    assert mapbiomas.CLASSE_PARA_MACRO[33] == "agua"  # Rio, Lago e Oceano
    assert mapbiomas.CLASSE_PARA_MACRO[27] == "nao_observado"  # Não observado


@pytest.fixture
def ee_mockado(monkeypatch):
    """Substitui `ee.Initialize`/`ee.Image` e `_area_por_classe_um_ano` por versões que não
    tocam rede — a área por classe é fixa e conhecida, só para testar a MONTAGEM da tabela
    final (trecho × ano × classe), não o cálculo de área em si (isso é responsabilidade do
    Earth Engine, não deste código)."""
    monkeypatch.setattr(mapbiomas.ee, "Initialize", lambda project=None: None)

    class _ImagemFalsa:
        def select(self, banda):
            return banda  # repassa só o nome da banda, suficiente para o teste

    monkeypatch.setattr(mapbiomas.ee, "Image", lambda asset_id: _ImagemFalsa())
    monkeypatch.setattr(mapbiomas, "_area_por_classe_um_ano", lambda imagem_ano, geometria, escala: {3: 100.0, 24: 900.0})
    monkeypatch.setattr(mapbiomas, "_geometria_uniao", lambda pontos, buffer: "geometria-falsa")


# Projeto falso só para passar a checagem `if not project: raise RuntimeError` (ver
# `config.EARTH_ENGINE_PROJECT`) — nunca chega a ser usado de verdade, já que `ee.Initialize`
# está mockado acima.
_PROJETO_TESTE = "projeto-teste-falso"


def test_fetch_gera_uma_linha_por_trecho_ano_classe(ee_mockado):
    pontos = {"alto_tiete": [(-46.1, -23.5)]}
    tabela = mapbiomas.fetch_uso_solo_por_trecho(pontos, ano_inicio=2020, ano_fim=2021, project=_PROJETO_TESTE)

    assert len(tabela) == 2 * 2  # 2 anos x 2 classes
    assert set(tabela["ano"]) == {2020, 2021}
    assert set(tabela["classe_mapbiomas"]) == {3, 24}


def test_fetch_mapeia_macro_categoria_corretamente(ee_mockado):
    pontos = {"alto_tiete": [(-46.1, -23.5)]}
    tabela = mapbiomas.fetch_uso_solo_por_trecho(
        pontos, ano_inicio=2023, ano_fim=2023, project=_PROJETO_TESTE
    ).set_index("classe_mapbiomas")

    assert tabela.loc[3, "macro_categoria"] == "natural"
    assert tabela.loc[24, "macro_categoria"] == "urbano_industrial"
    assert tabela.loc[3, "area_m2"] == 100.0
    assert tabela.loc[24, "area_m2"] == 900.0


def test_fetch_pula_trecho_sem_pontos(ee_mockado):
    pontos = {"alto_tiete": [(-46.1, -23.5)], "baixo_tiete": []}
    tabela = mapbiomas.fetch_uso_solo_por_trecho(pontos, ano_inicio=2023, ano_fim=2023, project=_PROJETO_TESTE)
    assert "baixo_tiete" not in set(tabela["trecho_id"])


def test_fetch_multiplos_trechos_todos_presentes(ee_mockado):
    pontos = {"alto_tiete": [(-46.1, -23.5)], "medio_tiete": [(-48.0, -22.5)]}
    tabela = mapbiomas.fetch_uso_solo_por_trecho(pontos, ano_inicio=2023, ano_fim=2023, project=_PROJETO_TESTE)
    assert set(tabela["trecho_id"]) == {"alto_tiete", "medio_tiete"}


def test_fetch_sem_projeto_levanta_erro_claro(ee_mockado):
    """Sem `WATERWEAVE_EE_PROJECT` (nem `project=` explícito), o erro precisa apontar a causa
    real — não o `ee.EEException` genérico do Earth Engine sobre projeto ausente."""
    with pytest.raises(RuntimeError, match="WATERWEAVE_EE_PROJECT"):
        mapbiomas.fetch_uso_solo_por_trecho({"alto_tiete": [(-46.1, -23.5)]}, ano_inicio=2023, ano_fim=2023, project=None)
