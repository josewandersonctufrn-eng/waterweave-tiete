"""Conector para séries de uso e cobertura do solo do MapBiomas.

Fornece a série anual de classes de cobertura do solo por município/bacia,
usada tanto pelo modelo biofísico (`models.biofisico.uso_solo`) quanto pelo
ABM (estado observável para decisões de outorga/multa).

Pesquisado em 2026-07 — duas rotas de acesso público existem, nenhuma
implementada ainda aqui:

  1. **Google Earth Engine** (`ee.Image` da coleção
     `projects/mapbiomas-public/assets/brazil/lulc/collection9/...`):
     permite recorte por geometria (bacia do Tietê) e cálculo de área por
     classe ano a ano, mas exige o usuário rodar `earthengine authenticate`
     (fluxo OAuth interativo) — não executável neste ambiente não
     interativo. É a rota mais flexível para recorte fino por bacia.
  2. **Estatísticas pré-computadas por município** (download direto, SEM
     Earth Engine): a página https://brasil.mapbiomas.org/en/estatisticas/
     disponibiliza uma planilha única "Biomes, states and municipalities"
     com área (ha) por classe de uso do solo, 1985-2024, para todos os
     municípios do Brasil, via link do Google Drive. Não precisa de conta
     Google Earth Engine — só teria que lidar com o fluxo de confirmação de
     download de arquivo grande do Google Drive e depois filtrar para os
     municípios do Tietê. Candidata mais realista para uma primeira
     implementação sem depender de autenticação do usuário, mas o arquivo é
     nacional e pesado (não testado ponta a ponta aqui por tempo).

Enquanto isso, `uso_solo` continua vindo da série simulada em
`silver.qualidade` (ver aviso de proveniência em `bronze_qualidade_solo`).
"""
from __future__ import annotations

from datetime import date

import pandas as pd


def fetch_new_records(since: date, bacias: list[str] | None = None) -> pd.DataFrame:
    """Busca a coleção mais recente do MapBiomas para as sub-bacias do Tietê desde `since`.

    Ver docstring do módulo para as duas rotas de acesso pesquisadas
    (Earth Engine com autenticação do usuário, ou planilha nacional por
    município) — nenhuma implementada ainda.
    """
    raise NotImplementedError(
        "Requer `earthengine authenticate` do usuário (rota 1) ou implementar o download/filtro "
        "da planilha nacional por município (rota 2) — ver docstring de waterweave.ingestion.connectors.mapbiomas."
    )
