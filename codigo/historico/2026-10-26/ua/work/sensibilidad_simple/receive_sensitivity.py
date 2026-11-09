"""Continuous independent reception of the two disjoint Windows sensitivity batches."""
from pathlib import Path
import sys,subprocess,json,tarfile,shutil,time,traceback,os,base64
import numpy as np,pandas as pd
from prepare_sensitivity import ROOT,OUT,OLD,CONFIG,SCENARIOS,read,save,sha,rec,now,DAYS
sys.path.insert(0,str(OLD/'work'))
sys.path.insert(0,str(OLD/'outputs/Biblioteca_Tesis'))
import salidas_estacionales_20261021 as summer
import salidas_invierno_20261026 as winter
MASTER=OUT/'Lotes/master'
REMOTE='C:/Users/Daniel/Documents/Tesis_Calculo_20261027/jobs/sensitivity_20261029/panel'
SSH=['ssh','-T','-o','BatchMode=yes','-o','UpdateHostKeys=no','-o','ConnectTimeout=8','windows3-tesis']
POINTS={(381128.,6323667.):'Piedra Carvajal',(380148.,6331485.):'Los Bronces',(384254.,6324494.):'Sulfatos',(381759.,6327947.):'La Paloma'}
def halt_dispatch():
 (MASTER/'STOP_AFTER_CURRENT').write_text('Independent reception failed; review before new dispatch.\n')
 script="[IO.File]::WriteAllText('"+REMOTE+"/STOP_AFTER_CURRENT','Independent reception requires review')"
 enc=base64.b64encode(script.encode('utf-16-le')).decode()
 subprocess.run(SSH+['powershell.exe -NoProfile -NonInteractive -EncodedCommand '+enc],capture_output=True,timeout=30,check=True)
def statuses():
 states={}
 if (MASTER/'status.json').exists():states['local']=read(MASTER/'status.json')
 try:
  r=subprocess.run(SSH+['type '+REMOTE.replace('/','\\')+'\\status.json'],capture_output=True,text=True,timeout=35)
  if r.returncode:raise ConnectionError(r.stderr[-1000:])
  states['windows3']=json.loads(r.stdout);save(OUT/'Estado_windows3.json',states['windows3'])
 except (ConnectionError,subprocess.TimeoutExpired,json.JSONDecodeError) as e:
  save(OUT/'Conexion.json',dict(updated_utc=now(),state='RETRY',error=str(e)))
 return states
def collect(c,plan,host):
 rp=OUT/'Recibos'/(c['id']+'.json')
 if rp.exists():return False
 folder=MASTER/c['folder']
 if host=='windows3':
  archive=OUT/'Descargas'/(c['id']+'.tar.gz')
  r=subprocess.run(['scp','-o','BatchMode=yes','-o','UpdateHostKeys=no','-o','ConnectTimeout=8','windows3-tesis:'+REMOTE+'/exports/'+c['id']+'.tar.gz',str(archive)],capture_output=True,text=True,timeout=120)
  if r.returncode:raise ConnectionError(r.stderr)
  allowed={'aermod.out','resumen.sum','errores.out','receptor_horas.out','receptor_24h.out','console.log','execution.json','receipt.json'}
  with tarfile.open(archive,'r:gz') as tar:
   files=tar.getmembers();assert len(files)==len(allowed) and {x.name for x in files}==allowed
   for item in files:
    assert item.isfile() and item.name==Path(item.name).name and item.size<300*1024**2
    dest=folder/item.name
    content=tar.extractfile(item).read()
    if dest.exists():assert dest.read_bytes()==content
    else:dest.write_bytes(content)
 native=read(folder/'receipt.json')
 assert native['id']==c['id'] and native['inputs']==c['inputs'] and native['binary_sha256']==plan['binary_sha256']
 for n,h in {**native['outputs'],**c['inputs']}.items():assert sha(folder/n)==h,n
 cfg=CONFIG[c['season']];full=pd.read_csv(Path(cfg['base'])/cfg['qc']/'Cobertura_horaria.csv');members=pd.read_csv(MASTER/'membresia.csv')
 if c['season']=='VERANO':
  mask=full.loc[full.dia.eq(c['day'])];qa,data,*_=summer.receive(folder,mask,members,receptors=40)
 else:
  mask=full.loc[full.dia_LST.eq(c['day'])];qa,data,*_=winter.receive(folder,mask,members,full,receptors=40)
 if c['scenario']=='BASE':
  oldroot=ROOT/'outputs/Piloto_conjunto_14dias_2026-10-27'
  oldreceipt=oldroot/'Recibos'/(c['id']+'.json')
  if oldreceipt.exists():
   oldfolder=oldroot/'Lotes/panel'/c['folder'];previous=read(oldreceipt)
   assert sha(oldfolder/'receptor_horas.out')==previous['outputs']['receptor_horas.out']
   previous_hourly=summer.postfile(oldfolder/'receptor_horas.out')
   new_hourly=summer.postfile(folder/'receptor_horas.out')
   pd.testing.assert_frame_equal(previous_hourly,new_hourly,check_exact=True)
   qa['BASE_matches_previous_pilot_all_hourly_values']=True
 grouped=data.groupby(['x_m','y_m']).C_ug_m3.agg(['sum','mean','max','count']).reset_index()
 grouped.columns=['x_m','y_m','suma_horaria_ug_m3','media_horas_validas_ug_m3','maximo_1h_ug_m3','horas_validas']
 assert len(grouped)==40 and grouped.horas_validas.nunique()==1
 grouped.to_csv(folder/'Por_receptor.csv',index=False);data.to_csv(folder/'Horario_con_mascara.csv',index=False)
 outputs={**native['outputs'],**{n:sha(folder/n) for n in ['Por_receptor.csv','Horario_con_mascara.csv']}}
 save(rp,dict(status='SCIENTIFIC_RECEPTION_PASSED',id=c['id'],host=host,season=c['season'],day=c['day'],scenario=c['scenario'],pollutant=c['pollutant'],qa=qa,seconds=native['execution']['seconds'],received_utc=now(),inputs=c['inputs'],outputs=outputs))
 print('Received '+host+' '+c['id'],flush=True);return True
def summarize(plans,states):
 receipts=[];parts=[]
 for host,plan in plans.items():
  for c in plan['cases']:
   rp=OUT/'Recibos'/(c['id']+'.json')
   if not rp.exists():continue
   r=read(rp);receipts.append(r);df=pd.read_csv(MASTER/c['folder']/'Por_receptor.csv')
   for key in ['season','day','scenario','pollutant']:df[key]=c[key]
   df['host']=host;parts.append(df)
 meta=dict(state='COMPLETE_RECEIVED' if len(receipts)==420 else 'RUNNING',updated_utc=now(),received=len(receipts),assigned=420,complete_dates_both_pollutants=0,total_dates=30,hosts={},scope='15days/season; controlled OAT sensitivity;40points; no calibrated uncertainty or full-season inference')
 for host,plan in plans.items():
  rr=[r for r in receipts if r['host']==host];st=states.get(host,{})
  done=len(st.get('completed',[]));remaining=210-done;times=[r['seconds'] for r in rr]
  etah=remaining*np.mean(times)/7200*1.25 if times else None
  meta['hosts'][host]=dict(state=st.get('state','UNKNOWN'),status_time=st.get('updated_utc'),completed_native=done,received=len(rr),active=st.get('active',[]),errors=st.get('errors',{}),mean_case_seconds=float(np.mean(times)) if times else None,eta_remaining_hours_with25pct_margin=float(etah) if etah is not None else None,eta_provisional=len(times)<8)
 full=pd.DataFrame();aggregates=pd.DataFrame()
 if parts:
  allpoints=pd.concat(parts,ignore_index=True);allpoints.to_csv(OUT/'Medias_por_caso.csv',index=False)
  idx=['season','day','pollutant','x_m','y_m']
  p=allpoints.pivot(index=idx,columns='scenario',values='media_horas_validas_ug_m3').reindex(columns=SCENARIOS)
  full=p.dropna(subset=SCENARIOS).reset_index();full['receptor']=[POINTS.get((x,y),'Panel') for x,y in zip(full.x_m,full.y_m)]
  full.to_csv(OUT/'Comparaciones_completas.csv',index=False)
  if len(full):
   cov=full.groupby(['season','day']).pollutant.nunique();meta['complete_dates_both_pollutants']=int((cov==2).sum())
   meta['complete_dates_by_season']={s:int(sum(cov.loc[s]==2)) if s in cov.index.get_level_values(0) else 0 for s in CONFIG}
   paired=[]
   for scenario in SCENARIOS[1:]:
    g=full[idx+['receptor','BASE',scenario]].rename(columns={scenario:'concentracion_ug_m3'}).copy();g['scenario']=scenario
    g['delta_ug_m3']=g.concentracion_ug_m3-g.BASE;g['delta_pct']=np.where(g.BASE>0,100*g.delta_ug_m3/g.BASE,np.nan);paired.append(g)
   comparison=pd.concat(paired,ignore_index=True);comparison.to_csv(OUT/'Diferencias_pareadas.csv',index=False)
   # Aggregate only complete dates with both pollutants, all7configs, common valid-hour weighting.
   complete=cov[cov==2].reset_index()[['season','day']]
   complete_points=allpoints.merge(complete,on=['season','day'],validate='many_to_one')
   a=complete_points.groupby(['season','pollutant','scenario','x_m','y_m']).agg(sum_C=('suma_horaria_ug_m3','sum'),valid_hours=('horas_validas','sum'),days=('day','nunique')).reset_index()
   a['mean_ug_m3']=a.sum_C/a.valid_hours;a['receptor']=[POINTS.get((x,y),'Panel') for x,y in zip(a.x_m,a.y_m)]
   b=a[a.scenario.eq('BASE')][['season','pollutant','x_m','y_m','mean_ug_m3']].rename(columns={'mean_ug_m3':'BASE'})
   aggregates=a.merge(b,on=['season','pollutant','x_m','y_m'],validate='many_to_one');aggregates['delta_ug_m3']=aggregates.mean_ug_m3-aggregates.BASE
   aggregates['delta_pct']=np.where(aggregates.BASE>0,100*aggregates.delta_ug_m3/aggregates.BASE,np.nan)
   aggregates.to_csv(OUT/'Resumen_periodo_comparable.csv',index=False)
   aggregates[aggregates.receptor.ne('Panel')].to_csv(OUT/'Resumen_cuatro_receptores.csv',index=False)
  base=allpoints[allpoints.scenario.eq('BASE')].copy();base['receptor']=[POINTS.get((x,y),'Panel') for x,y in zip(base.x_m,base.y_m)]
  records=[]
  for keys,g in base.groupby(['season','pollutant','x_m','y_m','receptor']):
   x=g.media_horas_validas_ug_m3;imax=x.idxmax();records.append(dict(zip(['season','pollutant','x_m','y_m','receptor'],keys),days=len(x),mean_daily=x.mean(),median=x.median(),sd_days=x.std(ddof=1),P25=x.quantile(.25),P75=x.quantile(.75),P90_descriptive=x.quantile(.9),minimum=x.min(),maximum=x.max(),date_max=g.loc[imax,'day']))
  pd.DataFrame(records).to_csv(OUT/'Variabilidad_diaria_BASE.csv',index=False)
 if any(v.get('errors') for v in states.values()):meta['state']='FAILED_WORKER'
 save(OUT/'Estado.json',meta)
 lines=['# Piloto de sensibilidad simple','',f"Actualizado UTC: {meta['updated_utc']}. Recibidos y verificados: {len(receipts)}/420.",f"Fechas con todas las configuraciones y ambos contaminantes: {meta['complete_dates_both_pollutants']}/30.",'',
 '15 días de verano (1–15 febrero de2017) y15 deinvierno (25julio–8agosto de2017).40nodos incluyen los4puntos sensibles. Este período es ilustrativo; no representa las temporadas completas.',
 'Siete configuraciones: BASE,T−,T+,u−,u+,v−,v+. Una variable modificada por vez; emisiones y receptores fijos.',
 'Amplitudes: verano T±0,953°C,u±1,780m/s,v±4,531m/s; invierno T±1,586°C,u±3,541m/s,v±6,725m/s. SD de discrepancias medias diarias del ajuste, sin corregir sesgo.',
 'Se modifica ONSITE (salida MMIF) y se regenera AERMET. Perfil atenuado hasta PBL BASE; RH y parámetros auxiliares retenidos. No se afirma equivalencia a modificar wrfout ni equilibrio atmosférico dinámico.',
 'Resultados: aporte modelado, µg/m³; medias de horas válidas. Una hora faltante en verano se conserva en todas las variantes. Rango de sensibilidad, no intervalo de confianza ni escenario legal más desfavorable.',
 'Los resúmenes agregados usan únicamente días con todas las configuraciones y ambos contaminantes; no comparar medias de distintos días. P90 de15días es descriptivo e inestable.','']
 if len(aggregates):
  lines+=['| Temporada | Contaminante | Receptor | Días | Caso | Media | BASE | Cambio % |','|---|---|---|---:|---|---:|---:|---:|']
  for r in aggregates[aggregates.receptor.ne('Panel')].itertuples():
   lines.append(f'|{r.season}|{r.pollutant}|{r.receptor}|{r.days}|{r.scenario}|{r.mean_ug_m3:.3f}|{r.BASE:.3f}|{r.delta_pct:.2f}|')
 (OUT/'Resultados.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 if len(receipts)==420:save(OUT/'Cierre.json',meta)
 return meta
def main():
 contract=read(OUT/'Contrato_recepcion.json')
 for x in contract['inputs']:assert sha(x['path'])==x['sha256'],x['path']
 plans={h:read(MASTER/('plan_'+h+'.json')) for h in ['local','windows3']}
 for n in ['Recibos','Descargas']:(OUT/n).mkdir(exist_ok=True)
 lock=OUT/'collector.lock'
 with lock.open('x') as f:json.dump(dict(pid=os.getpid(),started_utc=now()),f)
 while True:
  states=statuses();changed=False
  for host,st in states.items():
   try:
    for c in plans[host]['cases']:
     if c['id'] in st['completed']:changed=collect(c,plans[host],host) or changed
   except (ConnectionError,subprocess.TimeoutExpired) as e:save(OUT/'Conexion_receptor.json',dict(updated_utc=now(),error=str(e)))
  meta=summarize(plans,states);print(json.dumps(meta),flush=True)
  if any(st['errors'] for st in states.values()):raise RuntimeError('Worker failed; preserve all attempts')
  if meta['received']==420:break
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
