"""Preserve the pre-execution path-guard failure; authorize only frozen winter emission root."""
from pathlib import Path
import shutil,json,sys
from campaign import ROOT,OUT,read,save,sha,now,rec
def main():
 closed=read(OUT/'Supervisor_cierre.json');assert closed['exit_codes']=={'local':1,'collector':1}
 p=OUT/'Lotes/local/plan.json';plan=read(p);st=read(p.parent/'status.json')
 assert st['state']=='FAILED' and not st['active'] and not (p.parent/'run.lock').exists()
 assert set(st['errors'])=={'INVIERNO_20170814_BASE_MP10','INVIERNO_20170814_BASE_MP25'}
 assert all('Input source outside frozen roots' in e for e in st['errors'].values())
 backup=OUT/'Intentos/01_ruta_emisiones';backup.mkdir(parents=True,exist_ok=False)
 def bounded(path):
  x=Path(path).resolve();assert x.is_relative_to(OUT.resolve()) and x!=OUT.resolve();return x
 def preserve(path,move=False):
  src=bounded(path);dst=bounded(backup/src.relative_to(OUT.resolve()));dst.parent.mkdir(parents=True,exist_ok=True)
  if move:src.rename(dst)
  else:shutil.copy2(src,dst)
 for path in [p,OUT/'Reparto.json',OUT/'Contrato_recepcion.json',OUT/'Checkpoint_arranque.json',OUT/'Seguimiento_avisos.json']:preserve(path)
 emission_root=Path('D:/Tesis_Dan/BASE_invierno_2026-10-24/Emisiones').resolve();assert emission_root.is_dir()
 plan['allowed_input_roots'].append(str(emission_root))
 for c in plan['cases']:
  for name,source in c['input_sources'].items():
   s=Path(source).resolve();assert any(s.is_relative_to(Path(r).resolve()) for r in plan['allowed_input_roots'])
   assert s.is_file()
 for cid in st['errors']:
  folder=p.parent/'Casos'/cid;assert not (folder/'execution.json').exists() and not (folder/'aermod.out').exists();preserve(folder,True)
 for path in [p.parent/'status.json',p.parent/'STOP_AFTER_CURRENT',OUT/'collector.lock',OUT/'STOP_AFTER_CURRENT',OUT/'Fallo_recepcion.json',OUT/'local.stdout.log',OUT/'local.stderr.log',OUT/'collector.stdout.log',OUT/'collector.stderr.log',OUT/'Supervisor_cierre.json',OUT/'Supervisor_local.json']:
  if path.exists():preserve(path,True)
 save(p,plan);a=read(OUT/'Reparto.json');a['hosts']['local']['plan_sha256']=sha(p);save(OUT/'Reparto.json',a)
 contract=read(OUT/'Contrato_recepcion.json')
 for item in contract['files']:item['sha256']=sha(item['path'])
 contract['updated_utc']=now();contract['revision_reason']='Allow exact existing frozen winter-emission source root onD; no input bytes, cases or scientific outputs changed.';save(OUT/'Contrato_recepcion.json',contract)
 save(OUT/'Correccion_rutas.json',dict(status='VERIFIED_BEFORE_RESTART',updated_utc=now(),old_attempt=str(backup),new_allowed_root=str(emission_root),all854case_paths_within_frozen_roots=True,changed_scientific_inputs=False,completed_preserved=len(st['completed']),failed_cases_never_executed=list(st['errors'])))
 print('Path guard corrected;14completed cases preserved; both incomplete preparations archived',flush=True)
if __name__=='__main__':main()
