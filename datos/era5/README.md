# Descargas meteorológicas de ERA5

Se inspeccionaron los encabezados de los 453.088 mensajes de los 16 archivos GRIB conservados (66,05 GB). El [inventario](inventario_grib.json) registra, para cada archivo, el área de la grilla, la resolución, los identificadores de variable, los niveles y las fechas y horas de validez. Se usaron ocho horas UTC por día, de 00 a 21 con un intervalo de tres horas. Las fechas corresponden al contenido de los GRIB. Por ejemplo, `Dic2.grib` contiene marzo de 2017 y `mar.grib` contiene diciembre de 2016.

### Productos y variables

| Producto | Selección encontrada |
|---|---|
| [ERA5 en niveles de presión](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels?tab=download) | Geopotencial, temperatura, humedad relativa y componentes u y v del viento. Los GRIB del área centrada en Chile incluyen además divergencia y velocidad vertical en presión. |
| [ERA5 en niveles individuales](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download) | Veinte campos comunes. Temperatura y punto de rocío a 2 m, componentes u y v a 10 m, presión superficial y reducida al nivel del mar, temperatura de la piel de la superficie y temperatura superficial del mar, densidad y espesor de nieve en equivalente de agua, temperatura y contenido volumétrico de agua en las cuatro capas de suelo, geopotencial y máscara tierra–mar. |
| Campos adicionales de niveles individuales en el área centrada en Chile | Ráfaga de viento desde el procesamiento anterior, ráfaga instantánea a 10 m, evaporación, velocidad de fricción, altura de base de nubes, componentes u y v del viento neutro a 10 m y del viento a 100 m. Se identificaron tres campos de oleaje, correspondientes a altura significativa combinada, dirección media y período medio. |

Los 32 niveles de presión, expresados en hPa, son 10, 20, 30, 50, 70, 100, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 775, 800, 825, 850, 875, 900, 925, 950, 975 y 1000.

### Cobertura de los archivos

Las áreas se expresan en grados en el orden norte, oeste, sur y este. Los campos atmosféricos y terrestres tienen un paso de 0,25° y los tres campos de oleaje, de 0,5°.

| Producto y área | Fechas de validez conservadas |
|---|---|
| Presión, área extensa (26,75 / −131,25 / −52 / −6,5) | 1–12 dic. 2016, 1–21 mar. 2017 y 1 jun.–22 sept. 2017 |
| Presión, área centrada en Chile (−27 / −78 / −39 / −62) | 12 dic. 2016–28 feb. 2017 |
| Niveles individuales, área extensa (21 / −106,5 / −49,75 / −22,5) | 1–12 dic. 2016, 1–21 mar. 2017 y 1 jun.–30 sept. 2017 |
| Niveles individuales, área centrada en Chile (−27 / −78 / −39 / −62) | 12–31 dic. 2016 y todo 2017 |

El archivo de niveles individuales de todo 2017 incluye fechas fuera de las dos temporadas de dispersión. El inventario describe las descargas conservadas. La asignación de cada campo a un reinicio específico de WRF requiere el registro de ejecución de WPS y WRF correspondiente.

### Consulta y descarga

Desde la raíz del repositorio, el primer comando enumera los archivos y el segundo muestra una solicitud equivalente con los nombres utilizados por Copernicus. Ambos funcionan con la biblioteca estándar de Python.

```sh
python datos/era5/descargar.py
python datos/era5/descargar.py Dic2.grib
```

La opción de descarga requiere una cuenta del Climate Data Store, la aceptación de las condiciones de ambos productos y el cliente `cdsapi` configurado. Se genera un GRIB por grupo mensual de variables con fechas, niveles y grilla comunes. El agrupamiento y el orden de los mensajes pueden diferir del empaquetado histórico. [Configuración oficial del cliente CDS](https://cds.climate.copernicus.eu/how-to-api)

```sh
python -m pip install cdsapi
python datos/era5/descargar.py Dic2.grib --descargar descargas
```

Si se dispone de los originales, el comando siguiente vuelve a leer sus encabezados y comprueba que la suma de campos de las selecciones corresponda al número de mensajes de cada archivo.

```sh
python datos/era5/auditar_grib.py carpeta_con_los_grib inventario_recalculado.json
```
