"""Teste de guarda para `models.ml.predict_iqa` — cobre o achado de 2026-09: quando o uso do
solo real (MapBiomas) entrou como preditora de produção (`pct_natural`/`pct_agropecuaria`/
`pct_urbano_industrial`/`pct_agua`), `prever_iqa` nunca foi atualizado para preencher essas 4
colunas em `valores`, causando `KeyError` toda vez que a previsão recursiva era chamada (ex.:
página "Cenários Futuros" do dashboard, via `models.ml.comparacao_biofisico_ml`). Roda contra o
Gold real e os modelos `.joblib` já versionados no repositório (mesmo padrão de confiança em
artefato commitado usado para `data/fator_clima_cmip6.json`)."""
from __future__ import annotations

import pytest

pytest.importorskip("sklearn")

from waterweave.config import TRECHOS
from waterweave.models.ml.predict_iqa import prever_iqa


@pytest.mark.parametrize("trecho_id", list(TRECHOS))
def test_prever_iqa_nao_levanta_keyerror_de_uso_do_solo(trecho_id):
    """Regressão: `preditoras_anuais_do_trecho` inclui as 4 colunas de uso do solo há meses;
    `prever_iqa` precisa populá-las em `valores`, para todos os trechos (inclusive Baixo Tietê,
    que também remove `vazao_m3s_medio` — outra fonte histórica de KeyError/ValueError se a
    lista de preditoras e o dict de valores divergirem)."""
    previsao = prever_iqa(trecho_id, horizonte_anos=3)
    assert len(previsao) == 3
    assert previsao["ano"].is_monotonic_increasing
    assert previsao["iqa_previsto"].notna().all()
    assert previsao["od_previsto"].notna().all()
