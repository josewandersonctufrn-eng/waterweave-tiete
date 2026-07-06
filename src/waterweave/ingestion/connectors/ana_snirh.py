"""Conector para a API HidroWeb/SNIRH da ANA (vazão e chuva por estação convencional).

API legada, PÚBLICA e SEM CHAVE: `https://telemetriaws1.ana.gov.br/ServiceANA.asmx`
(REST simples sobre XML/diffgram — não é a API nova baseada em OAuth). Validada
manualmente em 2026-07 contra estações reais da bacia do Tietê (ex.: código
62110000 — Aços Anhanguera, Mogi das Cruzes — devolveu vazão diária de 1963 a
2014). Endpoints usados:

  - `HidroInventario`: cadastro de estações (nome, rio, lat/long, tipo).
    O filtro por rio (`nmRio=TIET`) só encontra estações FLUVIOMÉTRICAS (postos
    de rio têm nome de rio associado); estações PLUVIOMÉTRICAS (postos de
    chuva) não têm rio associado no cadastro da ANA, então são descobertas
    por município (`nmMunicipio`) dos municípios do Tietê.
  - `HidroSerieHistorica`: uma linha por mês, já com estatística mensal
    pronta (`Media` para vazão, `Total` para chuva) — não precisamos
    reconstruir o agregado mensal a partir dos 31 valores diários.

Classificação de trecho: como o cadastro da ANA não marca UGRHI, cada
estação é atribuída a um trecho pela LONGITUDE (o Tietê corre
predominantemente de leste/nascente para oeste/foz) — mesmos limites
observados nas 32 estações reais do eixo principal em
`transform.silver_estacoes` (Alto: Salesópolis/Guarulhos ~-45.8 a -46.8;
Médio: Itu/Barra Bonita ~-47 a -49; Baixo: Ibitinga/Itapura ~-49 a -51.5).

Substitui progressivamente `bronze_daee_fluviometria`/`bronze_daee_pluviometria`
como fonte de novas leituras — devolve os dados já no schema "consolidado"
usado por esses módulos (ver `parse_consolidado` em cada um), prontos para
`io_delta.write_table(..., mode="append")` sem precisar mudar a Silver.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://telemetriaws1.ana.gov.br/ServiceANA.asmx"
_NS_DIFFGRAM = "urn:schemas-microsoft-com:xml-diffgram-v1"
_TIMEOUT_S = 60

TIPO_DADOS_COTAS = "1"
TIPO_DADOS_CHUVA = "2"
TIPO_DADOS_VAZAO = "3"

# Sentinela conhecida usada pela ANA em séries antigas sem controle de qualidade
# (observado empiricamente: aparece como 100000, um valor fisicamente absurdo).
VALOR_SENTINELA_AUSENTE = 100000

MUNICIPIOS_TIETE = [
    "SALESOPOLIS", "SALESÓPOLIS", "BIRITIBA-MIRIM", "BIRITIBA MIRIM", "MOGI DAS CRUZES",
    "SUZANO", "ITAQUAQUECETUBA", "GUARULHOS", "SAO PAULO", "OSASCO", "BARUERI", "ITU",
    "SALTO", "PIRAPORA DO BOM JESUS", "TIETE", "BARRA BONITA", "BARIRI", "IBITINGA",
    "PROMISSAO", "AVANHANDAVA", "ITAPURA",
]

_LIMITES_LONGITUDE_TRECHO = [
    ("alto_tiete", -46.8),
    ("medio_tiete", -49.0),
    ("baixo_tiete", -float("inf")),
]

# Bounding box da bacia do Tietê (Salesópolis ~ -23.5,-45.8 até a foz em
# Itapura ~ -20.6,-51.4), com folga. Necessário porque a busca por município
# na ANA faz correspondência por SUBSTRING — dois falsos positivos reais
# encontrados testando contra a API ao vivo em 2026-07: "ITAPURA" casa com
# "ITAPURANGA" (Goiás, lat -15.5) e "ITU" casa com "ITUMIRIM" (Minas
# Gerais, lon -44.87). Latitude sozinha não pegou o segundo caso — por isso
# o filtro exige latitude E longitude dentro da bacia, não só latitude.
_LATITUDE_MIN_BACIA, _LATITUDE_MAX_BACIA = -24.5, -20.0
_LONGITUDE_MIN_BACIA, _LONGITUDE_MAX_BACIA = -52.0, -45.5


def _classificar_trecho_por_longitude(latitude: float | None, longitude: float | None) -> str | None:
    if latitude is None or longitude is None or pd.isna(latitude) or pd.isna(longitude):
        return None
    if not (_LATITUDE_MIN_BACIA <= latitude <= _LATITUDE_MAX_BACIA):
        return None
    if not (_LONGITUDE_MIN_BACIA <= longitude <= _LONGITUDE_MAX_BACIA):
        return None
    for trecho_id, limite_oeste in _LIMITES_LONGITUDE_TRECHO:
        if longitude >= limite_oeste:
            return trecho_id
    return None


def _parse_dataset(conteudo: bytes) -> list[dict]:
    """Converte a resposta XML/diffgram do serviço em uma lista de dicts (uma por linha da tabela)."""
    root = ET.fromstring(conteudo)
    diffgram = root.find(f"{{{_NS_DIFFGRAM}}}diffgram")
    if diffgram is None:
        return []
    dataset = next(iter(diffgram), None)
    if dataset is None:
        return []
    return [{filho.tag.split("}")[-1]: filho.text for filho in linha} for linha in dataset]


def fetch_inventario_por_rio(nome_rio: str) -> pd.DataFrame:
    """Consulta `HidroInventario` filtrando por substring do nome do rio (encontra estações FLUVIOMÉTRICAS)."""
    params = {
        "codEstDE": "", "codEstATE": "", "tpEst": "", "nmEst": "", "nmRio": nome_rio,
        "codSubBacia": "", "codBacia": "", "nmMunicipio": "", "nmEstado": "",
        "sgResp": "", "sgOper": "", "telemetrica": "",
    }
    resp = requests.get(f"{BASE_URL}/HidroInventario", params=params, timeout=_TIMEOUT_S)
    resp.raise_for_status()
    return pd.DataFrame(_parse_dataset(resp.content))


def fetch_inventario_por_municipio(nome_municipio: str) -> pd.DataFrame:
    """Consulta `HidroInventario` filtrando por município (encontra estações PLUVIOMÉTRICAS, sem rio associado)."""
    params = {
        "codEstDE": "", "codEstATE": "", "tpEst": "", "nmEst": "", "nmRio": "",
        "codSubBacia": "", "codBacia": "", "nmMunicipio": nome_municipio, "nmEstado": "",
        "sgResp": "", "sgOper": "", "telemetrica": "",
    }
    resp = requests.get(f"{BASE_URL}/HidroInventario", params=params, timeout=_TIMEOUT_S)
    resp.raise_for_status()
    return pd.DataFrame(_parse_dataset(resp.content))


def fetch_serie_historica(
    codigo_estacao: str, tipo_dados: str, data_inicio: date | None = None, nivel_consistencia: str = "1"
) -> pd.DataFrame:
    """Consulta `HidroSerieHistorica`: uma linha por mês, com estatística mensal (`Media`/`Total`) já calculada."""
    params = {
        "codEstacao": codigo_estacao,
        "dataInicio": data_inicio.strftime("%d/%m/%Y") if data_inicio else "",
        "dataFim": "",
        "tipoDados": tipo_dados,
        "nivelConsistencia": nivel_consistencia,
    }
    resp = requests.get(f"{BASE_URL}/HidroSerieHistorica", params=params, timeout=_TIMEOUT_S)
    resp.raise_for_status()
    return pd.DataFrame(_parse_dataset(resp.content))


def _serie_para_bronze(
    serie: pd.DataFrame, metadados_estacao: dict, coluna_valor_origem: str, coluna_valor_destino: str
) -> pd.DataFrame | None:
    """Converte uma série mensal da ANA para o schema 'consolidado' já usado em Bronze."""
    if serie.empty or coluna_valor_origem not in serie.columns:
        return None
    trecho_id = _classificar_trecho_por_longitude(metadados_estacao.get("latitude"), metadados_estacao.get("longitude"))
    if trecho_id is None:
        return None

    resultado = pd.DataFrame()
    resultado["data"] = pd.to_datetime(serie["DataHora"])
    resultado[coluna_valor_destino] = pd.to_numeric(serie[coluna_valor_origem], errors="coerce")
    resultado = resultado[resultado[coluna_valor_destino].abs() < VALOR_SENTINELA_AUSENTE]
    if resultado.empty:
        return None

    resultado["ano"] = resultado["data"].dt.year
    resultado["mes"] = resultado["data"].dt.month
    resultado["codigo_posto"] = f"ANA-{metadados_estacao['codigo']} - {metadados_estacao['nome']}"
    resultado["municipio"] = metadados_estacao.get("municipio")
    resultado["latitude"] = metadados_estacao.get("latitude")
    resultado["longitude"] = metadados_estacao.get("longitude")
    resultado["trecho_id"] = trecho_id
    return resultado


def _metadados(row: pd.Series) -> dict:
    def _float(valor):
        try:
            return float(valor)
        except (TypeError, ValueError):
            return None

    return {
        "codigo": row.get("Codigo"),
        "nome": row.get("Nome"),
        "municipio": row.get("nmMunicipio"),
        "latitude": _float(row.get("Latitude")),
        "longitude": _float(row.get("Longitude")),
    }


def fetch_new_records(since: date) -> dict[str, pd.DataFrame]:
    """Busca vazão (fluviométricas) e chuva (pluviométricas) publicadas pela ANA/SNIRH desde `since`.

    Retorna `{'fluviometria': df, 'pluviometria': df}`, no mesmo schema
    "consolidado" que `bronze_daee_fluviometria`/`bronze_daee_pluviometria`
    já produzem — o chamador (ver `ingestion.monthly_job`) grava cada
    DataFrame com `io_delta.write_table(..., mode='append')` na tabela
    Bronze correspondente.
    """
    estacoes_flu = fetch_inventario_por_rio("TIET")
    estacoes_pluv_partes = [fetch_inventario_por_municipio(m) for m in MUNICIPIOS_TIETE]
    estacoes_pluv = pd.concat([e for e in estacoes_pluv_partes if not e.empty], ignore_index=True)
    if not estacoes_pluv.empty:
        estacoes_pluv = estacoes_pluv[estacoes_pluv["TipoEstacaoPluviometro"] == "1"].drop_duplicates("Codigo")

    partes_vazao: list[pd.DataFrame] = []
    if not estacoes_flu.empty:
        postos_flu = estacoes_flu[estacoes_flu["TipoEstacaoDescLiquida"] == "1"].drop_duplicates("Codigo")
        for _, estacao in postos_flu.iterrows():
            try:
                serie = fetch_serie_historica(estacao["Codigo"], TIPO_DADOS_VAZAO, data_inicio=since)
                convertida = _serie_para_bronze(serie, _metadados(estacao), "Media", "vazao_m3s")
                if convertida is not None:
                    partes_vazao.append(convertida)
            except Exception:
                logger.warning("ANA/SNIRH: falha ao buscar vazão do posto %s — pulado.", estacao["Codigo"], exc_info=True)

    partes_chuva: list[pd.DataFrame] = []
    if not estacoes_pluv.empty:
        for _, estacao in estacoes_pluv.iterrows():
            try:
                serie = fetch_serie_historica(estacao["Codigo"], TIPO_DADOS_CHUVA, data_inicio=since)
                convertida = _serie_para_bronze(serie, _metadados(estacao), "Total", "altura_mm")
                if convertida is not None:
                    partes_chuva.append(convertida)
            except Exception:
                logger.warning("ANA/SNIRH: falha ao buscar chuva do posto %s — pulado.", estacao["Codigo"], exc_info=True)

    vazao = pd.concat(partes_vazao, ignore_index=True) if partes_vazao else pd.DataFrame()
    chuva = pd.concat(partes_chuva, ignore_index=True) if partes_chuva else pd.DataFrame()
    logger.info("ANA/SNIRH: %d linhas de vazão, %d linhas de chuva.", len(vazao), len(chuva))
    return {"fluviometria": vazao, "pluviometria": chuva}
