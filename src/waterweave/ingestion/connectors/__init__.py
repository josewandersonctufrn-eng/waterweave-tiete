"""Conectores para fontes externas ao vivo, a serem acionados pelo job mensal.

Cada conector implementa `fetch_new_records(since: date) -> pd.DataFrame`
com o mesmo contrato, para que `monthly_job.py` possa iterar sobre todos
sem conhecer detalhes de autenticação/paginação de cada API.
"""
