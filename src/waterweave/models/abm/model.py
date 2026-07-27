"""Modelo Mesa que orquestra os agentes stakeholders sobre os trechos do Tietê.

Cada passo (`step`) representa um mês. Dentro de um passo: (1) os agentes de
cada trecho observam o estado ecológico do mês ANTERIOR e ajustam seus
parâmetros de decisão (outorga, carga industrial, carga difusa); (2)
`models.hybrid_bridge.executar_passo` roda o balanço hídrico + Streeter-Phelps
do mês corrente sob esses parâmetros já atualizados, produzindo o novo
estado que os agentes vão observar no próximo passo.

ACHADO DE PESQUISA (2026-07, conectividade espacial entre trechos): `step` agora processa os
trechos em `hybrid_bridge.ordem_hidrologica` (montante -> jusante), propagando o DESVIO de
carga poluidora de cada trecho (em relação à própria carga-base histórica) para o próximo a
jusante, dentro do mesmo mês simulado — ver ACHADO DE PESQUISA "conectividade espacial" em
`models.hybrid_bridge` para o racional completo (por que só carga, não vazão; por que o
desvio, não a carga bruta; por que sem defasagem de trânsito). Vazão continua calibrada de
forma independente por trecho — RESSALVA ainda válida: o rio real é contínuo, e a vazão
acumulada de montante para jusante não é modelada explicitamente, só a carga poluidora.

ACHADO DE PESQUISA (2026-07, uso do solo REAL no ABM): `self._uso_solo` (usado a cada `step`
via `hybrid_bridge.executar_passo`) agora prioriza os percentuais reais do MapBiomas
(`_uso_solo_recente`/`hybrid_bridge.uso_solo_da_linha`) sobre a classe simulada de texto livre
que era a única fonte antes desta correção — ver ACHADO DE PESQUISA "uso do solo REAL" em
`transform.gold_features`. Continua sendo o uso do solo mais recente disponível, fixo para
toda a simulação (não muda passo a passo) — dinamizar isso ano a ano dentro de uma rodada do
ABM é uma extensão futura, não feita aqui.
"""
from __future__ import annotations

import mesa
import pandas as pd

from waterweave.config import GOLD_DIR
from waterweave.io_delta import read_table
from waterweave.models import hybrid_bridge
from waterweave.models.abm.agents import (
    AgricultorAgent,
    ComiteBaciaAgent,
    ConcessionariaAgent,
    IndustriaAgent,
    PoderPublicoAgent,
)
from waterweave.transform.gold_features import FRACAO_VAZAO_CAPTACAO_NECESSARIA


def _serie_trecho(trecho_id: str) -> pd.DataFrame:
    serie = read_table(GOLD_DIR / "serie_temporal_trecho_mes")
    return serie[serie["trecho_id"] == trecho_id]


def _climatologia_mensal(trecho_id: str) -> pd.Series:
    historico = _serie_trecho(trecho_id).dropna(subset=["chuva_mm_media"])
    return historico.groupby("mes")["chuva_mm_media"].mean()


def _uso_solo_recente(trecho_id: str) -> str | dict[str, float] | None:
    """Uso do solo mais recente do trecho — prioriza os percentuais REAIS do MapBiomas sobre a
    classe simulada de texto livre (ver `hybrid_bridge.uso_solo_da_linha`, ACHADO DE PESQUISA
    "uso do solo REAL" em `transform.gold_features`). Antes desta correção (2026-07), esta
    função só olhava a coluna `uso_solo` simulada, mesmo quando `pct_natural`/etc. reais já
    estavam disponíveis em `gold.serie_temporal_trecho_mes` para o mesmo trecho/ano."""
    colunas_uso_solo = ["uso_solo", *hybrid_bridge.COLUNAS_USO_SOLO]
    historico = _serie_trecho(trecho_id).dropna(subset=colunas_uso_solo, how="all").sort_values("mes_data")
    return None if historico.empty else hybrid_bridge.uso_solo_da_linha(historico.iloc[-1])


def _vazao_media_historica(trecho_id: str) -> float:
    historico = _serie_trecho(trecho_id)["vazao_m3s_medio"].dropna()
    return float(historico.mean()) if not historico.empty else 1.0


class RioTieteModel(mesa.Model):
    def __init__(
        self,
        trechos: list[str],
        cenario_id: str = "atual",
        fator_clima: float = 1.0,
        piso_fator_outorga: float = 0.5,
        restricao_ambiental: bool = False,
        seed: int | None = None,
        fiscaliza_em_serio: bool = False,
        crescimento_mensal_industria: float = 1.01,
        reducao_por_multa: float = 0.85,
        teto_fator_carga_industria: float = 2.0,
        reducao_agricola: float = 0.95,
        piso_fator_difusa: float = 0.5,
    ):
        super().__init__(rng=seed)
        self.trechos = trechos
        # Ordem MONTANTE -> JUSANTE (`config.TRECHOS[...].km_aproximado`) — usada em `step` para
        # propagar carga poluidora na direção certa (ver ACHADO DE PESQUISA "conectividade
        # espacial" na docstring do módulo). `_trecho_jusante[t]` é `None` para o trecho mais a
        # jusante da lista (nada recebe a carga dele dentro desta simulação).
        self._ordem_hidrologica = hybrid_bridge.ordem_hidrologica(trechos)
        self._trecho_jusante: dict[str, str | None] = {
            t: (self._ordem_hidrologica[i + 1] if i + 1 < len(self._ordem_hidrologica) else None)
            for i, t in enumerate(self._ordem_hidrologica)
        }
        self.cenario_id = cenario_id
        self.fator_clima = fator_clima
        self.piso_fator_outorga = piso_fator_outorga
        self.restricao_ambiental = restricao_ambiental

        self.mes_atual = pd.Timestamp.today().normalize().replace(day=1)
        self.parametros_por_trecho = {
            t: hybrid_bridge.ParametrosAgentes(fator_outorga=max(piso_fator_outorga, 0.90)) for t in trechos
        }
        self.estado_hidrologico_por_trecho = {t: hybrid_bridge.estado_hidrologico_inicial(t) for t in trechos}
        self.ultimo_passo_por_trecho: dict[str, hybrid_bridge.PassoHibrido] = {}
        self.historico: list[hybrid_bridge.PassoHibrido] = []

        self.multas_por_trecho: dict[str, int] = dict.fromkeys(trechos, 0)
        self.multa_aplicada_no_passo: dict[str, bool] = dict.fromkeys(trechos, False)
        self.estresse_hidrico_por_trecho: dict[str, bool] = dict.fromkeys(trechos, False)

        self._climatologia = {t: _climatologia_mensal(t) for t in trechos}
        self._uso_solo = {t: _uso_solo_recente(t) for t in trechos}
        self.captacao_necessaria_m3s = {t: FRACAO_VAZAO_CAPTACAO_NECESSARIA * _vazao_media_historica(t) for t in trechos}

        self.agentes_por_trecho: dict[str, dict[str, object]] = {}
        for trecho_id in trechos:
            self.agentes_por_trecho[trecho_id] = {
                "comite": ComiteBaciaAgent(self, trecho_id),
                "poder_publico": PoderPublicoAgent(self, trecho_id, fiscaliza_em_serio=fiscaliza_em_serio),
                "industria": IndustriaAgent(
                    self,
                    trecho_id,
                    crescimento_mensal=crescimento_mensal_industria,
                    reducao_por_multa=reducao_por_multa,
                    teto_fator_carga=teto_fator_carga_industria,
                ),
                "agricultor": AgricultorAgent(self, trecho_id, reducao=reducao_agricola, piso_fator=piso_fator_difusa),
                "concessionaria": ConcessionariaAgent(self, trecho_id),
            }

    def step(self) -> None:
        self.mes_atual = self.mes_atual + pd.DateOffset(months=1)
        mes_calendario = self.mes_atual.month

        # Desvio de carga poluidora a propagar para cada trecho, recebido do seu vizinho de
        # montante NESTE mês — populado trecho a trecho conforme a ordem hidrológica avança
        # (ver ACHADO DE PESQUISA "conectividade espacial" na docstring do módulo). Reiniciada
        # a cada `step`: a propagação é só dentro do mesmo mês, sem memória entre meses.
        carga_delta_recebida: dict[str, float] = {}

        for trecho_id in self._ordem_hidrologica:
            agentes = self.agentes_por_trecho[trecho_id]
            agentes["comite"].step()
            agentes["poder_publico"].step()
            agentes["industria"].step()
            agentes["agricultor"].step()
            agentes["concessionaria"].step()

            climatologia_trecho = self._climatologia[trecho_id]
            chuva_climatologica = (
                climatologia_trecho.get(mes_calendario, climatologia_trecho.mean())
                if not climatologia_trecho.empty
                else 100.0
            )
            chuva_mes = chuva_climatologica * self.fator_clima

            passo = hybrid_bridge.executar_passo(
                trecho_id,
                self.mes_atual,
                self.estado_hidrologico_por_trecho[trecho_id],
                self.parametros_por_trecho[trecho_id],
                chuva_mes,
                self._uso_solo[trecho_id],
                fator_clima=self.fator_clima,
                carga_delta_montante_kg_dia=carga_delta_recebida.get(trecho_id, 0.0),
            )
            self.estado_hidrologico_por_trecho[trecho_id] = passo.estado_hidrologico
            self.ultimo_passo_por_trecho[trecho_id] = passo
            self.historico.append(passo)

            trecho_jusante = self._trecho_jusante[trecho_id]
            if trecho_jusante is not None:
                desvio_carga = passo.carga_total_kg_dia - hybrid_bridge.carga_base_trecho_kg_dia(trecho_id)
                carga_delta_recebida[trecho_jusante] = hybrid_bridge.FRACAO_CARGA_PROPAGADA_MONTANTE * desvio_carga

    def run_horizonte(self, n_meses: int) -> None:
        """Roda o modelo por `n_meses` passos consecutivos."""
        for _ in range(n_meses):
            self.step()
