"""Exportação em PDF do relatório textual produzido por `narrative_generator`.

Usa fpdf2 (pure-Python, sem dependência de binário de sistema como
wkhtmltopdf/Chromium) para manter o build do Streamlit Community Cloud leve.
As fontes core do fpdf2 cobrem apenas Latin-1 — suficiente para PT-BR
acentuado, mas não para emojis, por isso os ícones de status são convertidos
para marcadores textuais equivalentes antes da renderização.
"""
from __future__ import annotations

import re

from fpdf import FPDF

from waterweave.config import TRECHOS
from waterweave.reports.cenario_narrativo import gerar_narrativa_cenario
from waterweave.reports.narrative_generator import gerar_relatorio_trecho

_EMOJI_PARA_TEXTO = {
    "✅": "[BOM] ",
    "⚠️": "[ATENÇÃO] ",
    "🟠": "[SÉRIO] ",
    "🔴": "[CRÍTICO] ",
}

# As fontes core do fpdf2 (Helvetica) só cobrem Latin-1: cabe acento PT-BR,
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


def _para_latin1_seguro(texto: str) -> str:
    """Garante que `texto` seja renderizável pelas fontes core (Latin-1) do fpdf2."""
    for original, substituto in _TIPOGRAFIA_PARA_LATIN1.items():
        texto = texto.replace(original, substituto)
    return texto.encode("latin-1", errors="replace").decode("latin-1")


_CODIGO_INLINE = re.compile(r"`([^`]+)`")


def _markdown_para_html(texto: str) -> str:
    """Converte o subconjunto de Markdown usado por `gerar_relatorio_trecho` em HTML simples."""
    for emoji, marcador in _EMOJI_PARA_TEXTO.items():
        texto = texto.replace(emoji, marcador)
    texto = _para_latin1_seguro(texto)

    # Protege identificadores entre crases (ex.: `bronze_qualidade_solo`) antes do
    # regex de itálico, que senão interpretaria os "_" internos como marcadores.
    codigos: list[str] = []

    def _guardar_codigo(match: re.Match[str]) -> str:
        codigos.append(match.group(1))
        return f"\x00{len(codigos) - 1}\x00"

    texto = _CODIGO_INLINE.sub(_guardar_codigo, texto)

    texto = re.sub(r"^### (.+)$", r"<h3>\1</h3>", texto, flags=re.MULTILINE)
    texto = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto)
    texto = re.sub(r"_(.+?)_", r"<i>\1</i>", texto)

    for indice, codigo in enumerate(codigos):
        texto = texto.replace(f"\x00{indice}\x00", codigo)

    paragrafos = texto.split("\n\n")
    return "".join(p if p.lstrip().startswith("<h3>") else f"<p>{p}</p>" for p in paragrafos)


def _novo_pdf(titulo: str) -> FPDF:
    pdf = FPDF()
    pdf.set_title(titulo)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    return pdf


def gerar_relatorio_trecho_pdf(qualidade, trecho_id: str, ano: int) -> bytes:
    """Gera o PDF do relatório automatizado de um único trecho, no ano informado."""
    nome_trecho = TRECHOS[trecho_id].nome if trecho_id in TRECHOS else trecho_id
    relatorio_md = gerar_relatorio_trecho(qualidade, trecho_id, ano)

    pdf = _novo_pdf(f"Relatório Automático - {nome_trecho} ({ano})")
    pdf.write_html(_markdown_para_html(relatorio_md))
    return bytes(pdf.output())


def gerar_relatorio_completo_pdf(qualidade, ano: int) -> bytes:
    """Gera o PDF consolidado do relatório automatizado de todos os trechos, no mesmo ano."""
    pdf = _novo_pdf(f"Relatório Automático - Todos os trechos ({ano})")
    for indice, trecho_id in enumerate(TRECHOS):
        if indice > 0:
            pdf.ln(4)
        relatorio_md = gerar_relatorio_trecho(qualidade, trecho_id, ano)
        pdf.write_html(_markdown_para_html(relatorio_md))
    return bytes(pdf.output())


def _polilinha(pdf: FPDF, pontos: list[tuple[float, float]]) -> None:
    for (x1, y1), (x2, y2) in zip(pontos, pontos[1:]):
        pdf.line(x1, y1, x2, y2)


def _desenhar_grafico_iqa(pdf: FPDF, serie_controlado: list[dict], serie_nao_controlado: list[dict]) -> None:
    """Gráfico de linha (IQA x ano, controlado vs. não controlado) desenhado com as primitivas
    nativas do fpdf2 (sem matplotlib/kaleido — mantém o build do Streamlit Cloud enxuto)."""
    largura, altura = 170.0, 55.0
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
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(208, 59, 59)
    pdf.cell(35, 5, "-- Nao controlado")
    pdf.set_text_color(27, 175, 122)
    pdf.cell(35, 5, "-- Controlado")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(9)


_CAMPOS_TABELA = [
    ("IQA", "iqa", "", 0),
    ("Oxigênio Dissolvido", "od_mg_l", " mg/L", 2),
    ("DBO", "dbo_mg_l", " mg/L", 1),
    ("Turbidez", "turbidez_ntu", " NTU", 0),
    ("Sólidos Totais", "solidos_totais_mg_l", " mg/L", 0),
    ("Temperatura", "temperatura_c", " °C", 1),
    ("pH", "ph", "", 2),
    ("Fósforo Total", "fosforo_mg_l", " mg/L", 2),
    ("Nitrogênio Total", "nitrogenio_mg_l", " mg/L", 2),
    ("Metais/Tóxicos (índice)", "metais_toxicos_indice", "", 0),
    ("E. coli", "e_coli_nmp_100ml", " NMP/100mL", 0),
    ("Índice Biótico", "indice_biotico", "", 0),
]


def _desenhar_tabela_comparativa(pdf: FPDF, linha_controlado: dict, linha_nao_controlado: dict) -> None:
    larguras = (75.0, 50.0, 50.0)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(42, 120, 214)
    pdf.set_text_color(255, 255, 255)
    for texto, largura in zip(("Parâmetro (valor final)", "Controlado", "Não controlado"), larguras):
        pdf.cell(largura, 7, _para_latin1_seguro(texto), border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", size=9)
    for indice, (nome, chave, unidade, casas) in enumerate(_CAMPOS_TABELA):
        if indice % 2 == 1:
            pdf.set_fill_color(244, 243, 240)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.cell(larguras[0], 6, _para_latin1_seguro(nome), border=1, fill=True)
        pdf.cell(larguras[1], 6, f"{linha_controlado[chave]:,.{casas}f}{unidade}", border=1, fill=True, align="C")
        pdf.cell(larguras[2], 6, f"{linha_nao_controlado[chave]:,.{casas}f}{unidade}", border=1, fill=True, align="C")
        pdf.ln()


def gerar_relatorio_cenario_pdf(
    trecho_nome: str,
    horizonte_anos: int,
    config: dict,
    serie_controlado: list[dict],
    serie_nao_controlado: list[dict],
) -> bytes:
    """Gera o PDF do cenário simulado em `webapp/pages/5_Cenarios_Futuros.py`: narrativa
    explicando a configuração escolhida, gráfico de IQA ao longo do horizonte e tabela
    comparativa final (controlado vs. não controlado) para todos os parâmetros simulados."""
    narrativa_md = gerar_narrativa_cenario(trecho_nome, horizonte_anos, config, serie_controlado, serie_nao_controlado)

    pdf = _novo_pdf(f"Cenário Futuro - {trecho_nome} ({horizonte_anos} anos)")
    pdf.write_html(_markdown_para_html(narrativa_md))
    pdf.ln(4)
    _desenhar_grafico_iqa(pdf, serie_controlado, serie_nao_controlado)
    pdf.ln(2)
    _desenhar_tabela_comparativa(pdf, serie_controlado[-1], serie_nao_controlado[-1])
    return bytes(pdf.output())
