"""Agentes do modelo baseado em agentes (Mesa) do WaterWeave-Tietê.

Um agente de cada classe por trecho (3 trechos x 5 papéis = 15 agentes).
Cada agente decide uma ação por passo de simulação (mensal) com base no
estado ecológico do trecho no passo ANTERIOR (`model.ultimo_passo_por_trecho`,
produzido por `models.hybrid_bridge.executar_passo`) — os agentes nunca veem
o estado do mês corrente antes de decidir, para não haver causalidade
invertida dentro do mesmo passo.
"""
from __future__ import annotations

import mesa

from waterweave.thresholds import status_para_iqa, status_para_od


class TrechoAgentBase(mesa.Agent):
    """Base comum: todo agente atua sobre um único trecho e lê/escreve os
    parâmetros de decisão compartilhados daquele trecho no modelo."""

    def __init__(self, model: mesa.Model, trecho_id: str):
        super().__init__(model)
        self.trecho_id = trecho_id

    @property
    def parametros(self):
        return self.model.parametros_por_trecho[self.trecho_id]

    @property
    def ultimo_passo(self):
        return self.model.ultimo_passo_por_trecho.get(self.trecho_id)


class ComiteBaciaAgent(TrechoAgentBase):
    """Define o limite de outorga: aperta captação quando o OD está ruim, relaxa quando está bom."""

    PASSO_AJUSTE = 0.03

    def step(self) -> None:
        passo = self.ultimo_passo
        if passo is None:
            return
        status = status_para_od(passo.od_simulado_mg_l)
        parametros = self.parametros
        piso = self.model.piso_fator_outorga
        if status in ("critical", "serious"):
            parametros.fator_outorga = min(1.0, parametros.fator_outorga + self.PASSO_AJUSTE)
        elif status == "good":
            parametros.fator_outorga = max(piso, parametros.fator_outorga - self.PASSO_AJUSTE / 2)


class PoderPublicoAgent(TrechoAgentBase):
    """Fiscaliza e multa quando o estado ecológico está ruim o bastante — sinaliza a Indústria no mesmo passo.

    `fiscaliza_em_serio` permite que cenários de fiscalização mais rígida ajam
    já no status "serious", em vez de esperar o rio chegar a "critical" —
    alavanca exposta ao usuário na página de Cenários Futuros.
    """

    def __init__(self, model: mesa.Model, trecho_id: str, fiscaliza_em_serio: bool = False):
        super().__init__(model, trecho_id)
        self.fiscaliza_em_serio = fiscaliza_em_serio

    def step(self) -> None:
        passo = self.ultimo_passo
        self.model.multa_aplicada_no_passo[self.trecho_id] = False
        if passo is None:
            return
        status = status_para_od(passo.od_simulado_mg_l)
        gatilhos = ("critical", "serious") if self.fiscaliza_em_serio else ("critical",)
        if status in gatilhos:
            self.model.multas_por_trecho[self.trecho_id] = self.model.multas_por_trecho.get(self.trecho_id, 0) + 1
            self.model.multa_aplicada_no_passo[self.trecho_id] = True


class IndustriaAgent(TrechoAgentBase):
    """Cresce a carga lançada gradualmente; reduz quando multada no mesmo passo (investimento forçado em tratamento).

    Os três parâmetros abaixo eram constantes fixas; viraram configuráveis
    por trecho/cenário para a página de Cenários Futuros, onde
    `crescimento_mensal` e `teto_fator_carga` respondem ao slider de
    "investimento em saneamento/tratamento" e `reducao_por_multa` ao slider
    de "rigor da fiscalização".
    """

    def __init__(
        self,
        model: mesa.Model,
        trecho_id: str,
        crescimento_mensal: float = 1.01,
        reducao_por_multa: float = 0.85,
        teto_fator_carga: float = 2.0,
    ):
        super().__init__(model, trecho_id)
        self.crescimento_mensal = crescimento_mensal
        self.reducao_por_multa = reducao_por_multa
        self.teto_fator_carga = teto_fator_carga

    def step(self) -> None:
        parametros = self.parametros
        if self.model.multa_aplicada_no_passo.get(self.trecho_id, False):
            parametros.fator_carga_industria *= self.reducao_por_multa
        else:
            parametros.fator_carga_industria = min(
                self.teto_fator_carga, parametros.fator_carga_industria * self.crescimento_mensal
            )


class AgricultorAgent(TrechoAgentBase):
    """Reduz uso de agroquímicos (carga difusa) quando o IQA está ruim e há pressão regulatória no cenário.

    `reducao` e `piso_fator` eram constantes fixas; viraram configuráveis
    para o slider de "controle de agrotóxicos/poluição difusa" da página de
    Cenários Futuros — quanto mais rigoroso o controle, menor `reducao`
    (corta mais por passo) e menor `piso_fator` (permite reduzir mais).
    """

    def __init__(self, model: mesa.Model, trecho_id: str, reducao: float = 0.95, piso_fator: float = 0.5):
        super().__init__(model, trecho_id)
        self.reducao = reducao
        self.piso_fator = piso_fator

    def step(self) -> None:
        passo = self.ultimo_passo
        if passo is None or not self.model.restricao_ambiental:
            return
        if status_para_iqa(passo.iqa_simulado) in ("critical", "serious"):
            parametros = self.parametros
            parametros.fator_carga_difusa = max(self.piso_fator, parametros.fator_carga_difusa * self.reducao)


class ConcessionariaAgent(TrechoAgentBase):
    """Não altera o estado do rio — apenas reporta estresse hídrico quando a vazão simulada
    fica abaixo da captação mínima necessária ao abastecimento do trecho."""

    def step(self) -> None:
        passo = self.ultimo_passo
        if passo is None:
            return
        necessidade = self.model.captacao_necessaria_m3s.get(self.trecho_id, 0.0)
        self.model.estresse_hidrico_por_trecho[self.trecho_id] = passo.vazao_simulada_m3s < necessidade
