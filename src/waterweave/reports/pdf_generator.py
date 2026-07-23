"""Exportação em PDF dos relatórios textuais (`narrative_generator`, `cenario_narrativo`).

Usa fpdf2 (pure-Python, sem dependência de binário de sistema como
wkhtmltopdf/Chromium) para manter o build do Streamlit Community Cloud leve.
As fontes core do fpdf2 cobrem apenas Latin-1 — suficiente para PT-BR/EN/FR/ES
acentuados, mas não para emojis, por isso os ícones de status são convertidos
para marcadores textuais equivalentes antes da renderização.

Formatação ABNT (NBR 14724): margens 3cm esquerda/superior e 2cm direita/
inferior, fonte Helvetica (equivalente a Arial) 12pt, espaçamento ~1,5 entre
linhas, texto **justificado**, seções numeradas em caixa alta e negrito,
legendas de tabela acima ("Tabela N –") e de gráfico abaixo ("Gráfico N –"),
com indicação de fonte — em vez de `write_html` (que não justifica texto no
fpdf2), o corpo é renderizado via `multi_cell(..., align="J", markdown=True)`.
"""
from __future__ import annotations

import re

from fpdf import FPDF

from waterweave.config import TRECHOS
from waterweave.reports.cenario_narrativo import gerar_narrativa_cenario
from waterweave.reports.narrative_generator import gerar_relatorio_trecho
from waterweave.webapp import i18n

_EMOJI_PARA_TEXTO = {
    "✅": "[BOM] ",
    "⚠️": "[ATENÇÃO/ALERTA] ",
    "🟠": "[SÉRIO] ",
    "🔴": "[CRÍTICO] ",
}

# As fontes core do fpdf2 (Helvetica) só cobrem Latin-1: cabe acento PT/EN/FR/ES,
# mas não pontuação tipográfica como travessão/aspas curvas.
_TIPOGRAFIA_PARA_LATIN1 = {
    "—": "-",
    "–": "-",
    "…": "...",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
}

# ABNT NBR 14724: margens 3cm (esquerda/superior) e 2cm (direita/inferior).
_MARGEM_ESQUERDA_MM = 30.0
_MARGEM_SUPERIOR_MM = 30.0
_MARGEM_DIREITA_MM = 20.0
_MARGEM_INFERIOR_MM = 20.0
_ALTURA_LINHA_MM = 7.0  # ~1,5 espaçamento para corpo 12pt
_TAMANHO_CORPO = 12
_TAMANHO_NOTA = 10


def _para_latin1_seguro(texto: str) -> str:
    """Garante que `texto` seja renderizável pelas fontes core (Latin-1) do fpdf2."""
    for original, substituto in _TIPOGRAFIA_PARA_LATIN1.items():
        texto = texto.replace(original, substituto)
    return texto.encode("latin-1", errors="replace").decode("latin-1")


_CODIGO_INLINE = re.compile(r"`([^`]+)`")
_ITALICO_SIMPLES = re.compile(r"(?<!_)_([^_]+)_(?!_)")


def _preparar_texto(texto: str) -> str:
    """Prepara um trecho de texto para `multi_cell(..., markdown=True)`: troca emoji por
    marcador textual, remove crases (identificadores de código viram texto simples) e
    normaliza itálico de sublinhado único (`_texto_`) para o duplo que o fpdf2 reconhece.

    Protege primeiro os identificadores entre crases (ex.: `models.hybrid_bridge`) com um
    placeholder sem underscore — senão o underscore interno do identificador é confundido
    com marcador de itálico pelo regex de sublinhado único (bug real encontrado ao testar
    a nota de rodapé, que continha dois identificadores de código na mesma frase).
    """
    for emoji, marcador in _EMOJI_PARA_TEXTO.items():
        texto = texto.replace(emoji, marcador)

    codigos: list[str] = []

    def _guardar_codigo(match: re.Match[str]) -> str:
        codigos.append(match.group(1))
        return f"\x00{len(codigos) - 1}\x00"

    texto = _CODIGO_INLINE.sub(_guardar_codigo, texto)
    texto = _ITALICO_SIMPLES.sub(r"__\1__", texto)
    for indice, codigo in enumerate(codigos):
        texto = texto.replace(f"\x00{indice}\x00", codigo)

    return _para_latin1_seguro(texto)


def _novo_pdf_abnt(titulo: str) -> FPDF:
    """Novo PDF com margens/fonte no padrão ABNT NBR 14724 (ver docstring do módulo)."""
    pdf = FPDF()
    pdf.set_title(titulo)
    pdf.set_margins(_MARGEM_ESQUERDA_MM, _MARGEM_SUPERIOR_MM, _MARGEM_DIREITA_MM)
    pdf.set_auto_page_break(auto=True, margin=_MARGEM_INFERIOR_MM)
    pdf.add_page()
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)
    return pdf


def _titulo_capa(pdf: FPDF, titulo: str, subtitulo: str = "") -> None:
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 9, _para_latin1_seguro(titulo.upper()), align="C")
    if subtitulo:
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 12)
        pdf.multi_cell(0, 7, _para_latin1_seguro(subtitulo), align="C")
    pdf.ln(4)
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)


def _titulo_secao_abnt(pdf: FPDF, numero: int, titulo: str) -> None:
    pdf.set_font("Helvetica", "B", 12.5)
    pdf.ln(2)
    pdf.multi_cell(0, 7, _para_latin1_seguro(f"{numero} {titulo.upper()}"), align="L")
    pdf.ln(1)
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)


def _paragrafo_abnt(pdf: FPDF, texto: str, tamanho: float = _TAMANHO_CORPO, italico: bool = False) -> None:
    if italico:
        pdf.set_font("Helvetica", "I", tamanho)
    else:
        pdf.set_font("Helvetica", size=tamanho)
    pdf.multi_cell(0, _ALTURA_LINHA_MM * (tamanho / _TAMANHO_CORPO), _preparar_texto(texto), align="J", markdown=True)
    pdf.ln(1)
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)


# ---------------------------------------------------------------------------
# Relatório Automático (narrative_generator) — trecho x ano
# ---------------------------------------------------------------------------

def _renderizar_relatorio_trecho(pdf: FPDF, relatorio_md: str) -> None:
    """Divide o markdown gerado por `narrative_generator.gerar_relatorio_trecho` em
    título + parágrafos justificados, com a nota final em fonte menor (estilo ABNT
    de nota de rodapé/observação)."""
    blocos = relatorio_md.split("\n\n")
    for bloco in blocos:
        if bloco.startswith("### "):
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(0, 7.5, _preparar_texto(bloco[4:]), align="L")
            pdf.ln(1)
            pdf.set_font("Helvetica", size=_TAMANHO_CORPO)
        elif bloco.startswith("_") and bloco.endswith("_"):
            _paragrafo_abnt(pdf, bloco.strip("_"), tamanho=_TAMANHO_NOTA, italico=True)
        else:
            _paragrafo_abnt(pdf, bloco)


def gerar_relatorio_trecho_pdf(qualidade, trecho_id: str, ano: int) -> bytes:
    """Gera o PDF do relatório automatizado de um único trecho, no ano informado."""
    from waterweave.webapp.theme import TRECHO_LABEL

    nome_trecho = TRECHO_LABEL[trecho_id] if trecho_id in TRECHOS else trecho_id
    relatorio_md = gerar_relatorio_trecho(qualidade, trecho_id, ano)

    pdf = _novo_pdf_abnt(f"Relatorio Automatico - {nome_trecho} ({ano})")
    _renderizar_relatorio_trecho(pdf, relatorio_md)
    return bytes(pdf.output())


def gerar_relatorio_completo_pdf(qualidade, ano: int) -> bytes:
    """Gera o PDF consolidado do relatório automatizado de todos os trechos, no mesmo ano."""
    pdf = _novo_pdf_abnt(f"Relatorio Automatico - Todos os trechos ({ano})")
    for indice, trecho_id in enumerate(TRECHOS):
        if indice > 0:
            pdf.ln(4)
        relatorio_md = gerar_relatorio_trecho(qualidade, trecho_id, ano)
        _renderizar_relatorio_trecho(pdf, relatorio_md)
    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Cenário Futuro (cenario_narrativo) — gráfico + tabela em formato ABNT
# ---------------------------------------------------------------------------

def _garantir_espaco(pdf: FPDF, altura_necessaria_mm: float) -> None:
    """Insere uma quebra de página manual se `altura_necessaria_mm` não couber no restante da
    página atual. Necessário porque os desenhos manuais (`pdf.rect`/`pdf.line`) NÃO acionam o
    page-break automático do fpdf2 como `multi_cell` faz — sem essa checagem, um gráfico ou
    tabela que começa perto do rodapé é cortado/renderizado em branco na página seguinte (bug
    real encontrado ao testar o relatório com uma seção "Nota Metodológica" longa antes)."""
    espaco_disponivel = pdf.h - pdf.b_margin - pdf.get_y()
    if espaco_disponivel < altura_necessaria_mm:
        pdf.add_page()


def _polilinha(pdf: FPDF, pontos: list[tuple[float, float]]) -> None:
    for (x1, y1), (x2, y2) in zip(pontos, pontos[1:]):
        pdf.line(x1, y1, x2, y2)


def _desenhar_grafico_iqa(pdf: FPDF, serie_controlado: list[dict], serie_nao_controlado: list[dict]) -> None:
    """Gráfico de linha (IQA x ano, controlado vs. não controlado) desenhado com as primitivas
    nativas do fpdf2 (sem matplotlib/kaleido — mantém o build do Streamlit Cloud enxuto).
    Legenda ABAIXO do gráfico (convenção ABNT para figuras)."""
    largura, altura = 160.0, 55.0
    x0, y0 = pdf.l_margin, pdf.get_y()

    anos = [linha["ano"] for linha in serie_controlado]
    ano_min, ano_max = min(anos), max(anos)
    intervalo_anos = max(ano_max - ano_min, 1)

    def px(ano: float) -> float:
        return x0 + (ano - ano_min) / intervalo_anos * largura

    def py(iqa: float) -> float:
        return y0 + altura - (max(0.0, min(100.0, iqa)) / 100.0) * altura

    pdf.set_draw_color(200, 199, 191)
    pdf.rect(x0, y0, largura, altura)

    pdf.set_font("Helvetica", size=7)
    pdf.set_text_color(137, 135, 129)
    for marca in (0, 25, 50, 75, 100):
        y = py(marca)
        pdf.set_draw_color(230, 229, 222)
        pdf.line(x0, y, x0 + largura, y)
        pdf.set_xy(x0 - 9, y - 2)
        pdf.cell(8, 4, str(marca), align="R")
    pdf.set_text_color(0, 0, 0)

    pdf.set_line_width(0.6)
    pdf.set_draw_color(208, 59, 59)
    _polilinha(pdf, [(px(linha["ano"]), py(linha["iqa"])) for linha in serie_nao_controlado])
    pdf.set_draw_color(27, 175, 122)
    _polilinha(pdf, [(px(linha["ano"]), py(linha["iqa"])) for linha in serie_controlado])
    pdf.set_line_width(0.2)

    pdf.set_xy(x0, y0 + altura + 2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 5, _para_latin1_seguro(i18n.t("pdf.grafico_titulo")), align="C")
    # `multi_cell` com largura 0 deixa o cursor X na borda direita da página (new_x=RIGHT por
    # padrão no fpdf2) — sem resetar para a margem esquerda aqui, a legenda seguinte "some"
    # cortada na borda direita (bug real encontrado ao renderizar o PDF de teste).
    pdf.set_xy(pdf.l_margin, pdf.get_y())
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(208, 59, 59)
    pdf.cell(45, 5, "-- " + _para_latin1_seguro(i18n.t("pdf.legenda_nao_controlado")))
    pdf.set_text_color(27, 175, 122)
    pdf.cell(45, 5, "-- " + _para_latin1_seguro(i18n.t("pdf.legenda_controlado")))
    pdf.ln(6)
    pdf.set_x(pdf.l_margin)
    pdf.set_text_color(137, 135, 129)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 4, _para_latin1_seguro(i18n.t("pdf.fonte", ano=ano_max)))
    pdf.ln(9)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)


def _campos_tabela() -> list[tuple[str, str, str, int]]:
    return [
        (i18n.t("pdf.parametros.iqa"), "iqa", "", 0),
        (i18n.t("pdf.parametros.od"), "od_mg_l", " mg/L", 2),
        (i18n.t("pdf.parametros.dbo"), "dbo_mg_l", " mg/L", 1),
        (i18n.t("pdf.parametros.turbidez"), "turbidez_ntu", " NTU", 0),
        (i18n.t("pdf.parametros.solidos"), "solidos_totais_mg_l", " mg/L", 0),
        (i18n.t("pdf.parametros.temperatura"), "temperatura_c", " C", 1),
        (i18n.t("pdf.parametros.ph"), "ph", "", 2),
        (i18n.t("pdf.parametros.fosforo"), "fosforo_mg_l", " mg/L", 2),
        (i18n.t("pdf.parametros.nitrogenio"), "nitrogenio_mg_l", " mg/L", 2),
        (i18n.t("pdf.parametros.metais"), "metais_toxicos_indice", "", 0),
        (i18n.t("pdf.parametros.ecoli"), "e_coli_nmp_100ml", " NMP/100mL", 0),
        (i18n.t("pdf.parametros.biotico"), "indice_biotico", "", 0),
    ]


def _desenhar_tabela_comparativa(pdf: FPDF, linha_controlado: dict, linha_nao_controlado: dict) -> None:
    """Tabela com legenda ACIMA (convenção ABNT) e indicação de fonte abaixo."""
    pdf.set_font("Helvetica", "B", 9)
    pdf.multi_cell(0, 5, _para_latin1_seguro(i18n.t("pdf.tabela_titulo")), align="L")
    pdf.ln(1)

    larguras = (75.0, 42.5, 42.5)
    pdf.set_fill_color(42, 120, 214)
    pdf.set_text_color(255, 255, 255)
    for texto, largura in zip(
        (i18n.t("pdf.tabela_col_param"), i18n.t("pdf.tabela_col_controlado"), i18n.t("pdf.tabela_col_nao_controlado")),
        larguras,
    ):
        pdf.cell(largura, 7, _para_latin1_seguro(texto), border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", size=9)
    for indice, (nome, chave, unidade, casas) in enumerate(_campos_tabela()):
        pdf.set_fill_color(244, 243, 240) if indice % 2 == 1 else pdf.set_fill_color(255, 255, 255)
        pdf.cell(larguras[0], 6, _para_latin1_seguro(nome), border=1, fill=True)
        pdf.cell(larguras[1], 6, f"{linha_controlado[chave]:,.{casas}f}{unidade}", border=1, fill=True, align="C")
        pdf.cell(larguras[2], 6, f"{linha_nao_controlado[chave]:,.{casas}f}{unidade}", border=1, fill=True, align="C")
        pdf.ln()

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(137, 135, 129)
    pdf.cell(0, 5, _para_latin1_seguro(i18n.t("pdf.fonte", ano=linha_controlado.get("ano", ""))))
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)


def gerar_relatorio_cenario_pdf(
    trecho_nome: str,
    horizonte_anos: int,
    config: dict,
    serie_controlado: list[dict],
    serie_nao_controlado: list[dict],
) -> bytes:
    """Gera o PDF (formatação ABNT — margens, fonte e texto justificado) do cenário simulado
    em `webapp/pages/5_Cenarios_Futuros.py`: narrativa em seções numeradas explicando a
    configuração escolhida, gráfico de IQA ao longo do horizonte e tabela comparativa final
    (controlado vs. não controlado) para todos os parâmetros simulados."""
    pdf = _novo_pdf_abnt(f"Cenario Futuro - {trecho_nome} ({horizonte_anos} anos)")
    _titulo_capa(pdf, i18n.t("cn.titulo", trecho=trecho_nome, horizonte=horizonte_anos))

    secoes = gerar_narrativa_cenario(trecho_nome, horizonte_anos, config, serie_controlado, serie_nao_controlado)
    for numero, (titulo, corpo) in enumerate(secoes, start=1):
        _garantir_espaco(pdf, 25)  # evita título de seção "órfão" sozinho no fim da página
        _titulo_secao_abnt(pdf, numero, titulo)
        tamanho = _TAMANHO_NOTA if numero == len(secoes) else _TAMANHO_CORPO
        italico = numero == len(secoes)
        _paragrafo_abnt(pdf, corpo, tamanho=tamanho, italico=italico)

    pdf.ln(3)
    _garantir_espaco(pdf, 80)
    _desenhar_grafico_iqa(pdf, serie_controlado, serie_nao_controlado)
    pdf.ln(2)
    _garantir_espaco(pdf, 90)
    _desenhar_tabela_comparativa(pdf, serie_controlado[-1], serie_nao_controlado[-1])
    return bytes(pdf.output())
