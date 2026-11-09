"""Freeze shared inputs, prove pilot reuse, and partition whole days exclusively."""
from pathlib import Path
import sys,json,re,hashlib,shutil,zipfile,copy
import pandas as pd
from campaign import ROOT,OUT,OLD,O,PILOT,SCENARIOS,read,save,sha,now,rec
sys.path.insert(0,str(OLD/'outputs/Biblioteca_Tesis'))
from tesis.vinculo_horario import validar_vinculo_horario
CONFIG=read(OUT/'Diseno.json')['seasons']
WINROOT='C:/Users/Daniel/Documents/Tesis_Calculo_20261027'
ROCKROOT='/home/usuario/tesis_aermod_20261026'
REMOTE={'windows3':WINROOT+'/jobs/seasonal_20261029','rocky':ROCKROOT+'/seasonal_20261029'}
LINUXSHA='e7b921d9b845cb440601300ad0af932c4ae9196be8fc12e803d55f4b0537cdb0'

def normalized(text):return re.sub(r'CO TITLEONE.*','CO TITLEONE TITLE',text).split()

def main():
 assert read(OUT/'Verificacion_meteorologia.json')['status']=='PASSED'
 assert not (OUT/'Reparto.json').exists(),'Existing frozen assignment'
 (OUT/'Inputs').mkdir(exist_ok=True);(OUT/'Lotes').mkdir(exist_ok=True)
 catalog={};cases=[];reused=[];proofs=[];hashcache={}
 def put(value):
  if isinstance(value,Path):
   p=value.resolve();key=str(p)
   if key not in hashcache:hashcache[key]=sha(p)
   h=hashcache[key]
  else:
   data=value.encode('ascii') if isinstance(value,str) else value
   h=hashlib.sha256(data).hexdigest();p=OUT/'Inputs'/h
   if not p.exists():p.write_bytes(data)
   else:assert sha(p)==h
  catalog.setdefault(h,dict(path=str(p),bytes=p.stat().st_size))
  return h
 pilotplan=read(PILOT/'Lotes/master/plan.json');prior={c['id']:c for c in pilotplan['cases']}
 source=O/'BASE_verano_2026-10-21/Comunes/fuentes_aermod.inc'
 common={'fuentes_aermod.inc':put(source),'receptores.inc':put(OUT/'Comunes/receptores.inc')}
 for season,cfg in CONFIG.items():
  base=Path(cfg['base']);emissions=read(base/'Emisiones.json')['resumen'];mask=pd.read_csv(OUT/'Calendarios'/(season+'.csv'))
  met={s:{k:(OUT/'Meteorologia'/season/s/('met.'+k)).read_text().splitlines() for k in ['SFC','PFL']} for s in SCENARIOS}
  templates={p:(base/('Lote_estacional/Casos/20161221' if season=='VERANO' else 'Primer_dia_20170621_2026-10-26')/p/'aermod.inp').read_text() for p in ['MP10','MP25']}
  for day in pd.date_range(cfg['start'],cfg['end']):
   stamp=day.strftime('%Y%m%d');date=str(day.date());col='dia' if season=='VERANO' else 'dia_LST';m=mask[mask[col].eq(date)]
   end=pd.to_datetime(m['fin_local' if season=='VERANO' else 'fin_LST']);hours=end.dt.hour.replace(0,24).tolist()
   assert hours==list(range(1,len(m)+1)) and len(m) in [17,23,24]
   states={day.strftime('%y%m%d')+f'{h:02}':str(state) for h,state in zip(hours,m.estado)}
   emission_inputs={}
   for pol in ['MP10','MP25']:
    meta=next(x for x in emissions[pol]['archivos'] if Path(x['path']).parent.name==stamp);src=Path(meta['path'])
    assert meta['horas']==len(hours);h=put(src);assert h==meta['sha256'];emission_inputs[pol]=h
    binding=validar_vinculo_horario(Path(catalog[put(templates[pol])]['path']),source,src,{(day.year%100,day.month,day.day,hour) for hour in hours})
    proofs.append(dict(season=season,day=date,pollutant=pol,source=meta,binding=binding))
   daily=[]
   for scenario in SCENARIOS:
    mi={}
    for kind in ['SFC','PFL']:
     raw=met[scenario][kind]
     rows=[l for l in (raw[1:] if kind=='SFC' else raw) if tuple(map(int,l.split()[:3]))==(day.year,day.month,day.day) and int(l.split()[4 if kind=='SFC' else 3]) in hours]
     assert len(rows)==len(hours)*(1 if kind=='SFC' else 29)
     mi['met.'+kind]=put('\n'.join((raw[:1] if kind=='SFC' else [])+rows)+'\n')
    for pol in ['MP10','MP25']:
     inp=re.sub(r'CO TITLEONE.*',f'CO TITLEONE Seasonal OAT {season} {stamp} {scenario} panel40',templates[pol])
     inp=re.sub(r'ME STARTEND.*',f'ME STARTEND {day:%Y %m %d} 1 {day:%Y %m %d} {max(hours)}',inp)
     for key in ['SURFDATA','UAIRDATA','SITEDATA']:inp=re.sub(r'(ME '+key+r'\s+\d+)\s+\d+',lambda mt:mt[1]+' '+str(day.year),inp)
     if len(hours)<24:inp=re.sub(r'^OU POSTFILE 24 ALL PLOT receptor_24h.out\s*\n','',inp,flags=re.M)
     inputs={**common,**mi,pol+'.emi':emission_inputs[pol],'aermod.inp':put(inp)}
     cid=f'{season}_{stamp}_{scenario}_{pol}'
     c=dict(id=cid,day=date,season=season,scenario=scenario,pollutant=pol,folder='Casos/'+cid,sources=12263,receptors=40,hour_states=states,inputs=inputs)
     if cid in prior and not (season=='VERANO' and date=='2017-02-01'):
      old=prior[cid];folder=PILOT/'Lotes/master'/old['folder'];receipt=PILOT/'Recibos'/(cid+'.json');r=read(receipt)
      assert r['status']=='SCIENTIFIC_RECEPTION_PASSED' and old['hour_states']==states and r['inputs']==old['inputs']
      eq={n:h==old['inputs'][n] for n,h in inputs.items() if n!='aermod.inp'}
      assert all(eq.values()),(cid,eq)
      assert sha(folder/'aermod.inp')==old['inputs']['aermod.inp'] and normalized(inp)==normalized((folder/'aermod.inp').read_text())
      for n,h in r['outputs'].items():assert sha(folder/n)==h,(cid,n)
      c['host']='reused';c['result_folder']=str(folder)
      reused.append(dict(id=cid,pilot_receipt=rec(receipt),original_host=r['host'],all_non_title_inputs_identical=True,all_products_rehashed=True))
     daily.append(c)
   cases+=daily
   print('Verified '+season+' '+date,flush=True)
 assert len(cases)==2548 and len(reused)==406
 # Assign all configurations of a date to one platform; balance season counts.
 weights={'local':.40,'rocky':.35,'windows3':.25};counts={s:{h:0 for h in weights} for s in CONFIG}
 days=sorted({(c['season'],c['day']) for c in cases if c.get('host')!='reused'},key=lambda x:(x[1],x[0]))
 forced={('VERANO','2017-03-20'):'local',('INVIERNO','2017-08-14'):'local',('INVIERNO','2017-09-20'):'windows3'}
 assignments={}
 for season,day in days:
  host=forced.get((season,day)) or min(weights,key=lambda h:counts[season][h]/weights[h])
  counts[season][host]+=1;assignments[season,day]=host
 for c in cases:
  if c.get('host')!='reused':c['host']=assignments[c['season'],c['day']]
 binary=OUT/'Binarios/aermod.exe';hosts={}
 for host in weights:
  target=OUT/'Lotes'/host;target.mkdir(exist_ok=True)
  for name,src in [('batch_runner.py',ROOT/'work/sensibilidad_estacional/batch_runner.py'),('membresia.csv',OUT/'Comunes/membresia.csv')]:shutil.copy2(src,target/name)
  root=str(target) if host=='local' else REMOTE[host]
  selected=[copy.deepcopy(c) for c in cases if c['host']==host]
  selected.sort(key=lambda c:(0 if (c['season'],c['day']) in forced else 1,(pd.Timestamp(c['day'])-pd.Timestamp(CONFIG[c['season']]['start'])).days,c['season'],SCENARIOS.index(c['scenario']),c['pollutant']))
  for c in selected:c['input_sources']={n:catalog[h]['path'] if host=='local' else root+'/blobs/'+h for n,h in c['inputs'].items()}
  plan=dict(platform='Linux' if host=='rocky' else 'Windows',binary=str(binary) if host=='local' else (ROCKROOT+'/bin/aermod_26135' if host=='rocky' else WINROOT+'/bin/aermod.exe'),binary_sha256=LINUXSHA if host=='rocky' else sha(binary),max_workers=2,allowed_input_roots=[str(O),str(OUT),'D:/Tesis_Dan/BASE_invierno_2026-10-24/Emisiones'] if host=='local' else [root+'/blobs'],dependencies={n:sha(target/n) for n in ['batch_runner.py','membresia.csv']},cases=selected)
  save(target/'plan.json',plan);hosts[host]=dict(root=root,plan=str(target/'plan.json'),plan_sha256=sha(target/'plan.json'),assigned=len(selected),days_by_season={s:counts[s][host] for s in CONFIG})
 # Eight native cross-platform canaries on independently received Windows results.
 target=OUT/'Lotes/canary';target.mkdir(exist_ok=True);canary=[];remote=REMOTE['rocky']+'/canary'
 for c in cases:
  if c['day'] not in ['2017-02-11','2017-08-02'] or c['scenario'] not in ['BASE','U_PLUS']:continue
  assert c['host']=='reused';old=prior[c['id']];folder=PILOT/'Lotes/master'/old['folder'];cc=copy.deepcopy(old)
  cc['id']='CHECK_'+cc['id'];cc['folder']='Casos/'+cc['id'];cc['cross_platform_canary']=True
  for n,h in cc['inputs'].items():assert put(folder/n)==h
  cc['inputs']['reference.out']=put(folder/'receptor_horas.out')
  cc['input_sources']={n:REMOTE['rocky']+'/blobs/'+h for n,h in cc['inputs'].items()};canary.append(cc)
 assert len(canary)==8
 pp=read(OUT/'Lotes/rocky/plan.json');pp.update(cases=canary,dependencies={})
 save(target/'plan.json',pp)
 save(OUT/'Catalogo_inputs.json',catalog);save(OUT/'Casos.json',dict(cases=cases));save(OUT/'Reutilizacion_piloto.json',dict(status='PASSED',count=len(reused),excluded_day='2017-02-01',reason='Extending perturbations to preceding days changes AERMET mixing height in early hours of U/V variants. Recompute all14cases of that day for coherent whole-day comparisons.',cases=reused))
 save(OUT/'Vinculo_emisiones.json',dict(status='PASSED',cases=proofs))
 for host in ['windows3','rocky']:
  selected=read(OUT/'Lotes'/host/'plan.json')['cases']+(canary if host=='rocky' else [])
  hashes={h for c in selected for h in c['inputs'].values()}
  archive=OUT/(host+'.zip')
  with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
   for f in (OUT/'Lotes'/host).iterdir():z.write(f,f.name)
   if host=='rocky':z.write(target/'plan.json','canary/plan.json')
   for h in sorted(hashes):z.write(catalog[h]['path'],'blobs/'+h)
  hosts[host]['archive']=rec(archive);hosts[host]['unique_input_bytes']=sum(catalog[h]['bytes'] for h in hashes)
 allids=[c['id'] for c in cases];assert len(set(allids))==2548 and sum(h['assigned'] for h in hosts.values())+406==2548
 save(OUT/'Reparto.json',dict(created_utc=now(),hosts=hosts,total=2548,reused=406,new=2142,canaries=8,exclusive_whole_days=True,day_weights=weights,assumption='Provisional workload weights, not controlled machine-speed benchmark'))
 print(json.dumps(read(OUT/'Reparto.json')),flush=True)

if __name__=='__main__':main()
