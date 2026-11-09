from pathlib import Path
from prepare_joint import ROOT,OUT,OLD,O,CONFIG,read,save,rec,now
import sys,json
sys.path.insert(0,str(OLD/'work'))
import salidas_invierno_20261026 as winter
checks=winter.tests();assert checks['estado']=='LECTOR_INVIERNO_VERIFICADO'
save(OUT/'Verificacion_lector_invierno.json',checks)
paths=[ROOT/'work/piloto_conjunto/receive_joint.py',ROOT/'work/piloto_conjunto/prepare_joint.py',OLD/'work/salidas_invierno_20261026.py',OLD/'work/salidas_estacionales_20261021.py',OLD/'work/ejecutar_base_verano_20261021.py',O/'Biblioteca_Tesis/tesis/receptores.py',OUT/'Diseno.json',OUT/'Lotes/panel/plan.json',OUT/'Lotes/panel/membresia.csv',OUT/'Verificacion_meteorologia.json']
paths += [Path(c['base'])/c['qc']/'Cobertura_horaria.csv' for c in CONFIG.values()]
save(OUT/'Contrato_recepcion.json',dict(created_utc=now(),inputs=[rec(p) for p in paths]))
(OUT/'LEEME.md').write_text('''# Piloto conjunto de 14 días: visión parcial de ambas temporadas

Se prioriza disponer de comparaciones completas entre BASE y ocho realizaciones conjuntas de temperatura y viento. Se conservan el inventario, las 12.263 fuentes, sus emisiones específicas de MP10 y MP2,5 y el terreno. El piloto es independiente de los lotes BASE estacionales que siguen en Windows y Linux.

## Cobertura y orden

- Verano: 1–7 de febrero de 2017, 167 horas válidas y una hora faltante conservada.
- Invierno: 25–31 de julio de 2017, 168 horas válidas. Estas fechas preceden al cambio de hora; se aplica además el lector invernal que distingue UTC, LST y hora civil.
- BASE y ocho trayectorias conjuntas, índices0–7 del conjunto RIDGE_24 ya congelado en cada temporada. No se reajusta el modelo, se escogen otros miembros ni se recorta su amplitud mirando concentraciones.
- Ambos contaminantes y un panel fijo de40receptores. Están incluidos los cuatro puntos sensibles y nodos en todas las zonas existentes de mina y glaciares. Se seleccionaron mediante distancia geométrica, sin consultar concentraciones.

Son252corridas diarias pequeñas:14días ×9configuraciones ×2contaminantes. El número de receptores baja de6295a40 para producir primero una visión amplia. Esto reduce el trabajo de dispersión por caso, aunque el costo no baja exactamente en esa proporción porque se conservan todas las fuentes y existe trabajo de lectura y preparación.

La cola completa primero BASE y las ocho realizaciones de la primera fecha de cada temporada, con ambos contaminantes. Luego hace lo mismo con la segunda fecha y así sucesivamente. Se publican comparaciones solo cuando están recibidas las nueve configuraciones correspondientes. Las salidas parciales no confunden un conjunto incompleto con ocho realizaciones.

## Qué se podrá mostrar

Concentraciones horarias y medias de horas válidas en cada punto, cambios frente a BASE, mediana, mínimo, máximo y desviación entre las ocho realizaciones. Las medias semanales se calculan primero por trayectoria, conservando su identidad y su dependencia temporal. Los ceros nativos de horas faltantes se enmascaran; no son concentraciones físicas.

El panel describe los puntos muestreados de todas las zonas, incluidos glaciares. Su máximo no es el máximo de toda una zona, de GENERAL o del dominio. Los resultados anteriores con6295receptores permanecen como productos separados. Extender espacialmente este piloto necesita una decisión posterior sobre costo y alcance; no se ejecuta automáticamente.

## Transferencia meteorológica explícita

Se aplica el residuo firmado T/u/v de la estación a la columna MMIF mediante un adaptador ONSITE previo a AERMET. Se usa la discrepancia de:49en el intervalo horario correspondiente, que termina11minutos después. Es una aproximación temporal declarada, sin desfases ajustados por correlación. Los triples y bloques horarios permanecen juntos y el sesgo no se suma otra vez.

La perturbación térmica vale su amplitud completa a2m y disminuye con una función cúbica hasta cero en la altura de capa límite de BASE; el viento usa el mismo tipo de transición desde10m. Se recalcula la diferencia de temperatura entre2y18,75m tras la escritura. Se conserva la humedad relativa de ONSITE, lo que permite cambiar el vapor implícito con la temperatura: no equivale al antiguo ensayo WRF con humedad específica fija.

Se mantienen presión, flujos, UST, altura de mezcla, sondeos y parámetros de superficie; AERMET deriva sus nuevos diagnósticos. No se reintegra la dinámica de WRF ni se afirma coherencia dinámica completa. Fuera de la semana objetivo se conserva BASE y se procesa el calendario estacional completo; la transición en los bordes es otra limitación. La transferencia estación–columna/perfil no está validada físicamente.

## Controles y límites

Las18configuraciones AERMET pasaron la revisión: reproducción exacta del BASE, conservación de calendarios y faltantes, recuperación de las perturbaciones térmicas/vectoriales dentro de la precisión de escritura y conservación de perfiles por encima del alcance. Los vientos fuertes que ya existían por encima de50m/s en niveles altos de invierno se conservaron; no se ampliaron artificialmente los vientos perturbados para aceptar resultados. El primer intento de preparación que detectó esos valores originales está archivado.

El modelo meteorológico conserva deficiencias de cobertura y persistencia ya documentadas, distintas entre temporadas. Estos rangos representan dispersión entre los escenarios generados bajo las hipótesis elegidas. No son incertidumbre total, intervalos calibrados, P95estable ni una muestra representativa de todos los regímenes estacionales.

## Operación y seguimiento

El tercer PC ejecuta como máximo dos modelos simultáneos. Las entradas idénticas se transfieren una sola vez y se materializan con enlaces locales cuando están disponibles; se comprueban todos los SHA256 antes de ejecutar. Cada caso queda en una carpeta independiente. El lector científico original verifica unidades, fuentes, receptores, horas, terreno, máximos nativos y medias antes de aceptar un resultado.

Estado.json informa corridas recibidas y fechas comparables completas. Estado_remoto.json es una instantánea fechada del ejecutor. Resultados.md y Comparacion_diaria_panel.csv se actualizan con los grupos completos. Solo Cierre.json confirma que las252corridas fueron recibidas. Los BASE de este panel no se suman a los días de producción en la malla completa.

Directorio remoto: C:/Users/Daniel/Documents/Tesis_Calculo_20261027/jobs/joint14_20261027/panel. La tarea existente se inicia bajo demanda, sin calendario. STOP_AFTER_CURRENT permite drenar los casos activos; no borrar candados ni repetir intentos para reanudar. Si falla la recepción científica, el receptor solicita detener nuevos despachos. Las desconexiones se registran y se reintenta la lectura; los modelos remotos siguen funcionando.
''',encoding='utf-8')
print(json.dumps(dict(contract_files=len(paths),winter_reader_verified=True)))