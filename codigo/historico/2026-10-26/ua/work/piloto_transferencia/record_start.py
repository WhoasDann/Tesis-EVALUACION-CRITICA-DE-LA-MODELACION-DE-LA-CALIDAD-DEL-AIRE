from pathlib import Path
from datetime import datetime,timezone
import json,subprocess
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/Piloto_transferencia_2026-10-27';T3=ROOT/'outputs/Tercer_PC_2026-10-27'
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
now=datetime.now(timezone.utc).isoformat()
r=subprocess.run(['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=8','windows3-tesis',r'type C:\Users\Daniel\Documents\Tesis_Calculo_20261027\jobs\transfer_20261027\full\status.json'],capture_output=True,text=True,timeout=25,check=True)
s=json.loads(r.stdout);assert s['state']=='RUNNING' and len(s['active'])==2 and not s['errors']
save(OUT/'full_remote_status.json',s)
small=json.loads((OUT/'Estado_small.json').read_text());assert small['received']==8 and small['state']=='RECEIVED_COMPLETE'
collector=json.loads((OUT/'full_collector.lock').read_text())
save(OUT/'Arranque.json',dict(status='ALTERNATIVE_FULL_GRID_PILOT_RUNNING',verified_utc=now,small_cases_received=8,small_hourly_values=768,full_cases_assigned=4,full_cases_received=0,remote=s,collector=collector,collector_exec_session=69512,base_jobs_modified=False,uncertainty_calibrated=False))
c=json.loads((T3/'Conexion.json').read_text());c.update(status='ALTERNATIVE_PILOT_RUNNING',verified_utc=now,production_job_assigned=True,job_scope='Deterministic PBL-limited wind sensitivity, 21-22 Dec 2016, MP10 and MP25, 6295 receptors',assigned_cases=4,short_cases_received=8,pilot_outputs=str(OUT),next_step='Complete and independently receive the four full-grid cases; do not count them as BASE days or calibrated ensemble members.')
save(T3/'Conexion.json',c)
p=T3/'LEEME.md';text=p.read_text(encoding='utf-8');text=text.replace('Estado actual: conexión y ejecución técnica listas. No hay un lote productivo de escenarios alternativos en ejecución. Las pruebas no se contabilizan como días de producción. Los dos primeros equipos mantienen sus lotes BASE.', 'Estado actual, actualizado el 27 de octubre: ocho casos cortos alternativos recibidos y cuatro casos PBL en la malla completa asignados, dos en ejecución. Detalles en ../Piloto_transferencia_2026-10-27/LEEME.md. Son sensibilidad determinista; no se contabilizan como días BASE ni como miembros de incertidumbre calibrada. Los dos primeros equipos mantienen sus lotes BASE.')
text=text.replace('El piloto alternativo requiere preparar y verificar sus entradas: días/bloques seleccionados de antemano, trayectorias meteorológicas, procesamiento y comparación con BASE emparejado.', 'El piloto de transferencia tiene entradas verificadas y comparación con BASE emparejado. Un futuro conjunto de realizaciones meteorológicas sigue requiriendo un diseño específico.')
p.write_text(text,encoding='utf-8')
d=pd.read_csv(OUT/'Comparaciones_small.csv');points={'PCAR':(381128.,6323667.),'LBCEN':(380148.,6331485.),'SULF':(384254.,6324494.),'PALP':(381759.,6327947.)}
rows=['# Resultados del contraste corto','', 'Ocho casos recibidos; 768 concentraciones horarias. Medias diarias de aportes MP10, en microgramos por metro cubico. Se conserva el BASE estacional emparejado. No son observaciones ni intervalos de confianza.','', '| Dia | Punto | BASE | UNIFORM | PBL |','|---|---|---:|---:|---:|']
for day in ['2016-12-21','2016-12-22']:
    for point,xy in points.items():
        a=d[(d.day==day)&(d.pollutant=='MP10')&(d.x_m==xy[0])&(d.y_m==xy[1])].set_index('scenario');assert len(a)==2
        rows.append(f"|{day}|{point}|{a.iloc[0].BASE_media24:.3f}|{a.loc['UNIFORM','alternativa_media24']:.3f}|{a.loc['PBL','alternativa_media24']:.3f}|")
rows+=['','Estos valores describen solo los cuatro puntos. No sustituyen maximos de zonas ni de la malla completa. Que las dos alternativas den resultados cercanos en estos puntos y fechas no demuestra que sean fisicamente equivalentes. El detalle de ambos contaminantes esta en Comparaciones_small.csv.','']
(OUT/'Resultados_cortos.md').write_text('\n'.join(rows),encoding='utf-8')
original=Path(r'/archivo/usuario\Documents\Codex\2026-10-08\hem\outputs\Contexto_vigente.md');current=original.read_text(encoding='utf-8')
heading='## Tercer PC ejecutando piloto de transferencia — 27 de octubre de 2026'
assert heading not in current
note=heading+'\n\nDESKTOP-Q7PJJIV (windows3-tesis) ejecuta cuatro casos PBL de sensibilidad determinista: 21-22dic2016, MP10/MP25, 6295 receptores, dos procesos simultaneos. Ocho casos cortos previos recibidos con768valores horarios. No son nuevos dias BASE ni incertidumbre calibrada. Los lotes BASE de los otros dos equipos no se modificaron.\n\nEntrega: '+str(OUT)+'\nEstado vivo: full_remote_status.json / Estado_full.json; Arranque.json registra el inicio. El receptor local receive_results.py full --watch conserva resultados separados. No repetir el lanzador ni borrar candados.\n\n'
original.write_text(note+current,encoding='utf-8')
print(json.dumps(dict(full_active=[a['id'] for a in s['active']],collector_pid=collector['pid'],short_received=8)))