from pathlib import Path
from prepare_sensitivity import *
sources=[OUT/'Diseno.json',OUT/'Verificacion_meteorologia.json',OUT/'Reparto.json']
sources+=[OUT/'Lotes/master'/n for n in ['plan_local.json','plan_windows3.json','batch_runner.py','membresia.csv']]
sources+=[ROOT/'work/sensibilidad_simple'/n for n in ['prepare_sensitivity.py','verify_meteorology.py','receive_sensitivity.py']]
sources+=[OLD/'work'/n for n in ['salidas_estacionales_20261021.py','salidas_invierno_20261026.py']]
save(OUT/'Contrato_recepcion.json',dict(created_utc=now(),inputs=[rec(p) for p in sources],validation='Native success; zero fatal errors;12263sources40receptors;960hourly rows/case; native24h; common valid hours; frozen hashes; independent seasonal readers; exact overlapping BASE hourly comparison to prior pilot.'))
note="""# Piloto autorizado de sensibilidad: 29 octubre 2026

Objetivo inmediato: resultados comparables en menos de24h, antes de decidir una campaña estacional.420casos=15días×2temporadas×7configuraciones×2contaminantes.40nodos fijos incluyen Los Bronces, Piedra Carvajal, Sulfatos y La Paloma. Todos los días y escenarios se fijaron antes de ver resultados.

## Ejecución
- Windows principal:210casos,2procesos. Plan en Lotes/master/plan_local.json; estado Lotes/master/status.json.
- windows3-tesis:210casos,2procesos. C:/Users/Daniel/Documents/Tesis_Calculo_20261027/jobs/sensitivity_20261029/panel.
- rocky-tesis continúa su cola BASE completa existente con2procesos. No se agregó un piloto ni se interrumpieron sus casos.
- BASE del Windows principal sigue pausada. NO iniciarla mientras esté este piloto.
- Supervisores independientes de este chat. Receptor continuo: work/sensibilidad_simple/receive_sensitivity.py. Estado consolidado: Estado.json; detalle Resultados.md.
- Parada suave: archivo STOP_AFTER_CURRENT en cada raíz de lote. No matar corridas activas. No reanudar otros lotes automáticamente al terminar.

## Resolución del operador
Este primer lote evalúa sensibilidad en la interfaz ONSITE de MMIF, mediante cambios controlados de perfiles y regeneración AERMET. No demuestra equivalencia con alterar wrfout y ejecutar MMIF de nuevo. La afirmación conceptual de la propuesta inicial se restringe explícitamente a este alcance en el piloto; no se usará como prueba de incertidumbre completa de WRF.

Una única componente T,u o v se cambia por ±SD de las discrepancias medias diarias del ajuste. No se suma el sesgo ni se sortean residuos. La perturbación superficial es constante en el período; su perfil depende de la PBL horaria BASE. Se aplica la atenuación cúbica previamente auditada y se vuelve a calcular DT01 y rapidez/dirección cuando corresponde. RH, presión, flujos, UST y MHGT se conservan: no hay reintegración dinámica ni garantía de equilibrio físico. La transferencia desde la estación a la columna MMIF sigue siendo una hipótesis.

## Verificación antes de AERMOD
14preprocesamientos AERMET exitosos. BASE SFC/PFL coincide numéricamente con los archivos originales.359horas verano y360invierno válidas, idénticas entre variantes. Campos ajenos al factor se mantienen en ONSITE. Se comprobaron temperaturas, módulos de viento, reconstrucción del vector, perfil superior sin cambios y errores de redondeo.
El control inicial de rapidez detectó valores originales de58,167m/s sobre la PBL invernal, ajenos a la perturbación. Se preservó el intento de preparación y se limitó el control de50m/s al perfil perturbado; no se recortaron vientos ni se ejecutó AERMOD con un intento fallido.

## Lectura
Comparaciones pareadas por fecha y nodo, tanto absolutas como porcentuales. Medias de horas válidas; una hora faltante estival no se rellena. Resúmenes entre configuraciones solo con días completos para ambos contaminantes. Los mapas de panel no representan máximos de6295receptores. Los15días no representan toda una temporada. No convertir el rango de7casos en intervalo de confianza ni llamarlo máximo legal.
"""
(OUT/'LEEME.md').write_text(note,encoding='utf-8')
ctx=OLD/'outputs/Contexto_vigente.md'
heading='## Piloto simple autorizado y activo — 29 octubre 2026\n\n'
if heading not in ctx.read_text(encoding='utf-8'):
 ctx.write_text(heading+'El usuario aprobó el piloto OAT de15días por temporada,7configuraciones y2contaminantes (420casos,40nodos). Ambos Windows ejecutan210casos cada uno,2procesos por equipo. La cola BASE local permanece pausada; NO reanudarla mientras este piloto esté activo. Rocky conserva su cola BASE. No nuevas1024trayectorias. Estado y alcance: '+str(OUT/'Estado.json')+' y '+str(OUT/'LEEME.md')+'. Revisar estados vivos antes de intervenir; no duplicar ni reiniciar automáticamente otros lotes al finalizar.\n\n'+ctx.read_text(encoding='utf-8'),encoding='utf-8')
print('Contract and operating scope recorded')

