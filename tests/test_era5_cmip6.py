"""Testes de `connectors.era5_cmip6` — cobrem só a parte que NÃO depende de rede/CDS de
verdade: montagem do request (`_area_cds`), erro claro sem token (`_cliente_cds`), e a conversão
de unidades/reshape (`_processar_reanalise`/`_processar_projecao`), com `xr.Dataset` sintéticos
em memória. NÃO testa `fetch_reanalysis`/`fetch_projection` fim-a-fim (isso exigiria um token
real da CDS e rede) — ver STATUS DE IMPLEMENTAÇÃO na docstring do módulo, mesmo escopo que
`test_mapbiomas.py`/`test_sensoriamento_historico.py` já cobrem para os conectores Earth Engine.
"""
from __future__ import annotations

import numpy as np
import pytest

xr = pytest.importorskip("xarray")
pytest.importorskip("cdsapi")  # era5_cmip6.py importa `cdsapi` no nível do módulo

from waterweave.ingestion.connectors import era5_cmip6 as ec


def test_area_cds_converte_bbox_para_formato_n_w_s_e():
    bbox = (-24.0, -52.0, -20.0, -45.5)
    assert ec._area_cds(bbox) == [-20.0, -52.0, -24.0, -45.5]


def test_cliente_sem_chave_levanta_erro_claro():
    with pytest.raises(RuntimeError, match="WATERWEAVE_CDS_API_KEY"):
        ec._cliente_cds(ec.CDS_API_URL, None)


def test_cliente_com_chave_constroi_client(monkeypatch):
    chamadas = {}

    class ClientFalso:
        def __init__(self, url=None, key=None):
            chamadas["url"] = url
            chamadas["key"] = key

    monkeypatch.setattr(ec.cdsapi, "Client", ClientFalso)
    cliente = ec._cliente_cds("url-teste", "chave-teste")
    assert isinstance(cliente, ClientFalso)
    assert chamadas == {"url": "url-teste", "key": "chave-teste"}


def _datasets_reanalise_sinteticos(offset_horas_tp: int = 6) -> list["xr.Dataset"]:
    """Reproduz a forma REAL da resposta da CDS (descoberta rodando `fetch_reanalysis` contra a
    CDS de verdade, 2026-07 — ver ACHADO na docstring do módulo): `t2m` e `tp` vêm em DOIS
    `xr.Dataset` separados, com `valid_time` em horários diferentes dentro do mesmo mês (`tp`,
    variável acumulada, tem +6h de offset em relação a `t2m`). 2 meses x grade 2x2 — valores
    escolhidos para uma média espacial fácil de conferir na mão: jan/2020 com t2m médio 295K e
    tp médio 0.002 m/dia; fev/2020 com t2m médio 290K e tp médio 0.004 m/dia."""
    tempo_t2m = np.array(["2020-01-01T00:00", "2020-02-01T00:00"], dtype="datetime64[ns]")
    tempo_tp = tempo_t2m + np.timedelta64(offset_horas_tp, "h")

    t2m = (("valid_time", "lat", "lon"), np.array([[[295.0, 296.0], [294.0, 295.0]], [[290.0, 291.0], [289.0, 290.0]]]))
    tp = (
        ("valid_time", "lat", "lon"),
        np.array([[[0.002, 0.003], [0.001, 0.002]], [[0.004, 0.005], [0.003, 0.004]]]),
    )
    ds_t2m = xr.Dataset({"t2m": t2m}, coords={"valid_time": tempo_t2m})
    ds_tp = xr.Dataset({"tp": tp}, coords={"valid_time": tempo_tp})
    return [ds_t2m, ds_tp]


def test_processar_reanalise_funde_t2m_e_tp_de_arquivos_separados_por_mes():
    """A CDS retorna t2m/tp em arquivos separados com horários diferentes (ver docstring de
    `_processar_reanalise`) — o merge precisa ser por mês-calendário, não por timestamp exato,
    ou as duas variáveis nunca coincidiriam numa mesma linha."""
    resultado = ec._processar_reanalise(_datasets_reanalise_sinteticos())

    assert list(resultado["mes_data"].dt.month) == [1, 2]
    # média espacial de jan: t2m (295+296+294+295)/4 = 295.0K -> 21.85 °C
    assert resultado["temperatura_c_media"].iloc[0] == pytest.approx(295.0 - 273.15)
    # tp médio jan = 0.002 m/dia * 31 dias * 1000 = 62.0 mm
    assert resultado["chuva_mm_total"].iloc[0] == pytest.approx(0.002 * 31 * 1000.0)
    assert (resultado["_fonte_tipo"] == "observado").all()
    assert (resultado["fonte_dado"] == "ERA5 (ECMWF) via Copernicus Climate Data Store").all()


def test_processar_reanalise_sem_offset_de_horario_tambem_funciona():
    """Caso a CDS volte a juntar t2m/tp no mesmo horário no futuro, o merge por mês continua
    funcionando (mês-calendário é um superconjunto do caso "mesmo timestamp exato")."""
    resultado = ec._processar_reanalise(_datasets_reanalise_sinteticos(offset_horas_tp=0))
    assert list(resultado["mes_data"].dt.month) == [1, 2]


def test_processar_reanalise_sem_uma_das_variaveis_levanta_erro_claro():
    tempo = np.array(["2020-01-01"], dtype="datetime64[ns]")
    so_t2m = xr.Dataset({"t2m": (("valid_time", "lat", "lon"), np.array([[[295.0]]]))}, coords={"valid_time": tempo})
    with pytest.raises(ValueError, match="tp"):
        ec._processar_reanalise([so_t2m])


def _datasets_projecao_sinteticos(com_precipitacao: bool) -> dict[str, "xr.Dataset"]:
    """Reproduz a forma REAL da resposta da CDS (descoberta rodando `fetch_projection` contra a
    CDS de verdade, 2026-07 — ver ACHADO na docstring do módulo): pedir `tas`+`pr` na MESMA
    requisição faz a CDS devolver silenciosamente só uma das duas — por isso cada variável tem
    seu próprio `xr.Dataset` (e sua própria requisição, em `fetch_projection`)."""
    tempo = np.array(["2050-06-01"], dtype="datetime64[ns]")
    tas = (("time", "lat", "lon"), np.array([[[300.0, 301.0], [299.0, 300.0]]]))
    datasets = {"tas": xr.Dataset({"tas": tas}, coords={"time": tempo})}
    if com_precipitacao:
        pr = (("time", "lat", "lon"), np.array([[[0.0001, 0.0002], [0.0001, 0.0001]]]))
        datasets["pr"] = xr.Dataset({"pr": pr}, coords={"time": tempo})
    return datasets


def test_processar_projecao_sem_precipitacao_disponivel_no_modelo():
    resultado = ec._processar_projecao(_datasets_projecao_sinteticos(com_precipitacao=False), "ssp2_4_5", "modelo-x")
    assert "chuva_mm_total" not in resultado.columns
    assert (resultado["_fonte_tipo"] == "simulado").all()
    assert (resultado["cenario_id"] == "ssp2_4_5").all()
    assert (resultado["modelo_cmip6"] == "modelo-x").all()


def test_processar_projecao_com_precipitacao_converte_kg_m2_s_para_mm_mes():
    resultado = ec._processar_projecao(_datasets_projecao_sinteticos(com_precipitacao=True), "ssp2_4_5", "modelo-x")
    media_pr = (0.0001 + 0.0002 + 0.0001 + 0.0001) / 4
    esperado_mm = media_pr * 86400 * 30  # junho tem 30 dias
    assert resultado["chuva_mm_total"].iloc[0] == pytest.approx(esperado_mm)


@pytest.mark.parametrize(
    "cenario,experimento_esperado",
    [("SSP2-4.5", "ssp2_4_5"), ("SSP1-2.6", "ssp1_2_6"), ("SSP5-8.5", "ssp5_8_5"), ("ssp2_4_5", "ssp2_4_5")],
)
def test_mapa_de_cenario_aceita_rotulo_popular_ou_id_tecnico(cenario, experimento_esperado):
    assert ec.CENARIO_PARA_EXPERIMENTO_CMIP6.get(cenario, cenario) == experimento_esperado


# ---------------------------------------------------------------------------------------------
# CMIP6 -> `fator_clima` do ABM (`fator_precipitacao_relativo`, `calibrar_fator_clima_ssp`,
# `calibrar_fatores_clima_cenarios`, `salvar_calibracao_fator_clima`) — ver ATUALIZAÇÃO na
# docstring do módulo e `tests/test_clima_real.py` para o lado que LÊ a calibração.
# ---------------------------------------------------------------------------------------------
import json
from datetime import date

import pandas as pd


def test_fator_precipitacao_relativo_calcula_razao_das_medias():
    baseline = pd.DataFrame({"chuva_mm_total": [100.0, 110.0, 90.0]})
    projecao = pd.DataFrame({"chuva_mm_total": [70.0, 80.0, 75.0]})
    fator = ec.fator_precipitacao_relativo(baseline, projecao)
    assert fator == pytest.approx((70.0 + 80.0 + 75.0) / 3 / ((100.0 + 110.0 + 90.0) / 3))


def test_fator_precipitacao_relativo_sem_chuva_levanta_erro_claro():
    baseline = pd.DataFrame({"chuva_mm_total": [100.0]})
    sem_chuva = pd.DataFrame({"temperatura_c_media": [20.0]})
    with pytest.raises(ValueError, match="chuva_mm_total"):
        ec.fator_precipitacao_relativo(baseline, sem_chuva)
    with pytest.raises(ValueError, match="chuva_mm_total"):
        ec.fator_precipitacao_relativo(sem_chuva, baseline)


def test_calibrar_fator_clima_ssp_busca_baseline_e_projecao_na_janela_certa(monkeypatch):
    chamadas = []

    def _fetch_projection_falso(cenario, bbox=None, desde=None, ate=None, modelo=None, url=None, key=None):
        chamadas.append((cenario, desde, ate))
        valor = 100.0 if cenario == "historical" else 65.0
        return pd.DataFrame({"chuva_mm_total": [valor] * 12})

    monkeypatch.setattr(ec, "fetch_projection", _fetch_projection_falso)
    fator = ec.calibrar_fator_clima_ssp("SSP5-8.5", ano_futuro_centro=2050, janela_anos=20)

    assert fator == pytest.approx(0.65)
    assert chamadas[0] == ("historical", ec.BASELINE_CMIP6_DESDE, ec.BASELINE_CMIP6_ATE)
    assert chamadas[1] == ("SSP5-8.5", date(2040, 1, 1), date(2060, 12, 31))


def test_calibrar_fatores_clima_cenarios_cobre_todo_cenario_abm_mapeado(monkeypatch):
    monkeypatch.setattr(
        ec, "fetch_projection",
        # `calibrar_fator_clima_ssp` chama `fetch_projection(experimento, bbox, ...)` com `bbox`
        # posicional — o mock precisa aceitar isso, não só `cenario` + kwargs.
        lambda cenario, *args, **kw: pd.DataFrame({"chuva_mm_total": [100.0 if cenario == "historical" else 70.0] * 12}),
    )
    fatores = ec.calibrar_fatores_clima_cenarios(ano_futuro_centro=2050)
    assert set(fatores) == set(ec.CENARIO_ABM_PARA_SSP)
    assert fatores["mudanca_climatica_extrema"] == pytest.approx(0.7)


def test_salvar_calibracao_fator_clima_grava_json_com_metadados(tmp_path):
    caminho = tmp_path / "fator_clima_cmip6.json"
    fatores = {"mudanca_climatica_extrema": 0.68}
    resultado = ec.salvar_calibracao_fator_clima(fatores, caminho=caminho)

    assert resultado == caminho
    conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    assert conteudo["fatores_clima"] == fatores
    assert conteudo["modelo_cmip6"] == ec._MODELO_CMIP6_PADRAO
    assert conteudo["baseline"]["desde"] == ec.BASELINE_CMIP6_DESDE.isoformat()
    assert "calibrado_em" in conteudo
