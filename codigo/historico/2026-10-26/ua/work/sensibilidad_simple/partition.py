from pathlib import Path
import json,zipfile,shutil,sys
from prepare_sensitivity import *
MASTER=OUT/'Lotes/master'
REMOTE_ROOT='C:/Users/Daniel/Documents/Tesis_Calculo_20261027'
REMOTE=REMOTE_ROOT+'/jobs/sensitivity_20261029/panel'
def main():
 p=read(MASTER/'plan.json');mat=read(MASTER/'materialization.json')
 assert len(p['cases'])==420
 hosts={}
 for key,ix in [('local',0),('windows3',1)]:
  cases=[c for c in p['cases'] if ((pd.Timestamp(c['day'])-pd.Timestamp(CONFIG[c['season']]['start'])).days+list(CONFIG).index(c['season']))%2==ix]
  assert len(cases)==210
  pp=dict(p,cases=cases)
  if key=='windows3':pp['binary']=REMOTE_ROOT+'/bin/aermod.exe'
  save(MASTER/('plan_'+key+'.json'),pp)
  hosts[key]=dict(plan=str(MASTER/('plan_'+key+'.json')),root=str(MASTER) if key=='local' else REMOTE,plan_sha256=sha(MASTER/('plan_'+key+'.json')),assigned=210)
 local_ids={c['id'] for c in read(hosts['local']['plan'])['cases']}
 remote_ids={c['id'] for c in read(hosts['windows3']['plan'])['cases']}
 assert not (local_ids & remote_ids) and local_ids|remote_ids=={c['id'] for c in p['cases']}
 selected=read(hosts['windows3']['plan'])['cases'];prefixes={c['folder'] for c in selected}
 links={k:v for k,v in mat['links'].items() if str(Path(k).parent).replace('\\','/') in prefixes}
 blobs={v:mat['blobs'][v] for v in set(links.values())}
 dest=OUT/'Paquete_windows3';dest.mkdir()
 for name in ['batch_runner.py','membresia.csv','materialize.py']:shutil.copy2(MASTER/name,dest/name)
 shutil.copy2(MASTER/'plan_windows3.json',dest/'plan.json')
 save(dest/'materialization.json',dict(blobs=blobs,links=links,case_count=210))
 with zipfile.ZipFile(OUT/'windows3.zip','w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
  for f in dest.iterdir():z.write(f,f.name)
  for rel in blobs:z.write(MASTER/rel,rel)
 save(OUT/'Reparto.json',dict(created_utc=now(),hosts=hosts,linux='Existing full6295receptor BASE queue remains running. No pilot assigned.',case_ids_disjoint=True,remote_archive=rec(OUT/'windows3.zip')))
 save(OUT/'job_windows3.json',dict(kind='aermod_batch',folder='jobs/sensitivity_20261029/launch',plan='jobs/sensitivity_20261029/panel/plan.json',plan_sha256=sha(dest/'plan.json'),runner_sha256=sha(dest/'batch_runner.py')))
 print(json.dumps(dict(local=210,windows3=210,zip_bytes=(OUT/'windows3.zip').stat().st_size)),flush=True)
if __name__=='__main__':main()

