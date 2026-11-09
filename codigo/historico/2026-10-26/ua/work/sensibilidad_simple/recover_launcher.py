from pathlib import Path
import shutil,json
from prepare_sensitivity import *
root=OUT/'Lotes/master';s=read(root/'status.json')
assert not s['completed'] and len(s['active'])==2
backup=OUT/'Intento_lanzador_01';assert not backup.exists();backup.mkdir()
plan=read(root/'plan_local.json')
for a in s['active']:
 c=next(x for x in plan['cases'] if x['id']==a['id']);folder=root/c['folder']
 for n,h in c['inputs'].items():assert sha(folder/n)==h
 dest=backup/c['id'];dest.mkdir()
 for p in folder.iterdir():
  if p.name not in c['inputs']:shutil.move(str(p),str(dest/p.name))
shutil.move(str(root/'run.lock'),str(backup/'run.lock'))
shutil.move(str(root/'status.json'),str(backup/'status.json'))
for n in ['local.stdout.log','local.stderr.log','collector.stdout.log','collector.stderr.log']:
 p=OUT/n
 if p.exists():shutil.move(str(p),str(backup/n))
assert not (OUT/'collector.lock').exists()
save(backup/'Registro.json',dict(updated_utc=now(),reason='Launcher shell exited and its detached children disappeared. Verified PIDs absent before preserving two incomplete attempts. No successful cases existed. Foreground persistent exec session used for new supervisor.',previous=s))
print('Preserved two incomplete attempts, no validated result replaced')

