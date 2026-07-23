"""Exportação em PDF dos relatórios textuais (`narrative_generator`, `cenario_narrativo`).

Usa fpdf2 (pure-Python, sem dependência de binário de sistema como
wkhtmltopdf/Chromium) para manter o build do Streamlit Community Cloud leve.
As fontes core do fpdf2 cobrem apenas Latin-1 — suficiente para PT-BR/EN/FR/ES
acentuados, mas não para emojis, por isso os ícones de status são convertidos
para marcadores textuais equivalentes antes da renderização.

Formatação segue o requisito de redação técnica/científica (ABNT NBR 10719):
margens moderadas (2,54cm superior/inferior, 1,91cm esquerda/direita), fonte
Helvetica (equivalente métrico de Arial) 11pt, espaçamento entre linhas de
1,15 com 6pt de espaço depois de cada parágrafo (sem linhas em branco
suplementares), texto **justificado** com hifenização automática (via
`pyphen`, dicionário do idioma corrente) para evitar lacunas excessivas do
alinhamento justificado, tom impessoal (3ª pessoa/voz passiva) em todo o
texto-fonte (`webapp.i18n`). Em vez de `write_html` (que não justifica texto
no fpdf2), o corpo é renderizado via `multi_cell(..., align="J", markdown=True)`.

Dois modelos de documento (ver seção 1 do requisito):
  Opção A (Resumido)  -> `gerar_relatorio_trecho_pdf`/`gerar_relatorio_completo_pdf`
                          (Relatório Automático): cabeçalho, objetivo, resumo das
                          atividades, resultados principais, assinatura.
  Opção B (Completo/NBR 10719) -> `gerar_relatorio_cenario_pdf` (Cenários Futuros):
                          capa, folha de rosto, resumo+palavras-chave, sumário,
                          introdução, metodologia, desenvolvimento, resultados e
                          discussão, conclusão, referências, anexos.
"""
from __future__ import annotations

import re

import pyphen
from fpdf import FPDF

from waterweave.config import TRECHOS
from waterweave.reports.cenario_narrativo import gerar_narrativa_cenario_completa
from waterweave.reports.narrative_generator import gerar_relatorio_trecho
from waterweave.webapp import i18n

def _emoji_para_texto() -> dict[str, str]:
    """Marcadores textuais equivalentes aos ícones de status, traduzidos no idioma corrente —
    sem isso, um relatório em EN/FR/ES ainda exibiria "[CRÍTICO]"/"[SÉRIO]" em português."""
    return {
        "✅": f"[{i18n.t('status.bom').upper()}] ",
        "⚠️": f"[{i18n.t('status.atencao').upper()}] ",
        "🟠": f"[{i18n.t('status.serio').upper()}] ",
        "🔴": f"[{i18n.t('status.critico').upper()}] ",
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

# Margens "moderadas" do requisito: 2,54cm superior/inferior, 1,91cm esquerda/direita.
_MARGEM_ESQUERDA_MM = 19.1
_MARGEM_SUPERIOR_MM = 25.4
_MARGEM_DIREITA_MM = 19.1
_MARGEM_INFERIOR_MM = 25.4
_TAMANHO_CORPO = 11
_TAMANHO_NOTA = 9
# 1,15 espaçamento de linha a 11pt = 12,65pt = ~4,46mm; 6pt "depois do parágrafo" = ~2,12mm.
_ALTURA_LINHA_MM = 4.46
_ESPACO_DEPOIS_PARAGRAFO_MM = 2.12


def _para_latin1_seguro(texto: str) -> str:
    """Garante que `texto` seja renderizável pelas fontes core (Latin-1) do fpdf2."""
    for original, substituto in _TIPOGRAFIA_PARA_LATIN1.items():
        texto = texto.replace(original, substituto)
    return texto.encode("latin-1", errors="replace").decode("latin-1")


_CODIGO_INLINE = re.compile(r"`([^`]+)`")
_ITALICO_SIMPLES = re.compile(r"(?<!_)_([^_]+)_(?!_)")
_PALAVRA = re.compile(r"[^\W\d_]+", re.UNICODE)

# Hifenização automática (requisito de formatação, seção 2): dicionários pt_BR/en_US/fr/es
# do `pyphen`, aplicados apenas a palavras com 5+ letras — abaixo disso o corte de sílaba
# não compensa visualmente e arrisca hifenizar siglas curtas por engano.
_IDIOMA_PYPHEN = {"pt": "pt_BR", "en": "en_US", "fr": "fr", "es": "es"}
_DICIONARIOS_HIFEN: dict[str, "pyphen.Pyphen"] = {}


def _dicionario_hifen(idioma: str) -> "pyphen.Pyphen":
    if idioma not in _DICIONARIOS_HIFEN:
        _DICIONARIOS_HIFEN[idioma] = pyphen.Pyphen(lang=_IDIOMA_PYPHEN.get(idioma, "pt_BR"))
    return _DICIONARIOS_HIFEN[idioma]


def _hifenizar(texto: str) -> str:
    """Insere hífens suaves (U+00AD) nos pontos de sílaba válidos de cada palavra — o fpdf2
    só os torna visíveis quando cabem exatamente na quebra de linha do texto justificado."""
    dicionario = _dicionario_hifen(i18n.idioma_atual())

    def _hifenizar_palavra(match: re.Match[str]) -> str:
        palavra = match.group(0)
        if len(palavra) < 5:
            return palavra
        return dicionario.inserted(palavra, hyphen="­")

    return _PALAVRA.sub(_hifenizar_palavra, texto)


def _preparar_texto(texto: str, hifenizar: bool = True) -> str:
    """Prepara um trecho de texto para `multi_cell(..., markdown=True)`: troca emoji por
    marcador textual, remove crases (identificadores de código viram texto simples),
    normaliza itálico de sublinhado único (`_texto_`) para o duplo que o fpdf2 reconhece,
    e hifeniza automaticamente (ver `_hifenizar`) para o texto justificado da seção 2.

    Protege primeiro os identificadores entre crases (ex.: `models.hybrid_bridge`) com um
    placeholder sem underscore — senão o underscore interno do identificador é confundido
    com marcador de itálico pelo regex de sublinhado único (bug real encontrado ao testar
    a nota de rodapé, que continha dois identificadores de código na mesma frase). O mesmo
    placeholder também protege esses trechos de serem hifenizados.
    """
    for emoji, marcador in _emoji_para_texto().items():
        texto = texto.replace(emoji, marcador)

    codigos: list[str] = []

    def _guardar_codigo(match: re.Match[str]) -> str:
        codigos.append(match.group(1))
        return f"\x00{len(codigos) - 1}\x00"

    texto = _CODIGO_INLINE.sub(_guardar_codigo, texto)
    texto = _ITALICO_SIMPLES.sub(r"__\1__", texto)
    if hifenizar:
        texto = _hifenizar(texto)
    for indice, codigo in enumerate(codigos):
        texto = texto.replace(f"\x00{indice}\x00", codigo)

    return _para_latin1_seguro(texto)


def _novo_pdf(titulo: str) -> FPDF:
    """Novo PDF com margens/fonte no padrão da seção 2 do requisito (ver docstring do módulo)."""
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


def _titulo_secao(pdf: FPDF, numero: int | str, titulo: str) -> None:
    pdf.set_font("Helvetica", "B", 12.5)
    pdf.ln(2)
    prefixo = f"{numero} " if numero != "" else ""
    pdf.multi_cell(0, 7, _para_latin1_seguro(f"{prefixo}{titulo.upper()}"), align="L")
    pdf.ln(1)
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)


def _paragrafo(pdf: FPDF, texto: str, tamanho: float = _TAMANHO_CORPO, italico: bool = False, hifenizar: bool = True) -> None:
    if italico:
        pdf.set_font("Helvetica", "I", tamanho)
    else:
        pdf.set_font("Helvetica", size=tamanho)
    altura = _ALTURA_LINHA_MM * (tamanho / _TAMANHO_CORPO)
    pdf.multi_cell(0, altura, _preparar_texto(texto, hifenizar=hifenizar), align="J", markdown=True)
    pdf.ln(_ESPACO_DEPOIS_PARAGRAFO_MM)
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)


# ---------------------------------------------------------------------------
# Relatório Automático (narrative_generator) — trecho x ano — Modelo Resumido (Opção A):
# cabeçalho, objetivo, resumo das atividades, resultados principais, assinatura.
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


def _renderizar_cabecalho_resumido(pdf: FPDF, titulo: str, local_valor: str) -> None:
    """Cabeçalho do Modelo Resumido (Opção A): título, data de emissão, local e autor/responsável."""
    from datetime import date

    pdf.set_font("Helvetica", "B", 15)
    pdf.multi_cell(0, 8, _para_latin1_seguro(titulo), align="L")
    pdf.ln(1)
    pdf.set_font("Helvetica", size=10)
    for linha in (
        f"{i18n.t('pdf.a.data_emissao')}: {date.today().isoformat()}",
        f"{i18n.t('pdf.a.local')}: {local_valor}",
        f"{i18n.t('pdf.a.autor')}: {i18n.t('pdf.a.autor_valor')}",
    ):
        # `multi_cell` deixa o cursor X na borda direita da página por padrão (new_x=RIGHT) —
        # sem resetar aqui, a PRÓXIMA linha do laço herda X quase no limite direito e o fpdf2
        # lança "Not enough horizontal space to render a single character" (bug real encontrado
        # ao testar este cabeçalho com 3 linhas em sequência).
        pdf.multi_cell(0, 5, _para_latin1_seguro(linha), align="L")
        pdf.ln(0)
    pdf.ln(3)
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)


def _renderizar_assinatura(pdf: FPDF) -> None:
    """Bloco de assinatura do Modelo Resumido (Opção A): campo para identificação, cargo e visto."""
    _garantir_espaco(pdf, 40)
    _titulo_secao(pdf, "", i18n.t("pdf.a.assinatura_titulo"))
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)
    for rotulo in (
        i18n.t("pdf.a.assinatura_responsavel"),
        i18n.t("pdf.a.assinatura_cargo"),
        i18n.t("pdf.a.assinatura_visto"),
    ):
        pdf.multi_cell(0, 9, _para_latin1_seguro(f"{rotulo} " + "_" * 45), align="L")
        pdf.ln(0)


def _dividir_blocos_resultado(relatorio_md: str) -> tuple[list[str], str | None]:
    """Separa os parágrafos de dado (o título markdown é descartado — o cabeçalho da Opção A já
    cobre o título) da nota de proveniência final (renderizada em fonte menor, como observação)."""
    blocos = [bloco for bloco in relatorio_md.split("\n\n") if not bloco.startswith("### ")]
    nota = None
    if blocos and blocos[-1].startswith("_") and blocos[-1].endswith("_"):
        nota = blocos.pop().strip("_")
    return blocos, nota


def _renderizar_resultados_trecho(pdf: FPDF, relatorio_md: str, subtitulo: str | None = None) -> None:
    if subtitulo:
        _garantir_espaco(pdf, 20)
        pdf.set_font("Helvetica", "B", 11.5)
        pdf.multi_cell(0, 6, _preparar_texto(subtitulo, hifenizar=False), align="L")
        pdf.ln(1)
        pdf.set_font("Helvetica", size=_TAMANHO_CORPO)
    blocos, nota = _dividir_blocos_resultado(relatorio_md)
    for bloco in blocos:
        _paragrafo(pdf, bloco)
    if nota:
        _paragrafo(pdf, nota, tamanho=_TAMANHO_NOTA, italico=True)


def gerar_relatorio_trecho_pdf(qualidade, trecho_id: str, ano: int) -> bytes:
    """Gera o PDF do relatório automatizado de um único trecho, no ano informado (Modelo
    Resumido / Opção A: cabeçalho, objetivo, resumo das atividades, resultados principais,
    assinatura — ver requisito de redação técnica em `webapp.i18n` namespace `pdf.a.*`)."""
    from waterweave.reports.narrative_generator import JANELA_TENDENCIA_ANOS
    from waterweave.webapp.theme import TRECHO_LABEL

    nome_trecho = TRECHO_LABEL[trecho_id] if trecho_id in TRECHOS else trecho_id
    relatorio_md = gerar_relatorio_trecho(qualidade, trecho_id, ano)
    titulo = i18n.t("pdf.a.titulo_pdf", trecho=nome_trecho, ano=ano)

    pdf = _novo_pdf(titulo)
    _renderizar_cabecalho_resumido(pdf, titulo, f"{i18n.t('pdf.a.local_prefixo')} — {nome_trecho}")

    _titulo_secao(pdf, "", i18n.t("pdf.a.objetivo_titulo"))
    _paragrafo(pdf, i18n.t("pdf.a.objetivo_texto", trecho=nome_trecho, ano=ano))

    _titulo_secao(pdf, "", i18n.t("pdf.a.resumo_atividades_titulo"))
    _paragrafo(pdf, i18n.t("pdf.a.resumo_atividades_itens", janela=JANELA_TENDENCIA_ANOS))

    _titulo_secao(pdf, "", i18n.t("pdf.a.resultados_titulo"))
    _renderizar_resultados_trecho(pdf, relatorio_md)

    _renderizar_assinatura(pdf)
    return bytes(pdf.output())


def gerar_relatorio_completo_pdf(qualidade, ano: int) -> bytes:
    """Gera o PDF consolidado do relatório automatizado de todos os trechos, no mesmo ano
    (Modelo Resumido / Opção A): um único cabeçalho/objetivo/resumo das atividades, seguido de
    "Resultados Principais" por trecho, e uma assinatura única ao final."""
    from waterweave.reports.narrative_generator import JANELA_TENDENCIA_ANOS
    from waterweave.webapp.theme import TRECHO_LABEL

    titulo = i18n.t("pdf.a.titulo_pdf_todos", ano=ano)
    pdf = _novo_pdf(titulo)
    _renderizar_cabecalho_resumido(pdf, titulo, i18n.t("pdf.a.local_prefixo"))

    _titulo_secao(pdf, "", i18n.t("pdf.a.objetivo_titulo"))
    _paragrafo(pdf, i18n.t("pdf.a.objetivo_texto_todos", ano=ano))

    _titulo_secao(pdf, "", i18n.t("pdf.a.resumo_atividades_titulo"))
    _paragrafo(pdf, i18n.t("pdf.a.resumo_atividades_itens", janela=JANELA_TENDENCIA_ANOS))

    _titulo_secao(pdf, "", i18n.t("pdf.a.resultados_titulo"))
    for trecho_id in TRECHOS:
        nome_trecho = TRECHO_LABEL[trecho_id]
        relatorio_md = gerar_relatorio_trecho(qualidade, trecho_id, ano)
        _renderizar_resultados_trecho(pdf, relatorio_md, subtitulo=nome_trecho)

    _renderizar_assinatura(pdf)
    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Cenário Futuro (cenario_narrativo) — Modelo Completo (Opção B / NBR 10719)
# ---------------------------------------------------------------------------


def _polilinha(pdf: FPDF, pontos: list[tuple[float, float]]) -> None:
    for (x1, y1), (x2, y2) in zip(pontos, pontos[1:]):
        pdf.line(x1, y1, x2, y2)


def _desenhar_grafico_iqa(pdf: FPDF, serie_controlado: list[dict], serie_nao_controlado: list[dict]) -> None:
    """Gráfico de linha (IQA x ano, controlado vs. não controlado) desenhado com as primitivas
    nativas do fpdf2 (sem matplotlib/kaleido — mantém o build do Streamlit Cloud enxuto).
    Legenda ABAIXO do gráfico (convenção ABNT para figuras)."""
    largura, altura = pdf.epw, 55.0
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

    larguras = (pdf.epw * 0.46875, pdf.epw * 0.265625, pdf.epw * 0.265625)
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
    # `cell()` não avança Y por padrão (new_y=TOP) — sem este `ln()`, o conteúdo seguinte (ex.:
    # o título "4 RESULTADOS E DISCUSSÃO") herda a MESMA linha da nota de fonte e as duas ficam
    # visualmente coladas/sobrepostas (bug real encontrado ao testar o relatório completo, que
    # agora tem conteúdo após a tabela — no formato anterior a tabela era sempre o último elemento).
    pdf.ln(9)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)


def _renderizar_capa(pdf: FPDF, titulo: str, local_valor: str) -> None:
    """Capa (elemento pré-textual): título, autor, local e data."""
    from datetime import date

    pdf.ln(40)
    _titulo_capa(pdf, titulo)
    pdf.set_font("Helvetica", size=11)
    for linha in (
        i18n.t("pdf.a.autor_valor"),
        local_valor,
        date.today().isoformat(),
    ):
        # ver nota em `_renderizar_cabecalho_resumido`: `multi_cell` deixa o cursor X na borda
        # direita por padrão — sem resetar, a linha seguinte do laço perde espaço horizontal.
        pdf.multi_cell(0, 6, _para_latin1_seguro(linha), align="C")
        pdf.ln(0)


def _renderizar_folha_rosto(pdf: FPDF, titulo: str, objetivo_texto: str) -> None:
    """Folha de rosto (elemento pré-textual): informações institucionais, natureza do
    trabalho e objetivo do relatório."""
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(0, 7, _para_latin1_seguro(titulo), align="C")
    pdf.ln(8)
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)
    for rotulo, valor in (
        (i18n.t("cn.b.folha_rosto.instituicao_label"), i18n.t("pdf.a.autor_valor")),
        (i18n.t("cn.b.folha_rosto.natureza_label"), i18n.t("cn.b.folha_rosto.natureza_texto")),
        (i18n.t("cn.b.folha_rosto.objetivo_label"), objetivo_texto),
    ):
        _rotulo_negrito(pdf, rotulo)
        pdf.multi_cell(0, _ALTURA_LINHA_MM, _preparar_texto(valor), align="J", markdown=True)
        pdf.ln(_ESPACO_DEPOIS_PARAGRAFO_MM)


def _renderizar_resumo(pdf: FPDF, resumo_texto: str, palavras_chave: str) -> None:
    """Resumo (elemento pré-textual): síntese em parágrafo único + palavras-chave."""
    pdf.add_page()
    _titulo_secao(pdf, "", i18n.t("cn.b.sec.resumo"))
    _paragrafo(pdf, resumo_texto)
    pdf.set_font("Helvetica", "B", _TAMANHO_CORPO)
    pdf.write(_ALTURA_LINHA_MM, _para_latin1_seguro(i18n.t("cn.b.palavras_chave_label") + " "))
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)
    pdf.write(_ALTURA_LINHA_MM, _para_latin1_seguro(palavras_chave))
    pdf.ln(_ALTURA_LINHA_MM + _ESPACO_DEPOIS_PARAGRAFO_MM)


def _rotulo_negrito(pdf: FPDF, texto: str) -> None:
    """Escreve uma linha em negrito (ex.: rótulo de campo) e restaura fonte/cursor para que o
    próximo `multi_cell`/parágrafo em largura total não herde a posição X da borda direita que
    o `multi_cell` anterior deixa por padrão (`new_x=RIGHT`) — mesma causa-raiz documentada em
    `_renderizar_cabecalho_resumido`."""
    pdf.set_font("Helvetica", "B", _TAMANHO_CORPO)
    pdf.multi_cell(0, _ALTURA_LINHA_MM, _para_latin1_seguro(texto), align="L")
    pdf.ln(0)
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)


def _renderizar_sumario(pdf: FPDF, outline: list) -> None:
    """Callback de `insert_toc_placeholder`: desenha o Sumário (título + página) com os
    números de página reais, já conhecidos neste ponto (pós-processamento do fpdf2)."""
    pdf.set_xy(pdf.l_margin, pdf.t_margin)
    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(0, 7, _para_latin1_seguro(i18n.t("cn.b.sec.sumario").upper()), align="L")
    pdf.ln(4)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", size=_TAMANHO_CORPO)
    for secao in outline:
        titulo = _para_latin1_seguro(secao.name)
        pagina = str(secao.page_number)
        largura_pagina = pdf.get_string_width(pagina) + 2
        largura_disponivel = pdf.epw - largura_pagina
        y_linha = pdf.y
        pdf.set_xy(pdf.l_margin, y_linha)
        pdf.cell(largura_disponivel, 7, titulo)
        pdf.set_xy(pdf.w - pdf.r_margin - largura_pagina, y_linha)
        pdf.cell(largura_pagina, 7, pagina, align="R", new_x="LMARGIN", new_y="NEXT")


def gerar_relatorio_cenario_pdf(
    trecho_nome: str,
    horizonte_anos: int,
    config: dict,
    serie_controlado: list[dict],
    serie_nao_controlado: list[dict],
) -> bytes:
    """Gera o PDF do cenário simulado em `webapp/pages/5_Cenarios_Futuros.py` no Modelo
    Completo (Opção B / NBR 10719): capa, folha de rosto, resumo com palavras-chave,
    sumário (com paginação real via `insert_toc_placeholder`), introdução, metodologia,
    desenvolvimento (configuração + gráfico + tabela), resultados e discussão, conclusão,
    referências bibliográficas e anexos."""
    narrativa = gerar_narrativa_cenario_completa(trecho_nome, horizonte_anos, config, serie_controlado, serie_nao_controlado)
    titulo = i18n.t("cn.titulo", trecho=trecho_nome, horizonte=horizonte_anos)
    local_valor = f"{i18n.t('pdf.a.local_prefixo')} — {trecho_nome}"

    pdf = _novo_pdf(titulo)
    _renderizar_capa(pdf, titulo, local_valor)
    _renderizar_folha_rosto(pdf, titulo, narrativa.objetivo_geral)
    _renderizar_resumo(pdf, narrativa.resumo, narrativa.palavras_chave)

    # `insert_toc_placeholder(pages=1)` já reserva a página atual para o Sumário e realiza,
    # internamente, o(s) page-break(s) necessário(s) — um `pdf.add_page()` extra aqui criaria
    # uma página em branco órfã entre o Sumário e a Introdução (bug real encontrado ao testar:
    # o Sumário reportava "Introdução" na página 6, mas a página 5 ficava vazia).
    pdf.add_page()
    pdf.insert_toc_placeholder(_renderizar_sumario, pages=1, allow_extra_pages=True)

    pdf.start_section(i18n.t("cn.b.sec.introducao"), level=0)
    _titulo_secao(pdf, 1, i18n.t("cn.b.sec.introducao"))
    _paragrafo(pdf, narrativa.introducao_contexto)
    _rotulo_negrito(pdf, i18n.t("cn.b.objetivo_geral_label"))
    _paragrafo(pdf, narrativa.objetivo_geral)
    _rotulo_negrito(pdf, i18n.t("cn.b.objetivos_especificos_label"))
    _paragrafo(pdf, narrativa.objetivos_especificos)

    _garantir_espaco(pdf, 25)
    pdf.start_section(i18n.t("cn.b.sec.metodologia"), level=0)
    _titulo_secao(pdf, 2, i18n.t("cn.b.sec.metodologia"))
    _paragrafo(pdf, narrativa.metodologia_intro)
    _paragrafo(pdf, narrativa.metodologia_corpo)

    _garantir_espaco(pdf, 25)
    pdf.start_section(i18n.t("cn.b.sec.desenvolvimento"), level=0)
    _titulo_secao(pdf, 3, i18n.t("cn.b.sec.desenvolvimento"))
    _paragrafo(pdf, narrativa.desenvolvimento_intro)
    _paragrafo(pdf, narrativa.desenvolvimento_config)
    pdf.ln(2)
    _garantir_espaco(pdf, 80)
    _desenhar_grafico_iqa(pdf, serie_controlado, serie_nao_controlado)
    pdf.ln(2)
    _garantir_espaco(pdf, 90)
    _desenhar_tabela_comparativa(pdf, serie_controlado[-1], serie_nao_controlado[-1])

    _garantir_espaco(pdf, 25)
    pdf.start_section(i18n.t("cn.b.sec.resultados_discussao"), level=0)
    _titulo_secao(pdf, 4, i18n.t("cn.b.sec.resultados_discussao"))
    for paragrafo in narrativa.resultados_discussao:
        _paragrafo(pdf, paragrafo)

    _garantir_espaco(pdf, 25)
    pdf.start_section(i18n.t("cn.b.sec.conclusao"), level=0)
    _titulo_secao(pdf, 5, i18n.t("cn.b.sec.conclusao"))
    _paragrafo(pdf, narrativa.conclusao)

    _garantir_espaco(pdf, 25)
    pdf.start_section(i18n.t("cn.b.sec.referencias"), level=0)
    _titulo_secao(pdf, "", i18n.t("cn.b.sec.referencias"))
    _paragrafo(pdf, narrativa.referencias, hifenizar=False)

    _garantir_espaco(pdf, 25)
    pdf.start_section(i18n.t("cn.b.sec.anexos"), level=0)
    _titulo_secao(pdf, "", i18n.t("cn.b.sec.anexos"))
    _paragrafo(pdf, narrativa.anexos)

    return bytes(pdf.output())
