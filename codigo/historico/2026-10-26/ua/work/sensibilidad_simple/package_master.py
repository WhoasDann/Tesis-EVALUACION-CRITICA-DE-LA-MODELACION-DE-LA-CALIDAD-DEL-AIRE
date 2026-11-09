from pathlib import Path
import sys,json,shutil,os,re,zipfile
import numpy as np,pandas as pd
from prepare_sensitivity import ROOT,OUT,OLD,O,CONFIG,SCENARIOS,read,save,sha,rec,now,DAYS
sys.path.insert(0,str(OLD/'outputs/Biblioteca_Tesis'))
from tesis.vinculo_horario import validar_vinculo_horario
BATCH=OUT/'Lotes/master';REMOTE='C:/Users/Daniel/Documents/Tesis_Calculo_20261027'
def main():
 qc=read(OUT/'Verificacion_meteorologia.json');assert qc['status']=='PASSED'
 assert not (BATCH/'plan.json').exists();BATCH.mkdir(parents=True,exist_ok=True);(BATCH/'blobs').mkdir(exist_ok=True)
 shutil.copy2(ROOT/'work/linux_aermod/batch_runner.py',BATCH/'batch_runner.py');shutil.copy2(OUT/'Comunes/membresia.csv',BATCH/'membresia.csv')
 links={};blobs={};proofs=[];binary=O/'BASE_verano_2026-10-21/Binarios/aermod.exe'
 assert sha(binary)=='599b491b021c7ec254ba3a1062386f287e56e54a0d3bb9b67cfa72275d6916da'
 plan=dict(platform='Windows',binary=str(OUT/'Binarios/aermod.exe'),binary_sha256=sha(binary),max_workers=2,scope='Controlled one-factor sensitivity; fixed40point panel; no calibrated uncertainty or full-grid maxima',dependencies={n:sha(BATCH/n) for n in ['batch_runner.py','membresia.csv']},cases=[])
 def put(folder,name,data):
  if isinstance(data,Path):content=data.read_bytes()
  else:content=data.encode('ascii') if isinstance(data,str) else data
  import hashlib
  digest=hashlib.sha256(content).hexdigest();blob=BATCH/'blobs'/digest
  if not blob.exists():blob.write_bytes(content)
  elif blob.stat().st_size!=len(content):raise ValueError('Blob collision')
  dest=folder/name
  if dest.exists():assert sha(dest)==digest
  else:shutil.copyfile(blob,dest)
  rel=dest.relative_to(BATCH).as_posix();links[rel]='blobs/'+digest;blobs['blobs/'+digest]=digest
  return digest
 cached={}
 for season,cfg in CONFIG.items():
  base=Path(cfg['base']);emissions=read(base/'Emisiones.json')['resumen'];metmap={}
  for scenario in SCENARIOS:
   recq=next(q for q in qc['cases'] if q['season']==season and q['scenario']==scenario)
   folder=OUT/'Meteorologia'/season/scenario
   for n,h in recq['files'].items():assert sha(folder/n)==h
   metmap[scenario]={kind:(folder/('met.'+kind)).read_text().splitlines() for kind in ['SFC','PFL']}
  templates={}
  for pol in ['MP10','MP25']:
   if season=='VERANO':src=base/'Lote_estacional/Casos/20161221'/pol
   else:src=base/'Primer_dia_20170621_2026-10-26'/pol
   templates[pol]=(src/'aermod.inp').read_text()
  cached[season]=dict(emissions=emissions,metmap=metmap,templates=templates,mask=pd.read_csv(OUT/'Calendarios'/(season+'.csv')))
 for d in range(DAYS):
  for scenario in SCENARIOS:
   for season,cfg in CONFIG.items():
    day=pd.Timestamp(cfg['start'])+pd.Timedelta(days=d);stamp=day.strftime('%Y%m%d');cache=cached[season];mask=cache['mask'];col='dia' if season=='VERANO' else 'dia_LST';m=mask[mask[col].eq(str(day.date()))];assert len(m)==24
    states={day.strftime('%y%m%d')+f'{h:02}':str(m.iloc[h-1].estado) for h in range(1,25)}
    assert set(states.values())<= {'VALIDA','FALTANTE_AERMET_I71'}
    for pol in ['MP10','MP25']:
     cid=f'{season}_{stamp}_{scenario}_{pol}';folder=BATCH/'Casos'/cid;folder.mkdir(parents=True,exist_ok=True)
     meta=next(x for x in cache['emissions'][pol]['archivos'] if Path(x['path']).parent.name==stamp);src=Path(meta['path']);assert meta['horas']==24 and sha(src)==meta['sha256']
     inp=cache['templates'][pol];inp=re.sub(r'CO TITLEONE.*',f'CO TITLEONE One-factor sensitivity {season} {stamp} {scenario} panel40',inp);inp=re.sub(r'ME STARTEND.*',f'ME STARTEND {day:%Y %m %d} 1 {day:%Y %m %d} 24',inp)
     for key in ['SURFDATA','UAIRDATA','SITEDATA']:inp=re.sub(r'(ME '+key+r'\s+\d+)\s+\d+',lambda mt:mt[1]+' '+str(day.year),inp)
     assert 'CO RUNORNOT RUN' in inp and inp.count('OU POSTFILE 24 ALL PLOT receptor_24h.out')==1
     inputs={'aermod.inp':put(folder,'aermod.inp',inp),pol+'.emi':put(folder,pol+'.emi',src),'fuentes_aermod.inc':put(folder,'fuentes_aermod.inc',O/'BASE_verano_2026-10-21/Comunes/fuentes_aermod.inc'),'receptores.inc':put(folder,'receptores.inc',OUT/'Comunes/receptores.inc')}
     for kind in ['SFC','PFL']:
      raw=cache['metmap'][scenario][kind];selected=[l for l in (raw[1:] if kind=='SFC' else raw) if tuple(map(int,l.split()[:3]))==(day.year,day.month,day.day)]
      assert len(selected)==24*(1 if kind=='SFC' else 29)
      data='\n'.join((raw[:1] if kind=='SFC' else [])+selected)+'\n';inputs['met.'+kind]=put(folder,'met.'+kind,data)
     if scenario=='BASE':
      binding=validar_vinculo_horario(folder/'aermod.inp',folder/'fuentes_aermod.inc',folder/(pol+'.emi'),{(day.year%100,day.month,day.day,h) for h in range(1,25)})
      proofs.append(dict(season=season,day=str(day.date()),pollutant=pol,source=meta,binding=binding))
     plan['cases'].append(dict(id=cid,day=str(day.date()),season=season,scenario=scenario,pollutant=pol,folder=folder.relative_to(BATCH).as_posix(),sources=12263,receptors=40,hour_states=states,inputs=inputs))
   print('Prepared day-position '+str(d+1)+' '+scenario,flush=True)
 assert len(plan['cases'])==DAYS*28
 save(BATCH/'plan.json',plan);save(BATCH/'materialization.json',dict(blobs=blobs,links=links,case_count=DAYS*28))
 installer='''from pathlib import Path
import json,hashlib,os,shutil
root=Path(__file__).resolve().parent
m=json.loads((root/'materialization.json').read_text())
def safe(rel):
 p=(root/rel).resolve()
 assert p.is_relative_to(root) and p!=root
 return p
for rel,h in m['blobs'].items():assert hashlib.sha256(safe(rel).read_bytes()).hexdigest()==h,rel
for rel,src in m['links'].items():
 p=safe(rel);p.parent.mkdir(parents=True,exist_ok=True);assert not p.exists(),rel
 try:os.link(safe(src),p)
 except PermissionError:shutil.copyfile(safe(src),p)
p=json.loads((root/'plan.json').read_text())
for c in p['cases']:
 for n,h in c['inputs'].items():assert hashlib.sha256(safe(c['folder']+'/'+n).read_bytes()).hexdigest()==h
(root/'Materialized.json').write_text(json.dumps({'verified_cases':len(p['cases']),'links':len(m['links']),'unique_blobs':len(m['blobs'])}))
print('Verified cases',len(p['cases']))
'''
 (BATCH/'materialize.py').write_text(installer,encoding='utf-8')
 save(OUT/'Emisiones_verificadas.json',proofs)
 print('Prepared master',len(plan['cases']),flush=True)
if __name__=='__main__':main()

