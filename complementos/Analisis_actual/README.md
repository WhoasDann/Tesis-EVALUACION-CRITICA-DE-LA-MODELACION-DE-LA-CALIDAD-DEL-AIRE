# Análisis incorporados al escrito vigente

Estos programas reproducen los recuentos de MP10 de la discusión y los ciclos meteorológicos de los anexos del manuscrito del 26 de noviembre. Se basan en salidas y pares archivados; no ejecutan WRF, MMIF, AERMET ni AERMOD. El paquete vecino `Reproduccion_doce` debe conservarse en la misma carpeta `complementos`.

## Ejecución desde la raíz del repositorio

```sh
python -m pip install -r complementos/Analisis_actual/requirements.txt
python complementos/Analisis_actual/amplitudes.py salida_amplitudes
python complementos/Analisis_actual/normalizacion_mp10.py salida_normalizacion
python complementos/Analisis_actual/meteorologia.py salida_meteorologia
```

Las carpetas de salida deben ser nuevas. Python 3.13.9 es el entorno utilizado. Se verifican los hashes, 704 filas diarias receptor-temporada, las medias normalizadas y los recuentos publicados. El segundo programa conserva los pares y máscaras archivados, calcula métricas con BIAS observado menos WRF y genera los ciclos diarios; sus bandas son percentiles temporales 5–95, no intervalos de incertidumbre predictiva.

## Normalización exploratoria y referencias

Se utiliza `C_N,h = C_h × (101325 / P_h) × ((T2_h + 273.15) / 298.15)`, antes de promediar las 24 horas. La presión y temperatura WRF corresponden al receptor y al fin del intervalo; se mantienen iguales entre escenarios. Se contrasta el aporte sin normalizar con 45 µg/m³ y el aporte normalizado exploratoriamente con 130 µg/m³N. Los recuentos usan desigualdad estricta `>`; no calculan P98 anual ni cumplimiento legal. La guía OMS no representa un umbral seguro. Se mantienen la interpretación volumétrica asumida, la representatividad meteorológica y la cobertura parcial como condiciones de esta comparación.

Los Bronces presenta 61→78 días estivales y 39→69 invernales sobre la referencia chilena al comparar BASE con la configuración de máximo diario. En invierno son 30 fechas que pasan de estar en o bajo la referencia a quedar por encima. Estos recuentos corresponden al aporte vial aislado bajo la normalización exploratoria.

## Procedencia

La adaptación conserva los cálculos y funciones gráficas de los programas utilizados para el escrito; cambia rutas locales por archivos distribuidos, añade comprobaciones y exige destinos nuevos. `Procedencia.json` identifica los scripts y datos originales por hash. Los campos `legacy` de los pares son metadatos heredados: el reloj aplicado se lee desde `fecha_utc` y se convierte a `America/Santiago`. Se conservan 2146 pares estivales y 2152 invernales de temperatura y rapidez, con máscaras propias para humedad y dirección.

La extracción inicial de humedad y meteorología desde NetCDF requiere archivos WRF externos; este paquete no sustituye esa etapa. Los cuatro CSV horarios de `Reproduccion_doce` siguen siendo la fuente para la dispersión. La tolerancia aritmética del cotejo no demuestra convergencia física del modelo.

`amplitudes.py` recalcula las cuatro desviaciones estándar desde los 4270 registros admitidos y coteja tamaños muestrales, días válidos y valores originales. Se distribuye la muestra ya admitida; la normalización inicial de todas las descargas de estación se conserva en el archivo del proyecto.
