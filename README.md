# Evaluación crítica de la modelación de la calidad del aire

Este repositorio documenta la reconstrucción de las emisiones viales de Los Bronces Integrado y la sensibilidad de los aportes de MP10 y MP2,5 a cambios en la meteorología. La comparación se desarrolla en Los Bronces, Piedra Carvajal, Sulfatos y el glaciar La Paloma. La simulación conserva un panel de 40 receptores.

## Reproducción de los resultados

Se requiere Python 3.10 o posterior. Los siguientes comandos se ejecutan desde la raíz de una copia descargada o clonada. La verificación, el cálculo de las medias y la preparación de los casos utilizan la biblioteca estándar de Python.

```sh
python reproducir.py verificar
python reproducir.py medias salida
```

El primer comando comprueba los archivos con SHA-256. El segundo parte de las **concentraciones horarias del modelo**, aplica la máscara de cada caso, recupera las fechas civiles de invierno y calcula las medias diarias de 24 horas de los cuatro receptores. Luego conserva las fechas comunes a las nueve configuraciones. El resultado, `salida/medias.csv`, contiene 144 medias de período: dos temporadas, nueve configuraciones, dos fracciones y cuatro receptores. Se comparan 87 días completos de verano y 90 de invierno. La tabla publicada se utiliza al final para comprobar el cálculo.

Las ocho figuras de distribución, una por receptor y fracción, están disponibles en [figuras](figuras). El comando siguiente reconstruye las curvas desde los datos diarios e identifica el escenario con la media más alta dentro de las nueve configuraciones. Se requiere Matplotlib.

```sh
python -m pip install matplotlib
python graficar.py salida/figuras
```

## Repetición de una simulación

```sh
python reproducir.py listar --filtro INVIERNO_20170621
python reproducir.py caso INVIERNO_20170621_BASE_MP10 corrida
```

Se crea una carpeta nueva con el control `aermod.inp`, las fuentes y los receptores, los perfiles meteorológicos `met.SFC` y `met.PFL` y las emisiones horarias. Cada archivo se verifica contra la huella del caso original. La representación compacta de las emisiones conserva la precisión decimal y el calendario de cada hora. Se reconstruyen las seis entradas para cualquiera de los 3.314 identificadores del catálogo.

Con el ejecutable AERMOD en el PATH, la corrida y el contraste se realizan así:

```sh
cd corrida
aermod
cd ..
python reproducir.py comparar INVIERNO_20170621_BASE_MP10 corrida/receptor_horas.out
```

El contraste exige igualdad a la precisión publicada de cinco decimales para cada par hora–receptor. También verifica la cobertura. Se conservan las huellas de los ejecutables Windows 26135 en [versiones de los modelos](datos/controles/versiones.json). La versión y la plataforma pueden influir en la comparación entre ejecutables. Las distribuciones oficiales se consultan en [US EPA, sistema AERMOD](https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models).

## Diseño del estudio

| Etapa | Configuraciones y cobertura | Casos distintos |
|---|---|---:|
| Sensibilidad por componente | BASE, T−, T+, u−, u+, v−, v+ en 182 fechas de ejecución y dos fracciones | 2.548 |
| Rapidez del viento y temperatura | WS+ y T+WS+ en las mismas fechas. Se reutilizan BASE y T+ para el contraste conjunto | 728 |
| Episodios | Ternas empíricas de discrepancias de T, u y v en cinco días civiles de verano y seis de invierno, con fechas auxiliares para el cómputo civil | 38 |
| Total | Casos únicos recibidos y verificados | **3.314** |

T es la temperatura, u la componente del viento hacia el este y v la componente hacia el norte. WS+ aumenta la rapidez con dirección fija. Las perturbaciones estacionales se prescriben en los datos ONSITE que se procesan con AERMET. La amplitud por componente procede de la desviación estándar de las discrepancias medias diarias entre la estación y WRF en el período de ajuste. El contraste conjunto diario se calcula como C(T+WS+) − C(T+) − C(WS+) + C(BASE), sobre el mismo receptor, fecha y horas. Las ternas combinan discrepancias que ocurrieron en un mismo día de estación. La interpretación física de su transferencia a la columna y al dominio requiere evidencia adicional.

El verano comprende el 21 de diciembre de 2016 al 20 de marzo de 2017 y el invierno, el 21 de junio al 20 de septiembre de 2017. El último día de verano tiene 17 horas. En invierno se considera el cambio de hora civil. Se distingue el escenario de mayor media de período del escenario de mayor concentración diaria. Los resultados describen sensibilidad en el panel evaluado.

## Archivos

| Directorio | Contenido y uso |
|---|---|
| [datos/aermod](datos/aermod) | Catálogo por caso, controles, geometría nativa, meteorología y tasas para reconstruir las entradas exactas |
| [datos/horarios](datos/horarios) | 3.175.680 valores horarios de salida, incluidos los que requieren máscara. El formato se describe [aquí](METODO.md) |
| [datos/aermet](datos/aermet) | Control y entradas ONSITE, SURFACE y UPPER por temporada y configuración, con huellas de las salidas esperadas |
| [datos/emisiones](datos/emisiones) y [geometría](datos/geometria) | Inventarios viales anuales, distribución por tramos y geometrías de refinamiento |
| [datos/observaciones](datos/observaciones), [meteorología](datos/meteorologia) y [transferencia](datos/transferencia) | Registros de estación, series de ajuste, evaluación meteorológica y perfiles extraídos de WRF |
| [datos/era5](datos/era5) | Selecciones de Copernicus reconstruidas a partir de 16 archivos GRIB, con variables, niveles, áreas, fechas, horas y comandos de descarga |
| [datos/wrf](datos/wrf) | Inventario de archivos WRF externos, índices temporales, huellas y configuraciones documentales |
| [codigo/tesis](codigo/tesis) | Biblioteca científica que procesa observaciones, archivos WRF, emisiones y receptores |
| [codigo/historico](codigo/historico) | Programas del estudio agrupados por la etapa y el directorio de procedencia |
| [resultados](resultados) | Medias, diferencias pareadas, interacción de temperatura y viento, selección por episodios y referencias del titular |

La BASE incluye 873 tramos viales. Representan el 96,43 % de la masa anual de MP10 y el 96,01 % de la masa de MP2,5 de tránsito documentada en el inventario de 2017. La comparación con el anexo ADC-160vi considera las diferencias de período, fuentes y formación de partículas secundarias. La interpretación normativa de MP10 requiere acreditar la normalización del volumen a 25 °C y 1 atm. Los indicadores anuales y trianuales requieren sus respectivos períodos y condiciones de cobertura.

Los datos necesarios para repetir la **dispersión desde las entradas preparadas** se distribuyen en el repositorio. Para iniciar la cadena meteorológica se documentan las descargas de ERA5 en [niveles de presión](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels?tab=download) y [niveles individuales](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download). Los antecedentes de WPS, WRF y MMIF y el alcance de su reproducción figuran en [método y procedencia](METODO.md). Para citar una reproducción se puede usar el enlace permanente a la revisión de GitHub que se descargó.
