"""Conector para dados de qualidade de água da CETESB (IQA, DBO, OD, metais, etc.).

Substituirá `bronze_qualidade_solo.py` (hoje simulado) por observações reais
publicadas pela CETESB — mas, ao contrário de `connectors.ana_snirh`, NÃO
há uma API pública documentada e estável para isso hoje (pesquisado em
2026-07):

  - O "Catálogo de Dados Abertos" da CETESB
    (https://cetesb.sp.gov.br/catalogo-de-dados-abertos/) e o sistema
    INFOÁGUAS (https://cetesb.sp.gov.br/infoaguas/) existem e são públicos,
    mas expõem apenas visualizações e DOWNLOAD DE PLANILHAS/relatórios via
    portal web (site institucional em IBM WebSphere Portal) — não uma rota
    HTTP com parâmetros de consulta como a `HidroSerieHistorica` da ANA.
  - Não confundir com o Relatório de Qualidade das Águas Interiores (PDF
    anual) — também sem endpoint de dados estruturados.

Implementação real, quando priorizada, seguiria o mesmo padrão dos módulos
`bronze_daee_*`: baixar a planilha/arquivo mais recente do INFOÁGUAS
manualmente (ou via automação de navegador, já que é um portal server-side)
e escrever um parser dedicado — não uma chamada de API parametrizada como
esta função sugere. Mantido como `NotImplementedError` até essa decisão.
"""
from __future__ import annotations

from datetime import date

import pandas as pd


def fetch_new_records(since: date, pontos_monitoramento: list[str] | None = None) -> pd.DataFrame:
    """Busca boletins de qualidade de água publicados pela CETESB desde `since`.

    Ver docstring do módulo: não há API pública para isso hoje — só
    planilhas para download manual no INFOÁGUAS.
    """
    raise NotImplementedError(
        "CETESB não expõe API pública de dados estruturados (verificado em 2026-07) — "
        "ver docstring de waterweave.ingestion.connectors.cetesb para o caminho de implementação real."
    )
