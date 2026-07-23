"""Infraestrutura de internacionalização (i18n) do dashboard WaterWeave-Tietê.

Cobre as 4 línguas pedidas (pt/en/fr/es) via um dicionário de chaves ->
traduções, com fallback para português se uma chave/idioma faltar (nunca
quebra a tela por falta de tradução). O idioma escolhido fica em
`st.session_state["idioma"]`, setado pelo seletor global (`seletor_idioma`,
chamado uma vez por página, igual a `theme.render_sidebar_brand`) e válido
para toda a sessão do usuário (persiste ao navegar entre páginas).

Nomes próprios (Rio Tietê, nomes de município, Alto/Médio/Baixo Tietê como
topônimo) não são traduzidos — só o texto descritivo da interface.
"""
from __future__ import annotations

import streamlit as st

IDIOMAS = {"pt": "Português", "en": "English", "fr": "Français", "es": "Español"}
IDIOMA_PADRAO = "pt"

# ---------------------------------------------------------------------------
# Dicionário de traduções: chave -> {idioma: texto}
# ---------------------------------------------------------------------------
_T: dict[str, dict[str, str]] = {
    # ---- Marca / navegação (theme.py) ----------------------------------------------------
    "marca.subtitulo": {"pt": "Rio Tietê · 1940–2025", "en": "Tietê River · 1940–2025", "fr": "Fleuve Tietê · 1940–2025", "es": "Río Tietê · 1940–2025"},
    "nav.titulo": {"pt": "Menu de Navegação", "en": "Navigation Menu", "fr": "Menu de Navigation", "es": "Menú de Navegación"},
    "nav.mapa": {"pt": "Mapa Interativo", "en": "Interactive Map", "fr": "Carte Interactive", "es": "Mapa Interactivo"},
    "nav.mapa.desc": {"pt": "estações de monitoramento georreferenciadas, nascente → foz.", "en": "georeferenced monitoring stations, source → mouth.", "fr": "stations de surveillance géoréférencées, source → embouchure.", "es": "estaciones de monitoreo georreferenciadas, nacimiento → desembocadura."},
    "nav.series": {"pt": "Séries Históricas", "en": "Historical Series", "fr": "Séries Historiques", "es": "Series Históricas"},
    "nav.series.desc": {"pt": "vazão, chuva e qualidade da água, 1940-2025.", "en": "flow, rainfall and water quality, 1940-2025.", "fr": "débit, pluie et qualité de l'eau, 1940-2025.", "es": "caudal, lluvia y calidad del agua, 1940-2025."},
    "nav.comparativo": {"pt": "Comparativo de Cenários", "en": "Scenario Comparison", "fr": "Comparaison de Scénarios", "es": "Comparativo de Escenarios"},
    "nav.comparativo.desc": {"pt": "Atual vs. Alta Restrição de Outorga vs. Mudança Climática Extrema.", "en": "Current vs. High Water-Rights Restriction vs. Extreme Climate Change.", "fr": "Actuel vs. Forte Restriction des Prélèvements vs. Changement Climatique Extrême.", "es": "Actual vs. Alta Restricción de Concesión vs. Cambio Climático Extremo."},
    "nav.cenarios_futuros": {"pt": "Cenários Futuros", "en": "Future Scenarios", "fr": "Scénarios Futurs", "es": "Escenarios Futuros"},
    "nav.cenarios_futuros.desc": {"pt": "simule 5 a 30 anos à frente ajustando saneamento, fiscalização, agrotóxicos e outorga; veja o rio em 3D.", "en": "simulate 5 to 30 years ahead by adjusting sanitation, enforcement, pesticides and water rights; see the river in 3D.", "fr": "simulez 5 à 30 ans en ajustant assainissement, contrôle, pesticides et prélèvements ; voyez la rivière en 3D.", "es": "simule de 5 a 30 años ajustando saneamiento, fiscalización, agroquímicos y concesión; vea el río en 3D."},
    "nav.relatorio": {"pt": "Relatório Automático", "en": "Automatic Report", "fr": "Rapport Automatique", "es": "Informe Automático"},
    "nav.relatorio.desc": {"pt": "análise textual sintética por trecho e ano.", "en": "synthetic text analysis by stretch and year.", "fr": "analyse textuelle synthétique par tronçon et année.", "es": "análisis textual sintético por tramo y año."},

    # ---- Trechos (nomes descritivos — o rio/cidades continuam em PT) --------------------
    "trecho.alto": {"pt": "Alto Tietê", "en": "Upper Tietê", "fr": "Haut Tietê", "es": "Alto Tietê"},
    "trecho.medio": {"pt": "Médio Tietê", "en": "Middle Tietê", "fr": "Moyen Tietê", "es": "Medio Tietê"},
    "trecho.baixo": {"pt": "Baixo Tietê", "en": "Lower Tietê", "fr": "Bas Tietê", "es": "Bajo Tietê"},

    # ---- Home (streamlit_app.py) --------------------------------------------------------
    "home.titulo": {"pt": "WaterWeave-Tietê", "en": "WaterWeave-Tietê", "fr": "WaterWeave-Tietê", "es": "WaterWeave-Tietê"},
    "home.caption": {
        "pt": "Gestão sustentável de recursos hídricos do Rio Tietê — Salesópolis (nascente) até Itapura (foz no Rio Paraná). Histórico 1940-2025 com automação mensal.",
        "en": "Sustainable water resource management for the Tietê River — from Salesópolis (source) to Itapura (mouth at the Paraná River). 1940-2025 history with monthly automation.",
        "fr": "Gestion durable des ressources en eau du fleuve Tietê — de Salesópolis (source) à Itapura (embouchure sur le fleuve Paraná). Historique 1940-2025 avec automatisation mensuelle.",
        "es": "Gestión sostenible de los recursos hídricos del río Tietê — desde Salesópolis (nacimiento) hasta Itapura (desembocadura en el río Paraná). Histórico 1940-2025 con automatización mensual.",
    },
    "home.panorama": {"pt": "Panorama por trecho — {ano}", "en": "Overview by stretch — {ano}", "fr": "Aperçu par tronçon — {ano}", "es": "Panorama por tramo — {ano}"},
    "home.aviso_simulado": {
        "pt": "⚠️ Os indicadores de qualidade da água abaixo vêm de uma série **simulada** (proxy histórico baseado em tendências CETESB/DAEE), não de telemetria direta — ver `ingestion.bronze_qualidade_solo`.",
        "en": "⚠️ The water quality indicators below come from a **simulated** series (historical proxy based on CETESB/DAEE trends), not direct telemetry — see `ingestion.bronze_qualidade_solo`.",
        "fr": "⚠️ Les indicateurs de qualité de l'eau ci-dessous proviennent d'une série **simulée** (proxy historique basé sur les tendances CETESB/DAEE), pas de télémétrie directe — voir `ingestion.bronze_qualidade_solo`.",
        "es": "⚠️ Los indicadores de calidad del agua a continuación provienen de una serie **simulada** (proxy histórico basado en tendencias CETESB/DAEE), no de telemetría directa — ver `ingestion.bronze_qualidade_solo`.",
    },
    "home.sem_dado": {"pt": "Sem dado para o ano mais recente.", "en": "No data for the most recent year.", "fr": "Aucune donnée pour l'année la plus récente.", "es": "Sin datos para el año más reciente."},
    "home.iqa_medio": {"pt": "IQA médio", "en": "Average WQI", "fr": "IQE moyen", "es": "ICA medio"},
    "home.estacoes_monitoradas": {"pt": "{n} estações monitoradas", "en": "{n} monitored stations", "fr": "{n} stations surveillées", "es": "{n} estaciones monitoreadas"},

    # ---- Mapa Interativo -----------------------------------------------------------------
    "mapa.titulo": {"pt": "Mapa Interativo — Rio Tietê", "en": "Interactive Map — Tietê River", "fr": "Carte Interactive — Fleuve Tietê", "es": "Mapa Interactivo — Río Tietê"},
    "mapa.caption": {
        "pt": "Estações fluvio/pluviométricas (DAEE) e pontos de sensoriamento remoto, da nascente à foz.",
        "en": "Flow/rainfall stations (DAEE) and remote sensing points, from source to mouth.",
        "fr": "Stations de débit/pluviométrie (DAEE) et points de télédétection, de la source à l'embouchure.",
        "es": "Estaciones fluvio/pluviométricas (DAEE) y puntos de teledetección, del nacimiento a la desembocadura.",
    },
    "mapa.filtrar_trecho": {"pt": "Filtrar por trecho", "en": "Filter by stretch", "fr": "Filtrer par tronçon", "es": "Filtrar por tramo"},
    "mapa.mostrar_sensoriamento": {"pt": "Mostrar pontos de sensoriamento remoto (dado simulado)", "en": "Show remote sensing points (simulated data)", "fr": "Afficher les points de télédétection (données simulées)", "es": "Mostrar puntos de teledetección (datos simulados)"},
    "mapa.sensoriamento_simulado": {"pt": "sensoriamento simulado", "en": "simulated sensing", "fr": "télédétection simulée", "es": "teledetección simulada"},
    "mapa.tabela_estacoes": {"pt": "Tabela de estações", "en": "Station table", "fr": "Tableau des stations", "es": "Tabla de estaciones"},
    "mapa.classe": {"pt": "Classe", "en": "Class", "fr": "Classe", "es": "Clase"},
    "mapa.trecho": {"pt": "Trecho", "en": "Stretch", "fr": "Tronçon", "es": "Tramo"},

    # ---- Séries Históricas -----------------------------------------------------------------
    "series.titulo": {"pt": "Séries Históricas", "en": "Historical Series", "fr": "Séries Historiques", "es": "Series Históricas"},
    "series.caption": {"pt": "1940–2025 · qualidade da água, vazão e chuva", "en": "1940–2025 · water quality, flow and rainfall", "fr": "1940–2025 · qualité de l'eau, débit et pluie", "es": "1940–2025 · calidad del agua, caudal y lluvia"},
    "series.qualidade_subheader": {"pt": "Qualidade da água por trecho", "en": "Water quality by stretch", "fr": "Qualité de l'eau par tronçon", "es": "Calidad del agua por tramo"},
    "series.aviso_simulado": {
        "pt": "⚠️ Série simulada (proxy histórico) — ver aviso de proveniência em `ingestion.bronze_qualidade_solo`.",
        "en": "⚠️ Simulated series (historical proxy) — see provenance notice in `ingestion.bronze_qualidade_solo`.",
        "fr": "⚠️ Série simulée (proxy historique) — voir l'avis de provenance dans `ingestion.bronze_qualidade_solo`.",
        "es": "⚠️ Serie simulada (proxy histórico) — ver aviso de procedencia en `ingestion.bronze_qualidade_solo`.",
    },
    "series.parametro": {"pt": "Parâmetro", "en": "Parameter", "fr": "Paramètre", "es": "Parámetro"},
    "series.iqa_medio": {"pt": "IQA Médio (0-100)", "en": "Average WQI (0-100)", "fr": "IQE Moyen (0-100)", "es": "ICA Medio (0-100)"},
    "series.od": {"pt": "Oxigênio Dissolvido (mg/L)", "en": "Dissolved Oxygen (mg/L)", "fr": "Oxygène Dissous (mg/L)", "es": "Oxígeno Disuelto (mg/L)"},
    "series.dbo": {"pt": "DBO (mg/L)", "en": "BOD (mg/L)", "fr": "DBO (mg/L)", "es": "DBO (mg/L)"},
    "series.metais": {"pt": "Metais Pesados (ppm)", "en": "Heavy Metals (ppm)", "fr": "Métaux Lourds (ppm)", "es": "Metales Pesados (ppm)"},
    "series.pesticidas": {"pt": "Pesticidas (ppm)", "en": "Pesticides (ppm)", "fr": "Pesticides (ppm)", "es": "Pesticidas (ppm)"},
    "series.materia_organica": {"pt": "Matéria Orgânica (%)", "en": "Organic Matter (%)", "fr": "Matière Organique (%)", "es": "Materia Orgánica (%)"},
    "series.ver_tabela": {"pt": "Ver tabela", "en": "View table", "fr": "Voir le tableau", "es": "Ver tabla"},
    "series.vazao_chuva_subheader": {"pt": "Vazão e chuva observadas (rede completa de postos DAEE)", "en": "Observed flow and rainfall (full DAEE station network)", "fr": "Débit et pluie observés (réseau complet de stations DAEE)", "es": "Caudal y lluvia observados (red completa de estaciones DAEE)"},
    "series.aviso_real": {
        "pt": "Dado real (não simulado), regularizado para média mensal por posto pelo pipeline de Ingestão.",
        "en": "Real (non-simulated) data, regularized to monthly averages per station by the Ingestion pipeline.",
        "fr": "Données réelles (non simulées), régularisées en moyenne mensuelle par station par le pipeline d'Ingestion.",
        "es": "Datos reales (no simulados), regularizados a promedio mensual por estación por el pipeline de Ingesta.",
    },
    "series.sem_vazao": {"pt": "Sem dado de vazão disponível para este trecho.", "en": "No flow data available for this stretch.", "fr": "Aucune donnée de débit disponible pour ce tronçon.", "es": "Sin datos de caudal disponibles para este tramo."},
    "series.sem_chuva": {"pt": "Sem dado de chuva disponível para este trecho.", "en": "No rainfall data available for this stretch.", "fr": "Aucune donnée de pluie disponible pour ce tronçon.", "es": "Sin datos de lluvia disponibles para este tramo."},
    "series.posto_fluvio": {"pt": "Posto fluviométrico", "en": "Flow gauge station", "fr": "Station hydrométrique", "es": "Estación fluviométrica"},
    "series.posto_pluvio": {"pt": "Posto pluviométrico", "en": "Rain gauge station", "fr": "Station pluviométrique", "es": "Estación pluviométrica"},
    "series.vazao_media": {"pt": "Vazão média mensal (m³/s)", "en": "Average monthly flow (m³/s)", "fr": "Débit mensuel moyen (m³/s)", "es": "Caudal medio mensual (m³/s)"},
    "series.chuva_mensal": {"pt": "Chuva mensal (mm)", "en": "Monthly rainfall (mm)", "fr": "Pluie mensuelle (mm)", "es": "Lluvia mensual (mm)"},

    # ---- Comparativo de Cenários -----------------------------------------------------------------
    "comp.titulo": {"pt": "Comparativo de Cenários", "en": "Scenario Comparison", "fr": "Comparaison de Scénarios", "es": "Comparativo de Escenarios"},
    "comp.caption": {
        "pt": "Simulação real via ABM (Mesa) + balanço hídrico biofísico + Streeter-Phelps — não são multiplicadores ilustrativos. Ver `models.hybrid_bridge` para as simplificações assumidas.",
        "en": "Real simulation via ABM (Mesa) + biophysical water balance + Streeter-Phelps — not illustrative multipliers. See `models.hybrid_bridge` for the assumed simplifications.",
        "fr": "Simulation réelle via ABM (Mesa) + bilan hydrique biophysique + Streeter-Phelps — pas de multiplicateurs illustratifs. Voir `models.hybrid_bridge` pour les simplifications adoptées.",
        "es": "Simulación real vía ABM (Mesa) + balance hídrico biofísico + Streeter-Phelps — no son multiplicadores ilustrativos. Ver `models.hybrid_bridge` para las simplificaciones asumidas.",
    },
    "comp.horizonte": {"pt": "Horizonte temporal", "en": "Time horizon", "fr": "Horizon temporel", "es": "Horizonte temporal"},
    "comp.curto_prazo": {"pt": "Curto prazo (5 anos)", "en": "Short term (5 years)", "fr": "Court terme (5 ans)", "es": "Corto plazo (5 años)"},
    "comp.medio_prazo": {"pt": "Médio prazo (15 anos)", "en": "Medium term (15 years)", "fr": "Moyen terme (15 ans)", "es": "Mediano plazo (15 años)"},
    "comp.longo_prazo": {"pt": "Longo prazo (30 anos)", "en": "Long term (30 years)", "fr": "Long terme (30 ans)", "es": "Largo plazo (30 años)"},
    "comp.parametro": {"pt": "Parâmetro", "en": "Parameter", "fr": "Paramètre", "es": "Parámetro"},
    "comp.iqa": {"pt": "IQA simulado (proxy 0-100)", "en": "Simulated WQI (0-100 proxy)", "fr": "IQE simulé (proxy 0-100)", "es": "ICA simulado (proxy 0-100)"},
    "comp.od": {"pt": "Oxigênio Dissolvido simulado (mg/L)", "en": "Simulated Dissolved Oxygen (mg/L)", "fr": "Oxygène Dissous simulé (mg/L)", "es": "Oxígeno Disuelto simulado (mg/L)"},
    "comp.dbo": {"pt": "DBO simulada (mg/L)", "en": "Simulated BOD (mg/L)", "fr": "DBO simulée (mg/L)", "es": "DBO simulada (mg/L)"},
    "comp.vazao": {"pt": "Vazão simulada (m³/s)", "en": "Simulated flow (m³/s)", "fr": "Débit simulé (m³/s)", "es": "Caudal simulado (m³/s)"},
    "comp.tabela_titulo": {"pt": "Tabela comparativa — estado simulado ao fim do horizonte ({data})", "en": "Comparison table — simulated state at the end of the horizon ({data})", "fr": "Tableau comparatif — état simulé à la fin de l'horizon ({data})", "es": "Tabla comparativa — estado simulado al final del horizonte ({data})"},
    "comp.expander_multas": {"pt": "Multas aplicadas e estresse hídrico durante a simulação", "en": "Fines applied and water stress during the simulation", "fr": "Amendes appliquées et stress hydrique pendant la simulation", "es": "Multas aplicadas y estrés hídrico durante la simulación"},
    "comp.expander_cenarios": {"pt": "O que cada cenário configura", "en": "What each scenario configures", "fr": "Ce que configure chaque scénario", "es": "Qué configura cada escenario"},
    "comp.cenario_atual": {"pt": "Cenário Atual", "en": "Current Scenario", "fr": "Scénario Actuel", "es": "Escenario Actual"},
    "comp.cenario_outorga": {"pt": "Alta Restrição de Outorga", "en": "High Water-Rights Restriction", "fr": "Forte Restriction des Prélèvements", "es": "Alta Restricción de Concesión"},
    "comp.cenario_clima": {"pt": "Mudança Climática Extrema", "en": "Extreme Climate Change", "fr": "Changement Climatique Extrême", "es": "Cambio Climático Extremo"},
    "comp.cenario_atual.desc": {"pt": "Regras de decisão e clima observado/climatológico sem alteração.", "en": "Decision rules and observed/climatological weather unchanged.", "fr": "Règles de décision et climat observé/climatologique inchangés.", "es": "Reglas de decisión y clima observado/climatológico sin alteración."},
    "comp.cenario_outorga.desc": {"pt": "Piso de outorga elevado (menos captação permitida) e restrição ambiental ativa sobre uso agrícola.", "en": "Raised water-rights floor (less abstraction allowed) and active environmental restriction on agricultural use.", "fr": "Plancher de prélèvement relevé (moins de captage autorisé) et restriction environnementale active sur l'usage agricole.", "es": "Piso de concesión elevado (menos captación permitida) y restricción ambiental activa sobre el uso agrícola."},
    "comp.cenario_clima.desc": {"pt": "Chuva reduzida em 25% em relação à climatologia histórica (proxy simplificado de cenário CMIP6 severo).", "en": "Rainfall reduced by 25% relative to historical climatology (simplified proxy for a severe CMIP6 scenario).", "fr": "Pluie réduite de 25% par rapport à la climatologie historique (proxy simplifié d'un scénario CMIP6 sévère).", "es": "Lluvia reducida en 25% respecto a la climatología histórica (proxy simplificado de un escenario CMIP6 severo)."},

    # ---- Relatório Automático -----------------------------------------------------------------
    "rel.titulo": {"pt": "Relatório Automático", "en": "Automatic Report", "fr": "Rapport Automatique", "es": "Informe Automático"},
    "rel.caption": {
        "pt": "Análise textual gerada por regras a partir dos indicadores de qualidade da água por trecho/ano.",
        "en": "Rule-based text analysis generated from water quality indicators by stretch/year.",
        "fr": "Analyse textuelle générée par des règles à partir des indicateurs de qualité de l'eau par tronçon/année.",
        "es": "Análisis textual generado por reglas a partir de los indicadores de calidad del agua por tramo/año.",
    },
    "rel.ano_referencia": {"pt": "Ano de referência", "en": "Reference year", "fr": "Année de référence", "es": "Año de referencia"},
    "rel.baixar_pdf": {"pt": "📄 Baixar este relatório em PDF", "en": "📄 Download this report as PDF", "fr": "📄 Télécharger ce rapport en PDF", "es": "📄 Descargar este informe en PDF"},
    "rel.gerar_todos": {"pt": "Gerar para todos os trechos neste ano", "en": "Generate for all stretches this year", "fr": "Générer pour tous les tronçons cette année", "es": "Generar para todos los tramos en este año"},
    "rel.baixar_pdf_todos": {"pt": "📄 Baixar relatório de todos os trechos em PDF", "en": "📄 Download report for all stretches as PDF", "fr": "📄 Télécharger le rapport de tous les tronçons en PDF", "es": "📄 Descargar informe de todos los tramos en PDF"},

    # ---- Relatório Automático — narrative_generator.py (texto dinâmico) -----------------
    "rel.sem_dados": {"pt": "Sem dados de qualidade da água para {trecho} em {ano}.", "en": "No water quality data for {trecho} in {ano}.", "fr": "Aucune donnée de qualité de l'eau pour {trecho} en {ano}.", "es": "Sin datos de calidad del agua para {trecho} en {ano}."},
    "rel.titulo_secao": {"pt": "Análise automatizada — {trecho}, {ano}", "en": "Automated analysis — {trecho}, {ano}", "fr": "Analyse automatisée — {trecho}, {ano}", "es": "Análisis automatizado — {trecho}, {ano}"},
    "rel.par_iqa": {
        "pt": "{icon} O trecho **{trecho}** apresentou IQA médio de **{iqa:.1f}** em {ano} ({status}), {comparacao} média histórica da série (1940-{ano_max}) de {media:.1f}.",
        "en": "{icon} The **{trecho}** stretch had an average WQI of **{iqa:.1f}** in {ano} ({status}), {comparacao} the series' historical average (1940-{ano_max}) of {media:.1f}.",
        "fr": "{icon} Le tronçon **{trecho}** a présenté un IQE moyen de **{iqa:.1f}** en {ano} ({status}), {comparacao} la moyenne historique de la série (1940-{ano_max}) de {media:.1f}.",
        "es": "{icon} El tramo **{trecho}** presentó un ICA medio de **{iqa:.1f}** en {ano} ({status}), {comparacao} promedio histórico de la serie (1940-{ano_max}) de {media:.1f}.",
    },
    "rel.acima_da": {"pt": "acima da", "en": "above", "fr": "au-dessus de", "es": "por encima del"},
    "rel.abaixo_da": {"pt": "abaixo da", "en": "below", "fr": "en dessous de", "es": "por debajo del"},
    "rel.par_od_dbo": {
        "pt": "{icon} O Oxigênio Dissolvido está em **{od:.2f} mg/L** ({status}) e a Demanda Bioquímica de Oxigênio em **{dbo:.2f} mg/L**. Uso do solo predominante no trecho: {uso_solo}.",
        "en": "{icon} Dissolved Oxygen is at **{od:.2f} mg/L** ({status}) and Biochemical Oxygen Demand at **{dbo:.2f} mg/L**. Predominant land use in the stretch: {uso_solo}.",
        "fr": "{icon} L'Oxygène Dissous est à **{od:.2f} mg/L** ({status}) et la Demande Biochimique en Oxygène à **{dbo:.2f} mg/L**. Usage des sols prédominant sur le tronçon : {uso_solo}.",
        "es": "{icon} El Oxígeno Disuelto está en **{od:.2f} mg/L** ({status}) y la Demanda Bioquímica de Oxígeno en **{dbo:.2f} mg/L**. Uso del suelo predominante en el tramo: {uso_solo}.",
    },
    "rel.par_tendencia": {
        "pt": "Nos últimos {janela} anos, o IQA apresentou tendência de **{dir_iqa}** ({delta_iqa:+.1f} pontos) e o OD tendência de **{dir_od}** ({delta_od:+.2f} mg/L).",
        "en": "Over the last {janela} years, the WQI trend was **{dir_iqa}** ({delta_iqa:+.1f} points) and the DO trend was **{dir_od}** ({delta_od:+.2f} mg/L).",
        "fr": "Au cours des {janela} dernières années, l'IQE a montré une tendance **{dir_iqa}** ({delta_iqa:+.1f} points) et l'OD une tendance **{dir_od}** ({delta_od:+.2f} mg/L).",
        "es": "En los últimos {janela} años, el ICA presentó una tendencia **{dir_iqa}** ({delta_iqa:+.1f} puntos) y el OD una tendencia **{dir_od}** ({delta_od:+.2f} mg/L).",
    },
    # Fragmentos que se encaixam no template acima de cada idioma (cuidado ao alterar um
    # sem checar o outro): EN "trend was X", FR/ES "tendance/tendencia X".
    "rel.melhora": {"pt": "melhora", "en": "improving", "fr": "à la hausse", "es": "al alza"},
    "rel.piora": {"pt": "piora", "en": "declining", "fr": "à la baisse", "es": "a la baja"},
    "rel.estavel": {"pt": "estável", "en": "stable", "fr": "stable", "es": "estable"},
    "rel.alerta_od": {
        "pt": "⚠️ **Alerta:** OD abaixo de 4 mg/L indica estresse para a biota aquática — recomenda-se priorizar fiscalização de lançamentos de efluentes neste trecho.",
        "en": "⚠️ **Alert:** DO below 4 mg/L indicates stress for aquatic life — prioritizing enforcement of effluent discharges in this stretch is recommended.",
        "fr": "⚠️ **Alerte :** un OD inférieur à 4 mg/L indique un stress pour la biote aquatique — il est recommandé de prioriser le contrôle des rejets d'effluents sur ce tronçon.",
        "es": "⚠️ **Alerta:** OD por debajo de 4 mg/L indica estrés para la biota acuática — se recomienda priorizar la fiscalización de vertidos de efluentes en este tramo.",
    },
    "rel.nota_proveniencia": {
        "pt": "_Nota de proveniência: indicadores desta seção vêm de uma série simulada (proxy histórico), não de telemetria direta — ver `ingestion.bronze_qualidade_solo`._",
        "en": "_Provenance note: indicators in this section come from a simulated series (historical proxy), not direct telemetry — see `ingestion.bronze_qualidade_solo`._",
        "fr": "_Note de provenance : les indicateurs de cette section proviennent d'une série simulée (proxy historique), pas de télémétrie directe — voir `ingestion.bronze_qualidade_solo`._",
        "es": "_Nota de procedencia: los indicadores de esta sección provienen de una serie simulada (proxy histórico), no de telemetría directa — ver `ingestion.bronze_qualidade_solo`._",
    },

    # ---- Seletor de formato do relatório em PDF (Resumido/Completo) — ambas as telas -------
    "pdf.formato_label": {"pt": "Formato do relatório em PDF", "en": "PDF report format", "fr": "Format du rapport PDF", "es": "Formato del informe en PDF"},
    "pdf.formato_resumido": {"pt": "Resumido", "en": "Summary", "fr": "Résumé", "es": "Resumido"},
    "pdf.formato_resumido_desc": {"pt": "Cabeçalho, objetivo, resumo das atividades, resultados principais e assinatura — 1 a 2 páginas.", "en": "Header, objective, summary of activities, main results and signature — 1 to 2 pages.", "fr": "En-tête, objectif, résumé des activités, résultats principaux et signature — 1 à 2 pages.", "es": "Encabezado, objetivo, resumen de actividades, resultados principales y firma — 1 a 2 páginas."},
    "pdf.formato_completo": {"pt": "Completo (NBR 10719)", "en": "Full (NBR 10719)", "fr": "Complet (NBR 10719)", "es": "Completo (NBR 10719)"},
    "pdf.formato_completo_desc": {"pt": "Capa, folha de rosto, resumo, sumário, introdução, metodologia, desenvolvimento, resultados e discussão, conclusão, referências e anexos.", "en": "Cover page, title page, abstract, table of contents, introduction, methodology, development, results and discussion, conclusion, references and appendices.", "fr": "Couverture, page de titre, résumé, sommaire, introduction, méthodologie, développement, résultats et discussion, conclusion, références et annexes.", "es": "Portada, hoja de rosto, resumen, sumario, introducción, metodología, desarrollo, resultados y discusión, conclusión, referencias y anexos."},

    # ---- pdf_generator.py — Relatório Automático em PDF, Modelo Completo (Opção B) ---------
    "rel.b.resumo_texto": {
        "pt": "Este relatório documenta o estado da qualidade da água do trecho {trecho} do Rio Tietê no ano de {ano}, com base na simulação hidrobiogeoquímica do sistema WaterWeave-Tietê (modelo baseado em agentes + balanço hídrico + Streeter-Phelps, ancorado em médias reais da CETESB). O Índice de Qualidade da Água (ICA) simulado foi de {iqa:.1f} pontos, em situação **{status}**, {comparacao} média histórica da série (1940-{ano_max}) de {media:.1f}. O Oxigênio Dissolvido está em {od:.2f} mg/L e a Demanda Bioquímica de Oxigênio em {dbo:.1f} mg/L. Nos últimos {janela} anos, o ICA apresentou tendência de {dir_iqa} ({delta_iqa:+.1f} pontos). Conclui-se que o trecho {trecho} {conclusao_curta}.",
        "en": "This report documents the water quality status of the {trecho} stretch of the Tietê River in {ano}, based on the WaterWeave-Tietê system's hydro-biogeochemical simulation (agent-based model + water balance + Streeter-Phelps, anchored to real CETESB averages). The simulated Water Quality Index (WQI) was {iqa:.1f} points, in **{status}** condition, {comparacao} the series' historical average (1940-{ano_max}) of {media:.1f}. Dissolved Oxygen is at {od:.2f} mg/L and Biochemical Oxygen Demand at {dbo:.1f} mg/L. Over the last {janela} years, the WQI trend was {dir_iqa} ({delta_iqa:+.1f} points). It is concluded that the {trecho} stretch {conclusao_curta}.",
        "fr": "Ce rapport documente l'état de la qualité de l'eau du tronçon {trecho} du fleuve Tietê en {ano}, sur la base de la simulation hydro-biogéochimique du système WaterWeave-Tietê (modèle multi-agents + bilan hydrique + Streeter-Phelps, ancré sur des moyennes réelles CETESB). L'Indice de Qualité de l'Eau (IQE) simulé était de {iqa:.1f} points, en situation **{status}**, {comparacao} la moyenne historique de la série (1940-{ano_max}) de {media:.1f}. L'Oxygène Dissous est à {od:.2f} mg/L et la Demande Biochimique en Oxygène à {dbo:.1f} mg/L. Au cours des {janela} dernières années, l'IQE a montré une tendance {dir_iqa} ({delta_iqa:+.1f} points). Il est conclu que le tronçon {trecho} {conclusao_curta}.",
        "es": "Este informe documenta el estado de la calidad del agua del tramo {trecho} del Río Tietê en el año {ano}, con base en la simulación hidrobiogeoquímica del sistema WaterWeave-Tietê (modelo basado en agentes + balance hídrico + Streeter-Phelps, anclado en promedios reales de la CETESB). El Índice de Calidad del Agua (ICA) simulado fue de {iqa:.1f} puntos, en situación **{status}**, {comparacao} promedio histórico de la serie (1940-{ano_max}) de {media:.1f}. El Oxígeno Disuelto está en {od:.2f} mg/L y la Demanda Bioquímica de Oxígeno en {dbo:.1f} mg/L. En los últimos {janela} años, el ICA presentó una tendencia {dir_iqa} ({delta_iqa:+.1f} puntos). Se concluye que el tramo {trecho} {conclusao_curta}.",
    },
    "rel.b.conclusao_curta.bom": {
        "pt": "apresenta qualidade da água satisfatória",
        "en": "presents satisfactory water quality",
        "fr": "présente une qualité de l'eau satisfaisante",
        "es": "presenta calidad del agua satisfactoria",
    },
    "rel.b.conclusao_curta.atencao": {
        "pt": "apresenta qualidade da água em ponto de atenção",
        "en": "presents water quality at a point of concern",
        "fr": "présente une qualité de l'eau nécessitant une attention",
        "es": "presenta calidad del agua en punto de atención",
    },
    "rel.b.conclusao_curta.serio": {
        "pt": "apresenta qualidade da água em situação séria, exigindo intervenção",
        "en": "presents water quality in serious condition, requiring intervention",
        "fr": "présente une qualité de l'eau en situation sérieuse, nécessitant une intervention",
        "es": "presenta calidad del agua en situación seria, que exige intervención",
    },
    "rel.b.conclusao_curta.critico": {
        "pt": "apresenta qualidade da água em situação crítica, exigindo intervenção imediata",
        "en": "presents water quality in critical condition, requiring immediate intervention",
        "fr": "présente une qualité de l'eau en situation critique, nécessitant une intervention immédiate",
        "es": "presenta calidad del agua en situación crítica, que exige intervención inmediata",
    },
    "rel.b.palavras_chave_lista": {
        "pt": "Qualidade da água; Rio Tietê; Monitoramento; Índice de Qualidade da Água; Oxigênio Dissolvido.",
        "en": "Water quality; Tietê River; Monitoring; Water Quality Index; Dissolved Oxygen.",
        "fr": "Qualité de l'eau ; Fleuve Tietê ; Surveillance ; Indice de Qualité de l'Eau ; Oxygène Dissous.",
        "es": "Calidad del agua; Río Tietê; Monitoreo; Índice de Calidad del Agua; Oxígeno Disuelto.",
    },
    "rel.b.objetivo_geral_texto": {
        "pt": "Analisar o estado da qualidade da água do trecho {trecho} do Rio Tietê no ano de {ano}, a partir dos indicadores simulados de Índice de Qualidade da Água, Oxigênio Dissolvido e Demanda Bioquímica de Oxigênio.",
        "en": "Analyze the water quality status of the {trecho} stretch of the Tietê River in {ano}, based on the simulated Water Quality Index, Dissolved Oxygen and Biochemical Oxygen Demand indicators.",
        "fr": "Analyser l'état de la qualité de l'eau du tronçon {trecho} du fleuve Tietê en {ano}, à partir des indicateurs simulés d'Indice de Qualité de l'Eau, d'Oxygène Dissous et de Demande Biochimique en Oxygène.",
        "es": "Analizar el estado de la calidad del agua del tramo {trecho} del Río Tietê en el año {ano}, a partir de los indicadores simulados de Índice de Calidad del Agua, Oxígeno Disuelto y Demanda Bioquímica de Oxígeno.",
    },
    "rel.b.objetivos_especificos_itens": {
        "pt": "- Reportar o Índice de Qualidade da Água (ICA), Oxigênio Dissolvido (OD) e Demanda Bioquímica de Oxigênio (DBO) no ano de referência.\n- Comparar o ICA com a média histórica da série.\n- Identificar a tendência dos últimos 10 anos e eventuais alertas.",
        "en": "- Report the Water Quality Index (WQI), Dissolved Oxygen (DO) and Biochemical Oxygen Demand (BOD) in the reference year.\n- Compare the WQI against the series' historical average.\n- Identify the trend over the last 10 years and any alerts.",
        "fr": "- Rapporter l'Indice de Qualité de l'Eau (IQE), l'Oxygène Dissous (OD) et la Demande Biochimique en Oxygène (DBO) pour l'année de référence.\n- Comparer l'IQE à la moyenne historique de la série.\n- Identifier la tendance des 10 dernières années et les éventuelles alertes.",
        "es": "- Reportar el Índice de Calidad del Agua (ICA), el Oxígeno Disuelto (OD) y la Demanda Bioquímica de Oxígeno (DBO) en el año de referencia.\n- Comparar el ICA con el promedio histórico de la serie.\n- Identificar la tendencia de los últimos 10 años y eventuales alertas.",
    },
    "rel.b.titulo_pdf_todos": {"pt": "Relatório de Qualidade da Água — Todos os Trechos ({ano})", "en": "Water Quality Report — All Stretches ({ano})", "fr": "Rapport de Qualité de l'Eau — Tous les Tronçons ({ano})", "es": "Informe de Calidad del Agua — Todos los Tramos ({ano})"},
    "rel.b.objetivo_geral_texto_todos": {
        "pt": "Analisar o estado da qualidade da água de todos os trechos monitorados do Rio Tietê no ano de {ano}, a partir dos indicadores simulados de Índice de Qualidade da Água, Oxigênio Dissolvido e Demanda Bioquímica de Oxigênio.",
        "en": "Analyze the water quality status of all monitored stretches of the Tietê River in {ano}, based on the simulated Water Quality Index, Dissolved Oxygen and Biochemical Oxygen Demand indicators.",
        "fr": "Analyser l'état de la qualité de l'eau de tous les tronçons surveillés du fleuve Tietê en {ano}, à partir des indicateurs simulés d'Indice de Qualité de l'Eau, d'Oxygène Dissous et de Demande Biochimique en Oxygène.",
        "es": "Analizar el estado de la calidad del agua de todos los tramos monitoreados del Río Tietê en el año {ano}, a partir de los indicadores simulados de Índice de Calidad del Agua, Oxígeno Disuelto y Demanda Bioquímica de Oxígeno.",
    },
    "rel.b.resumo_trecho_item": {
        "pt": "{trecho} apresentou ICA de {iqa:.1f} ({status})",
        "en": "{trecho} had a WQI of {iqa:.1f} ({status})",
        "fr": "{trecho} a présenté un IQE de {iqa:.1f} ({status})",
        "es": "{trecho} presentó un ICA de {iqa:.1f} ({status})",
    },
    "rel.b.resumo_texto_todos": {
        "pt": "Este relatório documenta o estado da qualidade da água de todos os trechos monitorados do Rio Tietê no ano de {ano}, com base na simulação hidrobiogeoquímica do sistema WaterWeave-Tietê (modelo baseado em agentes + balanço hídrico + Streeter-Phelps, ancorado em médias reais da CETESB). No ano de referência, {resumo_trechos}. Conclui-se que a bacia apresenta condições heterogêneas entre trechos, refletindo diferentes pressões de poluição ao longo do curso do rio, o que reforça a importância do acompanhamento segmentado por trecho.",
        "en": "This report documents the water quality status of all monitored stretches of the Tietê River in {ano}, based on the WaterWeave-Tietê system's hydro-biogeochemical simulation (agent-based model + water balance + Streeter-Phelps, anchored to real CETESB averages). In the reference year, {resumo_trechos}. It is concluded that the basin presents heterogeneous conditions across stretches, reflecting different pollution pressures along the river's course, which reinforces the importance of stretch-by-stretch monitoring.",
        "fr": "Ce rapport documente l'état de la qualité de l'eau de tous les tronçons surveillés du fleuve Tietê en {ano}, sur la base de la simulation hydro-biogéochimique du système WaterWeave-Tietê (modèle multi-agents + bilan hydrique + Streeter-Phelps, ancré sur des moyennes réelles CETESB). Pour l'année de référence, {resumo_trechos}. Il est conclu que le bassin présente des conditions hétérogènes entre les tronçons, reflétant différentes pressions de pollution le long du cours du fleuve, ce qui renforce l'importance d'un suivi segmenté par tronçon.",
        "es": "Este informe documenta el estado de la calidad del agua de todos los tramos monitoreados del Río Tietê en el año {ano}, con base en la simulación hidrobiogeoquímica del sistema WaterWeave-Tietê (modelo basado en agentes + balance hídrico + Streeter-Phelps, anclado en promedios reales de la CETESB). En el año de referencia, {resumo_trechos}. Se concluye que la cuenca presenta condiciones heterogéneas entre tramos, reflejando diferentes presiones de contaminación a lo largo del curso del río, lo que refuerza la importancia del seguimiento segmentado por tramo.",
    },
    "rel.b.conclusao_texto_todos": {
        "pt": "Com base nos indicadores analisados, os trechos do Rio Tietê apresentam condições heterogêneas de qualidade da água, refletindo diferentes pressões de poluição ao longo do curso do rio. Como limitação, destaca-se que os indicadores são obtidos de uma série simulada (proxy histórico), não de telemetria direta, e que cada trecho é reportado de forma independente. Recomenda-se o acompanhamento contínuo por trecho e a priorização de medidas de controle nos trechos em situação mais crítica.",
        "en": "Based on the analyzed indicators, the stretches of the Tietê River present heterogeneous water quality conditions, reflecting different pollution pressures along the river's course. As a limitation, it should be noted that the indicators are obtained from a simulated series (historical proxy), not direct telemetry, and that each stretch is reported independently. Continuous stretch-by-stretch monitoring is recommended, along with prioritizing control measures in the stretches with the most critical condition.",
        "fr": "Sur la base des indicateurs analysés, les tronçons du fleuve Tietê présentent des conditions hétérogènes de qualité de l'eau, reflétant différentes pressions de pollution le long du cours du fleuve. Comme limite, il convient de noter que les indicateurs proviennent d'une série simulée (proxy historique), pas de télémétrie directe, et que chaque tronçon est rapporté indépendamment. Un suivi continu par tronçon est recommandé, ainsi que la priorisation de mesures de contrôle dans les tronçons en situation la plus critique.",
        "es": "Con base en los indicadores analizados, los tramos del Río Tietê presentan condiciones heterogéneas de calidad del agua, reflejando diferentes presiones de contaminación a lo largo del curso del río. Como limitación, se destaca que los indicadores se obtienen de una serie simulada (proxy histórico), no de telemetría directa, y que cada tramo se reporta de forma independiente. Se recomienda el seguimiento continuo por tramo y la priorización de medidas de control en los tramos en situación más crítica.",
    },
    "rel.b.metodologia_intro": {
        "pt": "Os indicadores reportados a seguir são obtidos pelo mesmo motor de simulação do sistema WaterWeave-Tietê, descrito a seguir.",
        "en": "The indicators reported below are obtained by the same simulation engine of the WaterWeave-Tietê system, described below.",
        "fr": "Les indicateurs rapportés ci-dessous sont obtenus par le même moteur de simulation du système WaterWeave-Tietê, décrit ci-dessous.",
        "es": "Los indicadores reportados a continuación se obtienen mediante el mismo motor de simulación del sistema WaterWeave-Tietê, descrito a continuación.",
    },
    "rel.b.desenvolvimento_intro": {
        "pt": "Apresentam-se a seguir os indicadores simulados do trecho {trecho} no ano de {ano}.",
        "en": "The simulated indicators for the {trecho} stretch in {ano} are presented below.",
        "fr": "Les indicateurs simulés du tronçon {trecho} pour l'année {ano} sont présentés ci-dessous.",
        "es": "A continuación se presentan los indicadores simulados del tramo {trecho} en el año {ano}.",
    },
    "rel.b.conclusao_texto": {
        "pt": "Com base nos indicadores analisados, o trecho {trecho} encontrava-se em situação **{status}**, com tendência de {dir_iqa} ao longo dos últimos {janela} anos. Como limitação, destaca-se que os indicadores são obtidos de uma série simulada (proxy histórico), não de telemetria direta. Recomenda-se o acompanhamento contínuo dos parâmetros de Oxigênio Dissolvido e Demanda Bioquímica de Oxigênio, e a priorização de medidas de controle caso a tendência de deterioração se confirme.",
        "en": "Based on the analyzed indicators, the {trecho} stretch was in **{status}** condition, with a {dir_iqa} trend over the last {janela} years. As a limitation, it should be noted that the indicators are obtained from a simulated series (historical proxy), not direct telemetry. Continuous monitoring of the Dissolved Oxygen and Biochemical Oxygen Demand parameters is recommended, along with prioritizing control measures should the deteriorating trend be confirmed.",
        "fr": "Sur la base des indicateurs analysés, le tronçon {trecho} se trouvait en situation **{status}**, avec une tendance {dir_iqa} au cours des {janela} dernières années. Comme limite, il convient de noter que les indicateurs proviennent d'une série simulée (proxy historique), pas de télémétrie directe. Il est recommandé de suivre en continu les paramètres d'Oxygène Dissous et de Demande Biochimique en Oxygène, et de prioriser des mesures de contrôle si la tendance à la détérioration se confirme.",
        "es": "Con base en los indicadores analizados, el tramo {trecho} se encontraba en situación **{status}**, con tendencia {dir_iqa} a lo largo de los últimos {janela} años. Como limitación, se destaca que los indicadores se obtienen de una serie simulada (proxy histórico), no de telemetría directa. Se recomienda el seguimiento continuo de los parámetros de Oxígeno Disuelto y Demanda Bioquímica de Oxígeno, y la priorización de medidas de control en caso de confirmarse la tendencia de deterioro.",
    },
    "rel.b.anexos_texto": {
        "pt": "Os dados brutos da série histórica simulada (todos os anos e trechos) podem ser consultados nas telas \"Séries Históricas\" e \"Mapa Interativo\" do painel WaterWeave-Tietê.",
        "en": "The raw data of the simulated historical series (all years and stretches) can be consulted on the \"Historical Series\" and \"Interactive Map\" screens of the WaterWeave-Tietê dashboard.",
        "fr": "Les données brutes de la série historique simulée (toutes les années et tous les tronçons) peuvent être consultées sur les écrans « Séries Historiques » et « Carte Interactive » du tableau de bord WaterWeave-Tietê.",
        "es": "Los datos brutos de la serie histórica simulada (todos los años y tramos) pueden consultarse en las pantallas \"Series Históricas\" y \"Mapa Interactivo\" del panel WaterWeave-Tietê.",
    },
    "rel.b.titulo_pdf": {"pt": "Relatório de Qualidade da Água — {trecho} ({ano})", "en": "Water Quality Report — {trecho} ({ano})", "fr": "Rapport de Qualité de l'Eau — {trecho} ({ano})", "es": "Informe de Calidad del Agua — {trecho} ({ano})"},

    # ---- pdf_generator.py — Relatório de Cenário em PDF, Modelo Resumido (Opção A) ---------
    "cn.a.objetivo_texto": {
        "pt": "Apresentar, de forma direta e objetiva, o resultado projetado da configuração de controle escolhida para o trecho {trecho} do Rio Tietê, ao longo de um horizonte de {horizonte} anos.",
        "en": "Present, directly and objectively, the projected result of the chosen control configuration for the {trecho} stretch of the Tietê River, over a {horizonte}-year horizon.",
        "fr": "Présenter, de manière directe et objective, le résultat projeté de la configuration de contrôle choisie pour le tronçon {trecho} du fleuve Tietê, sur un horizon de {horizonte} ans.",
        "es": "Presentar, de forma directa y objetiva, el resultado proyectado de la configuración de control elegida para el tramo {trecho} del Río Tietê, a lo largo de un horizonte de {horizonte} años.",
    },
    "cn.a.resumo_atividades_itens": {
        "pt": "- Simulação da configuração de controle escolhida (sedimentos/erosão, esgoto/efluentes, fertilizantes/agrotóxicos, vazão ecológica) ao longo do horizonte.\n- Comparação com um cenário de inação (patamar fixo pessimista).\n- Identificação das implicações práticas do resultado projetado.",
        "en": "- Simulation of the chosen control configuration (sediment/erosion, sewage/effluents, fertilizers/pesticides, ecological flow) over the horizon.\n- Comparison against an inaction scenario (fixed, pessimistic baseline).\n- Identification of the practical implications of the projected result.",
        "fr": "- Simulation de la configuration de contrôle choisie (sédiments/érosion, eaux usées/effluents, engrais/pesticides, débit écologique) sur l'horizon.\n- Comparaison avec un scénario d'inaction (niveau fixe pessimiste).\n- Identification des implications pratiques du résultat projeté.",
        "es": "- Simulación de la configuración de control elegida (sedimentos/erosión, aguas residuales/efluentes, fertilizantes/agroquímicos, caudal ecológico) a lo largo del horizonte.\n- Comparación con un escenario de inacción (nivel fijo pesimista).\n- Identificación de las implicaciones prácticas del resultado proyectado.",
    },

    # ---- pdf_generator.py — Relatório Automático em PDF, modelo Resumido (Opção A) --------
    "pdf.a.titulo_pdf": {"pt": "Relatório de Qualidade da Água — {trecho} ({ano})", "en": "Water Quality Report — {trecho} ({ano})", "fr": "Rapport de Qualité de l'Eau — {trecho} ({ano})", "es": "Informe de Calidad del Agua — {trecho} ({ano})"},
    "pdf.a.titulo_pdf_todos": {"pt": "Relatório de Qualidade da Água — Todos os Trechos ({ano})", "en": "Water Quality Report — All Stretches ({ano})", "fr": "Rapport de Qualité de l'Eau — Tous les Tronçons ({ano})", "es": "Informe de Calidad del Agua — Todos los Tramos ({ano})"},
    "pdf.a.data_emissao": {"pt": "Data de emissão", "en": "Issue date", "fr": "Date d'émission", "es": "Fecha de emisión"},
    "pdf.a.local": {"pt": "Local", "en": "Location", "fr": "Lieu", "es": "Lugar"},
    "pdf.a.local_prefixo": {"pt": "Bacia do Rio Tietê", "en": "Tietê River Basin", "fr": "Bassin du Fleuve Tietê", "es": "Cuenca del Río Tietê"},
    "pdf.a.autor": {"pt": "Autor/Responsável", "en": "Author/Responsible party", "fr": "Auteur/Responsable", "es": "Autor/Responsable"},
    "pdf.a.autor_valor": {"pt": "Sistema WaterWeave-Tietê (geração automatizada)", "en": "WaterWeave-Tietê System (automated generation)", "fr": "Système WaterWeave-Tietê (génération automatisée)", "es": "Sistema WaterWeave-Tietê (generación automatizada)"},
    "pdf.a.objetivo_titulo": {"pt": "Objetivo", "en": "Objective", "fr": "Objectif", "es": "Objetivo"},
    "pdf.a.objetivo_texto": {
        "pt": "Apresentar, de forma direta e objetiva, o estado atual da qualidade da água do trecho {trecho} do Rio Tietê no ano de {ano}, com base na simulação hidrobiogeoquímica do sistema WaterWeave-Tietê.",
        "en": "Present, directly and objectively, the current water quality status of the {trecho} stretch of the Tietê River in {ano}, based on the WaterWeave-Tietê system's hydro-biogeochemical simulation.",
        "fr": "Présenter, de manière directe et objective, l'état actuel de la qualité de l'eau du tronçon {trecho} du fleuve Tietê en {ano}, sur la base de la simulation hydro-biogéochimique du système WaterWeave-Tietê.",
        "es": "Presentar, de forma directa y objetiva, el estado actual de la calidad del agua del tramo {trecho} del Río Tietê en el año {ano}, con base en la simulación hidrobiogeoquímica del sistema WaterWeave-Tietê.",
    },
    "pdf.a.objetivo_texto_todos": {
        "pt": "Apresentar, de forma direta e objetiva, o estado atual da qualidade da água de todos os trechos monitorados do Rio Tietê no ano de {ano}, com base na simulação hidrobiogeoquímica do sistema WaterWeave-Tietê.",
        "en": "Present, directly and objectively, the current water quality status of all monitored stretches of the Tietê River in {ano}, based on the WaterWeave-Tietê system's hydro-biogeochemical simulation.",
        "fr": "Présenter, de manière directe et objective, l'état actuel de la qualité de l'eau de tous les tronçons surveillés du fleuve Tietê en {ano}, sur la base de la simulation hydro-biogéochimique du système WaterWeave-Tietê.",
        "es": "Presentar, de forma directa y objetiva, el estado actual de la calidad del agua de todos los tramos monitoreados del Río Tietê en el año {ano}, con base en la simulación hidrobiogeoquímica del sistema WaterWeave-Tietê.",
    },
    "pdf.a.resumo_atividades_titulo": {"pt": "Resumo das Atividades", "en": "Summary of Activities", "fr": "Résumé des Activités", "es": "Resumen de las Actividades"},
    "pdf.a.resumo_atividades_itens": {
        "pt": "- Consulta à série histórica simulada (modelo baseado em agentes + balanço hídrico + Streeter-Phelps) do trecho.\n- Cálculo do Índice de Qualidade da Água (IQA), do Oxigênio Dissolvido (OD) e da Demanda Bioquímica de Oxigênio (DBO).\n- Comparação com a média histórica da série e com a tendência dos últimos {janela} anos.",
        "en": "- Consultation of the simulated historical series (agent-based model + water balance + Streeter-Phelps) for the stretch.\n- Calculation of the Water Quality Index (WQI), Dissolved Oxygen (DO) and Biochemical Oxygen Demand (BOD).\n- Comparison against the series' historical average and the trend over the last {janela} years.",
        "fr": "- Consultation de la série historique simulée (modèle multi-agents + bilan hydrique + Streeter-Phelps) du tronçon.\n- Calcul de l'Indice de Qualité de l'Eau (IQE), de l'Oxygène Dissous (OD) et de la Demande Biochimique en Oxygène (DBO).\n- Comparaison avec la moyenne historique de la série et la tendance des {janela} dernières années.",
        "es": "- Consulta a la serie histórica simulada (modelo basado en agentes + balance hídrico + Streeter-Phelps) del tramo.\n- Cálculo del Índice de Calidad del Agua (ICA), el Oxígeno Disuelto (OD) y la Demanda Bioquímica de Oxígeno (DBO).\n- Comparación con el promedio histórico de la serie y con la tendencia de los últimos {janela} años.",
    },
    "pdf.a.resultados_titulo": {"pt": "Resultados Principais", "en": "Main Results", "fr": "Résultats Principaux", "es": "Resultados Principales"},
    "pdf.a.assinatura_titulo": {"pt": "Assinatura", "en": "Signature", "fr": "Signature", "es": "Firma"},
    "pdf.a.assinatura_responsavel": {"pt": "Responsável técnico:", "en": "Technical officer:", "fr": "Responsable technique :", "es": "Responsable técnico:"},
    "pdf.a.assinatura_cargo": {"pt": "Cargo/Função:", "en": "Position/Role:", "fr": "Poste/Fonction :", "es": "Cargo/Función:"},
    "pdf.a.assinatura_visto": {"pt": "Visto:", "en": "Approved by:", "fr": "Visa :", "es": "Visto bueno:"},

    # ---- Cenários Futuros — cenario_narrativo.py (relatório PDF ABNT) --------------------
    "cn.titulo": {"pt": "Cenário simulado — {trecho}, {horizonte} anos à frente", "en": "Simulated scenario — {trecho}, {horizonte} years ahead", "fr": "Scénario simulé — {trecho}, {horizonte} ans plus tard", "es": "Escenario simulado — {trecho}, {horizonte} años más adelante"},
    "cn.sec.config": {"pt": "Configuração Escolhida", "en": "Chosen Configuration", "fr": "Configuration Choisie", "es": "Configuración Elegida"},
    "cn.sec.resultado": {"pt": "Resultado da Simulação", "en": "Simulation Result", "fr": "Résultat de la Simulation", "es": "Resultado de la Simulación"},
    "cn.sec.comparacao": {"pt": "Comparação com a Inação", "en": "Comparison with Inaction", "fr": "Comparaison avec l'Inaction", "es": "Comparación con la Inacción"},
    "cn.sec.implicacoes": {"pt": "Implicações Práticas", "en": "Practical Implications", "fr": "Implications Pratiques", "es": "Implicaciones Prácticas"},
    "cn.sec.nota": {"pt": "Nota Metodológica", "en": "Methodological Note", "fr": "Note Méthodologique", "es": "Nota Metodológica"},

    "cn.config.sedimentar_on": {"pt": "controle de sedimentos/erosão em {pct}% de esforço", "en": "sediment/erosion control at {pct}% effort", "fr": "contrôle des sédiments/érosion à {pct}% d'effort", "es": "control de sedimentos/erosión al {pct}% de esfuerzo"},
    "cn.config.sedimentar_off": {"pt": "nenhum controle de sedimentos/erosão", "en": "no sediment/erosion control", "fr": "aucun contrôle des sédiments/érosion", "es": "ningún control de sedimentos/erosión"},
    "cn.config.esgoto_on": {"pt": "controle de esgoto/efluentes em {pct}% de esforço", "en": "sewage/effluent control at {pct}% effort", "fr": "contrôle des eaux usées/effluents à {pct}% d'effort", "es": "control de aguas residuales/efluentes al {pct}% de esfuerzo"},
    "cn.config.esgoto_off": {"pt": "nenhum controle de esgoto/efluentes", "en": "no sewage/effluent control", "fr": "aucun contrôle des eaux usées/effluents", "es": "ningún control de aguas residuales/efluentes"},
    "cn.config.agricola_on": {"pt": "controle de fertilizantes/agrotóxicos em {pct}% de esforço", "en": "fertilizer/pesticide control at {pct}% effort", "fr": "contrôle des engrais/pesticides à {pct}% d'effort", "es": "control de fertilizantes/agroquímicos al {pct}% de esfuerzo"},
    "cn.config.agricola_off": {"pt": "nenhum controle de fertilizantes/agrotóxicos", "en": "no fertilizer/pesticide control", "fr": "aucun contrôle des engrais/pesticides", "es": "ningún control de fertilizantes/agroquímicos"},
    "cn.config.outorga": {"pt": "vazão ecológica mínima reservada de {pct}", "en": "minimum ecological flow reserved at {pct}", "fr": "débit écologique minimal réservé de {pct}", "es": "caudal ecológico mínimo reservado de {pct}"},
    "cn.config.clima": {"pt": "severidade climática assumida de {pct}%", "en": "assumed climate severity of {pct}%", "fr": "sévérité climatique supposée de {pct}%", "es": "severidad climática asumida de {pct}%"},
    "cn.config.prefixo": {"pt": "**Configuração escolhida:** ", "en": "**Chosen configuration:** ", "fr": "**Configuration choisie :** ", "es": "**Configuración elegida:** "},

    "cn.resultado.texto": {
        "pt": "**Se essas medidas forem mantidas:** o IQA simulado {tend_iqa}, terminando em situação **{status}**. O Oxigênio Dissolvido {tend_od}, e a DBO {tend_dbo}. A Turbidez {tend_turb} e o Índice Biótico (macroinvertebrados/peixes sensíveis) {tend_bio}.",
        "en": "**If these measures are kept:** the simulated WQI {tend_iqa}, ending in **{status}** condition. Dissolved Oxygen {tend_od}, and BOD {tend_dbo}. Turbidity {tend_turb} and the Biotic Index (sensitive macroinvertebrates/fish) {tend_bio}.",
        "fr": "**Si ces mesures sont maintenues :** l'IQE simulé {tend_iqa}, se terminant dans une situation **{status}**. L'Oxygène Dissous {tend_od}, et la DBO {tend_dbo}. La Turbidité {tend_turb} et l'Indice Biotique (macroinvertébrés/poissons sensibles) {tend_bio}.",
        "es": "**Si estas medidas se mantienen:** el ICA simulado {tend_iqa}, terminando en situación **{status}**. El Oxígeno Disuelto {tend_od}, y la DBO {tend_dbo}. La Turbidez {tend_turb} y el Índice Biótico (macroinvertebrados/peces sensibles) {tend_bio}.",
    },
    "cn.tend.subiu": {"pt": "subiu de {ini:.1f} para {fim:.1f} ({delta:+.1f})", "en": "rose from {ini:.1f} to {fim:.1f} ({delta:+.1f})", "fr": "est passé de {ini:.1f} à {fim:.1f} ({delta:+.1f})", "es": "subió de {ini:.1f} a {fim:.1f} ({delta:+.1f})"},
    "cn.tend.caiu": {"pt": "caiu de {ini:.1f} para {fim:.1f} ({delta:+.1f})", "en": "fell from {ini:.1f} to {fim:.1f} ({delta:+.1f})", "fr": "est tombé de {ini:.1f} à {fim:.1f} ({delta:+.1f})", "es": "cayó de {ini:.1f} a {fim:.1f} ({delta:+.1f})"},
    "cn.tend.estavel": {"pt": "manteve-se estável em {fim:.1f}", "en": "stayed stable at {fim:.1f}", "fr": "est resté stable à {fim:.1f}", "es": "se mantuvo estable en {fim:.1f}"},

    "cn.comparacao.melhor": {
        "pt": "Isso é **{diff:.0f} pontos de IQA melhor** do que se nada for feito — no cenário não controlado, o IQA chegaria a apenas {iqa_nc:.0f} ({status_nc}) no mesmo horizonte.",
        "en": "That is **{diff:.0f} WQI points better** than doing nothing — in the uncontrolled scenario, the WQI would reach only {iqa_nc:.0f} ({status_nc}) over the same horizon.",
        "fr": "C'est **{diff:.0f} points d'IQE de mieux** que de ne rien faire — dans le scénario non contrôlé, l'IQE n'atteindrait que {iqa_nc:.0f} ({status_nc}) sur le même horizon.",
        "es": "Eso es **{diff:.0f} puntos de ICA mejor** que no hacer nada — en el escenario no controlado, el ICA llegaría a solo {iqa_nc:.0f} ({status_nc}) en el mismo horizonte.",
    },
    "cn.comparacao.pior": {
        "pt": "Surpreendentemente, o cenário não controlado termina **{diff:.0f} pontos de IQA acima** deste — vale revisar os esforços escolhidos, ou isso reflete a resposta automática do Comitê de Bacia (outorga) já presente em ambos os cenários.",
        "en": "Surprisingly, the uncontrolled scenario ends **{diff:.0f} WQI points above** this one — it's worth reviewing the chosen efforts, or this reflects the automatic response of the Basin Committee (water rights) already present in both scenarios.",
        "fr": "Étonnamment, le scénario non contrôlé se termine **{diff:.0f} points d'IQE au-dessus** de celui-ci — il convient de revoir les efforts choisis, ou cela reflète la réponse automatique du Comité de Bassin (prélèvements) déjà présente dans les deux scénarios.",
        "es": "Sorprendentemente, el escenario no controlado termina **{diff:.0f} puntos de ICA por encima** de este — vale la pena revisar los esfuerzos elegidos, o esto refleja la respuesta automática del Comité de Cuenca (concesión) ya presente en ambos escenarios.",
    },
    "cn.comparacao.proximo": {
        "pt": "O resultado fica próximo do cenário não controlado (IQA {iqa_nc:.0f}) — os esforços escolhidos ainda não são suficientes para uma mudança clara neste horizonte.",
        "en": "The result stays close to the uncontrolled scenario (WQI {iqa_nc:.0f}) — the chosen efforts are not yet enough for a clear change over this horizon.",
        "fr": "Le résultat reste proche du scénario non contrôlé (IQE {iqa_nc:.0f}) — les efforts choisis ne suffisent pas encore à un changement net sur cet horizon.",
        "es": "El resultado queda cerca del escenario no controlado (ICA {iqa_nc:.0f}) — los esfuerzos elegidos aún no son suficientes para un cambio claro en este horizonte.",
    },

    "cn.impl.prefixo": {"pt": "**O que isso significa na prática:** ", "en": "**What this means in practice:** ", "fr": "**Ce que cela signifie en pratique :** ", "es": "**Qué significa esto en la práctica:** "},
    "cn.impl.ecoli_alto": {
        "pt": "a contagem de E. coli projetada ({valor} NMP/100 mL) ainda indicaria risco alto de contaminação por contato com a água ou consumo de peixe local.",
        "en": "the projected E. coli count ({valor} MPN/100 mL) would still indicate a high risk of contamination from water contact or eating local fish.",
        "fr": "le nombre projeté d'E. coli ({valor} NPP/100 mL) indiquerait toujours un risque élevé de contamination par contact avec l'eau ou consommation de poisson local.",
        "es": "el recuento proyectado de E. coli ({valor} NMP/100 mL) todavía indicaría un riesgo alto de contaminación por contacto con el agua o consumo de pescado local.",
    },
    "cn.impl.ecoli_moderado": {
        "pt": "a contagem de E. coli projetada ({valor} NMP/100 mL) ainda mereceria cautela para atividades de contato direto (banho, pesca esportiva).",
        "en": "the projected E. coli count ({valor} MPN/100 mL) would still warrant caution for direct-contact activities (swimming, sport fishing).",
        "fr": "le nombre projeté d'E. coli ({valor} NPP/100 mL) justifierait encore la prudence pour les activités de contact direct (baignade, pêche sportive).",
        "es": "el recuento proyectado de E. coli ({valor} NMP/100 mL) todavía merecería cautela para actividades de contacto directo (baño, pesca deportiva).",
    },
    "cn.impl.ecoli_baixo": {
        "pt": "a contagem de E. coli projetada indicaria baixo risco sanitário direto.",
        "en": "the projected E. coli count would indicate low direct health risk.",
        "fr": "le nombre projeté d'E. coli indiquerait un faible risque sanitaire direct.",
        "es": "el recuento proyectado de E. coli indicaría bajo riesgo sanitario directo.",
    },
    "cn.impl.od_critico": {
        "pt": "o Oxigênio Dissolvido projetado ({valor:.2f} mg/L) ainda causaria estresse para peixes e outros organismos aquáticos.",
        "en": "the projected Dissolved Oxygen ({valor:.2f} mg/L) would still cause stress for fish and other aquatic organisms.",
        "fr": "l'Oxygène Dissous projeté ({valor:.2f} mg/L) causerait toujours un stress pour les poissons et autres organismes aquatiques.",
        "es": "el Oxígeno Disuelto proyectado ({valor:.2f} mg/L) todavía causaría estrés para peces y otros organismos acuáticos.",
    },
    "cn.impl.turbidez": {
        "pt": "a Turbidez projetada ({valor:.0f} NTU) ainda comprometeria a entrada de luz, prejudicando plantas aquáticas e a fotossíntese do rio.",
        "en": "the projected Turbidity ({valor:.0f} NTU) would still compromise light penetration, harming aquatic plants and the river's photosynthesis.",
        "fr": "la Turbidité projetée ({valor:.0f} NTU) compromettrait encore la pénétration de la lumière, nuisant aux plantes aquatiques et à la photosynthèse de la rivière.",
        "es": "la Turbidez proyectada ({valor:.0f} NTU) todavía comprometería la entrada de luz, perjudicando las plantas acuáticas y la fotosíntesis del río.",
    },
    "cn.impl.eutrofizacao": {
        "pt": "os níveis de Fósforo/Nitrogênio projetados ainda favoreceriam a proliferação de algas (eutrofização), especialmente em trechos com água mais parada.",
        "en": "the projected Phosphorus/Nitrogen levels would still favor algae proliferation (eutrophication), especially in stretches with more stagnant water.",
        "fr": "les niveaux projetés de Phosphore/Azote favoriseraient encore la prolifération d'algues (eutrophisation), en particulier dans les tronçons où l'eau est plus stagnante.",
        "es": "los niveles proyectados de Fósforo/Nitrógeno todavía favorecerían la proliferación de algas (eutrofización), especialmente en tramos con agua más estancada.",
    },
    "cn.impl.metais": {
        "pt": "o índice de Metais Pesados e Tóxicos projetado ainda seria uma preocupação relevante.",
        "en": "the projected Heavy Metals and Toxics index would still be a relevant concern.",
        "fr": "l'indice projeté de Métaux Lourds et Toxiques resterait une préoccupation pertinente.",
        "es": "el índice proyectado de Metales Pesados y Tóxicos todavía sería una preocupación relevante.",
    },
    "cn.impl.biotico_bom": {
        "pt": "o Índice Biótico projetado sugere condições favoráveis ao retorno de espécies sensíveis à poluição (larvas de insetos aquáticos, peixes mais exigentes em qualidade de água).",
        "en": "the projected Biotic Index suggests favorable conditions for the return of pollution-sensitive species (aquatic insect larvae, more demanding fish species).",
        "fr": "l'Indice Biotique projeté suggère des conditions favorables au retour d'espèces sensibles à la pollution (larves d'insectes aquatiques, poissons plus exigeants en qualité d'eau).",
        "es": "el Índice Biótico proyectado sugiere condiciones favorables para el retorno de especies sensibles a la contaminación (larvas de insectos acuáticos, peces más exigentes en calidad de agua).",
    },
    "cn.impl.biotico_baixo": {
        "pt": "o Índice Biótico projetado permaneceria baixo — pouca perspectiva de retorno de espécies sensíveis à poluição nesse horizonte.",
        "en": "the projected Biotic Index would remain low — little prospect of pollution-sensitive species returning over this horizon.",
        "fr": "l'Indice Biotique projeté resterait faible — peu de perspective de retour d'espèces sensibles à la pollution sur cet horizon.",
        "es": "el Índice Biótico proyectado permanecería bajo — poca perspectiva de retorno de especies sensibles a la contaminación en este horizonte.",
    },

    "cn.nota": {
        "pt": "Simulação via modelo de agentes (Mesa) + balanço hídrico + Streeter-Phelps, com submodelos estendidos ancorados em médias reais 2012-2024 da CETESB. O IQA é um proxy simplificado de OD/DBO; o Índice Biótico e o índice de Metais/Tóxicos são proxies ilustrativos que combinam os demais parâmetros simulados, não medições diretas de campo. Cada trecho do rio é simulado de forma independente, sem propagação de carga entre trechos.",
        "en": "Simulation via agent-based model (Mesa) + water balance + Streeter-Phelps, with extended submodels anchored to real 2012-2024 CETESB averages. The WQI is a simplified proxy for DO/BOD; the Biotic Index and the Metals/Toxics index are illustrative proxies combining the other simulated parameters, not direct field measurements. Each river stretch is simulated independently, with no load propagation between stretches.",
        "fr": "Simulation via un modèle multi-agents (Mesa) + bilan hydrique + Streeter-Phelps, avec des sous-modèles étendus ancrés sur des moyennes réelles CETESB 2012-2024. L'IQE est un proxy simplifié de l'OD/DBO ; l'Indice Biotique et l'indice Métaux/Toxiques sont des proxys illustratifs combinant les autres paramètres simulés, pas des mesures directes de terrain. Chaque tronçon du fleuve est simulé indépendamment, sans propagation de charge entre les tronçons.",
        "es": "Simulación vía modelo basado en agentes (Mesa) + balance hídrico + Streeter-Phelps, con submodelos extendidos anclados en promedios reales 2012-2024 de la CETESB. El ICA es un proxy simplificado de OD/DBO; el Índice Biótico y el índice de Metales/Tóxicos son proxies ilustrativos que combinan los demás parámetros simulados, no mediciones directas de campo. Cada tramo del río se simula de forma independiente, sin propagación de carga entre tramos.",
    },

    # ---- cenario_narrativo.py / pdf_generator.py — Relatório de Cenário, Modelo Completo
    # ---- (Opção B / NBR 10719): capa, folha de rosto, resumo, sumário, introdução, ----------
    # ---- metodologia, desenvolvimento, resultados e discussão, conclusão, referências ------
    "cn.b.sec.resumo": {"pt": "Resumo", "en": "Abstract", "fr": "Résumé", "es": "Resumen"},
    "cn.b.palavras_chave_label": {"pt": "Palavras-chave:", "en": "Keywords:", "fr": "Mots-clés :", "es": "Palabras clave:"},
    "cn.b.palavras_chave_lista": {
        "pt": "Qualidade da água; Rio Tietê; Modelagem baseada em agentes; Simulação ambiental; Índice de Qualidade da Água.",
        "en": "Water quality; Tietê River; Agent-based modeling; Environmental simulation; Water Quality Index.",
        "fr": "Qualité de l'eau ; Fleuve Tietê ; Modélisation multi-agents ; Simulation environnementale ; Indice de Qualité de l'Eau.",
        "es": "Calidad del agua; Río Tietê; Modelado basado en agentes; Simulación ambiental; Índice de Calidad del Agua.",
    },
    "cn.b.sec.sumario": {"pt": "Sumário", "en": "Contents", "fr": "Sommaire", "es": "Sumario"},
    "cn.b.sec.introducao": {"pt": "Introdução", "en": "Introduction", "fr": "Introduction", "es": "Introducción"},
    "cn.b.sec.metodologia": {"pt": "Metodologia", "en": "Methodology", "fr": "Méthodologie", "es": "Metodología"},
    "cn.b.sec.desenvolvimento": {"pt": "Desenvolvimento", "en": "Development", "fr": "Développement", "es": "Desarrollo"},
    "cn.b.sec.resultados_discussao": {"pt": "Resultados e Discussão", "en": "Results and Discussion", "fr": "Résultats et Discussion", "es": "Resultados y Discusión"},
    "cn.b.sec.conclusao": {"pt": "Conclusão", "en": "Conclusion", "fr": "Conclusion", "es": "Conclusión"},
    "cn.b.sec.referencias": {"pt": "Referências Bibliográficas", "en": "Bibliographic References", "fr": "Références Bibliographiques", "es": "Referencias Bibliográficas"},
    "cn.b.sec.anexos": {"pt": "Anexos", "en": "Appendices", "fr": "Annexes", "es": "Anexos"},

    "cn.b.folha_rosto.natureza_label": {"pt": "Natureza do trabalho:", "en": "Nature of the work:", "fr": "Nature du travail :", "es": "Naturaleza del trabajo:"},
    "cn.b.folha_rosto.natureza_texto": {
        "pt": "Relatório técnico-científico gerado por simulação computacional.",
        "en": "Technical-scientific report generated by computational simulation.",
        "fr": "Rapport technico-scientifique généré par simulation informatique.",
        "es": "Informe técnico-científico generado por simulación computacional.",
    },
    "cn.b.folha_rosto.instituicao_label": {"pt": "Instituição/Sistema:", "en": "Institution/System:", "fr": "Institution/Système :", "es": "Institución/Sistema:"},
    "cn.b.folha_rosto.objetivo_label": {"pt": "Objetivo do relatório:", "en": "Report objective:", "fr": "Objectif du rapport :", "es": "Objetivo del informe:"},

    "cn.b.resumo_texto": {
        "pt": "Este relatório documenta uma simulação computacional da qualidade da água do trecho {trecho} do Rio Tietê, projetada por um horizonte de {horizonte} anos, com o objetivo de avaliar o impacto de diferentes níveis de esforço de controle da poluição (sedimentos/erosão, esgoto/efluentes, fertilizantes/agrotóxicos) e da vazão ecológica mínima reservada sobre a recuperação do corpo hídrico. A simulação combina um modelo baseado em agentes (Mesa), balanço hídrico simplificado e a formulação clássica de Streeter-Phelps, complementados por submodelos de Turbidez, Sólidos Totais, pH, Nutrientes, Metais/Tóxicos, E. coli e Índice Biótico, todos ancorados em médias reais da CETESB no período 2012-2024. Na configuração escolhida, o Índice de Qualidade da Água (ICA) simulado {tend_iqa_resumo}, terminando o horizonte em situação **{status}**; {comparacao_resumo}. Conclui-se que o cenário simulado permite estimar, de forma ilustrativa e não calibrada, a magnitude do efeito de cada frente de controle sobre a recuperação do rio, servindo de subsídio para a priorização de investimentos na bacia.",
        "en": "This report documents a computational simulation of water quality for the {trecho} stretch of the Tietê River, projected over a {horizonte}-year horizon, aiming to assess the impact of different levels of pollution-control effort (sediment/erosion, sewage/effluents, fertilizers/pesticides) and of the minimum ecological flow reserved on the recovery of the water body. The simulation combines an agent-based model (Mesa), a simplified water balance and the classic Streeter-Phelps formulation, complemented by submodels for Turbidity, Total Solids, pH, Nutrients, Metals/Toxics, E. coli and the Biotic Index, all anchored to real 2012-2024 CETESB averages. Under the chosen configuration, the simulated Water Quality Index (WQI) {tend_iqa_resumo}, ending the horizon in **{status}** condition; {comparacao_resumo}. It is concluded that the simulated scenario allows estimating, in an illustrative and non-calibrated way, the magnitude of the effect of each control front on the river's recovery, providing input for prioritizing investments in the basin.",
        "fr": "Ce rapport documente une simulation informatique de la qualité de l'eau du tronçon {trecho} du fleuve Tietê, projetée sur un horizon de {horizonte} ans, dans le but d'évaluer l'impact de différents niveaux d'effort de contrôle de la pollution (sédiments/érosion, eaux usées/effluents, engrais/pesticides) et du débit écologique minimal réservé sur la récupération du corps d'eau. La simulation combine un modèle multi-agents (Mesa), un bilan hydrique simplifié et la formulation classique de Streeter-Phelps, complétés par des sous-modèles de Turbidité, Solides Totaux, pH, Nutriments, Métaux/Toxiques, E. coli et Indice Biotique, tous ancrés sur des moyennes réelles CETESB 2012-2024. Dans la configuration choisie, l'Indice de Qualité de l'Eau (IQE) simulé {tend_iqa_resumo}, terminant l'horizon en situation **{status}** ; {comparacao_resumo}. Il est conclu que le scénario simulé permet d'estimer, de manière illustrative et non calibrée, l'ampleur de l'effet de chaque front de contrôle sur la récupération du fleuve, fournissant un appui à la priorisation des investissements dans le bassin.",
        "es": "Este informe documenta una simulación computacional de la calidad del agua del tramo {trecho} del Río Tietê, proyectada en un horizonte de {horizonte} años, con el objetivo de evaluar el impacto de diferentes niveles de esfuerzo de control de la contaminación (sedimentos/erosión, aguas residuales/efluentes, fertilizantes/agroquímicos) y del caudal ecológico mínimo reservado sobre la recuperación del cuerpo hídrico. La simulación combina un modelo basado en agentes (Mesa), un balance hídrico simplificado y la formulación clásica de Streeter-Phelps, complementados por submodelos de Turbidez, Sólidos Totales, pH, Nutrientes, Metales/Tóxicos, E. coli e Índice Biótico, todos anclados en promedios reales de la CETESB en el período 2012-2024. En la configuración elegida, el Índice de Calidad del Agua (ICA) simulado {tend_iqa_resumo}, terminando el horizonte en situación **{status}**; {comparacao_resumo}. Se concluye que el escenario simulado permite estimar, de forma ilustrativa y no calibrada, la magnitud del efecto de cada frente de control sobre la recuperación del río, sirviendo de insumo para la priorización de inversiones en la cuenca.",
    },
    "cn.b.resumo_comparacao_melhor": {
        "pt": "esse resultado supera em {diff:.0f} pontos de ICA o cenário de inação no mesmo horizonte",
        "en": "this result exceeds the inaction scenario by {diff:.0f} WQI points over the same horizon",
        "fr": "ce résultat dépasse de {diff:.0f} points d'IQE le scénario d'inaction sur le même horizon",
        "es": "este resultado supera en {diff:.0f} puntos de ICA al escenario de inacción en el mismo horizonte",
    },
    "cn.b.resumo_comparacao_pior": {
        "pt": "esse resultado fica {diff:.0f} pontos de ICA abaixo do cenário de inação no mesmo horizonte",
        "en": "this result falls {diff:.0f} WQI points short of the inaction scenario over the same horizon",
        "fr": "ce résultat reste {diff:.0f} points d'IQE en dessous du scénario d'inaction sur le même horizon",
        "es": "este resultado queda {diff:.0f} puntos de ICA por debajo del escenario de inacción en el mismo horizonte",
    },
    "cn.b.resumo_comparacao_proximo": {
        "pt": "esse resultado permanece próximo do cenário de inação, sem uma mudança clara no horizonte simulado",
        "en": "this result remains close to the inaction scenario, without a clear change over the simulated horizon",
        "fr": "ce résultat reste proche du scénario d'inaction, sans changement net sur l'horizon simulé",
        "es": "este resultado permanece cerca del escenario de inacción, sin un cambio claro en el horizonte simulado",
    },

    "cn.b.introducao_contexto": {
        "pt": "O Rio Tietê atravessa a Região Metropolitana de São Paulo e áreas agrícolas e industriais ao longo de seus três grandes trechos (Alto, Médio e Baixo Tietê), sofrendo pressões distintas de poluição em cada segmento. Compreender como diferentes níveis de esforço de controle afetam a trajetória futura da qualidade da água é essencial para orientar decisões de investimento e políticas de gestão da bacia.",
        "en": "The Tietê River crosses the São Paulo Metropolitan Region and agricultural and industrial areas along its three major stretches (Upper, Middle and Lower Tietê), facing distinct pollution pressures in each segment. Understanding how different levels of control effort affect the future trajectory of water quality is essential for guiding investment decisions and basin management policies.",
        "fr": "Le fleuve Tietê traverse la région métropolitaine de São Paulo ainsi que des zones agricoles et industrielles le long de ses trois grands tronçons (Haut, Moyen et Bas Tietê), subissant des pressions de pollution distinctes dans chaque segment. Comprendre comment différents niveaux d'effort de contrôle affectent la trajectoire future de la qualité de l'eau est essentiel pour orienter les décisions d'investissement et les politiques de gestion du bassin.",
        "es": "El Río Tietê atraviesa la Región Metropolitana de São Paulo y áreas agrícolas e industriales a lo largo de sus tres grandes tramos (Alto, Medio y Bajo Tietê), enfrentando presiones de contaminación distintas en cada segmento. Comprender cómo diferentes niveles de esfuerzo de control afectan la trayectoria futura de la calidad del agua es esencial para orientar decisiones de inversión y políticas de gestión de la cuenca.",
    },
    "cn.b.objetivo_geral_label": {"pt": "Objetivo geral:", "en": "General objective:", "fr": "Objectif général :", "es": "Objetivo general:"},
    "cn.b.objetivo_geral_texto": {
        "pt": "Simular e comparar a evolução da qualidade da água do trecho {trecho} do Rio Tietê ao longo de um horizonte de {horizonte} anos, sob a configuração de controle escolhida, frente a um cenário de inação.",
        "en": "Simulate and compare the evolution of water quality for the {trecho} stretch of the Tietê River over a {horizonte}-year horizon, under the chosen control configuration, against an inaction scenario.",
        "fr": "Simuler et comparer l'évolution de la qualité de l'eau du tronçon {trecho} du fleuve Tietê sur un horizon de {horizonte} ans, selon la configuration de contrôle choisie, face à un scénario d'inaction.",
        "es": "Simular y comparar la evolución de la calidad del agua del tramo {trecho} del Río Tietê a lo largo de un horizonte de {horizonte} años, bajo la configuración de control elegida, frente a un escenario de inacción.",
    },
    "cn.b.objetivos_especificos_label": {"pt": "Objetivos específicos:", "en": "Specific objectives:", "fr": "Objectifs spécifiques :", "es": "Objetivos específicos:"},
    "cn.b.objetivos_especificos_itens": {
        "pt": "- Estimar a trajetória do Índice de Qualidade da Água (ICA) e dos parâmetros físicos, químicos e biológicos associados.\n- Comparar o cenário controlado com um cenário de inação (patamar fixo pessimista).\n- Identificar as implicações práticas do resultado projetado para o uso da água e a vida aquática.",
        "en": "- Estimate the trajectory of the Water Quality Index (WQI) and the associated physical, chemical and biological parameters.\n- Compare the controlled scenario with an inaction scenario (fixed, pessimistic baseline).\n- Identify the practical implications of the projected result for water use and aquatic life.",
        "fr": "- Estimer la trajectoire de l'Indice de Qualité de l'Eau (IQE) et des paramètres physiques, chimiques et biologiques associés.\n- Comparer le scénario contrôlé à un scénario d'inaction (niveau fixe pessimiste).\n- Identifier les implications pratiques du résultat projeté pour l'usage de l'eau et la vie aquatique.",
        "es": "- Estimar la trayectoria del Índice de Calidad del Agua (ICA) y de los parámetros físicos, químicos y biológicos asociados.\n- Comparar el escenario controlado con un escenario de inacción (nivel fijo pesimista).\n- Identificar las implicaciones prácticas del resultado proyectado para el uso del agua y la vida acuática.",
    },

    "cn.b.metodologia_intro": {
        "pt": "A simulação é conduzida pelo motor de modelagem do sistema WaterWeave-Tietê, descrito a seguir.",
        "en": "The simulation is driven by the WaterWeave-Tietê system's modeling engine, described below.",
        "fr": "La simulation est pilotée par le moteur de modélisation du système WaterWeave-Tietê, décrit ci-dessous.",
        "es": "La simulación es conducida por el motor de modelado del sistema WaterWeave-Tietê, descrito a continuación.",
    },

    "cn.b.desenvolvimento_intro": {
        "pt": "Nesta seção, apresenta-se a configuração de controle escolhida para o trecho {trecho}, seguida da trajetória simulada do Índice de Qualidade da Água (Gráfico 1) e dos parâmetros ao final do horizonte (Tabela 1).",
        "en": "This section presents the chosen control configuration for the {trecho} stretch, followed by the simulated trajectory of the Water Quality Index (Chart 1) and the parameters at the end of the horizon (Table 1).",
        "fr": "Cette section présente la configuration de contrôle choisie pour le tronçon {trecho}, suivie de la trajectoire simulée de l'Indice de Qualité de l'Eau (Graphique 1) et des paramètres à la fin de l'horizon (Tableau 1).",
        "es": "Esta sección presenta la configuración de control elegida para el tramo {trecho}, seguida de la trayectoria simulada del Índice de Calidad del Agua (Gráfico 1) y de los parámetros al final del horizonte (Tabla 1).",
    },

    "cn.b.conclusao_atingido": {
        "pt": "Os objetivos deste relatório foram atingidos: a simulação demonstrou, de forma quantitativa, o efeito das medidas de controle escolhidas frente à inação para o trecho {trecho}. Como limitação, destaca-se que os parâmetros estendidos (Índice Biótico, Metais/Tóxicos) são proxies ilustrativos, e a modelagem não propaga carga/vazão entre trechos do rio. Como próxima etapa, recomenda-se testar outras combinações de esforço de controle e horizontes temporais, e confrontar os resultados com séries reais de monitoramento à medida que estas se tornem disponíveis.",
        "en": "The objectives of this report were achieved: the simulation quantitatively demonstrated the effect of the chosen control measures against inaction for the {trecho} stretch. As a limitation, it should be noted that the extended parameters (Biotic Index, Metals/Toxics) are illustrative proxies, and the model does not propagate load/flow between river stretches. As a next step, it is recommended to test other combinations of control effort and time horizons, and to compare the results with real monitoring series as they become available.",
        "fr": "Les objectifs de ce rapport ont été atteints : la simulation a démontré, de manière quantitative, l'effet des mesures de contrôle choisies face à l'inaction pour le tronçon {trecho}. Comme limite, il convient de noter que les paramètres étendus (Indice Biotique, Métaux/Toxiques) sont des proxys illustratifs, et que la modélisation ne propage pas la charge/le débit entre les tronçons du fleuve. Comme prochaine étape, il est recommandé de tester d'autres combinaisons d'effort de contrôle et d'horizons temporels, et de confronter les résultats à des séries réelles de surveillance à mesure qu'elles deviennent disponibles.",
        "es": "Los objetivos de este informe fueron alcanzados: la simulación demostró, de forma cuantitativa, el efecto de las medidas de control elegidas frente a la inacción para el tramo {trecho}. Como limitación, se destaca que los parámetros extendidos (Índice Biótico, Metales/Tóxicos) son proxies ilustrativos, y el modelado no propaga carga/caudal entre tramos del río. Como próxima etapa, se recomienda probar otras combinaciones de esfuerzo de control y horizontes temporales, y contrastar los resultados con series reales de monitoreo a medida que estén disponibles.",
    },
    "cn.b.conclusao_nao_atingido": {
        "pt": "Os objetivos deste relatório foram parcialmente atingidos: a simulação não indicou um ganho claro de qualidade da água frente à inação para o trecho {trecho} na configuração escolhida, o que sugere a necessidade de aumentar o esforço de controle ou revisar as premissas do cenário climático. Como limitação, destaca-se que os parâmetros estendidos (Índice Biótico, Metais/Tóxicos) são proxies ilustrativos, e a modelagem não propaga carga/vazão entre trechos do rio. Como próxima etapa, recomenda-se testar configurações de maior esforço de controle e confrontar os resultados com séries reais de monitoramento à medida que estas se tornem disponíveis.",
        "en": "The objectives of this report were partially achieved: the simulation did not indicate a clear water quality gain against inaction for the {trecho} stretch under the chosen configuration, which suggests the need to increase control effort or revise the climate scenario assumptions. As a limitation, it should be noted that the extended parameters (Biotic Index, Metals/Toxics) are illustrative proxies, and the model does not propagate load/flow between river stretches. As a next step, it is recommended to test configurations with greater control effort and to compare the results with real monitoring series as they become available.",
        "fr": "Les objectifs de ce rapport ont été partiellement atteints : la simulation n'a pas indiqué de gain net de qualité de l'eau face à l'inaction pour le tronçon {trecho} dans la configuration choisie, ce qui suggère la nécessité d'augmenter l'effort de contrôle ou de revoir les hypothèses du scénario climatique. Comme limite, il convient de noter que les paramètres étendus (Indice Biotique, Métaux/Toxiques) sont des proxys illustratifs, et que la modélisation ne propage pas la charge/le débit entre les tronçons du fleuve. Comme prochaine étape, il est recommandé de tester des configurations avec un effort de contrôle plus élevé et de confronter les résultats à des séries réelles de surveillance à mesure qu'elles deviennent disponibles.",
        "es": "Los objetivos de este informe fueron parcialmente alcanzados: la simulación no indicó una ganancia clara de calidad del agua frente a la inacción para el tramo {trecho} en la configuración elegida, lo que sugiere la necesidad de aumentar el esfuerzo de control o revisar los supuestos del escenario climático. Como limitación, se destaca que los parámetros extendidos (Índice Biótico, Metales/Tóxicos) son proxies ilustrativos, y el modelado no propaga carga/caudal entre tramos del río. Como próxima etapa, se recomienda probar configuraciones con mayor esfuerzo de control y contrastar los resultados con series reales de monitoreo a medida que estén disponibles.",
    },

    "cn.b.referencias_lista": {
        "pt": "- CETESB — Companhia Ambiental do Estado de São Paulo. Qualidade das águas superficiais no Estado de São Paulo: base de dados de monitoramento, 2012-2024.\n- CONAMA — Conselho Nacional do Meio Ambiente. Resolução nº 357/2005 e nº 430/2011: classificação de corpos hídricos e padrões de lançamento de efluentes.\n- STREETER, H. W.; PHELPS, E. B. A Study of the Pollution and Natural Purification of the Ohio River. Washington: U.S. Public Health Service, 1925.\n- KAZIL, J.; MASAD, D.; CROOKS, A. Utilizing Python for Agent-Based Modeling: The Mesa Framework. In: Social, Cultural, and Behavioral Modeling (SBP-BRiMS), 2020.\n- ANA — Agência Nacional de Águas e Saneamento Básico. Sistema Nacional de Informações sobre Recursos Hídricos (SNIRH).",
        "en": "- CETESB — Companhia Ambiental do Estado de São Paulo. Qualidade das águas superficiais no Estado de São Paulo: base de dados de monitoramento, 2012-2024.\n- CONAMA — Conselho Nacional do Meio Ambiente. Resolução nº 357/2005 e nº 430/2011: classificação de corpos hídricos e padrões de lançamento de efluentes.\n- STREETER, H. W.; PHELPS, E. B. A Study of the Pollution and Natural Purification of the Ohio River. Washington: U.S. Public Health Service, 1925.\n- KAZIL, J.; MASAD, D.; CROOKS, A. Utilizing Python for Agent-Based Modeling: The Mesa Framework. In: Social, Cultural, and Behavioral Modeling (SBP-BRiMS), 2020.\n- ANA — Agência Nacional de Águas e Saneamento Básico. Sistema Nacional de Informações sobre Recursos Hídricos (SNIRH).",
        "fr": "- CETESB — Companhia Ambiental do Estado de São Paulo. Qualidade das águas superficiais no Estado de São Paulo: base de dados de monitoramento, 2012-2024.\n- CONAMA — Conselho Nacional do Meio Ambiente. Resolução nº 357/2005 e nº 430/2011: classificação de corpos hídricos e padrões de lançamento de efluentes.\n- STREETER, H. W.; PHELPS, E. B. A Study of the Pollution and Natural Purification of the Ohio River. Washington: U.S. Public Health Service, 1925.\n- KAZIL, J.; MASAD, D.; CROOKS, A. Utilizing Python for Agent-Based Modeling: The Mesa Framework. In: Social, Cultural, and Behavioral Modeling (SBP-BRiMS), 2020.\n- ANA — Agência Nacional de Águas e Saneamento Básico. Sistema Nacional de Informações sobre Recursos Hídricos (SNIRH).",
        "es": "- CETESB — Companhia Ambiental do Estado de São Paulo. Qualidade das águas superficiais no Estado de São Paulo: base de dados de monitoramento, 2012-2024.\n- CONAMA — Conselho Nacional do Meio Ambiente. Resolução nº 357/2005 e nº 430/2011: classificação de corpos hídricos e padrões de lançamento de efluentes.\n- STREETER, H. W.; PHELPS, E. B. A Study of the Pollution and Natural Purification of the Ohio River. Washington: U.S. Public Health Service, 1925.\n- KAZIL, J.; MASAD, D.; CROOKS, A. Utilizing Python for Agent-Based Modeling: The Mesa Framework. In: Social, Cultural, and Behavioral Modeling (SBP-BRiMS), 2020.\n- ANA — Agência Nacional de Águas e Saneamento Básico. Sistema Nacional de Informações sobre Recursos Hídricos (SNIRH).",
    },

    "cn.b.anexos_texto": {
        "pt": "Os dados brutos da série simulada (ano a ano, cenário controlado e não controlado, todos os parâmetros físicos, químicos e biológicos) podem ser consultados nas telas \"Séries Históricas\" e \"Comparativo de Cenários\" do painel WaterWeave-Tietê. A cena 3D interativa da própria página \"Cenários Futuros\" oferece uma visualização complementar desta mesma simulação.",
        "en": "The raw data of the simulated series (year by year, controlled and uncontrolled scenarios, all physical, chemical and biological parameters) can be consulted on the \"Historical Series\" and \"Scenario Comparison\" screens of the WaterWeave-Tietê dashboard. The interactive 3D scene on the \"Future Scenarios\" page itself offers a complementary view of this same simulation.",
        "fr": "Les données brutes de la série simulée (année par année, scénarios contrôlé et non contrôlé, tous les paramètres physiques, chimiques et biologiques) peuvent être consultées sur les écrans « Séries Historiques » et « Comparaison de Scénarios » du tableau de bord WaterWeave-Tietê. La scène 3D interactive de la page « Scénarios Futurs » elle-même offre une visualisation complémentaire de cette même simulation.",
        "es": "Los datos brutos de la serie simulada (año a año, escenarios controlado y no controlado, todos los parámetros físicos, químicos y biológicos) pueden consultarse en las pantallas \"Series Históricas\" y \"Comparativo de Escenarios\" del panel WaterWeave-Tietê. La escena 3D interactiva de la propia página \"Escenarios Futuros\" ofrece una visualización complementaria de esta misma simulación.",
    },

    # ---- pdf_generator.py — legendas/tabela ABNT do relatório de cenário ------------------
    "pdf.tabela_titulo": {"pt": "Tabela 1 – Parâmetros simulados ao final do horizonte", "en": "Table 1 – Simulated parameters at the end of the horizon", "fr": "Tableau 1 – Paramètres simulés à la fin de l'horizon", "es": "Tabla 1 – Parámetros simulados al final del horizonte"},
    "pdf.tabela_col_param": {"pt": "Parâmetro (valor final)", "en": "Parameter (final value)", "fr": "Paramètre (valeur finale)", "es": "Parámetro (valor final)"},
    "pdf.tabela_col_controlado": {"pt": "Controlado", "en": "Controlled", "fr": "Contrôlé", "es": "Controlado"},
    "pdf.tabela_col_nao_controlado": {"pt": "Não controlado", "en": "Uncontrolled", "fr": "Non contrôlé", "es": "No controlado"},
    "pdf.grafico_titulo": {"pt": "Gráfico 1 – Evolução do IQA ao longo do horizonte simulado", "en": "Chart 1 – WQI evolution over the simulated horizon", "fr": "Graphique 1 – Évolution de l'IQE sur l'horizon simulé", "es": "Gráfico 1 – Evolución del ICA a lo largo del horizonte simulado"},
    "pdf.fonte": {"pt": "Fonte: elaborado com base na simulação ABM (WaterWeave-Tietê, {ano}).", "en": "Source: prepared based on the ABM simulation (WaterWeave-Tietê, {ano}).", "fr": "Source : élaboré à partir de la simulation ABM (WaterWeave-Tietê, {ano}).", "es": "Fuente: elaborado con base en la simulación ABM (WaterWeave-Tietê, {ano})."},
    "pdf.legenda_controlado": {"pt": "Controlado", "en": "Controlled", "fr": "Contrôlé", "es": "Controlado"},
    "pdf.legenda_nao_controlado": {"pt": "Não controlado", "en": "Uncontrolled", "fr": "Non contrôlé", "es": "No controlado"},
    "pdf.parametros.iqa": {"pt": "IQA", "en": "WQI", "fr": "IQE", "es": "ICA"},
    "pdf.parametros.od": {"pt": "Oxigênio Dissolvido", "en": "Dissolved Oxygen", "fr": "Oxygène Dissous", "es": "Oxígeno Disuelto"},
    "pdf.parametros.dbo": {"pt": "DBO", "en": "BOD", "fr": "DBO", "es": "DBO"},
    "pdf.parametros.turbidez": {"pt": "Turbidez", "en": "Turbidity", "fr": "Turbidité", "es": "Turbidez"},
    "pdf.parametros.solidos": {"pt": "Sólidos Totais", "en": "Total Solids", "fr": "Solides Totaux", "es": "Sólidos Totales"},
    "pdf.parametros.temperatura": {"pt": "Temperatura", "en": "Temperature", "fr": "Température", "es": "Temperatura"},
    "pdf.parametros.ph": {"pt": "pH", "en": "pH", "fr": "pH", "es": "pH"},
    "pdf.parametros.fosforo": {"pt": "Fósforo Total", "en": "Total Phosphorus", "fr": "Phosphore Total", "es": "Fósforo Total"},
    "pdf.parametros.nitrogenio": {"pt": "Nitrogênio Total", "en": "Total Nitrogen", "fr": "Azote Total", "es": "Nitrógeno Total"},
    "pdf.parametros.metais": {"pt": "Metais/Tóxicos (índice)", "en": "Metals/Toxics (index)", "fr": "Métaux/Toxiques (indice)", "es": "Metales/Tóxicos (índice)"},
    "pdf.parametros.ecoli": {"pt": "E. coli", "en": "E. coli", "fr": "E. coli", "es": "E. coli"},
    "pdf.parametros.biotico": {"pt": "Índice Biótico", "en": "Biotic Index", "fr": "Indice Biotique", "es": "Índice Biótico"},

    # ---- Cenários Futuros — 5_Cenarios_Futuros.py -----------------------------------------
    "cf.titulo": {"pt": "Cenários Futuros do Rio Tietê", "en": "Future Scenarios for the Tietê River", "fr": "Scénarios Futurs du Fleuve Tietê", "es": "Escenarios Futuros del Río Tietê"},
    "cf.caption": {"pt": "Escolha o que priorizar e veja o rio daqui a 5 a 30 anos.", "en": "Choose what to prioritize and see the river 5 to 30 years from now.", "fr": "Choisissez vos priorités et voyez la rivière dans 5 à 30 ans.", "es": "Elija qué priorizar y vea el río dentro de 5 a 30 años."},
    "cf.trecho_rio": {"pt": "Trecho do rio", "en": "River stretch", "fr": "Tronçon du fleuve", "es": "Tramo del río"},
    "cf.horizonte": {"pt": "Daqui a quantos anos?", "en": "How many years from now?", "fr": "Dans combien d'années ?", "es": "¿Dentro de cuántos años?"},
    "cf.clima_esperado": {"pt": "Mudança climática esperada", "en": "Expected climate change", "fr": "Changement climatique attendu", "es": "Cambio climático esperado"},
    "cf.clima_help": {"pt": "Quanto menor, mais seco/quente — aplicado igualmente aos dois cenários.", "en": "The lower, the drier/hotter — applied equally to both scenarios.", "fr": "Plus la valeur est basse, plus c'est sec/chaud — appliqué également aux deux scénarios.", "es": "Cuanto menor, más seco/caliente — aplicado igualmente a ambos escenarios."},
    "cf.cenario_climatico": {"pt": "Cenário climático", "en": "Climate scenario", "fr": "Scénario climatique", "es": "Escenario climático"},
    "cf.pergunta_priorizar": {"pt": "O que você quer priorizar controlar?", "en": "What do you want to prioritize controlling?", "fr": "Que voulez-vous prioriser dans le contrôle ?", "es": "¿Qué quiere priorizar controlar?"},

    "cf.fatores_fisicos": {"pt": "Fatores Físicos", "en": "Physical Factors", "fr": "Facteurs Physiques", "es": "Factores Físicos"},
    "cf.fatores_fisicos.desc": {"pt": "Alteram a estética da água e afetam a vida aquática e a entrada de luz.", "en": "Change the water's appearance and affect aquatic life and light penetration.", "fr": "Modifient l'aspect de l'eau et affectent la vie aquatique et la pénétration de la lumière.", "es": "Alteran la estética del agua y afectan la vida acuática y la entrada de luz."},
    "cf.fatores_fisicos.itens": {
        "pt": "- **Turbidez**: partículas em suspensão (argila, lodo) que impedem a luz de penetrar.\n- **Temperatura**: influencia a solubilidade de gases (oxigênio) e o metabolismo aquático.\n- **Sólidos Totais**: minerais e matéria orgânica dissolvida na água.",
        "en": "- **Turbidity**: suspended particles (clay, silt) that block light penetration.\n- **Temperature**: influences gas solubility (oxygen) and aquatic metabolism.\n- **Total Solids**: minerals and organic matter dissolved in the water.",
        "fr": "- **Turbidité** : particules en suspension (argile, limon) qui bloquent la pénétration de la lumière.\n- **Température** : influence la solubilité des gaz (oxygène) et le métabolisme aquatique.\n- **Solides Totaux** : minéraux et matière organique dissous dans l'eau.",
        "es": "- **Turbidez**: partículas en suspensión (arcilla, lodo) que impiden la entrada de luz.\n- **Temperatura**: influye en la solubilidad de gases (oxígeno) y el metabolismo acuático.\n- **Sólidos Totales**: minerales y materia orgánica disuelta en el agua.",
    },
    "cf.controlar_sedimentos": {"pt": "Controlar sedimentos/erosão (Turbidez, Sólidos Totais)", "en": "Control sediment/erosion (Turbidity, Total Solids)", "fr": "Contrôler sédiments/érosion (Turbidité, Solides Totaux)", "es": "Controlar sedimentos/erosión (Turbidez, Sólidos Totales)"},
    "cf.esforco": {"pt": "Esforço", "en": "Effort", "fr": "Effort", "es": "Esfuerzo"},
    "cf.turbidez_solidos": {"pt": "Turbidez/Sólidos", "en": "Turbidity/Solids", "fr": "Turbidité/Solides", "es": "Turbidez/Sólidos"},
    "cf.temperatura_nota": {"pt": "Temperatura reflete só o cenário climático — não é controlável por gestão local.", "en": "Temperature only reflects the climate scenario — it is not controllable by local management.", "fr": "La température reflète uniquement le scénario climatique — elle n'est pas contrôlable par la gestion locale.", "es": "La temperatura solo refleja el escenario climático — no es controlable por gestión local."},

    "cf.fatores_quimicos": {"pt": "Fatores Químicos", "en": "Chemical Factors", "fr": "Facteurs Chimiques", "es": "Factores Químicos"},
    "cf.fatores_quimicos.desc": {"pt": "Indicam a presença de poluentes e a capacidade do rio de sustentar a vida.", "en": "Indicate the presence of pollutants and the river's capacity to sustain life.", "fr": "Indiquent la présence de polluants et la capacité du fleuve à soutenir la vie.", "es": "Indican la presencia de contaminantes y la capacidad del río de sostener la vida."},
    "cf.fatores_quimicos.itens": {
        "pt": "- **Oxigênio Dissolvido (OD)**: essencial para peixes e plantas; baixo OD indica esgoto.\n- **DBO**: oxigênio consumido para decompor matéria orgânica; alta DBO = poluição orgânica.\n- **pH**: acidez/alcalinidade da água.\n- **Nutrientes (Fósforo e Nitrogênio)**: excesso causa eutrofização (proliferação de algas).\n- **Metais Pesados e Tóxicos**: chumbo, mercúrio, agrotóxicos.",
        "en": "- **Dissolved Oxygen (DO)**: essential for fish and plants; low DO indicates sewage.\n- **BOD**: oxygen consumed to decompose organic matter; high BOD = organic pollution.\n- **pH**: water acidity/alkalinity.\n- **Nutrients (Phosphorus and Nitrogen)**: excess causes eutrophication (algae proliferation).\n- **Heavy Metals and Toxics**: lead, mercury, pesticides.",
        "fr": "- **Oxygène Dissous (OD)** : essentiel pour les poissons et les plantes ; un OD faible indique des eaux usées.\n- **DBO** : oxygène consommé pour décomposer la matière organique ; une DBO élevée = pollution organique.\n- **pH** : acidité/alcalinité de l'eau.\n- **Nutriments (Phosphore et Azote)** : l'excès cause l'eutrophisation (prolifération d'algues).\n- **Métaux Lourds et Toxiques** : plomb, mercure, pesticides.",
        "es": "- **Oxígeno Disuelto (OD)**: esencial para peces y plantas; bajo OD indica aguas residuales.\n- **DBO**: oxígeno consumido para descomponer materia orgánica; alta DBO = contaminación orgánica.\n- **pH**: acidez/alcalinidad del agua.\n- **Nutrientes (Fósforo y Nitrógeno)**: el exceso causa eutrofización (proliferación de algas).\n- **Metales Pesados y Tóxicos**: plomo, mercurio, agroquímicos.",
    },
    "cf.controlar_esgoto": {"pt": "Controlar esgoto/efluentes (OD, DBO, pH, parte dos Metais)", "en": "Control sewage/effluents (DO, BOD, pH, part of Metals)", "fr": "Contrôler eaux usées/effluents (OD, DBO, pH, une partie des Métaux)", "es": "Controlar aguas residuales/efluentes (OD, DBO, pH, parte de los Metales)"},
    "cf.esgoto_od_dbo": {"pt": "Esgoto/OD/DBO", "en": "Sewage/DO/BOD", "fr": "Eaux usées/OD/DBO", "es": "Aguas residuales/OD/DBO"},
    "cf.controlar_fertilizantes": {"pt": "Controlar fertilizantes/agrotóxicos (Nutrientes, parte dos Metais)", "en": "Control fertilizers/pesticides (Nutrients, part of Metals)", "fr": "Contrôler engrais/pesticides (Nutriments, une partie des Métaux)", "es": "Controlar fertilizantes/agroquímicos (Nutrientes, parte de los Metales)"},
    "cf.nutrientes_eutrofizacao": {"pt": "Nutrientes/Eutrofização", "en": "Nutrients/Eutrophication", "fr": "Nutriments/Eutrophisation", "es": "Nutrientes/Eutrofización"},

    "cf.fatores_biologicos": {"pt": "Fatores Biológicos", "en": "Biological Factors", "fr": "Facteurs Biologiques", "es": "Factores Biológicos"},
    "cf.fatores_biologicos.desc": {"pt": "Avaliam a saúde do ecossistema a curto e longo prazo.", "en": "Assess the ecosystem's health in the short and long term.", "fr": "Évaluent la santé de l'écosystème à court et long terme.", "es": "Evalúan la salud del ecosistema a corto y largo plazo."},
    "cf.fatores_biologicos.itens": {
        "pt": "- **E. coli** (ex-Coliformes Termotolerantes): contaminação fecal, risco à saúde pública.\n- **Macroinvertebrados e Peixes**: espécies sensíveis à poluição, indicador da saúde do rio.",
        "en": "- **E. coli** (formerly Fecal Coliforms): fecal contamination, public health risk.\n- **Macroinvertebrates and Fish**: pollution-sensitive species, an indicator of river health.",
        "fr": "- **E. coli** (anciennement Coliformes Fécaux) : contamination fécale, risque pour la santé publique.\n- **Macroinvertébrés et Poissons** : espèces sensibles à la pollution, indicateur de la santé du fleuve.",
        "es": "- **E. coli** (ex-Coliformes Termotolerantes): contaminación fecal, riesgo para la salud pública.\n- **Macroinvertebrados y Peces**: especies sensibles a la contaminación, indicador de la salud del río.",
    },
    "cf.biologicos_nota": {"pt": "Ambos são resultado do que acontece nas outras duas colunas — não têm controle próprio.", "en": "Both are a result of what happens in the other two columns — they have no control of their own.", "fr": "Les deux résultent de ce qui se passe dans les deux autres colonnes — ils n'ont pas de contrôle propre.", "es": "Ambos son resultado de lo que sucede en las otras dos columnas — no tienen control propio."},
    "cf.vazao_ecologica": {"pt": "💧 Vazão ecológica mínima reservada", "en": "💧 Minimum ecological flow reserved", "fr": "💧 Débit écologique minimal réservé", "es": "💧 Caudal ecológico mínimo reservado"},
    "cf.vazao_help": {"pt": "Fração da vazão simulada reservada para diluição — quanto maior, menos captação é permitida em seca.", "en": "Fraction of the simulated flow reserved for dilution — the higher, the less abstraction is allowed during drought.", "fr": "Fraction du débit simulé réservée à la dilution — plus elle est élevée, moins de captage est autorisé en période de sécheresse.", "es": "Fracción del caudal simulado reservada para dilución — cuanto mayor, menos captación se permite en sequía."},
    "cf.diluicao_vazao": {"pt": "Diluição/vazão", "en": "Dilution/flow", "fr": "Dilution/débit", "es": "Dilución/caudal"},

    "cf.simulando": {"pt": "Simulando o rio...", "en": "Simulating the river...", "fr": "Simulation du fleuve...", "es": "Simulando el río..."},
    "cf.baixar_pdf": {"pt": "📄 Baixar relatório em PDF desta combinação", "en": "📄 Download PDF report of this combination", "fr": "📄 Télécharger le rapport PDF de cette combinaison", "es": "📄 Descargar informe en PDF de esta combinación"},
    "cf.como_calculado": {"pt": "Como isso é calculado", "en": "How this is calculated", "fr": "Comment cela est calculé", "es": "Cómo se calcula esto"},
    "cf.como_calculado.texto": {
        "pt": "Simulação real via ABM (Mesa) + balanço hídrico + Streeter-Phelps, com submodelos estendidos de Turbidez/Sólidos/Temperatura/pH/Fósforo/Nitrogênio/E. coli/Metais/Índice Biótico, ancorados em médias reais 2012-2024 da CETESB. O cenário 'não controlado' é um patamar fixo pessimista definido nesta página. Cada trecho é simulado de forma independente, sem propagar carga/vazão de montante para jusante. IQA é um proxy simplificado de OD/DBO, não o IQA oficial de 9 parâmetros. Índice Biótico (macroinvertebrados/peixes) e o índice de Metais/Tóxicos são proxies ilustrativos combinando os demais parâmetros simulados — o projeto não tem dado real de biomonitoramento nem série completa de metais individuais ingerida no pipeline. A cena 3D (indústria, residências, plantação, chuva, assoreamento, algas, bancos de areia) é estilizada em tempo real, não fotorrealista — cada elemento responde a uma variável simulada específica, não é uma animação decorativa solta.",
        "en": "Real simulation via ABM (Mesa) + water balance + Streeter-Phelps, with extended submodels for Turbidity/Solids/Temperature/pH/Phosphorus/Nitrogen/E. coli/Metals/Biotic Index, anchored to real 2012-2024 CETESB averages. The 'uncontrolled' scenario is a fixed, pessimistic baseline defined on this page. Each stretch is simulated independently, without propagating load/flow from upstream to downstream. WQI is a simplified proxy for DO/BOD, not the official 9-parameter WQI. Biotic Index (macroinvertebrates/fish) and the Metals/Toxics index are illustrative proxies combining the other simulated parameters — the project has no real biomonitoring data nor a complete individual-metals series ingested into the pipeline. The 3D scene (industry, housing, farmland, rain, sedimentation, algae, sandbanks) is stylized in real time, not photorealistic — each element responds to a specific simulated variable, it is not a loose decorative animation.",
        "fr": "Simulation réelle via ABM (Mesa) + bilan hydrique + Streeter-Phelps, avec des sous-modèles étendus de Turbidité/Solides/Température/pH/Phosphore/Azote/E. coli/Métaux/Indice Biotique, ancrés sur des moyennes réelles CETESB 2012-2024. Le scénario « non contrôlé » est un niveau fixe pessimiste défini sur cette page. Chaque tronçon est simulé indépendamment, sans propager la charge/le débit de l'amont vers l'aval. L'IQE est un proxy simplifié de l'OD/DBO, pas l'IQE officiel à 9 paramètres. L'Indice Biotique (macroinvertébrés/poissons) et l'indice Métaux/Toxiques sont des proxys illustratifs combinant les autres paramètres simulés — le projet n'a pas de données réelles de biosurveillance ni de série complète de métaux individuels intégrée au pipeline. La scène 3D (industrie, logements, terres agricoles, pluie, envasement, algues, bancs de sable) est stylisée en temps réel, pas photoréaliste — chaque élément répond à une variable simulée spécifique, ce n'est pas une animation décorative gratuite.",
        "es": "Simulación real vía ABM (Mesa) + balance hídrico + Streeter-Phelps, con submodelos extendidos de Turbidez/Sólidos/Temperatura/pH/Fósforo/Nitrógeno/E. coli/Metales/Índice Biótico, anclados en promedios reales 2012-2024 de la CETESB. El escenario 'no controlado' es un nivel fijo pesimista definido en esta página. Cada tramo se simula de forma independiente, sin propagar carga/caudal de aguas arriba hacia aguas abajo. El ICA es un proxy simplificado de OD/DBO, no el ICA oficial de 9 parámetros. El Índice Biótico (macroinvertebrados/peces) y el índice de Metales/Tóxicos son proxies ilustrativos que combinan los demás parámetros simulados — el proyecto no tiene datos reales de biomonitoreo ni una serie completa de metales individuales incorporada al pipeline. La escena 3D (industria, viviendas, cultivos, lluvia, sedimentación, algas, bancos de arena) es estilizada en tiempo real, no fotorrealista — cada elemento responde a una variable simulada específica, no es una animación decorativa suelta.",
    },
    "cf.tende_a_ficar": {"pt": "tende a ficar", "en": "tends to become", "fr": "tend à devenir", "es": "tiende a quedar"},
    "cf.dica_cor_agua": {
        "pt": "💡 A cor da água na cena 3D muda em tempo real: veja a legenda no rodapé da animação para saber o que cada tom significa.",
        "en": "💡 The water color in the 3D scene changes in real time: see the legend at the bottom of the animation to know what each shade means.",
        "fr": "💡 La couleur de l'eau dans la scène 3D change en temps réel : consultez la légende en bas de l'animation pour savoir ce que chaque teinte signifie.",
        "es": "💡 El color del agua en la escena 3D cambia en tiempo real: vea la leyenda al pie de la animación para saber qué significa cada tono.",
    },

    # ---- Cena 3D — components/rio_3d.py (texto embutido no HTML/JS) ----------------------
    "r3d.carregando": {"pt": "Carregando cena…", "en": "Loading scene…", "fr": "Chargement de la scène…", "es": "Cargando escena…"},
    "r3d.legenda": {"pt": "🏭 Indústria &nbsp; 🏘️ Residências &nbsp; 🌾 Plantação &nbsp; 🌧️ Chuva", "en": "🏭 Industry &nbsp; 🏘️ Housing &nbsp; 🌾 Farmland &nbsp; 🌧️ Rain", "fr": "🏭 Industrie &nbsp; 🏘️ Logements &nbsp; 🌾 Terres agricoles &nbsp; 🌧️ Pluie", "es": "🏭 Industria &nbsp; 🏘️ Viviendas &nbsp; 🌾 Cultivos &nbsp; 🌧️ Lluvia"},
    "r3d.ver_sem_controle": {"pt": "ver sem controle", "en": "view without control", "fr": "voir sans contrôle", "es": "ver sin control"},
    "r3d.legenda_cor.titulo": {"pt": "Cor da água = classificação", "en": "Water color = classification", "fr": "Couleur de l'eau = classification", "es": "Color del agua = clasificación"},
    "r3d.legenda_cor.fora_risco": {"pt": "Fora de risco", "en": "Out of risk", "fr": "Hors risque", "es": "Fuera de riesgo"},
    "r3d.legenda_cor.em_risco": {"pt": "Em risco", "en": "At risk", "fr": "À risque", "es": "En riesgo"},
    "r3d.ano": {"pt": "Ano", "en": "Year", "fr": "Année", "es": "Año"},
    "r3d.cenario_controlado": {"pt": "cenário controlado", "en": "controlled scenario", "fr": "scénario contrôlé", "es": "escenario controlado"},
    "r3d.cenario_nao_controlado": {"pt": "cenário não controlado", "en": "uncontrolled scenario", "fr": "scénario non contrôlé", "es": "escenario no controlado"},
    "r3d.fase.agua_limpa": {"pt": "Água limpa", "en": "Clean water", "fr": "Eau propre", "es": "Agua limpia"},
    "r3d.fase.recuperacao": {"pt": "Recuperação concluída", "en": "Recovery complete", "fr": "Récupération terminée", "es": "Recuperación concluida"},
    "r3d.fase.tratamento": {"pt": "Tratamento em ação — recuperando", "en": "Treatment underway — recovering", "fr": "Traitement en cours — en rétablissement", "es": "Tratamiento en acción — recuperando"},
    "r3d.fase.poluicao": {"pt": "Poluição avançando", "en": "Pollution advancing", "fr": "Pollution en progression", "es": "Contaminación avanzando"},
    "r3d.fase.critico": {"pt": "Estado crítico estável", "en": "Stable critical state", "fr": "État critique stable", "es": "Estado crítico estable"},
    "r3d.metrica.iqa": {"pt": "IQA", "en": "WQI", "fr": "IQE", "es": "ICA"},
    "r3d.metrica.od": {"pt": "OD", "en": "DO", "fr": "OD", "es": "OD"},
    "r3d.metrica.dbo": {"pt": "DBO", "en": "BOD", "fr": "DBO", "es": "DBO"},
    "r3d.metrica.turbidez": {"pt": "Turbidez", "en": "Turbidity", "fr": "Turbidité", "es": "Turbidez"},
    "r3d.metrica.vazao": {"pt": "Vazão", "en": "Flow", "fr": "Débit", "es": "Caudal"},
    "r3d.metrica.ecoli": {"pt": "E. coli", "en": "E. coli", "fr": "E. coli", "es": "E. coli"},
    "r3d.metrica.biotico": {"pt": "Índice biótico", "en": "Biotic index", "fr": "Indice biotique", "es": "Índice biótico"},
    "r3d.botao_reproduzir": {"pt": "▶ Reproduzir", "en": "▶ Play", "fr": "▶ Lire", "es": "▶ Reproducir"},
    "r3d.botao_pausar": {"pt": "⏸ Pausar", "en": "⏸ Pause", "fr": "⏸ Pause", "es": "⏸ Pausar"},
    "r3d.dica_camera": {
        "pt": "🖱️ arraste para girar · roda para aproximar",
        "en": "🖱️ drag to rotate · scroll to zoom",
        "fr": "🖱️ glisser pour tourner · molette pour zoomer",
        "es": "🖱️ arrastra para girar · rueda para acercar",
    },

    # ---- Status (thresholds.py) -----------------------------------------------------------------
    "status.bom": {"pt": "Bom", "en": "Good", "fr": "Bon", "es": "Bueno"},
    "status.atencao": {"pt": "Atenção", "en": "Warning", "fr": "Attention", "es": "Atención"},
    "status.serio": {"pt": "Sério", "en": "Serious", "fr": "Sérieux", "es": "Serio"},
    "status.critico": {"pt": "Crítico", "en": "Critical", "fr": "Critique", "es": "Crítico"},
}


def idioma_atual() -> str:
    return st.session_state.get("idioma", IDIOMA_PADRAO)


def t(chave: str, **valores) -> str:
    """Traduz `chave` para o idioma corrente da sessão. Aceita placeholders `{nome}` via
    `**valores` (ex.: `t("home.panorama", ano=2025)`). Faz fallback para PT e depois para a
    própria chave se a tradução não existir — nunca lança exceção nem quebra a tela."""
    idioma = idioma_atual()
    entrada = _T.get(chave)
    if entrada is None:
        return chave
    texto = entrada.get(idioma) or entrada.get(IDIOMA_PADRAO) or chave
    if valores:
        try:
            return texto.format(**valores)
        except (KeyError, IndexError):
            return texto
    return texto


def seletor_idioma() -> str:
    """Seletor de idioma global — chamar uma vez por página (junto de
    `theme.render_sidebar_brand`). O valor escolhido persiste em toda a navegação via
    `st.session_state["idioma"]` (mesma chave usada pelo widget)."""
    opcoes = list(IDIOMAS)
    indice_atual = opcoes.index(st.session_state.get("idioma", IDIOMA_PADRAO))
    with st.sidebar:
        st.selectbox(
            "🌐 Idioma / Language",
            options=opcoes,
            format_func=lambda k: IDIOMAS[k],
            index=indice_atual,
            key="idioma",
        )
    return idioma_atual()
