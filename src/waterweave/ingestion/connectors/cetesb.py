"""Conector para dados de qualidade de água da CETESB (IQA, DBO, OD, metais, etc.).

ATUALIZAÇÃO (ver docs/Auditoria_Engenharia_Dados_WaterWeave_Tiete.docx): a
lacuna que este conector pretendia fechar — observações reais da CETESB, em
vez da série simulada de `bronze_qualidade_solo.py` — já foi fechada para o
histórico 1978-2024 por `ingestion.bronze_cetesb` (ingestão em lote de
`base_de_dados_pontos.xlsx`, um export local já existente, não uma chamada de
API). O papel que resta para ESTE conector é estritamente incremental: buscar
apenas os boletins publicados DEPOIS do fim do export local (hoje 2024), nas
rodadas mensais seguintes — mas, ao contrário de `connectors.ana_snirh`, NÃO
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

Decisão formalizada (contexto/decisão/consequência/gatilho para revisitar)
em README.md, seção "Conector CETESB — decisão formalizada". Guardas de
regressão em `tests/test_cetesb_connector.py`: a mensagem desta exceção e o
skip gracioso de `ingestion.monthly_job.run_live_connectors`.
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
