# Plataforma Montecarlo para planeamiento minero (v2)

Compara escenarios de producción con incertidumbre en el **precio** y la **certeza geológica** y calcula
**qué escenario tiene más probabilidad de cumplir el plan**.

## Regla de la v2
- El determinístico (plan) **no considera** la certeza geológica.
- En cada iteración la certeza de cada zona se sortea (± puntos) de forma independiente y **baja la ley**:
  `ley efectiva = ley × [1 − P0 × (1 − certeza)]`, con P0 = 66,7 % (certeza 50 % → ley 6 → 4).
- Éxito = probabilidad de que la utilidad alcance al menos X % del plan (X se elige en la barra lateral).

## Pestañas
1 Escenarios · 2 Incertidumbre (con teoría de distribuciones y gráfico certeza → ley) · 3 Resultados por escenario ·
4 Comparación lado a lado · 5 Teoría (Montecarlo, distribuciones, certeza → ley, cómo decidir, glosario) · 6 Informe PDF con firma y exportación.

## Ejecutar
```
pip install -r requirements.txt
streamlit run app.py
pytest tests
```
