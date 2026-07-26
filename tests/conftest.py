"""Garante que `import waterweave` funcione ao rodar `pytest` sem configurar PYTHONPATH
manualmente — o pacote não está instalado em modo editável neste ambiente (mesmo padrão
já usado em cada página de `webapp/pages/*.py`)."""
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def gold_df_sintetico():
    """Fábrica de DataFrame sintético no formato de `gold.feature_store_ml_anual` — usada por
    `test_ml_train.py` e `test_shap_analysis.py`. Fica no conftest porque os dois precisam do
    mesmo formato de dado (evita duplicar a lógica de geração entre arquivos).

    Tendência de queda + ruído (não puro ruído): com dado puramente aleatório,
    `treinar_modelo_trecho` teria sempre `supera_baseline_com_margem=False`, o que mascararia
    um bug real de MECÂNICA de treino atrás de "o modelo não presta com dado sintético mesmo"
    — não é isso que estes testes verificam (eles testam mecânica, não acurácia)."""

    def _construir(n_anos: int = 40, trecho_id: str = "alto_tiete") -> pd.DataFrame:
        rng = np.random.default_rng(42)
        anos = list(range(1980, 1980 + n_anos))
        iqa = 80 - np.arange(n_anos) * 0.3 + rng.normal(0, 1.0, n_anos)
        od = 8 - np.arange(n_anos) * 0.02 + rng.normal(0, 0.2, n_anos)

        df = pd.DataFrame(
            {
                "trecho_id": trecho_id,
                "ano": anos,
                "iqa": iqa,
                "od_mg_l": od,
                "vazao_m3s_medio": 50 + rng.normal(0, 5, n_anos),
                "chuva_mm_media": 120 + rng.normal(0, 10, n_anos),
                # metade simulada, metade observada, real concentrada nos anos mais recentes —
                # reflete o padrão de verdade (CETESB real começa em 1978, simulado cobre o
                # resto), necessário para exercitar o fallback do item 2.
                "fonte_tipo": ["simulado" if a < 1980 + n_anos // 2 else "observado" for a in anos],
            }
        )
        for coluna in ("iqa", "od_mg_l"):
            for lag in (1, 2, 3):
                df[f"{coluna}_lag{lag}a"] = df[coluna].shift(lag)
            df[f"{coluna}_media_movel_5a"] = df[coluna].rolling(5, min_periods=2).mean()
        return df.dropna(subset=["iqa_lag3a", "od_mg_l_lag3a"]).reset_index(drop=True)

    return _construir
