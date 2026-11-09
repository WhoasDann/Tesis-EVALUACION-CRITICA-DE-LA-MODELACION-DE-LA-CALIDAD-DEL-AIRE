"""Independent native/scientific receipt, common-hour summaries, and bounded storage."""
from pathlib import Path
import sys,os,time,json,subprocess,base64,tarfile,shutil,traceback
import numpy as np,pandas as pd
from campaign import ROOT,OUT,OLD,PILOT,SCENARIOS,read,save,sha,now
sys.path.insert(0,str(OLD/'work'));sys.path.insert(0,str(OLD/'outputs/Biblioteca_Tesis'))
import salidas_estacionales_20261021 as summer
import salidas_invierno_20261026 as winter
CONFIG=read(OUT/'Diseno.json')['seasons']
POINTS={(381128.,6323667.):'Piedra Carvajal',(380148.,6331485.):'Los Bronces',(384254.,6324494.):'Sulfatos',(381759.,6327947.):'La Paloma'}
SSHOPT=['-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','UpdateHostKeys=no','-o','ConnectTimeout=8']
HOSTS={'windows3':'windows3-tesis','rocky':'rocky-tesis'}
checked=set()

def remote(host,code,timeout=35):
 if host=='windows3':
  enc=base64.b64encode(code.encode('utf-16-le')).decode();command='powershell.exe -NoProfile -NonInteractive -EncodedCommand '+enc
 else:command=code
 r=subprocess.run(['ssh','-T']+SSHOPT+[HOSTS[host],command],capture_output=True,text=True,timeout=timeout)
 if r.returncode:raise ConnectionError(r.stderr or r.stdout)
 return r.stdout

def halt_dispatch():
 a=read(OUT/'Reparto.json')
 (OUT/'STOP_AFTER_CURRENT').write_text('Scientific reception or supervisor requires review.\n')
 for h,v in a['hosts'].items():
  if h=='local':(Path(v['root'])/'STOP_AFTER_CURRENT').write_text('Scientific reception requires review.\n')
  elif h=='windows3':remote(h,"[IO.File]::WriteAllText('"+v['root']+"/STOP_AFTER_CURRENT','Scientific reception requires review')")
  else:remote(h,"touch '"+v['root']+"/STOP_AFTER_CURRENT'")

def statuses(assignment):
 states={}
 for h,v in assignment['hosts'].items():
  try:
   if h=='local':st=read(Path(v['root'])/'status.json') if (Path(v['root'])/'status.json').exists() else dict(state='NOT_STARTED',completed=[],active=[],errors={})
   elif h=='windows3':st=json.loads(remote(h,"$p='"+v['root']+"/status.json'; if(Test-Path -LiteralPath $p){Get-Content -Raw -LiteralPath $p}else{'{\"state\":\"NOT_STARTED\",\"completed\":[],\"active\":[],\"errors\":{}}'}"))
   else:
    r=v['root'];cmd="if [ -f '"+r+"/status.json' ]; then cat '"+r+"/status.json'; elif [ -f '"+r+"/handover.json' ]; then cat '"+r+"/handover.json'; else echo '{\"state\":\"NOT_STARTED\",\"completed\":[],\"active\":[],\"errors\":{}}'; fi"
    st=json.loads(remote(h,cmd))
   st['observed_utc']=now();states[h]=st;save(OUT/('Estado_'+h+'.json'),st)
  except (OSError,ConnectionError,subprocess.TimeoutExpired,json.JSONDecodeError) as e:
   states[h]=dict(state='CONNECTION_RETRY',completed=[],active=[],errors={},connection_error=str(e),observed_utc=now())
   save(OUT/('Conexion_'+h+'.json'),states[h])
 return states

def receive(c,plan,assignment,catalog,calendars,members):
 host=c['host'];rp=OUT/'Recibos'/(c['id']+'.json')
 if rp.exists():return False
 if host=='reused':
  source=PILOT/'Recibos'/(c['id']+'.json')
  frozen=next(x for x in read(OUT/'Reutilizacion.json')['cases'] if x['id']==c['id'])
  assert sha(source)==frozen['receipt']['sha256']
  old=read(source);folder=Path(c['result_folder'])
  assert old['status']=='SCIENTIFIC_RECEPTION_PASSED'
  for n,h in old['outputs'].items():
   if (folder/n).exists():assert sha(folder/n)==h
   else:
    import hashlib
    with tarfile.open(old['archive'],'r:gz') as tar:assert hashlib.sha256(tar.extractfile(n).read()).hexdigest()==h
  save(rp,dict(old,host='reused',original_host=old['host'],received_utc=now(),result_folder=str(folder),reused_receipt=str(source),reused_receipt_sha256=sha(source),current_equivalent_inputs=c['inputs']))
  return True
 root=assignment['hosts'][host]['root']
 archive=Path(root)/'exports'/(c['id']+'.tar.gz') if host=='local' else OUT/'Descargas'/(c['id']+'.tar.gz')
 if host!='local' and not archive.exists():
  part=archive.with_suffix('.gz.part')
  r=subprocess.run(['scp']+SSHOPT+[HOSTS[host]+':'+root+'/exports/'+c['id']+'.tar.gz',str(part)],capture_output=True,text=True,timeout=120)
  if r.returncode:raise ConnectionError(r.stderr)
  os.replace(part,archive)
 folder=OUT/'Recepcion'/c['id'];folder.mkdir(parents=True,exist_ok=True)
 allowed={'aermod.out','resumen.sum','errores.out','receptor_horas.out','console.log','execution.json','receipt.json'}
 if len(c['hour_states'])==24:allowed.add('receptor_24h.out')
 with tarfile.open(archive,'r:gz') as tar:
  items=tar.getmembers();assert len(items)==len(allowed) and {m.name for m in items}==allowed
  for m in items:
   assert m.isfile() and m.name==Path(m.name).name and m.size<300*1024**2
   data=tar.extractfile(m).read();dest=folder/m.name
   if dest.exists():assert dest.read_bytes()==data
   else:dest.write_bytes(data)
 native=read(folder/'receipt.json')
 assert native['id']==c['id'] and native['inputs']==c['inputs'] and native['binary_sha256']==plan['binary_sha256']
 for n,h in native['outputs'].items():assert sha(folder/n)==h
 for n,h in c['inputs'].items():
  source=Path(catalog[h]['path'])
  if h not in checked:assert sha(source)==h;checked.add(h)
  if n in ['receptores.inc','aermod.inp','met.SFC','met.PFL']:
   if (folder/n).exists():assert sha(folder/n)==h
   else:shutil.copyfile(source,folder/n)
 full=calendars[c['season']]
 if c['season']=='VERANO':qa,data,*_=summer.receive(folder,full[full.dia.eq(c['day'])],members,receptors=40)
 else:qa,data,*_=winter.receive(folder,full[full.dia_LST.eq(c['day'])],members,full,receptors=40)
 pts=data.groupby(['x_m','y_m']).C_ug_m3.agg(['sum','mean','max','count']).reset_index()
 pts.columns=['x_m','y_m','suma_horaria_ug_m3','media_horas_validas_ug_m3','maximo_1h_ug_m3','horas_validas']
 assert len(pts)==40 and pts.horas_validas.nunique()==1
 pts.to_csv(folder/'Por_receptor.csv',index=False);data.to_csv(folder/'Horario_con_mascara.csv',index=False)
 outputs={**native['outputs'],**{n:sha(folder/n) for n in ['Por_receptor.csv','Horario_con_mascara.csv']}}
 save(rp,dict(status='SCIENTIFIC_RECEPTION_PASSED',id=c['id'],host=host,season=c['season'],day=c['day'],scenario=c['scenario'],pollutant=c['pollutant'],qa=qa,seconds=native['execution']['seconds'],received_utc=now(),inputs=c['inputs'],outputs=outputs,result_folder=str(folder),archive=str(archive),archive_sha256=sha(archive),binary_sha256=native['binary_sha256']))
 # Both products were rehashed against the archive just extracted. Preserve native archive.
 for n in ['aermod.out','errores.out']:
  assert sha(folder/n)==outputs[n];(folder/n).unlink()
 print('Received '+host+' '+c['id'],flush=True);return True

def summarize(cases,states,assignment):
 parts=[];receipts=[]
 for c in cases:
  rp=OUT/'Recibos'/(c['id']+'.json')
  if not rp.exists():continue
  r=read(rp);receipts.append(r);df=pd.read_csv(Path(r['result_folder'])/'Por_receptor.csv')
  for k in ['season','day','scenario','pollutant','host']:df[k]=c[k]
  df['clock']='LST_UTC-4' if c['season']=='INVIERNO' else 'LOCAL_UTC-3';df['target_hours']=len(c['hour_states']);parts.append(df)
 meta=dict(state='COMPLETE_RECEIVED' if len(receipts)==len(cases) else 'RUNNING',updated_utc=now(),received=len(receipts),assigned=len(cases),reused=sum(r['host']=='reused' for r in receipts),total_dates=182,hosts={},limits='Available seasonal windows; common valid hours;40nodes; prescribed ONSITE sensitivity, not calibrated uncertainty. Winter daily operational rows are LST, civil reconstruction is separate.')
 for host,v in assignment['hosts'].items():
  st=states.get(host,{});rr=[r for r in receipts if r['host']==host];remaining=v['assigned']-len(st.get('completed',[]));times=[r['seconds'] for r in rr]
  mean=float(np.mean(times)) if times else None
  meta['hosts'][host]=dict(state=st.get('state','UNKNOWN'),status_time=st.get('updated_utc'),observed_utc=st.get('observed_utc'),assigned=v['assigned'],completed_native=len(st.get('completed',[])),received=len(rr),active=st.get('active',[]),errors=st.get('errors',{}),mean_case_seconds=mean,eta_remaining_hours=remaining*mean/7200 if times else None,eta_range_hours=[remaining*mean/7200*.75,remaining*mean/7200*1.75] if times else None,provisional=len(times)<28,by_season={s:dict(assigned=sum(c['host']==host and c['season']==s for c in cases),received=sum(r['season']==s for r in rr),mean_case_seconds=float(np.mean([r['seconds'] for r in rr if r['season']==s])) if any(r['season']==s for r in rr) else None) for s in CONFIG})
 if parts:
  allpts=pd.concat(parts,ignore_index=True);allpts['receptor']=[POINTS.get((x,y),'Panel') for x,y in zip(allpts.x_m,allpts.y_m)];allpts.to_csv(OUT/'Medias_por_caso_LST.csv',index=False)
  idx=['season','day','pollutant','x_m','y_m'];p=allpts.pivot(index=idx,columns='scenario',values='media_horas_validas_ug_m3').reindex(columns=SCENARIOS)
  full=p.dropna(subset=SCENARIOS).reset_index();full['receptor']=[POINTS.get((x,y),'Panel') for x,y in zip(full.x_m,full.y_m)];full.to_csv(OUT/'Comparaciones_completas_LST.csv',index=False)
  from interaction import contrasts
  contrasts(full).to_csv(OUT/'Interaccion_diaria_LST.csv',index=False)
  cov=full.groupby(['season','day']).pollutant.nunique();complete=cov[cov==2].reset_index()[['season','day']]
  meta['complete_dates_both_pollutants']=len(complete);meta['complete_dates_by_season']={s:int(sum(complete.season==s)) for s in CONFIG}
  paired=[]
  for scenario in SCENARIOS[1:]:
   g=full[idx+['receptor','BASE',scenario]].rename(columns={scenario:'concentracion_ug_m3'}).copy();g['scenario']=scenario;g['delta_ug_m3']=g.concentracion_ug_m3-g.BASE;g['delta_pct']=np.where(g.BASE>0,100*g.delta_ug_m3/g.BASE,np.nan);paired.append(g)
  pd.concat(paired,ignore_index=True).to_csv(OUT/'Diferencias_pareadas_LST.csv',index=False)
  common=allpts.merge(complete,on=['season','day'],validate='many_to_one')
  a=common.groupby(['season','pollutant','scenario','x_m','y_m','receptor']).agg(sum_C=('suma_horaria_ug_m3','sum'),valid_hours=('horas_validas','sum'),days=('day','nunique')).reset_index();a['mean_ug_m3']=a.sum_C/a.valid_hours
  b=a[a.scenario.eq('BASE')][['season','pollutant','x_m','y_m','mean_ug_m3']].rename(columns={'mean_ug_m3':'BASE'})
  a=a.merge(b,on=['season','pollutant','x_m','y_m'],validate='many_to_one');a['delta_ug_m3']=a.mean_ug_m3-a.BASE;a['delta_pct']=np.where(a.BASE>0,100*a.delta_ug_m3/a.BASE,np.nan)
  a.to_csv(OUT/'Resumen_periodo_comparable.csv',index=False);a[a.receptor.ne('Panel')].to_csv(OUT/'Resumen_cuatro_receptores.csv',index=False)
  pp=a.pivot(index=['season','pollutant','x_m','y_m','receptor'],columns='scenario',values='mean_ug_m3').reindex(columns=SCENARIOS).dropna().reset_index()
  contrasts(pp).to_csv(OUT/'Interaccion_periodo_comparable.csv',index=False)
 if any(v.get('errors') or v.get('state') in ['FAILED','FAILED_HANDOVER'] for v in states.values()):meta['state']='FAILED_WORKER'
 save(OUT/'Estado.json',meta)
 return meta

def civil_final(cases,calendars,members):
 rows=[]
 for scenario in SCENARIOS:
  for pol in ['MP10','MP25']:
   selected=[c for c in cases if c['season']=='INVIERNO' and c['scenario']==scenario and c['pollutant']==pol];frames=[]
   for c in selected:
    r=read(OUT/'Recibos'/(c['id']+'.json'));frames.append(pd.read_csv(Path(r['result_folder'])/'Horario_con_mascara.csv',dtype={'fecha_AERMOD':str}))
   pt,_,_=winter.civil_summaries(pd.concat(frames,ignore_index=True),members,calendars['INVIERNO'])
   assert pt.calendario_completo.all() and pt.dia_civil.nunique()==92
   pt['scenario']=scenario;pt['pollutant']=pol;rows.append(pt)
 pd.concat(rows,ignore_index=True).to_csv(OUT/'Invierno_dias_civiles.csv',index=False)

def main():
 assignment=read(OUT/'Reparto.json');cases=read(OUT/'Casos.json')['cases'];catalog=read(OUT/'Catalogo_inputs.json')
 plans={h:read(v['plan']) for h,v in assignment['hosts'].items()}
 for h,v in assignment['hosts'].items():assert sha(v['plan'])==v['plan_sha256']
 for item in read(OUT/'Contrato_recepcion.json')['files']:assert sha(item['path'])==item['sha256']
 calendars={s:pd.read_csv(OUT/'Calendarios'/(s+'.csv')) for s in CONFIG};members=pd.read_csv(OUT/'Comunes/membresia.csv')
 for n in ['Recibos','Descargas','Recepcion']:(OUT/n).mkdir(exist_ok=True)
 lock=OUT/'collector.lock'
 with lock.open('x') as f:json.dump(dict(pid=os.getpid(),started_utc=now()),f)
 last=0
 while True:
  states=statuses(assignment);changed=False
  for c in cases:
   if c['host']=='reused' or c['id'] in states.get(c['host'],{}).get('completed',[]):
    try:changed=receive(c,plans.get(c['host']),assignment,catalog,calendars,members) or changed
    except (ConnectionError,subprocess.TimeoutExpired) as e:save(OUT/'Conexion_recepcion.json',dict(updated_utc=now(),error=str(e)))
  if changed or time.monotonic()-last>240:
   meta=summarize(cases,states,assignment);last=time.monotonic();print(json.dumps(meta),flush=True)
   if meta['state']=='FAILED_WORKER':raise RuntimeError('Worker failure preserved for review')
   if meta['received']==len(cases):
    civil_final(cases,calendars,members);save(OUT/'Cierre.json',dict(meta,civil_calendar='RECONSTRUCTED_AND_VERIFIED'));break
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
