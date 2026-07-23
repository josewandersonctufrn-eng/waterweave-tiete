"""Gerador de relatórios textuais sintéticos sobre a saúde de um trecho do rio.

Implementação atual opera na granularidade disponível hoje — trecho x ano,
vinda de `webapp.data_loader.load_qualidade_historica()` (série simulada).
Quando a camada Gold tiver granularidade por ponto de monitoramento
(`gold.serie_temporal_ponto`) e `models.ml.predict_iqa` estiver treinado,
`gerar_relatorio_trecho` deve trocar sua fonte de dado para essas duas,
mantendo a mesma assinatura de saída.

Suporta os 4 idiomas do dashboard (`webapp.i18n`) via parâmetro `idioma` —
a lógica/limiares são os mesmos em qualquer idioma, só o texto muda.
"""
from __future__ import annotations

import pandas as pd

from waterweave.thresholds import STATUS, status_para_iqa, status_para_od
from waterweave.webapp import i18n
from waterweave.webapp.theme import TRECHO_LABEL

JANELA_TENDENCIA_ANOS = 10


def _tendencia(serie_trecho: pd.DataFrame, coluna: str, ano_referencia: int) -> tuple[str, float]:
    """Retorna (direção, variação_absoluta) comparando `ano_referencia` com `JANELA_TENDENCIA_ANOS` antes."""
    ano_base = ano_referencia - JANELA_TENDENCIA_ANOS
    valor_ref = serie_trecho.loc[serie_trecho["ano"] == ano_referencia, coluna]
    valor_base = serie_trecho.loc[serie_trecho["ano"] == ano_base, coluna]
    if valor_ref.empty or valor_base.empty:
        return i18n.t("rel.estavel"), 0.0
    variacao = float(valor_ref.iloc[0] - valor_base.iloc[0])
    if abs(variacao) < 1e-6:
        return i18n.t("rel.estavel"), variacao
    return (i18n.t("rel.melhora") if variacao > 0 else i18n.t("rel.piora")), variacao


def gerar_relatorio_trecho(qualidade: pd.DataFrame, trecho_id: str, ano: int) -> str:
    """Gera o texto de análise automatizada para `trecho_id` no `ano` informado, no idioma
    corrente da sessão (`webapp.i18n.idioma_atual`)."""
    serie_trecho = qualidade[qualidade["trecho_id"] == trecho_id].sort_values("ano")
    linha_ano = serie_trecho[serie_trecho["ano"] == ano]
    nome_trecho = TRECHO_LABEL[trecho_id] if trecho_id in TRECHO_LABEL else trecho_id
    if linha_ano.empty:
        return i18n.t("rel.sem_dados", trecho=nome_trecho, ano=ano)

    iqa = float(linha_ano["iqa"].iloc[0])
    od = float(linha_ano["od_mg_l"].iloc[0])
    dbo = float(linha_ano["dbo_mg_l"].iloc[0])
    uso_solo = str(linha_ano["uso_solo"].iloc[0])

    media_historica_iqa = serie_trecho["iqa"].mean()
    status_iqa = STATUS[status_para_iqa(iqa)]
    status_od = STATUS[status_para_od(od)]

    direcao_iqa, delta_iqa = _tendencia(serie_trecho, "iqa", ano)
    direcao_od, delta_od = _tendencia(serie_trecho, "od_mg_l", ano)

    comparacao = i18n.t("rel.acima_da") if iqa >= media_historica_iqa else i18n.t("rel.abaixo_da")

    paragrafos = [
        f"### {i18n.t('rel.titulo_secao', trecho=nome_trecho, ano=ano)}",
        i18n.t(
            "rel.par_iqa", icon=status_iqa["icon"], trecho=nome_trecho, iqa=iqa, ano=ano,
            status=i18n.t(f"status.{_status_chave(status_para_iqa(iqa))}"), comparacao=comparacao,
            ano_max=serie_trecho["ano"].max(), media=media_historica_iqa,
        ),
        i18n.t(
            "rel.par_od_dbo", icon=status_od["icon"], od=od,
            status=i18n.t(f"status.{_status_chave(status_para_od(od))}"), dbo=dbo, uso_solo=uso_solo,
        ),
        i18n.t(
            "rel.par_tendencia", janela=JANELA_TENDENCIA_ANOS, dir_iqa=direcao_iqa, delta_iqa=delta_iqa,
            dir_od=direcao_od, delta_od=delta_od,
        ),
    ]

    if od < 4:
        paragrafos.append(i18n.t("rel.alerta_od"))

    paragrafos.append(i18n.t("rel.nota_proveniencia"))
    return "\n\n".join(paragrafos)


def _status_chave(status_key: str) -> str:
    return {"good": "bom", "warning": "atencao", "serious": "serio", "critical": "critico"}[status_key]
