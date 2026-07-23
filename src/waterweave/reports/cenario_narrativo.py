"""Narrativa textual do cenário simulado em `webapp/pages/5_Cenarios_Futuros.py`.

Mesmo espírito de `reports.narrative_generator` (regras sobre indicadores,
sem inventar causalidade), mas comparando dois cenários (controlado vs. não
controlado) ao longo de um horizonte de anos, e cobrindo o conjunto
estendido de parâmetros de `models.biofisico.parametros_estendidos`.
"""
from __future__ import annotations

from waterweave.thresholds import STATUS, status_para_iqa, status_para_od


def _status_label(chave: str) -> str:
    return STATUS[chave]["label"]


def _tendencia_texto(inicio: float, fim: float, unidade: str = "", casas: int = 1) -> str:
    delta = fim - inicio
    if abs(delta) < 10 ** (-casas):
        return f"estável em {fim:.{casas}f}{unidade}"
    direcao = "subiu" if delta > 0 else "caiu"
    return f"{direcao} de {inicio:.{casas}f}{unidade} para {fim:.{casas}f}{unidade} ({delta:+.{casas}f}{unidade})"


def gerar_narrativa_cenario(
    trecho_nome: str,
    horizonte_anos: int,
    config: dict,
    serie_controlado: list[dict],
    serie_nao_controlado: list[dict],
) -> str:
    """Gera o texto (Markdown) explicando o que a configuração escolhida pelo usuário faz com o
    rio ao longo do horizonte, comparando com a inação (cenário não controlado)."""
    c0, cf = serie_controlado[0], serie_controlado[-1]
    nc0, ncf = serie_nao_controlado[0], serie_nao_controlado[-1]

    status_iqa_cf = status_para_iqa(cf["iqa"])
    status_iqa_ncf = status_para_iqa(ncf["iqa"])
    status_od_cf = status_para_od(cf["od_mg_l"])

    paragrafos = []

    paragrafos.append(f"### Cenário simulado — {trecho_nome}, {horizonte_anos} anos à frente")

    # ---- Configuração escolhida -------------------------------------------------
    itens_config = []
    if config["esforco_sedimentar"] > 0:
        itens_config.append(f"controle de sedimentos/erosão em {config['esforco_sedimentar']}% de esforço")
    else:
        itens_config.append("nenhum controle de sedimentos/erosão")
    if config["esforco_esgoto"] > 0:
        itens_config.append(f"controle de esgoto/efluentes em {config['esforco_esgoto']}% de esforço")
    else:
        itens_config.append("nenhum controle de esgoto/efluentes")
    if config["esforco_agricola"] > 0:
        itens_config.append(f"controle de fertilizantes/agrotóxicos em {config['esforco_agricola']}% de esforço")
    else:
        itens_config.append("nenhum controle de fertilizantes/agrotóxicos")
    itens_config.append(f"vazão ecológica mínima reservada de {config['outorga_piso']:.0%}")
    itens_config.append(f"severidade climática assumida de {config['clima_pct']}%")
    paragrafos.append("**Configuração escolhida:** " + "; ".join(itens_config) + ".")

    # ---- Trajetória do cenário controlado ----------------------------------------
    paragrafos.append(
        f"**Se essas medidas forem mantidas:** o IQA simulado {_tendencia_texto(c0['iqa'], cf['iqa'])}, "
        f"terminando em situação **{_status_label(status_iqa_cf)}**. O Oxigênio Dissolvido "
        f"{_tendencia_texto(c0['od_mg_l'], cf['od_mg_l'], ' mg/L', 2)}, e a DBO "
        f"{_tendencia_texto(c0['dbo_mg_l'], cf['dbo_mg_l'], ' mg/L', 1)}. A Turbidez "
        f"{_tendencia_texto(c0['turbidez_ntu'], cf['turbidez_ntu'], ' NTU', 0)} e o Índice Biótico "
        f"(macroinvertebrados/peixes sensíveis) {_tendencia_texto(c0['indice_biotico'], cf['indice_biotico'], '', 0)}."
    )

    # ---- Comparação com não fazer nada -------------------------------------------
    diferenca_iqa = cf["iqa"] - ncf["iqa"]
    if diferenca_iqa > 3:
        comparacao = (
            f"Isso é **{diferenca_iqa:.0f} pontos de IQA melhor** do que se nada for feito — no cenário "
            f"não controlado, o IQA chegaria a apenas {ncf['iqa']:.0f} ({_status_label(status_iqa_ncf)}) "
            f"no mesmo horizonte."
        )
    elif diferenca_iqa < -3:
        comparacao = (
            f"Surpreendentemente, o cenário não controlado termina **{-diferenca_iqa:.0f} pontos de IQA acima** "
            f"deste — vale revisar os esforços escolhidos, ou isso reflete a resposta automática do Comitê "
            f"de Bacia (outorga) já presente em ambos os cenários."
        )
    else:
        comparacao = (
            f"O resultado fica próximo do cenário não controlado (IQA {ncf['iqa']:.0f}) — os esforços "
            f"escolhidos ainda não são suficientes para uma mudança clara neste horizonte."
        )
    paragrafos.append(comparacao)

    # ---- O que isso significa na prática -----------------------------------------
    consequencias = []
    if cf["e_coli_nmp_100ml"] > 100_000:
        consequencias.append(
            f"a contagem de E. coli projetada ({cf['e_coli_nmp_100ml']:,.0f} NMP/100 mL) ainda indicaria "
            "risco alto de contaminação por contato com a água ou consumo de peixe local."
        )
    elif cf["e_coli_nmp_100ml"] > 1_000:
        consequencias.append(
            f"a contagem de E. coli projetada ({cf['e_coli_nmp_100ml']:,.0f} NMP/100 mL) ainda mereceria "
            "cautela para atividades de contato direto (banho, pesca esportiva)."
        )
    else:
        consequencias.append("a contagem de E. coli projetada indicaria baixo risco sanitário direto.")

    if status_od_cf in ("critical", "serious"):
        consequencias.append(
            f"o Oxigênio Dissolvido projetado ({cf['od_mg_l']:.2f} mg/L) ainda causaria estresse para peixes "
            "e outros organismos aquáticos."
        )
    if cf["turbidez_ntu"] > 30:
        consequencias.append(
            f"a Turbidez projetada ({cf['turbidez_ntu']:.0f} NTU) ainda comprometeria a entrada de luz, "
            "prejudicando plantas aquáticas e a fotossíntese do rio."
        )
    if cf["fosforo_mg_l"] > 0.5 or cf["nitrogenio_mg_l"] > 5:
        consequencias.append(
            "os níveis de Fósforo/Nitrogênio projetados ainda favoreceriam a proliferação de algas "
            "(eutrofização), especialmente em trechos com água mais parada."
        )
    if cf["metais_toxicos_indice"] > 40:
        consequencias.append(
            "o índice de Metais Pesados e Tóxicos projetado ainda seria uma preocupação relevante."
        )
    if cf["indice_biotico"] >= 70:
        consequencias.append(
            "o Índice Biótico projetado sugere condições favoráveis ao retorno de espécies sensíveis à "
            "poluição (larvas de insetos aquáticos, peixes mais exigentes em qualidade de água)."
        )
    elif cf["indice_biotico"] < 40:
        consequencias.append(
            "o Índice Biótico projetado permaneceria baixo — pouca perspectiva de retorno de espécies "
            "sensíveis à poluição nesse horizonte."
        )

    paragrafos.append(
        "**O que isso significa na prática:** " + " ".join(consequencias)
    )

    paragrafos.append(
        "_Nota: simulação via ABM (Mesa) + balanço hídrico + Streeter-Phelps, com submodelos "
        "estendidos ancorados em médias reais 2012-2024 da CETESB. IQA é um proxy simplificado de "
        "OD/DBO; Índice Biótico e Metais/Tóxicos são proxies ilustrativos combinando os demais "
        "parâmetros simulados. Cada trecho é simulado de forma independente. Ver "
        "`models.hybrid_bridge` e `models.biofisico.parametros_estendidos` para as simplificações "
        "assumidas._"
    )

    return "\n\n".join(paragrafos)
