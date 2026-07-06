"""Modelo Mesa que orquestra os agentes stakeholders sobre os trechos do Tietê.

Cada passo (`step`) representa um mês. Dentro de um passo: (1) os agentes de
cada trecho observam o estado ecológico do mês ANTERIOR e ajustam seus
parâmetros de decisão (outorga, carga industrial, carga difusa); (2)
`models.hybrid_bridge.executar_passo` roda o balanço hídrico + Streeter-Phelps
do mês corrente sob esses parâmetros já atualizados, produzindo o novo
estado que os agentes vão observar no próximo passo.

Simplificação assumida: cada trecho é simulado de forma independente, sem
propagar vazão/carga de montante para jusante (o Tietê real é um rio
contínuo — Alto deságua no Médio, que deságua no Baixo). Encadear os três
trechos é uma extensão natural, não implementada aqui.
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


def _serie_trecho(trecho_id: str) -> pd.DataFrame:
    serie = read_table(GOLD_DIR / "serie_temporal_trecho_mes")
    return serie[serie["trecho_id"] == trecho_id]


def _climatologia_mensal(trecho_id: str) -> pd.Series:
    historico = _serie_trecho(trecho_id).dropna(subset=["chuva_mm_media"])
    return historico.groupby("mes")["chuva_mm_media"].mean()


def _uso_solo_recente(trecho_id: str) -> str | None:
    historico = _serie_trecho(trecho_id).dropna(subset=["uso_solo"]).sort_values("mes_data")
    return None if historico.empty else historico["uso_solo"].iloc[-1]


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
    ):
        super().__init__(rng=seed)
        self.trechos = trechos
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
        self.captacao_necessaria_m3s = {t: 0.15 * _vazao_media_historica(t) for t in trechos}

        self.agentes_por_trecho: dict[str, dict[str, object]] = {}
        for trecho_id in trechos:
            self.agentes_por_trecho[trecho_id] = {
                "comite": ComiteBaciaAgent(self, trecho_id),
                "poder_publico": PoderPublicoAgent(self, trecho_id),
                "industria": IndustriaAgent(self, trecho_id),
                "agricultor": AgricultorAgent(self, trecho_id),
                "concessionaria": ConcessionariaAgent(self, trecho_id),
            }

    def step(self) -> None:
        self.mes_atual = self.mes_atual + pd.DateOffset(months=1)
        mes_calendario = self.mes_atual.month

        for trecho_id in self.trechos:
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
            )
            self.estado_hidrologico_por_trecho[trecho_id] = passo.estado_hidrologico
            self.ultimo_passo_por_trecho[trecho_id] = passo
            self.historico.append(passo)

    def run_horizonte(self, n_meses: int) -> None:
        """Roda o modelo por `n_meses` passos consecutivos."""
        for _ in range(n_meses):
            self.step()
