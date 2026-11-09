from pathlib import Path
import sys,json
from campaign import ROOT,OUT,OLD,PILOT,read,save,sha,now,rec
def main():
 a=read(OUT/'Reparto.json');assert a['total']==2548 and a['new']==2142 and a['reused']==406
 assert read(PILOT/'Lotes/master/plan.json')['binary_sha256']==sha(OUT/'Binarios/aermod.exe')
 cases=read(OUT/'Casos.json')['cases'];assert len(cases)==2548
 save(OUT/'Cobertura_esperada.json',dict(cases=2548,receptors=40,hourly_values=2441600,valid_hourly_values=2439360,masked_hourly_values=2240,case_receptor_rows=101920,summer_valid_hours_per_configuration_pollutant=2151,winter_valid_hours_per_configuration_pollutant=2205,winter_civil_dates=92))
 groups={h:{c['id'] for c in cases if c['host']==h} for h in ['local','windows3','rocky','reused']}
 assert sum(map(len,groups.values()))==len(set.union(*groups.values()))==2548
 for h,v in a['hosts'].items():
  assert sha(v['plan'])==v['plan_sha256']
  plan=read(v['plan']);assert {c['id'] for c in plan['cases']}==groups[h]
  for c in plan['cases']:assert len(c['hour_states']) in [17,23,24] and c['sources']==12263 and c['receptors']==40
 d=read(OUT/'Diseno.json');d['comparison']='Same dates, emissions,40receptors and common valid hours. Whole available seasonal windows2016/2017; daily paired differences and absolute means. Native Linux/Windows equality checked with8canaries. No calibrated intervals, scenario probabilities, full-grid maxima, or other-year representativeness.';save(OUT/'Diseno.json',d)
 sys.path.insert(0,str(OLD/'work'));sys.path.insert(0,str(OLD/'outputs/Biblioteca_Tesis'))
 import salidas_estacionales_20261021 as summer
 import salidas_invierno_20261026 as winter
 save(OUT/'Pruebas_lectores.json',dict(status='PASSED',summer=summer.test_masks(),winter=winter.tests()))
 files=[OUT/n for n in ['Diseno.json','Reparto.json','Casos.json','Catalogo_inputs.json','Reutilizacion_piloto.json','Verificacion_meteorologia.json','Comunes/membresia.csv','Comunes/receptores.inc','Calendarios/VERANO.csv','Calendarios/INVIERNO.csv']]
 files += [ROOT/'work/sensibilidad_estacional'/n for n in ['collect.py','supervisor.py','run_local.py','batch_runner.py']]
 files += [OLD/'work'/n for n in ['salidas_estacionales_20261021.py','salidas_invierno_20261026.py','ejecutar_base_verano_20261021.py']]
 files += [Path(v['plan']) for v in a['hosts'].values()]
 save(OUT/'Contrato_recepcion.json',dict(created_utc=now(),files=[rec(p) for p in files]))
 rows=['# Sensibilidad simple: verano e invierno completos disponibles','',f"Preparado UTC: {now()}",'','Solicitud humana: continuar ambas temporadas con los tres computadores. Esta autorización reemplaza la pausa anterior y no autoriza colas duplicadas.','',
 'Alcance: 90 fechas de verano (21-dic-2016 a20-mar-2017) y92 fechas LST de invierno (21-jun-2017 a20-sep-2017);7configuraciones BASE/T-/T+/u-/u+/v-/v+;MP10 yMP2,5;40receptores fijos que incluyen Los Bronces, Piedra Carvajal, La Paloma y Sulfatos. Total2548casos,406reutilizados y2142nuevos.',
 'Los14casos del1-febrero se recalculan: extender la perturbación a días precedentes cambia algunas alturas de mezcla SFC de primeras horas en variantes de viento. No se mezclan esos resultados del piloto con el diseño estacional.',
 'Conservar el piloto original: ../Sensibilidad_simple_2026-10-29. Reutilizacion_piloto.json prueba entradas equivalentes, controles idénticos salvo título y todos los productos rehasheados.',
 '', '## Reparto exclusivo', '', '| Equipo | Casos nuevos | Días verano | Días invierno |', '|---|---:|---:|---:|']
 for h,v in a['hosts'].items():rows.append(f"|{h}|{v['assigned']}|{v['days_by_season']['VERANO']}|{v['days_by_season']['INVIERNO']}|")
 rows += ['', 'Dos procesos AERMOD simultáneos por equipo. Linux termina las dos corridas BASE completas en curso, verifica candado y supervisor liberados, ejecuta8canarios entre plataformas y comienza su lote. Los canarios no se cuentan dentro de2548. La cola BASE antigua queda pausada; no reanudarla automáticamente.',
 'El reparto está congelado en Reparto.json y Casos.json. No iniciar nuevos supervisores si existen candados. Si falla un caso, preservar el intento y detener nuevos despachos con STOP_AFTER_CURRENT; los casos activos finalizan.',
 '', '## Recepción y almacenamiento', '',
 'Supervisor_local.json y Lotes/local/status.json son señales vivas. Estado.json integra recepción independiente; no confundir caso nativo terminado con recibo científico. collect.py recoge archivos comprimidos remotos por SSH estricto y usa los lectores originales de verano/invierno. Cada recibo contiene hashes, calendario, resultados, origen y tiempo.',
 'Las entradas repetidas se comparten y se copian únicamente al despachar. Las salidas aermod.out y errores.out se retienen completas dentro del tar.gz; después de verificar igualdad se elimina su copia expandida. Las emisiones y fuentes originales no se eliminan. Storage.json documenta la compactación. La recepción conserva las concentraciones horarias y las medias por receptor.',
 '', '## Interpretación científica', '',
 'Se mantienen amplitudes fijadas a partir de la desviación estándar de discrepancias medias diarias Obs-WRF del período de ajuste. Una variable por vez: verano T±0,953°C,u±1,780m/s,v±4,531m/s; invierno T±1,586°C,u±3,541m/s,v±6,725m/s. No hay corrección de sesgo ni nuevas realizaciones Ridge.',
 'Operador: perfiles ONSITE serializados de MMIF, atenuación vertical cúbica hasta la PBL BASE, nuevo AERMET y AERMOD. Se conservan campos auxiliares según Diseno.json. No equivale a reintegrar WRF ni valida equilibrio dinámico de montaña. Hipótesis de transferencia espacial de amplitudes de estación a la columna MMIF.',
 'Verano:2153horas objetivo y2151válidas;20-mar tiene17horas y no se etiqueta como media24h. Invierno:2207horas objetivo y2205válidas; dos faltantes se enmascaran. El reloj de simulación es LST UTC-4. El cambio civil de agosto genera un día23h; el último día civil se recompone desde dos archivos LST. Invierno_dias_civiles.csv se genera al terminar y verifica92fechas completas respecto al calendario disponible.',
 'Los CSV con sufijo LST son resúmenes por ventana de ejecución, no medias civiles de invierno. Resumen_periodo_comparable.csv usa únicamente fechas completas en las7configuraciones y ambos contaminantes, ponderadas por las mismas horas válidas. Las horas faltantes no son concentraciones cero. Las diferencias porcentuales se omiten cuando BASE es cero.',
 'El rango de variantes mide sensibilidad prescrita; no es intervalo de confianza ni un peor caso legal demostrado. La variabilidad temporal BASE también contiene emisiones variables por día. El panel40no identifica máximos de la malla completa6295. Las conclusiones se limitan a las temporadas y horas disponibles.',
 '', '## Próximo control', '',
 'Comprobar progreso con estados recientes, incremento de POSTFILE y nuevos recibos. No relanzar por un estado antiguo o una consulta aislada deCPU. Revisar canarios Linux antes de aceptar producción. Al completar2548recibos, auditar cobertura/hashes, generar gráficos científicos/tablas y síntesis para el profesor. Notificar sólo fallas, cambios relevantes de plazo o entrega completa.','']
 (OUT/'LEEME.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
 print(json.dumps({h:v['assigned'] for h,v in a['hosts'].items()}),flush=True)
if __name__=='__main__':main()
