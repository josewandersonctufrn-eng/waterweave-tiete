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


def _dataset_reanalise_sintetico() -> "xr.Dataset":
    """2 meses x grade 2x2 — valores escolhidos para uma média espacial fácil de conferir na
    mão: jan/2020 com t2m médio 295K e tp médio 0.002 m/dia; fev/2020 com t2m médio 290K e tp
    médio 0.004 m/dia."""
    tempo = np.array(["2020-01-01", "2020-02-01"], dtype="datetime64[ns]")
    t2m = (("time", "lat", "lon"), np.array([[[295.0, 296.0], [294.0, 295.0]], [[290.0, 291.0], [289.0, 290.0]]]))
    tp = (
        ("time", "lat", "lon"),
        np.array([[[0.002, 0.003], [0.001, 0.002]], [[0.004, 0.005], [0.003, 0.004]]]),
    )
    return xr.Dataset({"t2m": t2m, "tp": tp}, coords={"time": tempo})


def test_processar_reanalise_converte_unidades_e_agrega_espacialmente():
    resultado = ec._processar_reanalise(_dataset_reanalise_sintetico())

    assert list(resultado["mes_data"].dt.month) == [1, 2]
    # média espacial de jan: t2m (295+296+294+295)/4 = 295.0K -> 21.85 °C
    assert resultado["temperatura_c_media"].iloc[0] == pytest.approx(295.0 - 273.15)
    # tp médio jan = 0.002 m/dia * 31 dias * 1000 = 62.0 mm
    assert resultado["chuva_mm_total"].iloc[0] == pytest.approx(0.002 * 31 * 1000.0)
    assert (resultado["_fonte_tipo"] == "observado").all()
    assert (resultado["fonte_dado"] == "ERA5 (ECMWF) via Copernicus Climate Data Store").all()


def _dataset_projecao_sintetico(com_precipitacao: bool) -> "xr.Dataset":
    tempo = np.array(["2050-06-01"], dtype="datetime64[ns]")
    tas = (("time", "lat", "lon"), np.array([[[300.0, 301.0], [299.0, 300.0]]]))
    data_vars = {"tas": tas}
    if com_precipitacao:
        data_vars["pr"] = (("time", "lat", "lon"), np.array([[[0.0001, 0.0002], [0.0001, 0.0001]]]))
    return xr.Dataset(data_vars, coords={"time": tempo})


def test_processar_projecao_sem_precipitacao_disponivel_no_modelo():
    resultado = ec._processar_projecao(_dataset_projecao_sintetico(com_precipitacao=False), "ssp245", "modelo-x")
    assert "chuva_mm_total" not in resultado.columns
    assert (resultado["_fonte_tipo"] == "simulado").all()
    assert (resultado["cenario_id"] == "ssp245").all()
    assert (resultado["modelo_cmip6"] == "modelo-x").all()


def test_processar_projecao_com_precipitacao_converte_kg_m2_s_para_mm_mes():
    resultado = ec._processar_projecao(_dataset_projecao_sintetico(com_precipitacao=True), "ssp245", "modelo-x")
    media_pr = (0.0001 + 0.0002 + 0.0001 + 0.0001) / 4
    esperado_mm = media_pr * 86400 * 30  # junho tem 30 dias
    assert resultado["chuva_mm_total"].iloc[0] == pytest.approx(esperado_mm)


@pytest.mark.parametrize(
    "cenario,experimento_esperado",
    [("SSP2-4.5", "ssp245"), ("SSP1-2.6", "ssp126"), ("SSP5-8.5", "ssp585"), ("ssp245", "ssp245")],
)
def test_mapa_de_cenario_aceita_rotulo_popular_ou_id_tecnico(cenario, experimento_esperado):
    assert ec.CENARIO_PARA_EXPERIMENTO_CMIP6.get(cenario, cenario) == experimento_esperado
