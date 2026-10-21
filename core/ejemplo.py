"""Datos de ejemplo: los 3 escenarios del Excel (mismas 3 zonas; distinto tonelaje y certeza geológica por escenario)."""
import pandas as pd

from .modelo import (
    COL_CERTEZA, COL_COSTO, COL_LEY, COL_PRECIO, COL_REC, COL_TMS, COL_ZONA, COLUMNAS_ENTRADA,
)


def tabla_base(tms: list[float], certeza: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_ZONA: ["Zona 1", "Zona 2", "Zona 3"],
            COL_TMS: [float(t) for t in tms],
            COL_LEY: [7.0, 5.0, 9.0],
            COL_REC: [95.0, 90.0, 75.0],
            COL_PRECIO: [4500.0, 4500.0, 4500.0],
            COL_COSTO: [80.0, 60.0, 40.0],
            COL_CERTEZA: [float(c) for c in certeza],
        }
    )[COLUMNAS_ENTRADA]


def escenarios_ejemplo() -> dict[str, pd.DataFrame]:
    return {
        # Certeza por zona según el criterio del ingeniero: E2 tiene más recurso indicado en la Zona 1; E3 explota más de la Zona 1 (menos certera)
        "Escenario 1": tabla_base([10000, 10000, 10000], [50, 75, 90]),
        "Escenario 2": tabla_base([7000, 10000, 13000], [70, 75, 60]),
        "Escenario 3": tabla_base([15000, 3000, 12000], [40, 90, 70]),
    }


def tabla_vacia() -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_ZONA: ["Zona 1"],
            COL_TMS: [10000.0],
            COL_LEY: [5.0],
            COL_REC: [90.0],
            COL_PRECIO: [4500.0],
            COL_COSTO: [60.0],
            COL_CERTEZA: [75.0],
        }
    )[COLUMNAS_ENTRADA]
