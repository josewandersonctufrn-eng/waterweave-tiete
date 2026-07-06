"""Camadas Silver e Gold: limpeza, padronização e agregação.

Silver: uma linha por (ponto_monitoramento, timestamp, variável), schema
único independente da fonte original, com `_fonte_tipo` preservado.

Gold: tabelas agregadas prontas para consumo — feature store para ML,
estado inicial para o ABM, e views pré-agregadas para o dashboard.
"""
