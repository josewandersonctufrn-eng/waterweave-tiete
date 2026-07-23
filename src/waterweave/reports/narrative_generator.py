"""Gerador de relatórios textuais sintéticos sobre a saúde de um trecho do rio.

Implementação atual opera na granularidade disponível hoje — trecho x ano,
vinda de `webapp.data_loader.load_qualidade_historica()` (série simulada).
Quando a camada Gold tiver granularidade por ponto de monitoramento
(`gold.serie_temporal_ponto`) e `models.ml.predict_iqa` estiver treinado,
`gerar_relatorio_trecho` deve trocar sua fonte de dado para essas duas,
mantendo a mesma assinatura de saída.

Suporta os 4 idiomas do dashboard (`webapp.i18n`) via parâmetro `idioma` —
a lógica/limiares são os mesmos em qualquer idioma, só o texto muda.

`gerar_relatorio_trecho` produz o texto do Modelo Resumido (Opção A —
exibido também na tela e reaproveitado por `reports.pdf_generator`).
`gerar_relatorio_trecho_completo` produz o conteúdo do Modelo Completo
(Opção B / NBR 10719) para o mesmo trecho/ano — ambos compartilham o
mesmo cálculo de indicadores via `_indicadores`, garantindo que os dois
modelos sempre reportem os mesmos números.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from waterweave.thresholds import STATUS, status_para_iqa, status_para_od
from waterweave.webapp import i18n
from waterweave.webapp.theme import TRECHO_LABEL

JANELA_TENDENCIA_ANOS = 10


@dataclass
class _Indicadores:
    nome_trecho: str
    iqa: float
    od: float
    dbo: float
    uso_solo: str
    media_historica_iqa: float
    ano_max: int
    status_iqa_chave: str
    status_od_chave: str
    comparacao: str
    direcao_iqa: str
    delta_iqa: float
    direcao_od: str
    delta_od: float


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


def _status_chave(status_key: str) -> str:
    return {"good": "bom", "warning": "atencao", "serious": "serio", "critical": "critico"}[status_key]


def _indicadores(qualidade: pd.DataFrame, trecho_id: str, ano: int) -> _Indicadores | None:
    """Calcula os indicadores compartilhados pelos dois modelos de relatório (Resumido e
    Completo) — `None` se não houver dado para `trecho_id`/`ano`."""
    serie_trecho = qualidade[qualidade["trecho_id"] == trecho_id].sort_values("ano")
    linha_ano = serie_trecho[serie_trecho["ano"] == ano]
    nome_trecho = TRECHO_LABEL[trecho_id] if trecho_id in TRECHO_LABEL else trecho_id
    if linha_ano.empty:
        return None

    iqa = float(linha_ano["iqa"].iloc[0])
    od = float(linha_ano["od_mg_l"].iloc[0])
    dbo = float(linha_ano["dbo_mg_l"].iloc[0])
    uso_solo = str(linha_ano["uso_solo"].iloc[0])
    media_historica_iqa = float(serie_trecho["iqa"].mean())

    direcao_iqa, delta_iqa = _tendencia(serie_trecho, "iqa", ano)
    direcao_od, delta_od = _tendencia(serie_trecho, "od_mg_l", ano)
    comparacao = i18n.t("rel.acima_da") if iqa >= media_historica_iqa else i18n.t("rel.abaixo_da")

    return _Indicadores(
        nome_trecho=nome_trecho,
        iqa=iqa,
        od=od,
        dbo=dbo,
        uso_solo=uso_solo,
        media_historica_iqa=media_historica_iqa,
        ano_max=int(serie_trecho["ano"].max()),
        status_iqa_chave=status_para_iqa(iqa),
        status_od_chave=status_para_od(od),
        comparacao=comparacao,
        direcao_iqa=direcao_iqa,
        delta_iqa=delta_iqa,
        direcao_od=direcao_od,
        delta_od=delta_od,
    )


def gerar_relatorio_trecho(qualidade: pd.DataFrame, trecho_id: str, ano: int) -> str:
    """Gera o texto de análise automatizada (Modelo Resumido / Opção A) para `trecho_id` no
    `ano` informado, no idioma corrente da sessão (`webapp.i18n.idioma_atual`)."""
    ind = _indicadores(qualidade, trecho_id, ano)
    if ind is None:
        nome_trecho = TRECHO_LABEL[trecho_id] if trecho_id in TRECHO_LABEL else trecho_id
        return i18n.t("rel.sem_dados", trecho=nome_trecho, ano=ano)

    status_iqa = STATUS[ind.status_iqa_chave]
    status_od = STATUS[ind.status_od_chave]

    paragrafos = [
        f"### {i18n.t('rel.titulo_secao', trecho=ind.nome_trecho, ano=ano)}",
        i18n.t(
            "rel.par_iqa", icon=status_iqa["icon"], trecho=ind.nome_trecho, iqa=ind.iqa, ano=ano,
            status=i18n.t(f"status.{_status_chave(ind.status_iqa_chave)}"), comparacao=ind.comparacao,
            ano_max=ind.ano_max, media=ind.media_historica_iqa,
        ),
        i18n.t(
            "rel.par_od_dbo", icon=status_od["icon"], od=ind.od,
            status=i18n.t(f"status.{_status_chave(ind.status_od_chave)}"), dbo=ind.dbo, uso_solo=ind.uso_solo,
        ),
        i18n.t(
            "rel.par_tendencia", janela=JANELA_TENDENCIA_ANOS, dir_iqa=ind.direcao_iqa, delta_iqa=ind.delta_iqa,
            dir_od=ind.direcao_od, delta_od=ind.delta_od,
        ),
    ]

    if ind.od < 4:
        paragrafos.append(i18n.t("rel.alerta_od"))

    paragrafos.append(i18n.t("rel.nota_proveniencia"))
    return "\n\n".join(paragrafos)


def resumo_trecho_item(qualidade: pd.DataFrame, trecho_id: str, ano: int) -> str | None:
    """Fragmento curto "{trecho} apresentou ICA de X (status)" — usado por
    `reports.pdf_generator` para compor o Resumo consolidado do relatório "todos os trechos"
    no Modelo Completo (Opção B). `None` se não houver dado."""
    ind = _indicadores(qualidade, trecho_id, ano)
    if ind is None:
        return None
    return i18n.t(
        "rel.b.resumo_trecho_item", trecho=ind.nome_trecho, iqa=ind.iqa,
        status=i18n.t(f"status.{_status_chave(ind.status_iqa_chave)}"),
    )


@dataclass
class RelatorioTrechoCompleto:
    """Conteúdo do relatório automatizado no Modelo Completo (Opção B / NBR 10719).

    `desenvolvimento` e `resultados_discussao` são listas de parágrafos, renderizadas como
    parágrafos justificados separados dentro da mesma seção."""

    resumo: str
    palavras_chave: str
    introducao_contexto: str
    objetivo_geral: str
    objetivos_especificos: str
    metodologia_intro: str
    metodologia_corpo: str
    desenvolvimento_intro: str
    desenvolvimento: list[str]
    resultados_discussao: list[str]
    conclusao: str
    referencias: str
    anexos: str


def gerar_relatorio_trecho_completo(qualidade: pd.DataFrame, trecho_id: str, ano: int) -> RelatorioTrechoCompleto | None:
    """Gera o conteúdo do relatório automatizado no Modelo Completo (Opção B / NBR 10719) para
    `trecho_id` no `ano` informado — `None` se não houver dado (mesma condição de
    `gerar_relatorio_trecho`). Reaproveita os mesmos indicadores e frases de dado já usados no
    Modelo Resumido (`rel.par_iqa`/`rel.par_od_dbo`/`rel.par_tendencia`/`rel.alerta_od`),
    reorganizados na estrutura textual da NBR 10719."""
    ind = _indicadores(qualidade, trecho_id, ano)
    if ind is None:
        return None

    status_iqa = STATUS[ind.status_iqa_chave]
    status_od = STATUS[ind.status_od_chave]

    par_iqa = i18n.t(
        "rel.par_iqa", icon=status_iqa["icon"], trecho=ind.nome_trecho, iqa=ind.iqa, ano=ano,
        status=i18n.t(f"status.{_status_chave(ind.status_iqa_chave)}"), comparacao=ind.comparacao,
        ano_max=ind.ano_max, media=ind.media_historica_iqa,
    )
    par_od_dbo = i18n.t(
        "rel.par_od_dbo", icon=status_od["icon"], od=ind.od,
        status=i18n.t(f"status.{_status_chave(ind.status_od_chave)}"), dbo=ind.dbo, uso_solo=ind.uso_solo,
    )
    par_tendencia = i18n.t(
        "rel.par_tendencia", janela=JANELA_TENDENCIA_ANOS, dir_iqa=ind.direcao_iqa, delta_iqa=ind.delta_iqa,
        dir_od=ind.direcao_od, delta_od=ind.delta_od,
    )

    resultados_discussao = [par_tendencia]
    if ind.od < 4:
        resultados_discussao.append(i18n.t("rel.alerta_od"))
    resultados_discussao.append(i18n.t("rel.nota_proveniencia"))

    resumo = i18n.t(
        "rel.b.resumo_texto",
        trecho=ind.nome_trecho, ano=ano, iqa=ind.iqa,
        status=i18n.t(f"status.{_status_chave(ind.status_iqa_chave)}"), comparacao=ind.comparacao,
        ano_max=ind.ano_max, media=ind.media_historica_iqa, od=ind.od, dbo=ind.dbo,
        janela=JANELA_TENDENCIA_ANOS, dir_iqa=ind.direcao_iqa, delta_iqa=ind.delta_iqa,
        conclusao_curta=i18n.t(f"rel.b.conclusao_curta.{_status_chave(ind.status_iqa_chave)}"),
    )

    return RelatorioTrechoCompleto(
        resumo=resumo,
        palavras_chave=i18n.t("rel.b.palavras_chave_lista"),
        introducao_contexto=i18n.t("cn.b.introducao_contexto"),
        objetivo_geral=i18n.t("rel.b.objetivo_geral_texto", trecho=ind.nome_trecho, ano=ano),
        objetivos_especificos=i18n.t("rel.b.objetivos_especificos_itens"),
        metodologia_intro=i18n.t("rel.b.metodologia_intro"),
        metodologia_corpo=i18n.t("cn.nota"),
        desenvolvimento_intro=i18n.t("rel.b.desenvolvimento_intro", trecho=ind.nome_trecho, ano=ano),
        desenvolvimento=[par_iqa, par_od_dbo],
        resultados_discussao=resultados_discussao,
        conclusao=i18n.t("rel.b.conclusao_texto", trecho=ind.nome_trecho, status=i18n.t(f"status.{_status_chave(ind.status_iqa_chave)}"), dir_iqa=ind.direcao_iqa, janela=JANELA_TENDENCIA_ANOS),
        referencias=i18n.t("cn.b.referencias_lista"),
        anexos=i18n.t("rel.b.anexos_texto"),
    )
