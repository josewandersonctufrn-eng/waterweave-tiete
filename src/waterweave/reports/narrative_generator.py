"""Gerador de relatórios textuais sintéticos sobre a saúde de um trecho do rio.

Implementação atual opera na granularidade disponível hoje — trecho x ano,
vinda de `webapp.data_loader.load_qualidade_historica()` (série simulada).
Quando a camada Gold tiver granularidade por ponto de monitoramento
(`gold.serie_temporal_ponto`) e `models.ml.predict_iqa` estiver treinado,
`gerar_relatorio_trecho` deve trocar sua fonte de dado para essas duas,
mantendo a mesma assinatura de saída (string PT-BR).
"""
from __future__ import annotations

import pandas as pd

from waterweave.config import TRECHOS
from waterweave.thresholds import STATUS, status_para_iqa, status_para_od

JANELA_TENDENCIA_ANOS = 10


def _tendencia(serie_trecho: pd.DataFrame, coluna: str, ano_referencia: int) -> tuple[str, float]:
    """Retorna (direção, variação_absoluta) comparando `ano_referencia` com `JANELA_TENDENCIA_ANOS` antes."""
    ano_base = ano_referencia - JANELA_TENDENCIA_ANOS
    valor_ref = serie_trecho.loc[serie_trecho["ano"] == ano_referencia, coluna]
    valor_base = serie_trecho.loc[serie_trecho["ano"] == ano_base, coluna]
    if valor_ref.empty or valor_base.empty:
        return "estável", 0.0
    variacao = float(valor_ref.iloc[0] - valor_base.iloc[0])
    if abs(variacao) < 1e-6:
        return "estável", variacao
    return ("melhora" if variacao > 0 else "piora", variacao)


def gerar_relatorio_trecho(qualidade: pd.DataFrame, trecho_id: str, ano: int) -> str:
    """Gera o texto de análise automatizada para `trecho_id` no `ano` informado."""
    serie_trecho = qualidade[qualidade["trecho_id"] == trecho_id].sort_values("ano")
    linha_ano = serie_trecho[serie_trecho["ano"] == ano]
    nome_trecho = TRECHOS[trecho_id].nome if trecho_id in TRECHOS else trecho_id
    if linha_ano.empty:
        return f"Sem dados de qualidade da água para {nome_trecho} em {ano}."

    iqa = float(linha_ano["iqa"].iloc[0])
    od = float(linha_ano["od_mg_l"].iloc[0])
    dbo = float(linha_ano["dbo_mg_l"].iloc[0])
    uso_solo = str(linha_ano["uso_solo"].iloc[0])

    media_historica_iqa = serie_trecho["iqa"].mean()
    status_iqa = STATUS[status_para_iqa(iqa)]
    status_od = STATUS[status_para_od(od)]

    direcao_iqa, delta_iqa = _tendencia(serie_trecho, "iqa", ano)
    direcao_od, delta_od = _tendencia(serie_trecho, "od_mg_l", ano)

    vs_historico = "acima da" if iqa >= media_historica_iqa else "abaixo da"

    paragrafos = [
        f"### Análise automatizada — {nome_trecho}, {ano}",
        (
            f"{status_iqa['icon']} O trecho **{nome_trecho}** apresentou IQA médio de **{iqa:.1f}** em {ano} "
            f"({status_iqa['label']}), {vs_historico} média histórica da série (1940-{serie_trecho['ano'].max()}) "
            f"de {media_historica_iqa:.1f}."
        ),
        (
            f"{status_od['icon']} O Oxigênio Dissolvido está em **{od:.2f} mg/L** ({status_od['label']}) e a "
            f"Demanda Bioquímica de Oxigênio em **{dbo:.2f} mg/L**. Uso do solo predominante no trecho: {uso_solo}."
        ),
        (
            f"Nos últimos {JANELA_TENDENCIA_ANOS} anos, o IQA apresentou tendência de **{direcao_iqa}** "
            f"({delta_iqa:+.1f} pontos) e o OD tendência de **{direcao_od}** ({delta_od:+.2f} mg/L)."
        ),
    ]

    if od < 4:
        paragrafos.append(
            "⚠️ **Alerta:** OD abaixo de 4 mg/L indica estresse para a biota aquática — "
            "recomenda-se priorizar fiscalização de lançamentos de efluentes neste trecho."
        )

    paragrafos.append(
        "_Nota de proveniência: indicadores desta seção vêm de uma série simulada (proxy histórico), "
        "não de telemetria direta — ver `ingestion.bronze_qualidade_solo`._"
    )
    return "\n\n".join(paragrafos)
