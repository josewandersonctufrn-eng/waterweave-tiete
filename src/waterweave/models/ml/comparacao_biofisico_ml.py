"""Acopla (compara/valida cruzadamente) a previsão estatística de ML (`models.ml.predict_iqa`)
com a simulação determinística do biofísico/ABM (`models.abm.scenarios`) — item 6 do roadmap de
pesquisa WaterWeave-Water4All ("integrar modelos biofísicos determinísticos e modelos baseados
em dados... para representar o funcionamento dos ecossistemas").

ACHADO DE PESQUISA (2026-07): até esta correção, os dois "braços" de modelagem do projeto nunca
se falavam — rodavam de forma completamente independente (ver docstring de `models.hybrid_bridge`:
"Ambos consomem a mesma Gold, mas não se chamam um ao outro"), sem nenhum ponto de checagem
cruzada. Isso é uma lacuna real para uma "metodologia unificada": se as duas famílias de modelo
divergem muito para o mesmo trecho/horizonte, isso é justamente o tipo de sinal que a pesquisa
quer capturar (onde o biofísico simplificado e o padrão estatístico do histórico discordam) — e
esse sinal não existia em lugar nenhum do pipeline antes desta correção.

O QUE ESTE MÓDULO FAZ (e o que não faz): compara as DUAS trajetórias passo a passo (1 a
`horizonte_anos` anos à frente), não tenta reconciliar/fazer ensemble das duas num valor único —
a divergência em si já é informação (quanto o cenário do ABM se afasta da inércia estatística do
histórico). NÃO ajusta parâmetros de um modelo a partir do outro (um acoplamento mais forte, tipo
recalibração automática do biofísico pelo ML, é uma extensão futura, não feita aqui).

RESSALVA (âncoras de tempo diferentes — comparação por PASSO, não por ano civil): a previsão de
ML é ancorada no ÚLTIMO ANO COM DADO REAL de qualidade da água do trecho (`models.ml.predict_iqa`,
ex. 2024+1, 2024+2, ...). A simulação do ABM é ancorada em HOJE
(`models.abm.model.RioTieteModel.mes_atual = pd.Timestamp.today()`, via `models.abm.scenarios`).
Como esses dois anos-âncora normalmente NÃO coincidem (qualidade da água tem defasagem real de
publicação), os dois modelos não representam o mesmo ano civil no mesmo índice — por isso a
comparação é por PASSO relativo (1º ano projetado por cada modelo, 2º ano projetado por cada
modelo, ...), com as duas datas de referência expostas nas colunas de saída (`ano_civil_ml`,
`ano_civil_biofisico`) para quem precisar auditar isso, em vez de escondido atrás de um merge por
ano civil que pareceria "alinhado" sem estar.
"""
from __future__ import annotations

import pandas as pd

from waterweave.models.abm.scenarios import PARAMETROS_CENARIO, rodar_cenario_customizado
from waterweave.models.ml.predict_iqa import prever_iqa

# Diferença de IQA (pontos, escala 0-100) acima da qual os dois modelos são lidos como EM
# DESACORDO — não é um teste estatístico formal (os dois modelos não compartilham a mesma fonte
# de incerteza para calcular um p-valor conjunto), é um limiar de leitura prática: abaixo disso,
# a diferença é da ordem do próprio ruído já documentado do proxy de IQA do biofísico
# (`models.hybrid_bridge.iqa_proxy`, que não é o IQA oficial NSF/CETESB).
LIMIAR_DIVERGENCIA_IQA = 15.0


def comparar_ml_vs_biofisico(trecho_id: str, horizonte_anos: int, cenario_biofisico: str = "atual") -> pd.DataFrame:
    """Roda os dois modelos para o mesmo trecho/horizonte e retorna uma linha por PASSO (1..N,
    ver RESSALVA na docstring do módulo) com o IQA de cada um, a diferença absoluta e se
    divergem (`LIMIAR_DIVERGENCIA_IQA`).

    `cenario_biofisico` (default `"atual"`) escolhe qual dos `models.abm.scenarios.PARAMETROS_CENARIO`
    roda no braço biofísico — a comparação só é uma checagem "justa" contra `"atual"` (o ML foi
    treinado no histórico observado, não sob uma política hipotética; comparar contra outro
    cenário mede outra coisa — "quanto esse cenário se afasta da inércia estatística do
    histórico", que também pode ser útil, daí o parâmetro ficar exposto em vez de fixo)."""
    previsao_ml = prever_iqa(trecho_id, horizonte_anos)[["ano", "iqa_previsto"]].sort_values("ano").reset_index(drop=True)
    previsao_ml = previsao_ml.rename(columns={"ano": "ano_civil_ml", "iqa_previsto": "iqa_ml"})
    previsao_ml["passo"] = range(1, len(previsao_ml) + 1)

    parametros = PARAMETROS_CENARIO[cenario_biofisico]
    historico_biofisico = rodar_cenario_customizado(parametros, [trecho_id], horizonte_anos * 12)
    anual_biofisico = (
        historico_biofisico.groupby("ano_relativo", as_index=False)
        .agg(iqa_biofisico=("iqa", "mean"), ano_civil_biofisico=("mes_data", lambda s: pd.Timestamp(s.iloc[-1]).year))
        .rename(columns={"ano_relativo": "passo"})
    )

    comparacao = previsao_ml.merge(anual_biofisico, on="passo", how="inner")
    comparacao["diferenca_abs_iqa"] = (comparacao["iqa_ml"] - comparacao["iqa_biofisico"]).abs()
    comparacao["divergem"] = comparacao["diferenca_abs_iqa"] > LIMIAR_DIVERGENCIA_IQA
    comparacao["cenario_biofisico"] = cenario_biofisico

    colunas_finais = [
        "passo", "ano_civil_ml", "ano_civil_biofisico", "iqa_ml", "iqa_biofisico",
        "diferenca_abs_iqa", "divergem", "cenario_biofisico",
    ]
    return comparacao[colunas_finais]
