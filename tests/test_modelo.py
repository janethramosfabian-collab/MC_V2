import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
import pytest
from core import Supuestos, simular, totales_deterministas, tabla_determinista
from core.analisis import tabla_zonas, veredicto
from core.distribuciones import CATALOGO, congelar
from core.ejemplo import escenarios_ejemplo
from core.estadistica import curva_cumplimiento, prob_mejor, resumen, sensibilidad
from core.modelo import PERDIDA_CERO_DEFECTO, factor_ley

E = escenarios_ejemplo()


def test_determinista_coincide_con_excel():
    esperado = {"Escenario 1": 24097407.04, "Escenario 2": 24260810.52, "Escenario 3": 26243750.38}
    for k, v in esperado.items():
        assert totales_deterministas(E[k])["Utilidad (US$)"] == pytest.approx(v, abs=0.01)


def test_totales_ponderados_por_tms_propio():
    assert totales_deterministas(E["Escenario 2"])["Ley (g/t)"] == pytest.approx(7.2)
    assert totales_deterministas(E["Escenario 3"])["Ley (g/t)"] == pytest.approx(7.6)
    assert totales_deterministas(E["Escenario 1"])["Certeza geológica (%)"] == pytest.approx(71.667, abs=1e-3)
    assert totales_deterministas(E["Escenario 3"])["Certeza geológica (%)"] == pytest.approx(57.0)  # (15·40+3·90+12·70)/30


def test_onzas_por_zona():
    t = tabla_determinista(E["Escenario 1"])
    assert t["Onzas (oz)"].round(0).tolist() == [2138, 1447, 2170]


def test_regla_lineal_del_ingeniero():
    # ley 6 con certeza 50 % -> 4 (pierde 33.3 %); 100 % -> sin pérdida; 60 % -> pierde 26.7 %
    assert 6 * factor_ley(0.5, PERDIDA_CERO_DEFECTO) == pytest.approx(4.0)
    assert factor_ley(1.0, PERDIDA_CERO_DEFECTO) == pytest.approx(1.0)
    assert 1 - factor_ley(0.6, PERDIDA_CERO_DEFECTO) == pytest.approx(0.26667, abs=1e-4)
    # regla de tres sobre lo que falta: 33.33 * 40 / 50
    assert (1 - factor_ley(0.6, PERDIDA_CERO_DEFECTO)) == pytest.approx((1 - factor_ley(0.5, PERDIDA_CERO_DEFECTO)) * 40 / 50)


def test_la_certeza_baja_la_ley_y_la_utilidad():
    r = simular(E, Supuestos(n_iter=20000, semilla=5))
    for k, df in r.items():
        det = totales_deterministas(E[k])["Utilidad (US$)"]
        assert df["Utilidad (US$)"].mean() < det                      # el plan no considera la certeza
    # ley efectiva media de una zona ≈ ley × factor de su certeza de tabla (regla lineal, media simétrica)
    z1 = r["Escenario 1"]["Ley efectiva Zona 1"].mean()
    assert z1 == pytest.approx(7.0 * float(factor_ley(0.5, PERDIDA_CERO_DEFECTO)), rel=0.01)


def test_el_ranking_cambia_con_la_certeza():
    r = simular(E, Supuestos(n_iter=20000, semilla=5))
    det = {k: totales_deterministas(v)["Utilidad (US$)"] for k, v in E.items()}
    assert max(det, key=det.get) == "Escenario 3"                      # mejor en el plan
    p = {k: curva_cumplimiento(df["Utilidad (US$)"].to_numpy(), det[k], [75])[0] for k, df in r.items()}
    assert max(p, key=p.get) == "Escenario 1"                          # mejor con certeza
    assert p["Escenario 1"] > p["Escenario 2"] > p["Escenario 3"]


def test_reproducible_con_semilla():
    a = simular(E, Supuestos(n_iter=500, semilla=3))["Escenario 1"]["Utilidad (US$)"]
    b = simular(E, Supuestos(n_iter=500, semilla=3))["Escenario 1"]["Utilidad (US$)"]
    c = simular(E, Supuestos(n_iter=500, semilla=4))["Escenario 1"]["Utilidad (US$)"]
    assert (a == b).all() and not (a == c).all()


def test_sin_incertidumbre_y_certeza_100_da_el_plan():
    s = Supuestos(n_iter=200, precio_min_pct=0, precio_max_pct=0, precio_moda_pct=0, certeza_delta_pp=0, perdida_cero_pct=0)
    for k, df in simular(E, s).items():
        assert df["Utilidad (US$)"].std() < 1e-6
        assert df["Utilidad (US$)"].iloc[0] == pytest.approx(totales_deterministas(E[k])["Utilidad (US$)"])


def test_precio_solo_media_igual_al_plan_si_no_hay_perdida():
    s = Supuestos(n_iter=40000, semilla=1, certeza_delta_pp=0, perdida_cero_pct=0)
    for k, df in simular(E, s).items():
        det = totales_deterministas(E[k])["Utilidad (US$)"]
        assert abs(df["Utilidad (US$)"].mean() - det) < 4 * df["Utilidad (US$)"].std() / np.sqrt(len(df))


def test_certeza_independiente_por_zona_y_compartida_entre_escenarios():
    r = simular(E, Supuestos(n_iter=5000, certeza_dist="Uniforme", certeza_delta_pp=10, rho_zonas=0.0))
    a, b = r["Escenario 1"], r["Escenario 1"]
    assert abs(np.corrcoef(a["Certeza Zona 1"], a["Certeza Zona 2"])[0, 1]) < 0.05      # independientes entre zonas
    r2 = simular(E, Supuestos(n_iter=300, compartir_geologia=True, certeza_dist="Uniforme"))
    u1 = (r2["Escenario 1"]["Certeza Zona 1"] - 40) / 20                                  # mismo uniforme subyacente
    u2 = (r2["Escenario 2"]["Certeza Zona 1"] - 60) / 20
    assert np.allclose(u1, u2, atol=1e-9)
    r3 = simular(E, Supuestos(n_iter=300, compartir_geologia=False, certeza_dist="Uniforme"))
    assert not np.allclose((r3["Escenario 1"]["Certeza Zona 1"] - 40) / 20, (r3["Escenario 2"]["Certeza Zona 1"] - 60) / 20)


def test_certeza_acotada_y_distribuciones():
    for d in ["Triangular", "PERT", "Uniforme", "Normal", "Lognormal"]:
        r = simular(E, Supuestos(n_iter=4000, precio_dist=d))["Escenario 1"]
        assert r["Factor precio"].mean() == pytest.approx(1.0, abs=0.02), d
    for d in ["Triangular", "PERT", "Uniforme", "Normal"]:
        r = simular(E, Supuestos(n_iter=4000, certeza_dist=d, certeza_delta_pp=30))["Escenario 3"]
        assert r["Certeza Zona 2"].between(0, 100).all(), d      # 90 % ± 30 se recorta a 100


def test_correlacion_entre_zonas():
    r = simular(E, Supuestos(n_iter=20000, rho_zonas=0.8, certeza_dist="Uniforme"))["Escenario 1"]
    assert np.corrcoef(r["Certeza Zona 1"], r["Certeza Zona 3"])[0, 1] > 0.6


def test_prob_mejor_tornado_y_veredicto():
    r = simular(E, Supuestos(n_iter=3000))
    assert sum(prob_mejor(r).values()) == pytest.approx(1.0)
    t = sensibilidad(r["Escenario 1"])
    assert {"Factor precio", "Certeza Zona 1"} <= set(t["Variable"])
    assert not any(v.startswith("Factor ley") for v in t["Variable"])    # duplicado exacto de la certeza
    det = {k: totales_deterministas(v)["Utilidad (US$)"] for k, v in E.items()}
    tabla = resumen(r, det, "pct", 75)
    ver = veredicto(tabla, "pct", 75, {k: totales_deterministas(v)["Certeza geológica (%)"] for k, v in E.items()}, 3000)
    assert ver["recomendado"] == "Escenario 1" and ver["frases"] and ver["avisos"]
    tz = tabla_zonas(E["Escenario 3"], r["Escenario 3"])
    assert (tz["Pérdida de ley (%)"] > 0).all()


def test_catalogo_de_distribuciones():
    for nombre, info in CATALOGO.items():
        assert info["coloquial"] and info["tecnica"] and info["formulas"]
        if info["params"]:
            d = congelar(nombre, **{k: df for k, _, _, _, df, _ in info["params"]})
            assert np.isfinite(d.mean()) and d.ppf(0.05) < d.ppf(0.95)
    assert congelar("Lognormal", cv=10.0).mean() == pytest.approx(0.0, abs=1e-6)   # factor de media 1 = variación 0


def test_exportar_excel_y_pdf():
    import io, openpyxl
    from core.exportar import excel_bytes
    from core.informe_pdf import pdf_bytes
    s = Supuestos(n_iter=2000)
    r = simular(E, s)
    det = {k: totales_deterministas(v)["Utilidad (US$)"] for k, v in E.items()}
    tot = {k: totales_deterministas(v) for k, v in E.items()}
    tabla = resumen(r, det, "pct", 75)
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes(E, s, tabla, r)))
    assert {"Supuestos", "Determinístico", "Resumen estocástico", "Sim Escenario 1"} <= set(wb.sheetnames)
    assert any(isinstance(v, float) and abs(v - 24097407.04) < 0.01 for v in [c.value for c in wb["Determinístico"]["K"]])
    ver = veredicto(tabla, "pct", 75, {k: v["Certeza geológica (%)"] for k, v in tot.items()}, 2000)
    um = {k: det[k] * 0.75 for k in det}
    pdf = pdf_bytes(entradas=E, supuestos=s, res=r, tot=tot, det_u=det, tabla=tabla, modo="pct", valor=75, umbrales=um, ver=ver,
                    huella="abc123", meta={"proyecto": "Prueba", "elaborado_por": "Ana", "cargo": "Ing."})
    assert pdf[:4] == b"%PDF" and len(pdf) > 30000
