# Método vigente, procedencia y niveles de reproducción

Esta descripción corresponde al manuscrito cotejado el 26 de noviembre de 2026. El procedimiento histórico de discrepancias y ternas se conserva en [historico/METODO.md](historico/METODO.md).

## Cadena y diseño actual

ERA5 alimenta WPS/WRF; MMIF extrae la columna meteorológica; las perturbaciones se aplican a sus perfiles ONSITE; AERMET genera SFC/PFL y AERMOD calcula el aporte vial. Se mantienen fuentes, emisiones, terreno y receptores entre escenarios. La muestra estacional observada define SD(T) y SD(WS), con denominador N−1 y al menos 18 registros conjuntos por día. Los datos de ajuste histórico de discrepancias no se utilizan como amplitudes del diseño final.

El factorial escalar cruza a,b ∈ {−1,0,+1}: T′ = T + a σ_T w_T(z); WS′ = max(0, WS + b σ_WS w_WS(z)). La ampliación vectorial define q = WS − σ_WS w_WS(z), WS′ = |q| y gira la dirección 180° si q < 0. Usa la SD de rapidez, no desviaciones separadas de u/v. La función cúbica de atenuación conserva amplitud completa en la altura de referencia y la anula en la altura de mezcla BASE; el detalle figura en la tesis. La prescripción no demuestra coherencia dinámica de una nueva atmósfera.

## Calendario y agregación

Un caso es una fecha de ejecución, escenario y fracción. El diseño vigente contiene 4368 casos y 16 controles entre plataformas adicionales. Las salidas comparables incorporan 2150/2205 horas estivales/invernales por receptor. La selección diaria utiliza 86/90 fechas civiles de 24 horas comunes; la media de todas las horas de ventana es un indicador diferente. Los códigos AERMOD indican la hora de término. El calendario invernal se reconstruye desde UTC−4 fijo hacia UTC y luego `America/Santiago`.

Se agregan las horas de cada escenario antes de seleccionar su máximo diario o media estacional. El efecto conjunto se calcula como J_combinado − J_T − J_WS + J_BASE, sobre las mismas fechas y con el mismo operador de viento. Se conservan aumentos y disminuciones. Los 264 contrastes de orden estacional no invierten el orden de las medias; los ejemplos diarios se interpretan por separado.

## Análisis incorporados al manuscrito

La [normalización exploratoria](complementos/Analisis_actual/README.md) usa presión superficial y temperatura WRF por receptor y fin de intervalo, comunes a los escenarios: C_N,h = C_h (101325/P_h) ((T2_h+273,15)/298,15). Se normaliza cada hora antes de promediar. Los recuentos del manuscrito se reproducen con datos y comprobaciones explícitas; no representan cumplimiento normativo ni concentración ambiental total.

Los ciclos diarios se calculan desde los pares archivados de observaciones y WRF. El muestreo conserva el minuto original e interpola componentes del viento antes de obtener la rapidez. Las bandas temporales 5–95 % no son probabilidades de la concentración. La extracción de humedad original se realizó desde variables WRF; el paquete portable parte de esos pares ya extraídos.

## Niveles de reproducción

| Material | Alcance comprobable |
|---|---|
| `complementos/Reproduccion_doce` | Posproceso final desde concentraciones horarias comunes, con hashes y tablas de referencia |
| `complementos/Analisis_actual` | Normalización exploratoria, recuentos, métricas y ciclos desde factores, calendarios y pares archivados |
| `tesis` | PDF vigente, fuentes LaTeX y figuras; copia cotejada de los originales |
| `datos/aermod`, `datos/aermet`, programas raíz | Reconstrucción de entradas y resultados de los 3314 casos históricos, no de todos los 4368 finales |
| `datos/era5`, `datos/wrf` | Documentación de descargas e inventarios; NetCDF y parte de los antecedentes de integración permanecen externos |

La publicación completa de entradas nativas de la campaña final sigue pendiente. No se presenta la reproducción del posproceso como una ejecución completa de los modelos. Los datos compactos históricos, sus formatos y comandos se describen en [el método histórico](historico/METODO.md).

## WRF y alcances documentales

Los inventarios públicos de exportaciones WRF corresponden a selecciones para las ventanas de análisis. El cotejo posterior del manuscrito examinó cabeceras de 952 archivos nativos de los tres dominios y 36 opciones comparables; no debe confundirse con el inventario de exportaciones d03. Se identificaron diferencias entre la propuesta histórica de optimización y las copias efectivamente conservadas. Las cabeceras y copias de segmentos permiten un cotejo parcial; falta el registro completo de todos los reinicios y una comparación A/B de ambas configuraciones. Los archivos WPS/WRF documentales no garantizan reconstrucción exacta de cada segmento histórico.

Persisten límites en el reloj, intervalo y alturas instrumentales de Piedra Carvajal, la transferencia estación–columna, la procedencia/referencia vertical del relieve y los controles específicos de nuevos extremos. El inventario vial seleccionado no reproduce íntegramente el caso del titular, que utiliza otra cobertura e inventario y CALPUFF. La normalización exploratoria no acredita por sí sola equivalencia volumétrica ni aplicabilidad regulatoria.
