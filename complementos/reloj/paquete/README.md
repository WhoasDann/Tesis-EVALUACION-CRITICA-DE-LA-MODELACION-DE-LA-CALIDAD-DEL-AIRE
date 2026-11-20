# Reproducción del diagnóstico de horario y ternas

Este paquete reproduce el análisis meteorológico de sensibilidad al horario de Piedra Carvajal del 15 de noviembre de 2026. La preparación portable corresponde al 19 de noviembre de 2026. Contiene las observaciones normalizadas, las series WRF extraídas, los residuos de referencia, los diseños, los módulos utilizados y las siete tablas de comprobación. No requiere la unidad D: ni rutas privadas del computador original.

## Ejecución

Se utiliza Python 3.12. Los paquetes y versiones de referencia figuran en `requirements.txt`. La instalación de dependencias requiere acceso a su repositorio de distribución; el cálculo posterior se realiza localmente y no descarga datos.

```sh
python -m venv .venv
```

En Windows:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe reproducir.py --salida salida
```

En Linux o macOS:

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python reproducir.py --salida salida
```

También puede ejecutarse `python reproducir.py --solo-verificar` para comprobar todos los hashes o `python reproducir.py --salida salida_tablas --sin-figuras` para omitir los gráficos. La carpeta de salida debe ser nueva; no se sobrescriben intentos previos. No debe utilizarse Python con la opción `-O`, que desactiva las aserciones de los cálculos originales.

La ruta del programa puede ser absoluta y el directorio actual puede ser otro. Las rutas de datos se resuelven respecto del propio paquete. No se utilizan las rutas absolutas conservadas en el protocolo histórico.

## Qué se reproduce

1. Las discrepancias, amplitudes SD y tres ternas originales.
2. Cuatro convenciones horarias y dos operadores sobre una muestra común: 734 registros estivales y 686 invernales, distribuidos en 31 y 29 días.
3. Las selecciones con escala fija y recalculada, conservando juntas T, u y v de una misma fecha.
4. Un control escalar independiente de 11.360 filas hora-caso y 45.440 residuos, sin importar la biblioteca de emparejamiento.
5. Las tres figuras, en PNG y SVG: amplitudes, fechas seleccionadas y vectores de las fechas originales.

Los resultados se contrastan celda por celda con las siete tablas archivadas. Fechas, escenarios y textos deben coincidir exactamente; la tolerancia absoluta para valores numéricos es 10^-9, sin tolerancia relativa. Esa tolerancia controla la reproducción computacional; no constituye un margen físico ni estadístico de incertidumbre. Los archivos JSON registran resultados, versiones y diferencias.

## Archivos y procedencia

| Ubicación | Contenido |
|---|---|
| `entradas/` | Ocho archivos de datos y diseños, copiados sin modificar sus bytes |
| `biblioteca/tesis/` | Cuatro módulos originales necesarios para el emparejamiento |
| `scripts/` | Cálculo, verificación independiente, gráficos, rutas y comparación |
| `referencia/tablas/` | Siete tablas archivadas para cotejar la reproducción |
| `referencia/figuras/` | Gráficos originales; la igualdad de imagen depende también de versiones y fuentes |
| `referencia/Informe_sensibilidad_reloj_y_ternas.pdf` | Informe original revisado; se distribuye como documento de referencia |
| `Protocolo_original.json` | Protocolo congelado, conservado íntegro, con conocimiento previo y hashes |
| `Entradas_portatiles.json` | Correspondencia entre cada insumo histórico y su ruta relativa |
| `procedencia/` | Scripts originales, diferencias de adaptación y hashes |
| `MANIFEST_SHA256.json` | Integridad del contenido distribuido |

La adaptación cambia las rutas de entrada/salida y elimina la dependencia de una instalación local de Matplotlib. Los cuerpos del cálculo, del verificador independiente y de los gráficos se conservan. La integridad de cada insumo original se comprueba al preparar el paquete y al ejecutar el análisis. El programa no ejecuta los scripts editoriales ni modifica el manuscrito.

La prueba entregada utiliza una copia ubicada en otro directorio, un directorio actual diferente y un control que impide leer los archivos científicos originales. Las dependencias se reutilizan desde el entorno Python disponible; no se acredita aquí una instalación nueva desde Internet ni ejecución en un segundo sistema operativo. `Verificacion_portabilidad.json`, junto al paquete, documenta la prueba concreta.

## Límites

Se reproduce el diagnóstico meteorológico posterior, no toda la cadena ERA5–WRF–MMIF–AERMET–AERMOD ni las concentraciones de la tesis. Las series WRF aquí incluidas son extracciones previas. Se mantienen los períodos de ajuste, las observaciones y las reglas del estudio retrospectivo.

El mayor cambio relativo absoluto de SD fue 11,94 % para temperatura y 3,63 % entre u, v y rapidez. El horario supuesto puede cambiar la fecha seleccionada y el vector. No se confirma el reloj de la estación, su intervalo de registro, la altura instrumental ni la transferencia física de perturbaciones. Tampoco se otorgan probabilidades a los escenarios ni se infiere un peor caso legal. Las concentraciones originales no se asignan a los candidatos nuevos.
