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
