"""Camada Bronze: ingestão bruta de todas as fontes, sem transformação de esquema.

Cada módulo `bronze_*` lê uma fonte específica e grava uma tabela Delta em
`data/bronze/<fonte>` preservando o dado como veio (1 linha bronze == 1 linha
da fonte), acrescentando apenas colunas técnicas de proveniência:
`_ingested_at`, `_source_file`, `_fonte_tipo` (observado|simulado).
"""
