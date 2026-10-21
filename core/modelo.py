"""
Modelo minero por zonas y simulación de Montecarlo (versión 2).

Determinístico (idéntico a tu Excel, por zona) = el PLAN, sin considerar la certeza:
    Onzas       = TMS * Ley * Recuperación / 31.1035
    Valorizado  = Precio * Onzas
    Costo total = Costo explotación * TMS
    Utilidad    = Valorizado - Costo total

Totales (ponderados por TMS de ESE escenario):
    TMS, Onzas, Valorizado, Costo, Utilidad = sumas (Utilidad = Valorizado - Costo)
    Ley, Recuperación, Precio, Certeza       = SUMPRODUCT(TMS, x) / TMS total

Estocástico: en cada iteración varían
    1. el PRECIO (un factor multiplicativo común a todo el mercado), y
    2. la CERTEZA GEOLÓGICA de cada zona (independiente por zona; ± puntos alrededor de la tabla).
La certeza BAJA la ley (regla lineal del ingeniero):
    pérdida de ley = P0 * (1 - certeza)          con P0 = pérdida con 0 % de certeza (2/3 por defecto)
    ley efectiva   = ley_tabla * (1 - pérdida)
    Ej.: ley 6 con certeza 50 % -> pérdida 33.3 % -> ley efectiva 4.0 ; con 100 % -> 6.0 (sin pérdida).
Así la utilidad simulada queda, en promedio, por debajo del plan, y se mide
qué escenario tiene más probabilidad de alcanzar al menos X % de lo planificado.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats

G_POR_OZ = 31.1035

COL_ZONA = "Zona"
COL_TMS = "TMS"
COL_LEY = "Ley (g/t)"
COL_REC = "Recuperación (%)"
COL_PRECIO = "Precio (US$/oz)"
COL_COSTO = "Costo explotación (US$/t)"
COL_CERTEZA = "Certeza geológica (%)"
COLUMNAS_ENTRADA = [COL_ZONA, COL_TMS, COL_LEY, COL_REC, COL_PRECIO, COL_COSTO, COL_CERTEZA]

DIST_PRECIO = ["Triangular", "PERT", "Uniforme", "Normal", "Lognormal"]
DIST_CERTEZA = ["Triangular", "PERT", "Uniforme", "Normal"]
PERDIDA_CERO_DEFECTO = 200.0 / 3.0   # % de ley que se pierde con 0 % de certeza (50 % -> -33.3 %)


# --------------------------------------------------------------------------
# Supuestos
# --------------------------------------------------------------------------
@dataclass
class Supuestos:
    n_iter: int = 10000
    semilla: int = 42
    # Precio: variación relativa respecto al precio de la tabla (en %)
    precio_dist: str = "Triangular"
    precio_min_pct: float = -20.0   # Triangular / Uniforme
    precio_moda_pct: float = 0.0    # Triangular
    precio_max_pct: float = 20.0    # Triangular / Uniforme
    precio_sd_pct: float = 10.0     # Normal / Lognormal (desv. estándar o CV en %)
    # Certeza geológica: se mueve ± delta (puntos porcentuales) alrededor del valor de la tabla
    certeza_dist: str = "Triangular"
    certeza_delta_pp: float = 10.0
    # Cuánto baja la ley por falta de certeza: pérdida (%) = perdida_cero_pct * (1 - certeza)
    perdida_cero_pct: float = PERDIDA_CERO_DEFECTO
    # Correlación entre la certeza de distintas zonas (0 = independientes)
    rho_zonas: float = 0.0
    # Misma zona = mismo sorteo en todos los escenarios (comparación justa)
    compartir_geologia: bool = True

    def a_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Validación y determinístico
# --------------------------------------------------------------------------
def limpiar_tabla(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza la tabla editada: tipos numéricos y sin filas vacías."""
    d = df.copy()
    for c in COLUMNAS_ENTRADA:
        if c not in d.columns:
            d[c] = np.nan
    d = d[COLUMNAS_ENTRADA]
    d[COL_ZONA] = d[COL_ZONA].astype("string").str.strip()
    for c in COLUMNAS_ENTRADA[1:]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(how="all")
    d = d[d[COL_ZONA].notna() & (d[COL_ZONA] != "")]
    return d.reset_index(drop=True)


def validar_tabla(df: pd.DataFrame, nombre: str) -> list[str]:
    errores: list[str] = []
    if df.empty:
        return [f"{nombre}: agrega al menos una zona."]
    if df[COL_ZONA].duplicated().any():
        errores.append(f"{nombre}: hay zonas con el mismo nombre.")
    if df[COLUMNAS_ENTRADA[1:]].isna().any().any():
        errores.append(f"{nombre}: hay celdas vacías o no numéricas.")
    if (df[COL_TMS] < 0).any() or (df[COL_LEY] < 0).any() or (df[COL_COSTO] < 0).any() or (df[COL_PRECIO] < 0).any():
        errores.append(f"{nombre}: TMS, ley, costo y precio no pueden ser negativos.")
    if ((df[COL_REC] < 0) | (df[COL_REC] > 100)).any():
        errores.append(f"{nombre}: la recuperación debe estar entre 0 y 100 %.")
    if ((df[COL_CERTEZA] < 0) | (df[COL_CERTEZA] > 100)).any():
        errores.append(f"{nombre}: la certeza geológica debe estar entre 0 y 100 %.")
    if not errores and df[COL_TMS].sum() <= 0:
        errores.append(f"{nombre}: el tonelaje total debe ser mayor que cero.")
    return errores


def tabla_determinista(df: pd.DataFrame) -> pd.DataFrame:
    """Cálculo por zona, igual que las filas del Excel (zonas en filas)."""
    d = limpiar_tabla(df)
    tms, ley = d[COL_TMS], d[COL_LEY]
    rec, precio = d[COL_REC] / 100.0, d[COL_PRECIO]
    onzas = tms * ley * rec / G_POR_OZ
    valorizado = onzas * precio
    costo_total = d[COL_COSTO] * tms
    return pd.DataFrame(
        {
            "Zona": d[COL_ZONA],
            "TMS": tms,
            "Ley (g/t)": ley,
            "Recuperación (%)": d[COL_REC],
            "Onzas (oz)": onzas,
            "Precio (US$/oz)": precio,
            "Valorizado (US$)": valorizado,
            "Costo explotación (US$/t)": d[COL_COSTO],
            "Costo total (US$)": costo_total,
            "Utilidad (US$)": valorizado - costo_total,
            "Certeza geológica (%)": d[COL_CERTEZA],
        }
    )


def totales_deterministas(df: pd.DataFrame) -> dict:
    """Columna 'Total' del Excel, ponderada por las TMS del propio escenario."""
    t = tabla_determinista(df)
    tms_total = float(t["TMS"].sum())

    def pond(col: str) -> float:
        return float((t["TMS"] * t[col]).sum() / tms_total) if tms_total else 0.0

    valorizado = float(t["Valorizado (US$)"].sum())
    costo = float(t["Costo total (US$)"].sum())
    return {
        "TMS": tms_total,
        "Ley (g/t)": pond("Ley (g/t)"),
        "Recuperación (%)": pond("Recuperación (%)"),
        "Onzas (oz)": float(t["Onzas (oz)"].sum()),
        "Precio (US$/oz)": pond("Precio (US$/oz)"),
        "Valorizado (US$)": valorizado,
        "Costo total (US$)": costo,
        "Utilidad (US$)": valorizado - costo,
        "Certeza geológica (%)": pond("Certeza geológica (%)"),
    }


# --------------------------------------------------------------------------
# Muestreo
# --------------------------------------------------------------------------
def _uniformes_lhs(n: int, rng: np.random.Generator) -> np.ndarray:
    """Latin Hypercube 1-D: una muestra por cada estrato de probabilidad."""
    u = (rng.permutation(n) + rng.random(n)) / n
    return np.clip(u, 1e-9, 1 - 1e-9)


def _ppf_triangular(u, lo, moda, hi):
    if hi <= lo:
        return np.full_like(u, lo, dtype=float)
    moda = min(max(moda, lo), hi)
    return stats.triang.ppf(u, c=(moda - lo) / (hi - lo), loc=lo, scale=hi - lo)


def _ppf_pert(u, lo, moda, hi):
    """Beta-PERT: como la triangular pero más concentrada en el valor más probable."""
    if hi <= lo:
        return np.full_like(u, lo, dtype=float)
    moda = min(max(moda, lo), hi)
    a = 1 + 4 * (moda - lo) / (hi - lo)
    b = 1 + 4 * (hi - moda) / (hi - lo)
    return stats.beta.ppf(u, a, b, loc=lo, scale=hi - lo)


def factor_precio(u: np.ndarray, s: Supuestos) -> np.ndarray:
    """Factor multiplicativo del precio (media ≈ 1) a partir de uniformes u."""
    d = s.precio_dist
    if d == "Triangular":
        lo, mo, hi = 1 + s.precio_min_pct / 100, 1 + s.precio_moda_pct / 100, 1 + s.precio_max_pct / 100
        f = _ppf_triangular(u, lo, mo, hi)
    elif d == "PERT":
        lo, mo, hi = 1 + s.precio_min_pct / 100, 1 + s.precio_moda_pct / 100, 1 + s.precio_max_pct / 100
        f = _ppf_pert(u, lo, mo, hi)
    elif d == "Uniforme":
        lo, hi = 1 + s.precio_min_pct / 100, 1 + s.precio_max_pct / 100
        f = lo + (hi - lo) * u
    elif d == "Normal":
        sd = max(s.precio_sd_pct / 100, 1e-9)
        a = (0.05 - 1.0) / sd  # trunca en 5 % del precio base para evitar precios negativos
        f = stats.truncnorm.ppf(u, a, np.inf, loc=1.0, scale=sd)
    elif d == "Lognormal":
        cv = max(s.precio_sd_pct / 100, 1e-9)
        sigma2 = np.log1p(cv**2)
        f = np.exp(-sigma2 / 2 + np.sqrt(sigma2) * stats.norm.ppf(u))
    else:
        raise ValueError(f"Distribución de precio desconocida: {d}")
    return np.asarray(f, dtype=float)


def certeza_simulada(u: np.ndarray, base: float, s: Supuestos) -> np.ndarray:
    """Certeza (0-1) en cada iteración, alrededor de `base` (0-1)."""
    delta = s.certeza_delta_pp / 100.0
    if delta <= 0:
        return np.full_like(u, base, dtype=float)
    lo, hi = max(0.0, base - delta), min(1.0, base + delta)
    if s.certeza_dist == "Triangular":
        c = _ppf_triangular(u, lo, base, hi)
    elif s.certeza_dist == "PERT":
        c = _ppf_pert(u, lo, base, hi)
    elif s.certeza_dist == "Uniforme":
        c = lo + (hi - lo) * u
    elif s.certeza_dist == "Normal":
        a, b = (0.0 - base) / delta, (1.0 - base) / delta
        c = stats.truncnorm.ppf(u, a, b, loc=base, scale=delta)
    else:
        raise ValueError(f"Distribución de certeza desconocida: {s.certeza_dist}")
    return np.clip(np.asarray(c, dtype=float), 0.0, 1.0)


def factor_ley(certeza, perdida_cero_pct: float):
    """Fracción de la ley que se conserva: 1 - P0 * (1 - certeza). Certeza en 0-1."""
    return 1.0 - (perdida_cero_pct / 100.0) * (1.0 - np.asarray(certeza, dtype=float))


# --------------------------------------------------------------------------
# Simulación
# --------------------------------------------------------------------------
def simular(escenarios: dict[str, pd.DataFrame], s: Supuestos) -> dict[str, pd.DataFrame]:
    """
    Corre Montecarlo para todos los escenarios con los MISMOS números aleatorios
    (precio común; y, si `compartir_geologia`, misma zona = mismo sorteo).
    Devuelve un DataFrame por escenario con una fila por iteración.
    """
    n = int(s.n_iter)
    rng = np.random.default_rng(int(s.semilla))
    tablas = {nom: limpiar_tabla(df) for nom, df in escenarios.items()}

    u_precio = _uniformes_lhs(n, rng)
    f_precio = factor_precio(u_precio, s)
    z_global = rng.standard_normal(n)
    rho = float(np.clip(s.rho_zonas, 0.0, 0.99))

    sorteos: dict[tuple, np.ndarray] = {}

    def sorteo(clave: tuple) -> np.ndarray:
        """Uniformes (0-1) de la certeza de una zona; con ρ > 0 las zonas se correlacionan (cópula gaussiana)."""
        if clave not in sorteos:
            if rho > 0:
                z = np.sqrt(rho) * z_global + np.sqrt(1.0 - rho) * rng.standard_normal(n)
                sorteos[clave] = np.clip(stats.norm.cdf(z), 1e-9, 1 - 1e-9)
            else:
                sorteos[clave] = _uniformes_lhs(n, rng)
        return sorteos[clave]

    resultados: dict[str, pd.DataFrame] = {}
    for nom, t in tablas.items():
        util = np.zeros(n)
        onzas = np.zeros(n)
        cols: dict[str, np.ndarray] = {"Factor precio": f_precio}
        for _, fila in t.iterrows():
            zona = str(fila[COL_ZONA])
            clave = (zona,) if s.compartir_geologia else (nom, zona)
            cert = certeza_simulada(sorteo(clave), float(fila[COL_CERTEZA]) / 100.0, s)
            f_ley = factor_ley(cert, s.perdida_cero_pct)
            oz = fila[COL_TMS] * (fila[COL_LEY] * f_ley) * (fila[COL_REC] / 100.0) / G_POR_OZ
            valor = oz * fila[COL_PRECIO] * f_precio
            util_z = valor - fila[COL_COSTO] * fila[COL_TMS]
            onzas += oz
            util += util_z
            cols[f"Certeza {zona}"] = cert * 100.0
            cols[f"Factor ley {zona}"] = f_ley
            cols[f"Ley efectiva {zona}"] = fila[COL_LEY] * f_ley
            cols[f"Utilidad {zona}"] = util_z
        df = pd.DataFrame({"Utilidad (US$)": util, "Onzas (oz)": onzas, **cols})
        # Certeza geológica del escenario (ponderada por TMS), como la fila del Excel
        pesos = t[COL_TMS].to_numpy() / t[COL_TMS].sum()
        df["Certeza escenario (%)"] = sum(
            p * df[f"Certeza {z}"] for p, z in zip(pesos, t[COL_ZONA].astype(str))
        )
        resultados[nom] = df
    return resultados
