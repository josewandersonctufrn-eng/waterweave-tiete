"""Ponte entre a calibração de `fator_clima` via CMIP6 (`ingestion.connectors.era5_cmip6`) e
`models.abm.scenarios.PARAMETROS_CENARIO`.

ACHADO DE PESQUISA (2026-07): a calibração real (`era5_cmip6.calibrar_fatores_clima_cenarios`)
precisa de rede e de um token pessoal da Copernicus Climate Data Store
(`config.CDS_API_KEY`/`WATERWEAVE_CDS_API_KEY`) — nenhum dos dois está disponível no boot da
aplicação Streamlit em produção (mesma restrição que impede `connectors.mapbiomas`/
`connectors.sensoriamento_historico` de rodar ao vivo no dashboard). Por isso a calibração é um
passo em LOTE, separado (`python -m waterweave.ingestion.connectors.era5_cmip6`), que grava o
resultado num JSON pequeno e versionado (`config.FATOR_CLIMA_CALIBRACAO_FILE`) — mesmo padrão
já usado para os modelos de ML (`models.ml.train` treina uma vez, salva `.joblib`,
`models.ml.predict_iqa` só carrega e usa). Este módulo é o lado "só carrega e usa": leitura
síncrona do JSON, sem rede, segura para chamar no import de `scenarios.py`.

Fallback: se a calibração ainda não rodou (JSON ausente) ou está corrompida, retorna o valor
`fallback` passado pelo chamador — o mesmo proxy simplificado fixo que `scenarios.py` já usava
antes desta correção (chuva reduzida em 25%) — com um log explicando o motivo, nunca um erro que
derrubaria a aplicação inteira por falta de uma calibração opcional.
"""
from __future__ import annotations

import json
import logging

from waterweave.config import FATOR_CLIMA_CALIBRACAO_FILE

logger = logging.getLogger(__name__)


def fator_clima_calibrado(cenario_id: str, fallback: float) -> float:
    """Retorna o `fator_clima` calibrado via CMIP6 para `cenario_id`, se
    `config.FATOR_CLIMA_CALIBRACAO_FILE` existir e tiver uma entrada para ele; caso contrário,
    retorna `fallback` — ver docstring do módulo para o racional completo do fallback."""
    if not FATOR_CLIMA_CALIBRACAO_FILE.exists():
        logger.info(
            "Calibração CMIP6 de fator_clima não encontrada (%s) — usando fallback %.2f para "
            "'%s'. Rode `python -m waterweave.ingestion.connectors.era5_cmip6` (com "
            "WATERWEAVE_CDS_API_KEY configurado) para calibrar com dado real.",
            FATOR_CLIMA_CALIBRACAO_FILE, fallback, cenario_id,
        )
        return fallback

    try:
        conteudo = json.loads(FATOR_CLIMA_CALIBRACAO_FILE.read_text(encoding="utf-8"))
        return float(conteudo["fatores_clima"][cenario_id])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as erro:
        logger.warning(
            "Calibração CMIP6 de fator_clima ilegível ou sem entrada para '%s' (%s) — usando "
            "fallback %.2f: %s",
            cenario_id, FATOR_CLIMA_CALIBRACAO_FILE, fallback, erro,
        )
        return fallback
