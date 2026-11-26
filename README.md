# Evaluación crítica de la modelación de la calidad del aire

**Estado cotejado: 26 de noviembre de 2026.** Este repositorio acompaña la tesis sobre el aporte vial seleccionado de Los Bronces Integrado. El diseño vigente comprende **4368 casos, doce configuraciones, MP10 y MP2,5**, con un panel fijo de 40 receptores y análisis destacado en Los Bronces, Piedra Carvajal, Sulfatos y un punto del glaciar La Paloma.

## Versión vigente y acceso directo

- [Tesis actual en PDF](tesis/Tesis_2026-11-26.pdf), [fuentes LaTeX](tesis/Fuentes_LaTeX_2026-11-26.zip) y [trazabilidad del manuscrito](tesis/README.md).
- [Reproducción de las medias, máximos, interacciones y orden entre receptores](complementos/Reproduccion_doce/README.md).
- [Normalización exploratoria de MP10, recuentos y ciclos meteorológicos](complementos/Analisis_actual/README.md).
- [Método, procedencia y límites de reproducción](METODO.md).
- [Antecedentes y controles históricos](complementos/README.md).

Los programas y datos antiguos de la raíz se conservan para reproducir campañas previas. **El comando raíz `python reproducir.py medias ...` calcula la campaña histórica de 3314 casos; no la campaña final.**

## Reproducir los resultados finales

Se requiere descargar o clonar el repositorio completo y ejecutar desde su raíz. Las dependencias fijadas requieren Python 3.11 o posterior; el entorno ensayado fue Python 3.13.9.

```sh
python -m pip install -r complementos/Reproduccion_doce/requirements.txt
python complementos/Reproduccion_doce/reproducir.py salida_final
python -m pip install -r complementos/Analisis_actual/requirements.txt
python complementos/Analisis_actual/amplitudes.py salida_amplitudes
python complementos/Analisis_actual/normalizacion_mp10.py salida_normalizacion
python complementos/Analisis_actual/meteorologia.py salida_meteorologia
```

Cada destino debe ser nuevo. Se comprueban hashes y se reconstruyen **192 medias, 16 selecciones de mayor media/máximo diario, 96 contrastes de interacción y 264 comparaciones de orden estacional**. Se utilizan los mismos **86 días estivales y 90 invernales de 24 horas** para las doce configuraciones, a partir de 2150 y 2205 horas comunes por receptor. No se imputan horas ni se forman series tomando máximos horarios entre escenarios.

## Diseño vigente

Las amplitudes se calculan mediante la desviación estándar muestral de registros horarios observados de temperatura y rapidez en Piedra Carvajal, por temporada, admitiendo días con al menos 18 registros conjuntos válidos. No son desviaciones de las discrepancias con WRF ni de medias diarias. Se emplean 2153 registros estivales y 2117 invernales: σ_T = 3,3 y 4,7 °C; σ_WS = 1,9 y 3,2 m/s, respectivamente, mostradas con un decimal y conservadas con precisión completa en las corridas.

| Grupo | Configuraciones | Casos |
|---|---|---:|
| Factorial escalar | BASE; BASE ± σ_T; BASE ± σ_WS; las cuatro combinaciones de signos de temperatura y rapidez | 3276 |
| Ampliación vectorial | BASE − σ_WS⃗; BASE − σ_T − σ_WS⃗; BASE + σ_T − σ_WS⃗ | 1092 |
| Total vigente | Doce configuraciones × 182 fechas × dos fracciones | **4368** |

Se reutilizaron 364 casos BASE compatibles y se ejecutaron 4004 nuevos; 16 controles entre plataformas se contabilizan aparte. Las ventanas corresponden al 21 de diciembre de 2016–20 de marzo de 2017 y al 21 de junio–20 de septiembre de 2017. La fecha final de verano tiene 17 horas; en invierno se trata explícitamente el cambio de hora civil.

El ajuste escalar conserva la dirección y limita en cero la rapidez al restar. El ajuste vectorial usa la misma SD de rapidez, conserva el módulo absoluto del resultado firmado y gira 180° donde la resta cruza cero. En los archivos, `_INV` identifica el ajuste vectorial; no significa una inversión térmica. Las perturbaciones entran en ONSITE después de MMIF y se reprocesan con AERMET/AERMOD; WRF, emisiones y receptores permanecen fijos.

## Resultados e interpretación

La selección depende del receptor, la temporada y el indicador. En Los Bronces, el máximo diario MP10 fue 1352,9 µg/m³ en verano con BASE − σ_T − σ_WS y 1697,8 µg/m³ en invierno con su variante vectorial. Las diferencias frente a BASE de las mismas fechas fueron +140,2 % y +200,4 %. Las tablas del paquete contienen los resultados de los cuatro receptores y ambas fracciones.

El orden de las medias estacionales se mantuvo: Los Bronces > Piedra Carvajal > La Paloma > Sulfatos; hubo cambios en días particulares. El análisis describe sensibilidad prescrita, sin probabilidades calibradas ni acreditación de un peor caso regulatorio.

La normalización exploratoria de MP10 por receptor y hora se reproduce por separado. Sus recuentos no constituyen evaluación de cumplimiento: el aporte vial no es la concentración ambiental total, no cubre un año/trienio y conserva condiciones de representatividad y base volumétrica. Las medias anuales del titular son referencias contextuales con otros períodos, fuentes y modelo de dispersión.

## Qué se distribuye y qué permanece externo

Se incluyen el manuscrito vigente, sus fuentes y figuras, las salidas horarias comunes del diseño final, programas portables del posproceso, datos para los análisis nuevos y los insumos de las campañas históricas. **Todavía no se distribuyen conjuntamente todos los insumos nativos y ejecutables necesarios para repetir los 4368 casos desde los modelos.** La verificación de los indicadores finales no equivale a repetir WRF–MMIF–AERMET–AERMOD.

Los datos ERA5 se documentan en [datos/era5](datos/era5/README.md); los NetCDF WRF voluminosos permanecen externos e identificados por hashes. [METODO.md](METODO.md) detalla estos niveles de reproducción.

## Campañas anteriores

Los 3314 casos de discrepancias y ternas son antecedentes del diseño vigente; no deben sumarse a los 4368 como si fueran un único diseño sin reutilizaciones. Sus instrucciones se conservan en [historico/README.md](historico/README.md). Las carpetas raíz `datos/aermod`, `datos/aermet`, `datos/horarios`, `resultados`, `figuras` y los programas raíz `reproducir.py` y `graficar.py` corresponden a esos antecedentes. Sus cifras de 87/90 días y nueve configuraciones no describen la comparación final de doce configuraciones.

La integridad global se comprueba con `python reproducir.py verificar`, que verifica `MANIFIESTO.sha256`. Para citar una versión se debe conservar el identificador de commit descargado.
