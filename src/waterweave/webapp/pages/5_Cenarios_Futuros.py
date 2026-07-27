"""Cenários Futuros: o usuário escolhe quais fatores da água priorizar e o esforço de controle,
e vê uma cena 3D do Rio Tietê evoluindo de 5 a 30 anos — reaproveitando o mesmo motor real de
simulação (ABM + balanço hídrico + Streeter-Phelps + `models.biofisico.parametros_estendidos`)
das demais páginas, sem os cartões técnicos de um dashboard de dados.

Os 4 controles do usuário (poluição orgânica/sanitária, poluição agrícola/sedimentar, vazão
ecológica, severidade climática) alimentam parâmetros reais do ABM (ver
`models.abm.agents`/`models.abm.model`) — não são multiplicadores de fachada. A cena 3D
(`webapp.components.rio_3d`) é 100% pilotada pelos valores simulados de cada ano, não uma
animação solta.

Suporta os 4 idiomas do dashboard (`webapp.i18n`) — inclusive o texto embutido na cena 3D,
que recebe os rótulos já traduzidos via `renderizar_html(..., textos=...)`.

ACHADO DE PESQUISA (2026-07, itens 5/6/7 do roadmap de pesquisa WaterWeave-Water4All), 3 seções
novas abaixo da cena 3D:
  - "Serviços Ecossistêmicos" (item 5): os 3 indicadores de `models.servicos_ecossistemicos`
    (regulação da qualidade da água, provisão hídrica, suporte à biodiversidade), calculados a
    partir do último ano do cenário controlado — só aqui (não na série histórica real, ver
    ACHADO DE PESQUISA naquele módulo) o suporte à biodiversidade é computável.
  - "Validação cruzada: ML vs. Biofísico" (item 6): compara a previsão estatística
    (`models.ml.predict_iqa`) com a simulação determinística deste trecho no cenário "Atual" —
    ver `models.ml.comparacao_biofisico_ml` para a ressalva sobre âncoras de tempo diferentes.
    Degrada graciosamente (mensagem em vez de erro) se os modelos de ML ainda não foram
    treinados no ambiente atual.
  - "Propostas da comunidade" (item 7, co-criação): salvar a configuração atual como uma
    proposta nomeada (nome, autor, justificativa) e recarregar propostas salvas por outros
    participantes — ver `models.abm.scenario_store`. O reload usa `st.session_state[key] = valor`
    seguido de `st.rerun()` (por isso os widgets de controle acima têm `key=` explícito, ver
    comentário antes da seleção de trecho/horizonte).
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[3]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from waterweave.config import TRECHOS
from waterweave.models import servicos_ecossistemicos as se
from waterweave.models.abm import scenario_store
from waterweave.models.abm.scenarios import rodar_cenario_customizado
from waterweave.reports.pdf_generator import gerar_relatorio_cenario_pdf_completo, gerar_relatorio_cenario_pdf_resumido
from waterweave.thresholds import STATUS, status_para_iqa
from waterweave.webapp import i18n, theme
from waterweave.webapp.components.rio_3d import renderizar_html

# `comparacao_biofisico_ml` importa a cadeia de treino de ML (`sklearn`/`joblib`) e do ABM
# (`mesa`) — ambos já são dependências reais do projeto (`requirements.txt`), mas o import fica
# isolado num try/except para a página inteira não quebrar se, por algum motivo de ambiente,
# essa cadeia falhar (ver item 6 do roadmap de pesquisa: "acoplar" ML e biofísico é um EXTRA
# desta página, não deveria conseguir derrubar a simulação principal).
try:
    from waterweave.models.ml.comparacao_biofisico_ml import LIMIAR_DIVERGENCIA_IQA, comparar_ml_vs_biofisico

    _VALIDACAO_CRUZADA_DISPONIVEL = True
except ImportError:
    _VALIDACAO_CRUZADA_DISPONIVEL = False

st.set_page_config(page_title="Cenários Futuros — WaterWeave-Tietê", page_icon="🔮", layout="wide")
theme.inject_style()
theme.render_sidebar_brand()
i18n.seletor_idioma()

st.title(i18n.t("cf.titulo"))
st.caption(i18n.t("cf.caption"))

TRECHO_IDS = list(TRECHOS)

CAMPOS_SAIDA = [
    "iqa", "od_mg_l", "dbo_mg_l", "turbidez_ntu", "solidos_totais_mg_l", "temperatura_c",
    "ph", "fosforo_mg_l", "nitrogenio_mg_l", "metais_toxicos_indice", "e_coli_nmp_100ml", "indice_biotico",
    "vazao_m3s_medio", "indice_escoamento_mm",
]

# ---------------------------------------------------------------------------
# Feedback visual instantâneo: um selo com a cor que a água tenderia a ter,
# atualizado a cada interação (Streamlit reexecuta o script a cada mudança de
# slider/checkbox) — não espera a simulação completa do ABM rodar, é a mesma
# lógica de cor usada na cena 3D (`webapp.components.rio_3d`), calculada aqui
# de forma direta e instantânea para dar resposta imediata ao usuário.
# ---------------------------------------------------------------------------
_COR_LIMPA = (28, 127, 174)
_COR_POLUIDA = (90, 74, 52)
_COR_SECA = (191, 130, 43)
_COR_ESCASSEZ = (176, 164, 138)


def _cor_interpolada(fracao: float, cor_a: tuple[int, int, int], cor_b: tuple[int, int, int]) -> str:
    fracao = max(0.0, min(1.0, fracao))
    r = round(cor_a[0] + (cor_b[0] - cor_a[0]) * fracao)
    g = round(cor_a[1] + (cor_b[1] - cor_a[1]) * fracao)
    b = round(cor_a[2] + (cor_b[2] - cor_a[2]) * fracao)
    return f"rgb({r},{g},{b})"


def _selo_impacto(rotulo: str, pct_bom: float, cor_ruim: tuple[int, int, int] = _COR_POLUIDA, pulsar_critico: bool = True) -> None:
    """Desenha um selo colorido (cor da água + status) proporcional a `pct_bom` (0-100, quanto
    maior, melhor para o rio) — atualiza instantaneamente a cada interação do usuário."""
    cor_agua = _cor_interpolada(1 - pct_bom / 100, _COR_LIMPA, cor_ruim)
    status = STATUS[status_para_iqa(pct_bom)]
    classe_pulso = "selo-pulsar" if (pulsar_critico and pct_bom < 25) else ""
    st.markdown(
        f"""
        <style>
        @keyframes pulsarSelo {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.45; }} }}
        .selo-pulsar {{ animation: pulsarSelo 1.1s ease-in-out infinite; }}
        </style>
        <div style="display:flex;align-items:center;gap:9px;margin:4px 0 10px;">
          <div class="{classe_pulso}" style="width:26px;height:26px;border-radius:7px;background:{cor_agua};
                       border:1px solid rgba(0,0,0,0.15);flex-shrink:0;transition:background 0.3s ease;"></div>
          <div style="font-size:12.5px;line-height:1.3;">
            {status['icon']} <b>{rotulo}</b> {i18n.t('cf.tende_a_ficar')} <b style="color:{status['color']}">{theme.status_label(status_para_iqa(pct_bom))}</b>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Cenário "não controlado" — patamar fixo, pessimista (continuidade das regras
# de decisão de hoje, sem novas medidas).
# ---------------------------------------------------------------------------
NAO_CONTROLADO_BASE = dict(
    piso_fator_outorga=0.30, restricao_ambiental=False, fiscaliza_em_serio=False,
    crescimento_mensal_industria=1.01, reducao_por_multa=0.90, teto_fator_carga_industria=3.0,
    reducao_agricola=0.99, piso_fator_difusa=0.90,
)

# ---------------------------------------------------------------------------
# Co-criação (item 7 do roadmap de pesquisa): se o usuário clicou em "Carregar esta proposta"
# no passo anterior, os valores dos widgets abaixo foram gravados em `st.session_state` ANTES
# do rerun (ver seção "Propostas da comunidade", mais abaixo) — só precisam já existir em
# `st.session_state` para os widgets (todos com `key=` correspondente) nascerem com esse valor
# nesta execução, sem precisar de nenhuma lógica extra aqui.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Seleção de trecho e horizonte
# ---------------------------------------------------------------------------
col_trecho, col_horizonte, col_clima = st.columns([1.2, 1.4, 1])
with col_trecho:
    trecho_id = st.selectbox(
        i18n.t("cf.trecho_rio"), options=TRECHO_IDS, format_func=lambda t: theme.TRECHO_LABEL[t], key="trecho_id"
    )
with col_horizonte:
    horizonte_anos = st.slider(i18n.t("cf.horizonte"), 5, 30, 15, step=1, key="horizonte_anos")
with col_clima:
    clima_pct = st.slider(
        i18n.t("cf.clima_esperado"), 60, 105, 90, format="%d%%",
        help=i18n.t("cf.clima_help"), key="clima_pct",
    )
    clima_severidade = clima_pct / 100.0
    _selo_impacto(i18n.t("cf.cenario_climatico"), (clima_pct - 60) / 45 * 100, cor_ruim=_COR_SECA, pulsar_critico=False)

st.divider()

# ---------------------------------------------------------------------------
# Fatores da água (esquerda, em abas para caber ao lado da cena) + animação 3D
# (direita) lado a lado — assim qualquer ajuste de slider mostra a mudança na
# cor da água sem precisar rolar a página para cima e para baixo.
# ---------------------------------------------------------------------------
st.markdown(f"### {i18n.t('cf.pergunta_priorizar')}")

col_controles, col_cena = st.columns([1, 1.6], gap="large")

with col_controles:
    tab_fis, tab_quim, tab_bio = st.tabs([
        i18n.t("cf.fatores_fisicos"), i18n.t("cf.fatores_quimicos"), i18n.t("cf.fatores_biologicos"),
    ])

    with tab_fis:
        st.caption(i18n.t("cf.fatores_fisicos.desc"))
        st.markdown(i18n.t("cf.fatores_fisicos.itens"))
        controlar_fisico = st.checkbox(i18n.t("cf.controlar_sedimentos"), value=True, key="controlar_fisico")
        esforco_fisico = st.slider(i18n.t("cf.esforco"), 0, 100, 60, format="%d%%", key="esforco_fisico", disabled=not controlar_fisico)
        _selo_impacto(i18n.t("cf.turbidez_solidos"), esforco_fisico if controlar_fisico else 0)
        st.caption(i18n.t("cf.temperatura_nota"))

    with tab_quim:
        st.caption(i18n.t("cf.fatores_quimicos.desc"))
        st.markdown(i18n.t("cf.fatores_quimicos.itens"))
        controlar_organico = st.checkbox(i18n.t("cf.controlar_esgoto"), value=True, key="controlar_organico")
        esforco_organico = st.slider(i18n.t("cf.esforco"), 0, 100, 60, format="%d%%", key="esforco_organico", disabled=not controlar_organico)
        _selo_impacto(i18n.t("cf.esgoto_od_dbo"), esforco_organico if controlar_organico else 0)
        controlar_nutrientes = st.checkbox(i18n.t("cf.controlar_fertilizantes"), value=True, key="controlar_nutrientes")
        esforco_nutrientes = st.slider(i18n.t("cf.esforco"), 0, 100, 60, format="%d%%", key="esforco_nutrientes", disabled=not controlar_nutrientes)
        _selo_impacto(i18n.t("cf.nutrientes_eutrofizacao"), esforco_nutrientes if controlar_nutrientes else 0)

    with tab_bio:
        st.caption(i18n.t("cf.fatores_biologicos.desc"))
        st.markdown(i18n.t("cf.fatores_biologicos.itens"))
        st.caption(i18n.t("cf.biologicos_nota"))
        outorga_piso = st.slider(
            i18n.t("cf.vazao_ecologica"), 0.30, 0.95, 0.60, step=0.05, format="%.2f",
            help=i18n.t("cf.vazao_help"), key="outorga_piso",
        )
        _selo_impacto(i18n.t("cf.diluicao_vazao"), (outorga_piso - 0.30) / 0.65 * 100, cor_ruim=_COR_ESCASSEZ)

esforco_sedimentar = esforco_fisico if controlar_fisico else 0
esforco_esgoto = esforco_organico if controlar_organico else 0
esforco_agricola = esforco_nutrientes if controlar_nutrientes else 0

CONTROLADO_PARAMS = dict(
    piso_fator_outorga=outorga_piso,
    restricao_ambiental=(esforco_agricola > 0) or (esforco_sedimentar > 0),
    fiscaliza_em_serio=esforco_esgoto >= 50,
    crescimento_mensal_industria=1.01 - 0.008 * (esforco_esgoto / 100),
    reducao_por_multa=0.90 - 0.35 * (esforco_esgoto / 100),
    teto_fator_carga_industria=3.0 - 1.8 * (esforco_esgoto / 100),
    reducao_agricola=0.99 - 0.14 * (max(esforco_agricola, esforco_sedimentar) / 100),
    piso_fator_difusa=0.90 - 0.50 * (max(esforco_agricola, esforco_sedimentar) / 100),
)

# ---------------------------------------------------------------------------
# Executa o ABM (cacheado) e prepara a série anual para a cena 3D
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=i18n.t("cf.simulando"))
def _rodar(parametros: dict, fator_clima: float, horizonte_meses: int) -> pd.DataFrame:
    parametros_completos = {**parametros, "fator_clima": fator_clima}
    return rodar_cenario_customizado(parametros_completos, TRECHO_IDS, horizonte_meses)


def _serie_anual(historico: pd.DataFrame, trecho: str) -> list[dict]:
    sub = historico[historico.trecho_id == trecho]
    agregacoes = {campo: (campo, "mean") for campo in CAMPOS_SAIDA}
    anual = sub.groupby("ano_relativo", as_index=False).agg(**agregacoes)
    anual = anual.rename(columns={"ano_relativo": "ano"}).sort_values("ano")
    return anual.to_dict(orient="records")


horizonte_meses = horizonte_anos * 12
hist_nao_controlado = _rodar(NAO_CONTROLADO_BASE, clima_severidade, horizonte_meses)
hist_controlado = _rodar(CONTROLADO_PARAMS, clima_severidade, horizonte_meses)

serie_nc = _serie_anual(hist_nao_controlado, trecho_id)
serie_c = _serie_anual(hist_controlado, trecho_id)

textos_cena = {
    "carregando": i18n.t("r3d.carregando"),
    "legenda": i18n.t("r3d.legenda"),
    "ver_sem_controle": i18n.t("r3d.ver_sem_controle"),
    "ano": i18n.t("r3d.ano"),
    "cenario_controlado": i18n.t("r3d.cenario_controlado"),
    "cenario_nao_controlado": i18n.t("r3d.cenario_nao_controlado"),
    "fase_agua_limpa": i18n.t("r3d.fase.agua_limpa"),
    "fase_recuperacao": i18n.t("r3d.fase.recuperacao"),
    "fase_tratamento": i18n.t("r3d.fase.tratamento"),
    "fase_poluicao": i18n.t("r3d.fase.poluicao"),
    "fase_critico": i18n.t("r3d.fase.critico"),
    "metrica_iqa": i18n.t("r3d.metrica.iqa"),
    "metrica_od": i18n.t("r3d.metrica.od"),
    "metrica_dbo": i18n.t("r3d.metrica.dbo"),
    "metrica_turbidez": i18n.t("r3d.metrica.turbidez"),
    "metrica_vazao": i18n.t("r3d.metrica.vazao"),
    "metrica_ecoli": i18n.t("r3d.metrica.ecoli"),
    "metrica_biotico": i18n.t("r3d.metrica.biotico"),
    "botao_reproduzir": i18n.t("r3d.botao_reproduzir"),
    "botao_pausar": i18n.t("r3d.botao_pausar"),
    "dica_camera": i18n.t("r3d.dica_camera"),
    "legenda_cor_titulo": i18n.t("r3d.legenda_cor.titulo"),
    "legenda_cor_fora": i18n.t("r3d.legenda_cor.fora_risco"),
    "legenda_cor_em": i18n.t("r3d.legenda_cor.em_risco"),
    "status_bom": i18n.t("status.bom"),
    "status_atencao": i18n.t("status.atencao"),
    "status_serio": i18n.t("status.serio"),
    "status_critico": i18n.t("status.critico"),
}

html = renderizar_html(serie_c, serie_nc, ano_min=1, ano_max=horizonte_anos, altura_px=620, textos=textos_cena)

with col_cena:
    st.caption(i18n.t("cf.dica_cor_agua"))
    components.html(html, height=640, scrolling=False)

    config_relatorio = dict(
        esforco_sedimentar=esforco_sedimentar, esforco_esgoto=esforco_esgoto, esforco_agricola=esforco_agricola,
        outorga_piso=outorga_piso, clima_pct=clima_pct,
    )
    formato_pdf = st.radio(
        i18n.t("pdf.formato_label"),
        options=["resumido", "completo"],
        format_func=lambda f: i18n.t(f"pdf.formato_{f}"),
        horizontal=True,
        captions=[i18n.t("pdf.formato_resumido_desc"), i18n.t("pdf.formato_completo_desc")],
    )
    gerar_cenario_pdf = gerar_relatorio_cenario_pdf_resumido if formato_pdf == "resumido" else gerar_relatorio_cenario_pdf_completo
    pdf_bytes = gerar_cenario_pdf(theme.TRECHO_LABEL[trecho_id], horizonte_anos, config_relatorio, serie_c, serie_nc)
    st.download_button(
        i18n.t("cf.baixar_pdf"),
        data=pdf_bytes,
        file_name=f"cenario_{trecho_id}_{horizonte_anos}anos_{formato_pdf}.pdf",
        mime="application/pdf",
    )

st.divider()

# ---------------------------------------------------------------------------
# Serviços Ecossistêmicos (item 5 do roadmap de pesquisa) — regulação da qualidade da água,
# provisão hídrica e suporte à biodiversidade, calculados a partir do ÚLTIMO ano simulado do
# cenário controlado. Ver `models.servicos_ecossistemicos` para a definição de cada um.
# ---------------------------------------------------------------------------
st.subheader(i18n.t("cf.servicos_titulo"))
st.caption(i18n.t("cf.servicos_desc"))

ultimo_ano_controlado = serie_c[-1]
captacao_necessaria_trecho = float(
    hist_controlado.loc[hist_controlado.trecho_id == trecho_id, "captacao_necessaria_m3s"].iloc[0]
)
servicos = se.ServicosEcossistemicos(
    regulacao_qualidade_agua=se.regulacao_qualidade_agua(ultimo_ano_controlado["iqa"]),
    provisao_hidrica=se.provisao_hidrica(ultimo_ano_controlado["vazao_m3s_medio"], captacao_necessaria_trecho),
    suporte_biodiversidade=se.suporte_biodiversidade(
        ultimo_ano_controlado["od_mg_l"],
        ultimo_ano_controlado["turbidez_ntu"],
        ultimo_ano_controlado["metais_toxicos_indice"],
    ),
)

col_serv1, col_serv2, col_serv3 = st.columns(3)
col_serv1.metric(i18n.t("cf.servico_regulacao"), f"{servicos.regulacao_qualidade_agua * 100:.0f}%")
col_serv2.metric(i18n.t("cf.servico_provisao"), f"{servicos.provisao_hidrica * 100:.0f}%")
col_serv3.metric(i18n.t("cf.servico_biodiversidade"), f"{servicos.suporte_biodiversidade * 100:.0f}%")

# ---------------------------------------------------------------------------
# Validação cruzada ML vs. Biofísico (item 6 do roadmap de pesquisa) — compara a previsão
# estatística (`models.ml.predict_iqa`, treinada no histórico real) com a simulação
# determinística do cenário "Atual" para o mesmo trecho/horizonte. Ver ACHADO DE PESQUISA em
# `models.ml.comparacao_biofisico_ml` para a ressalva sobre âncoras de tempo diferentes.
# ---------------------------------------------------------------------------
with st.expander(i18n.t("cf.validacao_titulo")):
    st.caption(i18n.t("cf.validacao_desc"))
    if not _VALIDACAO_CRUZADA_DISPONIVEL:
        st.info(i18n.t("cf.validacao_indisponivel"))
    else:
        try:
            comparacao = comparar_ml_vs_biofisico(trecho_id, horizonte_anos)
        except FileNotFoundError:
            st.info(i18n.t("cf.validacao_indisponivel"))
        else:
            tabela_exibicao = comparacao.rename(
                columns={
                    "passo": i18n.t("cf.validacao_coluna_passo"),
                    "iqa_ml": i18n.t("cf.validacao_coluna_iqa_ml"),
                    "iqa_biofisico": i18n.t("cf.validacao_coluna_iqa_biofisico"),
                    "diferenca_abs_iqa": i18n.t("cf.validacao_coluna_diferenca"),
                    "divergem": i18n.t("cf.validacao_coluna_divergem"),
                }
            )[
                [
                    i18n.t("cf.validacao_coluna_passo"), i18n.t("cf.validacao_coluna_iqa_ml"),
                    i18n.t("cf.validacao_coluna_iqa_biofisico"), i18n.t("cf.validacao_coluna_diferenca"),
                    i18n.t("cf.validacao_coluna_divergem"),
                ]
            ]
            st.dataframe(tabela_exibicao, hide_index=True, use_container_width=True)
            st.caption(f"{i18n.t('cf.validacao_coluna_divergem')}: |Δ IQA| > {LIMIAR_DIVERGENCIA_IQA:.0f}")

# ---------------------------------------------------------------------------
# Co-criação: propostas de cenário (item 7 do roadmap de pesquisa) — salvar a configuração
# atual como uma proposta nomeada, e listar/recarregar propostas já salvas por outros
# participantes. Ver `models.abm.scenario_store`.
# ---------------------------------------------------------------------------
st.divider()
st.subheader(i18n.t("cf.propostas_titulo"))
st.caption(i18n.t("cf.propostas_desc"))

with st.form("form_salvar_proposta", clear_on_submit=True):
    st.markdown(f"**{i18n.t('cf.salvar_proposta_titulo')}**")
    nome_proposta = st.text_input(i18n.t("cf.proposta_nome"))
    autor_proposta = st.text_input(i18n.t("cf.proposta_autor"))
    justificativa_proposta = st.text_area(i18n.t("cf.proposta_justificativa"))
    salvar_clicado = st.form_submit_button(i18n.t("cf.proposta_salvar_botao"))

if salvar_clicado:
    if not nome_proposta.strip():
        st.warning(i18n.t("cf.proposta_nome_obrigatorio"))
    else:
        scenario_store.salvar_proposta(
            nome=nome_proposta.strip(),
            autor=autor_proposta.strip(),
            justificativa=justificativa_proposta.strip(),
            trecho_id=trecho_id,
            horizonte_anos=horizonte_anos,
            parametros={**CONTROLADO_PARAMS, "fator_clima": clima_severidade},
            resumo_metricas={
                "iqa_final": ultimo_ano_controlado["iqa"],
                "regulacao_qualidade_agua": servicos.regulacao_qualidade_agua,
                "provisao_hidrica": servicos.provisao_hidrica,
                "suporte_biodiversidade": servicos.suporte_biodiversidade,
            },
            controles_ui={
                "trecho_id": trecho_id, "horizonte_anos": horizonte_anos, "clima_pct": clima_pct,
                "controlar_fisico": controlar_fisico, "esforco_fisico": esforco_fisico,
                "controlar_organico": controlar_organico, "esforco_organico": esforco_organico,
                "controlar_nutrientes": controlar_nutrientes, "esforco_nutrientes": esforco_nutrientes,
                "outorga_piso": outorga_piso,
            },
        )
        st.success(i18n.t("cf.proposta_salva_sucesso"))

propostas_salvas = scenario_store.listar_propostas()
if not propostas_salvas:
    st.caption(i18n.t("cf.propostas_vazio"))
else:
    for proposta in propostas_salvas:
        with st.container(border=True):
            col_info, col_botao = st.columns([4, 1])
            with col_info:
                st.markdown(f"**{proposta.nome}**")
                if proposta.justificativa:
                    st.caption(proposta.justificativa)
                st.caption(
                    i18n.t("cf.proposta_metadados").format(
                        trecho=theme.TRECHO_LABEL.get(proposta.trecho_id, proposta.trecho_id),
                        horizonte=proposta.horizonte_anos,
                        autor=proposta.autor or "—",
                        data=proposta.criado_em[:10],
                    )
                )
            with col_botao:
                if st.button(i18n.t("cf.proposta_carregar_botao"), key=f"carregar_{proposta.id}"):
                    for chave, valor in proposta.controles_ui.items():
                        st.session_state[chave] = valor
                    st.success(i18n.t("cf.proposta_carregada_sucesso"))
                    st.rerun()

with st.expander(i18n.t("cf.como_calculado")):
    st.markdown(i18n.t("cf.como_calculado.texto"))
