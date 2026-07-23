"""Narrativa textual do cenário simulado em `webapp/pages/5_Cenarios_Futuros.py`.

Mesmo espírito de `reports.narrative_generator` (regras sobre indicadores,
sem inventar causalidade), mas comparando dois cenários (controlado vs. não
controlado) ao longo de um horizonte de anos, e cobrindo o conjunto
estendido de parâmetros de `models.biofisico.parametros_estendidos`.

Retorna uma lista de seções `(titulo, corpo)` — não um único bloco de
markdown — para que `reports.pdf_generator` monte um PDF com numeração e
formatação ABNT (título numerado por seção, corpo justificado). Suporta os
4 idiomas do dashboard (`webapp.i18n`) via `idioma_atual()`.
"""
from __future__ import annotations

from waterweave.thresholds import STATUS, status_para_iqa, status_para_od
from waterweave.webapp import i18n


def _status_chave(status_key: str) -> str:
    return {"good": "bom", "warning": "atencao", "serious": "serio", "critical": "critico"}[status_key]


def _tendencia_texto(inicio: float, fim: float) -> str:
    delta = fim - inicio
    if abs(delta) < 1e-6:
        return i18n.t("cn.tend.estavel", fim=fim)
    chave = "cn.tend.subiu" if delta > 0 else "cn.tend.caiu"
    return i18n.t(chave, ini=inicio, fim=fim, delta=delta)


def gerar_narrativa_cenario(
    trecho_nome: str,
    horizonte_anos: int,
    config: dict,
    serie_controlado: list[dict],
    serie_nao_controlado: list[dict],
) -> list[tuple[str, str]]:
    """Gera as seções (título, corpo) explicando o que a configuração escolhida pelo usuário
    faz com o rio ao longo do horizonte, comparando com a inação (cenário não controlado)."""
    c0, cf = serie_controlado[0], serie_controlado[-1]
    ncf = serie_nao_controlado[-1]

    status_iqa_cf = status_para_iqa(cf["iqa"])
    status_iqa_ncf = status_para_iqa(ncf["iqa"])
    status_od_cf = status_para_od(cf["od_mg_l"])

    secoes: list[tuple[str, str]] = []

    # ---- Configuração escolhida --------------------------------------------------
    itens_config = [
        i18n.t("cn.config.sedimentar_on", pct=config["esforco_sedimentar"]) if config["esforco_sedimentar"] > 0
        else i18n.t("cn.config.sedimentar_off"),
        i18n.t("cn.config.esgoto_on", pct=config["esforco_esgoto"]) if config["esforco_esgoto"] > 0
        else i18n.t("cn.config.esgoto_off"),
        i18n.t("cn.config.agricola_on", pct=config["esforco_agricola"]) if config["esforco_agricola"] > 0
        else i18n.t("cn.config.agricola_off"),
        i18n.t("cn.config.outorga", pct=f"{config['outorga_piso']:.0%}"),
        i18n.t("cn.config.clima", pct=config["clima_pct"]),
    ]
    secoes.append((i18n.t("cn.sec.config"), i18n.t("cn.config.prefixo") + "; ".join(itens_config) + "."))

    # ---- Trajetória do cenário controlado -----------------------------------------
    corpo_resultado = i18n.t(
        "cn.resultado.texto",
        tend_iqa=_tendencia_texto(c0["iqa"], cf["iqa"]),
        status=i18n.t(f"status.{_status_chave(status_iqa_cf)}"),
        tend_od=_tendencia_texto(c0["od_mg_l"], cf["od_mg_l"]),
        tend_dbo=_tendencia_texto(c0["dbo_mg_l"], cf["dbo_mg_l"]),
        tend_turb=_tendencia_texto(c0["turbidez_ntu"], cf["turbidez_ntu"]),
        tend_bio=_tendencia_texto(c0["indice_biotico"], cf["indice_biotico"]),
    )
    secoes.append((i18n.t("cn.sec.resultado"), corpo_resultado))

    # ---- Comparação com não fazer nada --------------------------------------------
    diferenca_iqa = cf["iqa"] - ncf["iqa"]
    if diferenca_iqa > 3:
        comparacao = i18n.t("cn.comparacao.melhor", diff=diferenca_iqa, iqa_nc=ncf["iqa"], status_nc=i18n.t(f"status.{_status_chave(status_iqa_ncf)}"))
    elif diferenca_iqa < -3:
        comparacao = i18n.t("cn.comparacao.pior", diff=-diferenca_iqa)
    else:
        comparacao = i18n.t("cn.comparacao.proximo", iqa_nc=ncf["iqa"])
    secoes.append((i18n.t("cn.sec.comparacao"), comparacao))

    # ---- O que isso significa na prática -------------------------------------------
    consequencias = []
    if cf["e_coli_nmp_100ml"] > 100_000:
        consequencias.append(i18n.t("cn.impl.ecoli_alto", valor=f"{cf['e_coli_nmp_100ml']:,.0f}"))
    elif cf["e_coli_nmp_100ml"] > 1_000:
        consequencias.append(i18n.t("cn.impl.ecoli_moderado", valor=f"{cf['e_coli_nmp_100ml']:,.0f}"))
    else:
        consequencias.append(i18n.t("cn.impl.ecoli_baixo"))

    if status_od_cf in ("critical", "serious"):
        consequencias.append(i18n.t("cn.impl.od_critico", valor=cf["od_mg_l"]))
    if cf["turbidez_ntu"] > 30:
        consequencias.append(i18n.t("cn.impl.turbidez", valor=cf["turbidez_ntu"]))
    if cf["fosforo_mg_l"] > 0.5 or cf["nitrogenio_mg_l"] > 5:
        consequencias.append(i18n.t("cn.impl.eutrofizacao"))
    if cf["metais_toxicos_indice"] > 40:
        consequencias.append(i18n.t("cn.impl.metais"))
    if cf["indice_biotico"] >= 70:
        consequencias.append(i18n.t("cn.impl.biotico_bom"))
    elif cf["indice_biotico"] < 40:
        consequencias.append(i18n.t("cn.impl.biotico_baixo"))

    corpo_implicacoes = consequencias[0] if consequencias else ""
    for frase in consequencias[1:]:
        corpo_implicacoes += " " + frase[:1].upper() + frase[1:]
    secoes.append((i18n.t("cn.sec.implicacoes"), i18n.t("cn.impl.prefixo") + corpo_implicacoes))

    # ---- Nota metodológica ----------------------------------------------------------
    secoes.append((i18n.t("cn.sec.nota"), i18n.t("cn.nota")))

    return secoes
