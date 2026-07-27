"""Mecanismo de CO-CRIAÇÃO com stakeholders — item 7 do roadmap de pesquisa WaterWeave-Water4All
("ferramenta... construída através da co-criação com gestores, tomadores de decisão e
representantes de comunidades locais... testar propostas de gestão... explorar cenários
alternativos... para encontrar COLETIVAMENTE caminhos mais sustentáveis").

ACHADO DE PESQUISA (2026-07): a página "Cenários Futuros" (`webapp.pages.5_Cenarios_Futuros`)
já deixava qualquer pessoa AJUSTAR os parâmetros de gestão e ver o resultado — mas cada sessão
começava do zero e terminava sem deixar rastro: não havia como um stakeholder nomear/registrar
sua proposta, revisitá-la depois, nem ver o que outros participantes já haviam proposto. Isso é
o oposto de "encontrar COLETIVAMENTE" — sem persistência e sem repositório compartilhado, cada
pessoa só explora sozinha, uma vez. Este módulo fecha essa lacuna com o mínimo necessário: salvar
uma proposta nomeada (com autor e justificativa) e listar/recarregar as já salvas.

O QUE NÃO É: não é um sistema de votação/deliberação nem de controle de acesso — qualquer pessoa
com acesso ao dashboard pode salvar e ver as propostas de qualquer outra (apropriado para um
protótipo de pesquisa em uso com um grupo de stakeholders já conhecido dos pesquisadores; um
piloto com público aberto precisaria de autenticação e moderação, não implementadas aqui).

Formato de armazenamento: um arquivo JSON por proposta em `config.PROPOSTAS_DIR`
(`data/cenarios_propostos/`, VERSIONADO — ver docstring de `config.PROPOSTAS_DIR`) — plain-text,
legível/editável fora do dashboard se necessário (ex.: um pesquisador revisando propostas
diretamente no repositório), sem exigir um banco de dados para um volume de escrita baixo
(propostas de stakeholders, não telemetria de sensor).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from waterweave.config import PROPOSTAS_DIR


@dataclass(frozen=True)
class PropostaCenario:
    id: str
    nome: str
    autor: str
    justificativa: str
    trecho_id: str
    horizonte_anos: int
    parametros: dict  # dict pronto para `models.abm.scenarios.rodar_cenario_customizado` (reproduz a simulação)
    resumo_metricas: dict = field(default_factory=dict)
    # Valores BRUTOS dos controles da UI (sliders/checkboxes de `webapp.pages.5_Cenarios_Futuros`)
    # — SEPARADOS de `parametros` porque a conversão controle-de-UI -> parâmetro-do-ABM não é
    # sempre inversível (ex.: `fiscaliza_em_serio = esforco_esgoto >= 50` perde o valor exato de
    # `esforco_esgoto` dentro de cada lado do limiar). Guardar os dois permite reproduzir tanto a
    # SIMULAÇÃO (`parametros`) quanto a TELA exatamente como o autor a deixou (`controles_ui`) ao
    # recarregar a proposta — ver `carregar_proposta`.
    controles_ui: dict = field(default_factory=dict)
    criado_em: str = ""


def _slug(texto: str) -> str:
    """Slug ascii/snake_case, mesmo padrão de `transform.gold_features._normalizar_nome_parametro`
    — usado para o nome do arquivo, não para exibição (o `nome` original fica preservado no
    corpo do JSON)."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")
    return slug or "proposta"


def salvar_proposta(
    nome: str,
    autor: str,
    justificativa: str,
    trecho_id: str,
    horizonte_anos: int,
    parametros: dict,
    resumo_metricas: dict | None = None,
    controles_ui: dict | None = None,
) -> PropostaCenario:
    """Grava uma nova proposta de cenário como JSON em `config.PROPOSTAS_DIR`. `parametros` é o
    dict completo passado a `models.abm.scenarios.rodar_cenario_customizado` (inclui
    `fator_clima`, `piso_fator_outorga` etc.) — salvo tal qual, para a proposta ser
    100% reproduzível ao ser recarregada em código (ver `carregar_proposta`). `controles_ui`
    (opcional) guarda os valores brutos dos widgets da página, para a TELA também poder ser
    restaurada exatamente — ver docstring de `PropostaCenario.controles_ui`. O nome do arquivo
    combina um slug do nome da proposta com timestamp (evita colisão entre propostas com o mesmo
    nome, mantém ordenação cronológica na listagem de diretório sem precisar ler cada arquivo)."""
    PROPOSTAS_DIR.mkdir(parents=True, exist_ok=True)
    agora = datetime.now(timezone.utc)
    identificador = f"{agora.strftime('%Y%m%dT%H%M%S')}_{_slug(nome)}"

    proposta = PropostaCenario(
        id=identificador,
        nome=nome,
        autor=autor,
        justificativa=justificativa,
        trecho_id=trecho_id,
        horizonte_anos=horizonte_anos,
        parametros=parametros,
        resumo_metricas=resumo_metricas or {},
        controles_ui=controles_ui or {},
        criado_em=agora.isoformat(),
    )
    caminho = PROPOSTAS_DIR / f"{identificador}.json"
    caminho.write_text(json.dumps(asdict(proposta), ensure_ascii=False, indent=2), encoding="utf-8")
    return proposta


def listar_propostas() -> list[PropostaCenario]:
    """Lista todas as propostas salvas, mais recente primeiro. Ignora silenciosamente arquivos
    que não sejam JSON válido no formato esperado (ex.: edição manual malformada) — loga um
    aviso, não derruba a listagem inteira por causa de um arquivo ruim."""
    if not PROPOSTAS_DIR.exists():
        return []
    propostas = []
    for caminho in sorted(PROPOSTAS_DIR.glob("*.json"), reverse=True):
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            propostas.append(PropostaCenario(**dados))
        except (json.JSONDecodeError, TypeError) as erro:
            import logging

            logging.getLogger(__name__).warning("Proposta de cenário ilegível (%s): %s", caminho.name, erro)
    return propostas


def carregar_proposta(identificador: str) -> PropostaCenario:
    """Recarrega uma proposta pelo `id` (mesmo valor retornado por `salvar_proposta`/
    `listar_propostas`). Levanta `FileNotFoundError` claro se o id não existir (ex.: proposta
    apagada manualmente entre a listagem e o clique de recarregar)."""
    caminho = PROPOSTAS_DIR / f"{identificador}.json"
    if not caminho.exists():
        raise FileNotFoundError(f"Proposta de cenário '{identificador}' não encontrada em {PROPOSTAS_DIR}.")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return PropostaCenario(**dados)
