# WaterWeave-Tietê

Plataforma híbrida (modelo biofísico + machine learning + modelo baseado em
agentes) para gestão sustentável de recursos hídricos do Rio Tietê,
cobrindo 1940-2025 com automação mensal contínua.

**Status**: Pipeline de Ingestão (Bronze/Silver/Gold), Modelagem Híbrida
(Biofísico/ML/ABM) e Dashboard Web implementados e testados contra os
dados reais do projeto.

## Como rodar

```powershell
pip install -r requirements.txt

# 1) materializar as tabelas Delta a partir dos arquivos brutos
$env:PYTHONPATH = "src"
python -m waterweave.ingestion.monthly_job

# 2) treinar os modelos de ML (IQA/OD)
python -m waterweave.models.ml.train

# 3) abrir o dashboard
streamlit run src/waterweave/webapp/streamlit_app.py
```

## Arquitetura de dados (Medallion)

```
data/
├── bronze/   # espelho fiel das fontes brutas, + proveniência (_fonte_tipo, _source_file)
├── silver/   # schema único e limpo, granularidade por posto/trecho
└── gold/     # agregações por trecho/mês, consumidas por ML, ABM e dashboard
```

Implementado com **`deltalake`** (bindings Python do delta-rs) em vez de
PySpark — tabelas Delta reais (log de transação ACID, particionamento Hive
por `trecho_id`), sem exigir JVM/Hadoop, adequado para rodar em uma única
máquina Windows. Se o projeto crescer para processamento distribuído, o
mesmo diretório de tabelas pode ser lido por um cluster Spark real
(`pyspark` + `delta-spark`) sem migração de dado.

Fontes brutas já presentes no projeto e mapeadas em `src/waterweave/config.py`:

| Fonte | Pasta/arquivo | Tipo | Observação |
|---|---|---|---|
| Vazão (DAEE) | `ALTO\|MEDIO\|BAIXO TIETE_FLUV/` | observado | 1 arquivo por posto (cabeçalho + eventos), + arquivos "consolidado" já mensais em Médio Tietê |
| Chuva (DAEE) | `ALTO\|MEDIO\|BAIXO TIETE_PLUV/` | observado | matriz Ano x Mês por posto, + variante "consolidado" |
| **Vazão/chuva (ANA/SNIRH)** | API pública `telemetriaws1.ana.gov.br` | observado | **conector real** (`connectors/ana_snirh.py`) — sem chave; +1.762 linhas de vazão / +6.355 de chuva já incorporadas ao Bronze |
| Estações | `cod_latlong.xlsx` | observado | 699 estações estaduais; Silver filtra as 32 sobre o eixo do Tietê |
| Pontos consolidados | `base_de_dados_pontos.xlsx` | observado | base agregada (147MB) — ainda não ingerida, ver "Próximos passos" |
| Qualidade da água/solo | `Planilha_Historica_Solo_Sedimentos_Rio_Tiete_1940_2025.xlsx` | **simulado** | proxy histórico baseado em tendências CETESB/DAEE/SOS Mata Atlântica |
| Sensoriamento remoto | `Sensoriamento_Remoto_Rio_Tiete.xlsx` | **simulado** | placeholder para INPE/ESA/USGS/ANA reais |

`_fonte_tipo` (`observado`/`simulado`) é propagado de Bronze até Gold para que
o dashboard e os modelos nunca tratem dado sintético como observação de
campo.

Tabelas produzidas:

| Camada | Tabela | Granularidade |
|---|---|---|
| Bronze | `fluviometria`, `pluviometria`, `estacoes`, `qualidade_solo`, `sensoriamento` | espelho da fonte |
| Silver | `vazao_mensal`, `chuva_mensal` | posto × ano × mês |
| Silver | `estacoes` | ponto (filtrado ao eixo do Tietê) |
| Silver | `qualidade` | trecho × ano |
| Silver | `sensoriamento` | ponto × data de coleta |
| Gold | `serie_temporal_trecho_mes` | trecho × mês (vazão/chuva médias + qualidade do ano) |
| Gold | `feature_store_ml` | igual acima + lags/média móvel de IQA/OD |
| Gold | `estado_inicial_abm` | snapshot mais recente por trecho |

## Estrutura do projeto

```
src/waterweave/
├── config.py                  # paths, trechos, constantes de domínio
├── io_delta.py                 # leitura/escrita das tabelas Delta
├── thresholds.py                # limiares de status (IQA/OD), domínio puro
├── ingestion/                   # Camada Bronze — implementado
│   ├── _daee_common.py            # parser de cabeçalho compartilhado (FLUV/PLUV)
│   ├── bronze_daee_fluviometria.py
│   ├── bronze_daee_pluviometria.py
│   ├── bronze_estacoes.py
│   ├── bronze_qualidade_solo.py
│   ├── bronze_sensoriamento.py
│   ├── connectors/              # ana_snirh.py real e testado; cetesb/mapbiomas stub (ver docstrings); era5_cmip6 stub
│   └── monthly_job.py            # orquestrador real (Bronze -> conectores -> Silver -> Gold)
├── transform/                   # Camadas Silver e Gold — implementado
│   ├── silver_estacoes.py
│   ├── silver_hidrologia.py
│   ├── silver_qualidade.py
│   ├── silver_sensoriamento.py
│   └── gold_features.py
├── models/                      # Modelagem Híbrida — implementado
│   ├── biofisico/                 # balanço hídrico mensal (bucket linear) + Streeter-Phelps + uso do solo
│   ├── ml/                        # RandomForest p/ IQA e OD (feature_store_ml), previsão recursiva
│   ├── abm/                       # Mesa: ComitêBacia, Indústria, Agricultor, Concessionária, PoderPúblico
│   └── hybrid_bridge.py            # integra biofísico + Streeter-Phelps por passo, sob decisão dos agentes
├── reports/narrative_generator.py  # implementado (regras sobre `silver.qualidade`)
└── webapp/                      # Dashboard — implementado
    ├── data_loader.py              # lê Silver/Gold (não mais os .xlsx brutos)
    ├── theme.py                    # paleta e chrome de gráfico (skill dataviz)
    ├── streamlit_app.py            # home + KPIs por trecho
    └── pages/                      # Mapa, Séries Históricas, Cenários, Relatório Automático
orchestration/airflow_dags/tiete_monthly_pipeline.py
```

## Modelagem Híbrida — como as três peças se encaixam

- **Biofísico** (`models/biofisico/`): balanço hídrico mensal simplificado
  (bucket linear, sem calibração de campo) produz um ÍNDICE de escoamento;
  `hybrid_bridge` o converte em vazão simulada (m³/s) por um fator
  calibrado contra a média histórica REAL do trecho (`gold.serie_temporal_trecho_mes`).
  A qualidade da água usa Streeter-Phelps clássico (coeficientes de
  literatura, não calibrados no Tietê).
- **ABM** (`models/abm/`, Mesa): 5 agentes por trecho (ComitêBacia, Indústria,
  Agricultor, Concessionária, PoderPúblico) ajustam outorga/carga
  poluidora a cada mês com base no estado ecológico do mês anterior;
  `models.abm.scenarios.rodar_cenario()` roda o modelo completo e alimenta
  `pages/3_Comparativo_Cenarios.py` — não são mais multiplicadores
  ilustrativos.
- **ML** (`models/ml/`): RandomForest treinado em `gold.feature_store_ml`
  (R² ≈ 0.99 no holdout pós-2015, esperado dado o forte autocorrelação da
  série simulada) para previsão estatística rápida de IQA/OD — um caso de
  uso diferente e independente do ABM (que usa o cálculo determinístico).

Simplificações documentadas nos próprios módulos (não escondidas): IQA do
ABM é um proxy simplificado de OD/DBO, não o IQA oficial (9 parâmetros);
cada trecho é simulado de forma independente, sem propagar vazão/carga de
montante para jusante; coeficientes de Streeter-Phelps e do balanço
hídrico não são calibrados para o Tietê especificamente.

## Conector ANA/SNIRH — o que foi resolvido de verdade

`connectors/ana_snirh.py` chama a API legada `telemetriaws1.ana.gov.br/ServiceANA.asmx`
(pública, sem chave, validada em 2026-07 contra estações reais do Tietê) e
devolve vazão (`HidroSerieHistorica`, tipo 3) e chuva (tipo 2) já no schema
"consolidado" que `bronze_daee_*` usa — `monthly_job` anexa (`mode="append"`,
`schema_mode="merge"`) direto nas tabelas Bronze, sem precisar mudar Silver/Gold.

Dois bugs reais foram encontrados e corrigidos testando contra a API ao vivo
(não em teste unitário — a API da ANA faz correspondência por SUBSTRING no
filtro de município, então "ITAPURA" também casava com "ITAPURANGA", Goiás,
e "ITU" com "ITUMIRIM", Minas Gerais): a classificação de trecho agora exige
latitude E longitude dentro de um bounding box da bacia do Tietê antes de
aceitar qualquer estação, não só a lógica de longitude por trecho. Backfill
real de 2000 a 2026 já rodou: **+1.762 linhas de vazão, +6.355 de chuva**,
zero fora do bounding box (verificado).

CETESB e MapBiomas foram pesquisados (não deixados como suposição
genérica) e documentados nos próprios módulos: CETESB não tem API pública
estruturada (só portal de download); MapBiomas tem uma rota sem Earth
Engine (planilha nacional por município via Google Drive, não testada
ponta a ponta por tempo) e uma rota com Earth Engine (exige
`earthengine authenticate` do usuário, não executável em sessão não
interativa). Ambos seguem `NotImplementedError` com o caminho de
implementação documentado.

## Próximos passos

- **CETESB/MapBiomas**: ver docstrings dos respectivos módulos em
  `ingestion/connectors/` para o caminho de implementação já pesquisado.
- **`base_de_dados_pontos.xlsx`**: ainda não tem um `bronze_*` dedicado —
  inspecionar seu schema antes de decidir se substitui ou complementa
  `cod_latlong.xlsx`.
- **Encadeamento entre trechos**: o Alto deságua no Médio, que deságua no
  Baixo — hoje cada trecho é simulado isoladamente no ABM; propagar
  vazão/carga de montante para jusante é a extensão mais natural.
- **Backfill incremental da ANA**: a primeira rodada usou `since=2000-01-01`
  (decisão manual, para um backfill rápido); `monthly_job.main()` já usa a
  data da última execução bem-sucedida daqui em diante.
