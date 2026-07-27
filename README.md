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

## Uso do solo real (MapBiomas / Google Earth Engine)

`ingestion/bronze_uso_solo.py` busca uso do solo real (MapBiomas Coleção 9,
1985-2023) via Google Earth Engine. Requer, uma única vez por máquina:

```powershell
pip install earthengine-api   # não está em requirements.txt (ver comentário lá — build do Streamlit Cloud fica enxuto)
earthengine authenticate       # fluxo OAuth interativo, abre o navegador
```

E, a cada sessão de terminal onde for rodar a ingestão:

```powershell
$env:WATERWEAVE_EE_PROJECT = "seu-project-id"   # ID de um projeto Google Cloud com a API do Earth Engine habilitada
```

Sem essa variável definida, `bronze_uso_solo.py` levanta um erro claro (não
o erro genérico do Earth Engine) — ver `config.EARTH_ENGINE_PROJECT`. O mesmo
padrão (`fetch_series_historica`, NDVI/temperatura de superfície/turbidez-proxy
histórico via Landsat) vale para `ingestion/connectors/sensoriamento_historico.py`.

## Clima real (ERA5/CMIP6 / Copernicus Climate Data Store)

`ingestion/connectors/era5_cmip6.py` busca reanálise histórica ERA5
(`fetch_reanalysis`) e projeções futuras CMIP6 por cenário SSP
(`fetch_projection`) via a Copernicus Climate Data Store. Requer, uma única
vez: criar uma conta gratuita em <https://cds.climate.copernicus.eu> e copiar
o token pessoal em <https://cds.climate.copernicus.eu/how-to-api>. A cada
sessão de terminal onde for usar este conector:

```powershell
pip install cdsapi xarray netCDF4   # não estão em requirements.txt (mesmo raciocínio do earthengine-api)
$env:WATERWEAVE_CDS_API_KEY = "seu-token-pessoal"
```

Sem essa variável definida, `era5_cmip6.py` levanta um erro claro — ver
`config.CDS_API_KEY`.

**Calibrar `fator_clima` do cenário "Mudança Climática Extrema" com CMIP6 real**: por padrão
esse cenário usa um proxy fixo (chuva -25%). Para calibrá-lo com a projeção CMIP6 real
(SSP5-8.5, comparada ao período de referência 1995-2014), com `WATERWEAVE_CDS_API_KEY`
configurado:

```powershell
python -m waterweave.ingestion.connectors.era5_cmip6
```

Isso grava `data/fator_clima_cmip6.json` (versionado no repositório) — `models.abm.scenarios`
passa a ler esse arquivo automaticamente na próxima vez que for importado (`models.abm.clima_real`,
sem precisar de rede). Sem o arquivo, cai de volta no proxy fixo — nunca quebra a aplicação por
falta de calibração.

## Serviços ecossistêmicos, acoplamento ML↔biofísico e co-criação

Itens 5-7 do roadmap de pesquisa WaterWeave-Water4All:

- **Serviços ecossistêmicos** (`models/servicos_ecossistemicos.py`): regulação da qualidade da
  água, provisão hídrica e suporte à biodiversidade, cada um em fração 0-1. Regulação e provisão
  têm série histórica REAL (`gold.servicos_ecossistemicos_trecho_ano`); suporte à biodiversidade
  só é computável no braço simulado do ABM (ver docstring do módulo para o porquê) — exibido na
  página "Cenários Futuros".
- **Acoplamento ML ↔ biofísico** (`models/ml/comparacao_biofisico_ml.py`): compara, passo a
  passo, a previsão estatística (`models.ml.predict_iqa`) com a simulação determinística do
  cenário "Atual" para o mesmo trecho — exibido no expander "Validação cruzada" da página
  "Cenários Futuros". Ver docstring do módulo para a ressalva sobre âncoras de tempo diferentes
  entre os dois modelos.
- **Co-criação** (`models/abm/scenario_store.py`): stakeholders podem salvar uma configuração de
  cenário como proposta nomeada (nome, autor, justificativa) e recarregar propostas salvas por
  outros participantes — persistido em `data/cenarios_propostos/` (JSON, versionado). Seção
  "Propostas da comunidade" na página "Cenários Futuros".

## Testes

```powershell
pip install -r requirements-dev.txt
pytest tests/ -v
```

Roda automaticamente a cada push/PR para `main` via GitHub Actions
(`.github/workflows/tests.yml`). Cobre dois tipos de regressão: o gap de
ingestão original (`test_pipeline_paridade.py` — toda fonte em
`RAW_SOURCES` precisa ter um módulo `bronze_*.py` que a leia de fato) e os
achados da auditoria de ML de 2026-07 (`test_ml_features.py`,
`test_gold_features_ml_anual.py`, `test_ml_train.py`,
`test_shap_analysis.py` — granularidade anual sem vazamento, separação
real/simulado no treino, ausência de vazamento temporal no walk-forward,
SHAP diagnóstico sem lags do próprio alvo; ver docstrings de
`transform/gold_features.py` e `models/ml/train.py` para o detalhe de cada
item).

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
| Gold | `feature_store_ml` | igual acima + lags/média móvel de IQA/OD (legado, mensal) |
| Gold | `feature_store_ml_anual` | trecho × ano + lags/média móvel de IQA/OD — fonte de treino atual do ML |
| Gold | `estado_inicial_abm` | snapshot mais recente por trecho |
| Gold | `sensoriamento_trecho_ano` | trecho × ano (NDVI/turbidez/clorofila-a/temp. superfície/TSS/nível — ver ressalva de cobertura temporal na docstring de `transform.gold_features`) |
| Gold | `servicos_ecossistemicos_trecho_ano` | trecho × ano (regulação da qualidade da água + provisão hídrica, fração 0-1 — ver `models.servicos_ecossistemicos`; suporte à biodiversidade só existe no braço simulado do ABM, não nesta tabela histórica) |

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
│   ├── connectors/              # ana_snirh.py, mapbiomas.py, sensoriamento_historico.py e era5_cmip6.py reais e testados; cetesb ainda stub (ver docstring)
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
