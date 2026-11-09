"""Independent scientific reception and partial broad summaries; never alters BASE production receipts."""
from pathlib import Path
import sys,subprocess,json,tarfile,shutil,time,traceback,os,base64
import numpy as np,pandas as pd
from prepare_joint import ROOT,OUT,OLD,CONFIG,SCENARIOS,read,save,sha,rec,now
sys.path.insert(0,str(OLD/'work'))
import salidas_estacionales_20261021 as summer
import salidas_invierno_20261026 as winter
BATCH=OUT/'Lotes/panel';REMOTE='C:/Users/Daniel/Documents/Tesis_Calculo_20261027/jobs/joint14_20261027/panel'
SSH=['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=8','windows3-tesis']
def halt_dispatch():
 p=REMOTE.replace('/','\\')+'\\STOP_AFTER_CURRENT'
 script="$ErrorActionPreference='Stop';[IO.File]::WriteAllText('"+p+"','Scientific reception requires review')"
 enc=base64.b64encode(script.encode('utf-16-le')).decode()
 subprocess.run(SSH+['powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand '+enc],capture_output=True,timeout=30,check=True)
def get_status():
 r=subprocess.run(SSH+['type '+REMOTE.replace('/','\\')+'\\status.json'],capture_output=True,text=True,timeout=35)
 if r.returncode:raise ConnectionError(r.stderr[-1000:])
 s=json.loads(r.stdout);save(OUT/'Estado_remoto.json',s);return s

def summarize(plan,state):
 parts=[];receipts=[]
 for c in plan['cases']:
  rp=OUT/'Recibos'/(c['id']+'.json')
  if not rp.exists():continue
  receipt=read(rp);receipts.append(receipt);df=pd.read_csv(BATCH/c['folder']/'Por_receptor.csv')
  for k in ['season','day','scenario','pollutant']:df[k]=c[k]
  parts.append(df)
 metadata=dict(status='COMPLETE_RECEIVED' if len(receipts)==252 else state['state'],updated_utc=now(),received=len(receipts),assigned=252,receptors=40,complete_dates_both_pollutants=0,total_dates=14,hourly_values=sum(r['qa']['valores_horarios'] for r in receipts),active=state['active'],errors=state['errors'],scope='Sampled points only; joint exploratory propagation, not calibrated uncertainty.')
 table=None
 if parts:
  allpoints=pd.concat(parts,ignore_index=True);allpoints.to_csv(OUT/'Medias_por_caso.csv',index=False)
  index=['season','day','pollutant','x_m','y_m'];p=allpoints.pivot(index=index,columns='scenario',values='media_horas_validas_ug_m3')
  for n in SCENARIOS:
   if n not in p:p[n]=np.nan
  p=p.dropna(subset=SCENARIOS)
  if len(p):
   variants=p[SCENARIOS[1:]];table=pd.DataFrame(dict(BASE=p['BASE'],media_realizaciones=variants.mean(axis=1),mediana_realizaciones=variants.median(axis=1),minimo_realizaciones=variants.min(axis=1),maximo_realizaciones=variants.max(axis=1),sd_realizaciones=variants.std(axis=1,ddof=1)))
   table['delta_media_vs_BASE']=table.media_realizaciones-table.BASE
   table['delta_porcentaje']=np.where(table.BASE>0,100*table.delta_media_vs_BASE/table.BASE,np.nan)
   table=table.reset_index();table.to_csv(OUT/'Comparacion_diaria_panel.csv',index=False)
   coverage=table.groupby(['season','day']).pollutant.nunique();metadata['complete_dates_both_pollutants']=int((coverage==2).sum())
   metadata['complete_dates_by_season']={season:int(sum((coverage.loc[season]==2))) if season in coverage.index.get_level_values(0) else 0 for season in CONFIG}
   table.to_csv(OUT/'Dispersion_entre_realizaciones.csv',index=False)
  metadata['measured_case_seconds_median']=float(np.median([r['seconds'] for r in receipts]))
  metadata['wall_hours_projection_remaining_two_workers']=float((252-len(receipts))*np.mean([r['seconds'] for r in receipts])/7200)
 save(OUT/'Estado.json',metadata)
 lines=['# Piloto conjunto: resultados parciales','',f"Actualizado: {metadata['updated_utc']}",f"Corridas recibidas: {len(receipts)}/252. Fechas con BASE y ocho realizaciones, ambos contaminantes: {metadata['complete_dates_both_pollutants']}/14.",'','Las comparaciones incluyen solamente grupos completos de nueve configuraciones y las mismas horas válidas. La desviación y el rango describen ocho realizaciones del modelo; no son intervalos calibrados ni variabilidad observada. Los 40 nodos cubren todas las zonas, pero no representan sus máximos completos.','']
 if table is not None:
  points={(381128.,6323667.):'Piedra Carvajal',(380148.,6331485.):'Estación Los Bronces',(384254.,6324494.):'Sulfatos',(381759.,6327947.):'La Paloma'}
  selected=table[table.apply(lambda r:(r.x_m,r.y_m) in points,axis=1)].copy()
  lines+=['Medias de horas válidas, µg/m³. El archivo Comparacion_diaria_panel.csv incluye todos los nodos.','','| Temporada | Día | Contaminante | Punto | BASE | Mediana de 8 | Mínimo–máximo de 8 |','|---|---|---|---|---:|---:|---:|']
  for r in selected.sort_values(['season','day','pollutant','x_m']).itertuples():lines.append(f'|{r.season}|{r.day}|{r.pollutant}|{points[(r.x_m,r.y_m)]}|{r.BASE:.4g}|{r.mediana_realizaciones:.4g}|{r.minimo_realizaciones:.4g}–{r.maximo_realizaciones:.4g}|')
  # Seven-day member aggregates preserve member identity; do not pool hours as independent realizations.
  if metadata['complete_dates_both_pollutants']==14:
   weekly=allpoints.groupby(['season','pollutant','scenario','x_m','y_m']).agg(total=('suma_horaria_ug_m3','sum'),valid_hours=('horas_validas','sum')).reset_index();weekly['media_semana_horas_validas']=weekly.total/weekly.valid_hours
   weekly.to_csv(OUT/'Medias_semanales_por_realizacion.csv',index=False)
 (OUT/'Resultados.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 if len(receipts)==252:
  save(OUT/'Cierre.json',metadata)
  cp=ROOT/'outputs/Tercer_PC_2026-10-27/Conexion.json';c=read(cp)
  if c.get('pilot_outputs')==str(OUT):
   c.update(status='JOINT_PILOT_COMPLETE_RECEIVED',production_job_assigned=False,next_step='Review the broad partial pilot and decide any scientifically justified extension; no new cases automatically assigned.');save(cp,c)
 return metadata

def collect(plan,state):
 members=pd.read_csv(BATCH/'membresia.csv');(OUT/'Recibos').mkdir(exist_ok=True);(OUT/'Descargas').mkdir(exist_ok=True)
 for c in plan['cases']:
  receipt_path=OUT/'Recibos'/(c['id']+'.json')
  if receipt_path.exists() or c['id'] not in state['completed']:continue
  folder=BATCH/c['folder'];archive=OUT/'Descargas'/(c['id']+'.tar.gz')
  r=subprocess.run(['scp','-o','BatchMode=yes','-o','ConnectTimeout=8','windows3-tesis:'+REMOTE+'/exports/'+c['id']+'.tar.gz',str(archive)],capture_output=True,text=True,timeout=120)
  if r.returncode:raise ConnectionError(r.stderr)
  allowed={'aermod.out','resumen.sum','errores.out','receptor_horas.out','receptor_24h.out','console.log','execution.json','receipt.json'}
  with tarfile.open(archive,'r:gz') as tar:
   files=tar.getmembers();assert len(files)==len(allowed) and {x.name for x in files}==allowed
   for item in files:
    assert item.isfile() and item.name==Path(item.name).name and item.size<300*1024**2
    dest=folder/item.name
    assert not dest.exists(),'Unreceived prior attempt requires review'
    with tar.extractfile(item) as src,dest.open('xb') as out:shutil.copyfileobj(src,out)
  native=read(folder/'receipt.json');assert native['id']==c['id'] and native['inputs']==c['inputs'] and native['binary_sha256']==plan['binary_sha256']
  for n,h in {**native['outputs'],**c['inputs']}.items():assert sha(folder/n)==h,n
  cfg=CONFIG[c['season']];full=pd.read_csv(Path(cfg['base'])/cfg['qc']/'Cobertura_horaria.csv')
  if c['season']=='VERANO':mask=full.loc[full.dia.eq(c['day'])];qa,data,*_=summer.receive(folder,mask,members,receptors=40)
  else:mask=full.loc[full.dia_LST.eq(c['day'])];qa,data,*_=winter.receive(folder,mask,members,full,receptors=40)
  qa['valores_horarios']=len(data)
  grouped=data.groupby(['x_m','y_m']).C_ug_m3.agg(['sum','mean','max','count']).reset_index();grouped.columns=['x_m','y_m','suma_horaria_ug_m3','media_horas_validas_ug_m3','maximo_1h_ug_m3','horas_validas']
  assert len(grouped)==40 and grouped.horas_validas.nunique()==1
  grouped.to_csv(folder/'Por_receptor.csv',index=False);data.to_csv(folder/'Horario_con_mascara.csv',index=False)
  outputs={**native['outputs'],**{n:sha(folder/n) for n in ['Por_receptor.csv','Horario_con_mascara.csv']}}
  save(receipt_path,dict(status='SCIENTIFIC_RECEPTION_PASSED',id=c['id'],season=c['season'],day=c['day'],scenario=c['scenario'],pollutant=c['pollutant'],qa=qa,seconds=native['execution']['seconds'],received_utc=now(),inputs=c['inputs'],outputs=outputs))
  print('Received '+c['id'],flush=True)

def main():
 contract=read(OUT/'Contrato_recepcion.json')
 for x in contract['inputs']:assert sha(x['path'])==x['sha256'],x['path']
 plan=read(BATCH/'plan.json');assert len(plan['cases'])==252
 lock=OUT/'collector.lock'
 with lock.open('x') as f:json.dump(dict(pid=os.getpid(),started_utc=now()),f)
 while True:
  try:
   state=get_status();collect(plan,state);summary=summarize(plan,state)
   print(json.dumps({k:summary[k] for k in ['status','received','complete_dates_both_pollutants']}),flush=True)
   if state['errors']:raise ValueError(str(state['errors']))
   if summary['received']==252:break
  except (ConnectionError,subprocess.TimeoutExpired) as e:save(OUT/'Conexion_receptor.json',dict(status='RETRY_NETWORK',updated_utc=now(),error=str(e)))
  if (OUT/'STOP_COLLECTOR').exists():break
  time.sleep(60)
 lock.rename(OUT/('collector.finished.'+str(time.time_ns())+'.lock'))
if __name__=='__main__':
 try:main()
 except Exception:
  save(OUT/'Fallo_recepcion.json',dict(updated_utc=now(),error=traceback.format_exc()))
  try:halt_dispatch()
  except Exception:save(OUT/'Fallo_detencion.json',dict(updated_utc=now(),error=traceback.format_exc()))
  raise