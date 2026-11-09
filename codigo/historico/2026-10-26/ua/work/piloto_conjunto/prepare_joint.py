"""Exploratory joint meteorology pilot. Frozen members, explicit column transfer, fixed spatial panel."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil,re,sys,subprocess,os
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/Piloto_conjunto_14dias_2026-10-27';OLD=Path(r'/archivo/usuario\Documents\Codex\2026-10-08\hem');O=OLD/'outputs'
CONFIG={
 'VERANO':dict(base=str(O/'BASE_verano_2026-10-21'),met=str(O/'BASE_verano_2026-10-21/Meteorologia/aermet_20261021_145804_172910'),model=str(O/'Evaluacion_febrero_2026-10-21'),start='2017-02-01',offset=-3,qc='Revision_QC_2026-10-21'),
 'INVIERNO':dict(base=str(O/'BASE_invierno_2026-10-24'),met=str(O/'BASE_invierno_2026-10-24/Revision_MMIF_2026-10-25/AERMET_ejecucion_20261025_214304_003569'),model=str(O/'Evaluacion_meteorologica_invierno_2026-10-26'),start='2017-07-25',offset=-4,qc='Revision_QC_2026-10-25')}
SCENARIOS=['BASE']+[f'R{i:02}' for i in range(1,9)]
def now():return datetime.now(timezone.utc).isoformat()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,d):
 p=Path(p);t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8');os.replace(t,p)
def rec(p):return dict(path=str(Path(p).resolve()),sha256=sha(p))
def weight(z,h,reference):
 assert h>reference and z>=0 and np.isfinite([z,h]).all()
 s=np.clip((z-reference)/(h-reference),0,1);return float(1-3*s*s+2*s*s*s)
def uv(ws,wd):a=np.deg2rad(wd);return -ws*np.sin(a),-ws*np.cos(a)
def wswd(u,v):return float(np.hypot(u,v)),float(np.rad2deg(np.arctan2(-u,-v))%360)
def fps(df,n):
 a=df[['x_m','y_m']].drop_duplicates().sort_values(['x_m','y_m']).to_numpy();center=a.mean(axis=0)
 ids=[int(np.argmin(((a-center)**2).sum(axis=1)))];distance=((a-a[ids[0]])**2).sum(axis=1)
 while len(ids)<min(n,len(a)):
  k=int(np.argmax(distance));assert k not in ids;ids.append(k);distance=np.minimum(distance,((a-a[k])**2).sum(axis=1))
 return {tuple(x) for x in a[ids]}

def prepare():
 assert not OUT.exists(),'Preserve prior design and attempts'
 # Immutable source predictors and trajectories; no observation scoring or refitting.
 inputs=[];res={}
 for season,cfg in CONFIG.items():
  model=Path(cfg['model']);freeze=read(model/'Predicciones_congeladas.json')
  for x in freeze['archivos']:assert sha(x['path'])==x['sha256'];inputs.append(x)
  a=np.load(model/'Predicciones.npz');delta=a['RIDGE_24'][:8,:168,:]-a['BASE'][None,:168,:]
  assert delta.shape==(8,168,3) and np.isfinite(delta).all();res[season]=delta
  dates=pd.read_csv(model/'Predictores.csv').fecha_local.iloc[:168]
  assert pd.DatetimeIndex(pd.to_datetime(dates)).equals(pd.date_range(cfg['start']+' 00:49',periods=168,freq='h'))
  met=Path(cfg['met'])
  if season=='VERANO':
   assert all(sha(x['path'])==x['sha256'] for x in read(ROOT/'outputs/Piloto_transferencia_2026-10-27/Diseno.json')['inputs'])
  else:
   manifest=read(Path(cfg['base'])/'Ejecucion_preprocesamiento.json')['archivos'];known={Path(x['path']).name.lower():x['sha256'] for x in manifest}
   for name in ['met.IN1','onsite.dat','upper.dat','surface.dat','met.SFC','met.PFL']:assert sha(met/name)==known[name.lower()]
  inputs.extend(rec(met/n) for n in ['met.IN1','onsite.dat','upper.dat','surface.dat','met.SFC','met.PFL'])
 members=pd.read_csv(O/'BASE_verano_2026-10-21/Comunes/membresia_completa.csv');fixed=members[members.grupo.isin(['PCAR','LBCEN','SULF','PALP'])]
 chosen=set(map(tuple,fixed[['x_m','y_m']].to_numpy()));rules={}
 for group,g in members.groupby('grupo',sort=True):
  if len(g)==1:continue
  n=8 if group in ['GENERAL','MINA_envolvente_red'] else 4
  chosen.update(fps(g,n));rules[group]=n
 panel=members[members.apply(lambda r:(r.x_m,r.y_m) in chosen,axis=1)].copy();assert set(panel.grupo)==set(members.grupo)
 OUT.mkdir();(OUT/'Binarios').mkdir();(OUT/'Comunes').mkdir()
 source=O/'BASE_verano_2026-10-21/Binarios/aermet.exe';assert sha(source)=='2ed8a9c5923abccca61873796eabcdcbaf697bff072f90c5907d11159f935265'
 shutil.copy2(source,OUT/'Binarios/aermet.exe')
 panel.rename(columns={'grupo':'grupo_original'}).to_csv(OUT/'Comunes/membresia_original.csv',index=False)
 panel['grupo']='PANEL: '+panel.grupo;panel.to_csv(OUT/'Comunes/membresia.csv',index=False)
 full=(O/'BASE_verano_2026-10-21/Comunes/receptores.inc').read_text().splitlines()
 selected=[l for l in full if tuple(map(float,l.split()[2:4])) in chosen];assert len(selected)==len(chosen)
 (OUT/'Comunes/receptores.inc').write_text('\n'.join(selected)+'\n',encoding='ascii')
 design=dict(created_utc=now(),status='FROZEN_BEFORE_PILOT_CONCENTRATIONS',objective='Early broad partial results across both seasons, both pollutants and the frozen joint meteorology model.',
   seasons=CONFIG,days_per_season=7,meteorological_days=14,scenarios=SCENARIOS,members='First 8 existing RIDGE_24 trajectories, indices0..7, without reselection, refit, clipping, or repeated bias. All T/u/v triplets and temporal block sequences remain paired.',
   station_to_column='Signed discrepancy predicted at the meteorological station is applied additively at MMIF cell I43/J44. This is an explicit unvalidated spatial transfer hypothesis, not known error at that point.',
   clock='For the model interval ending h, use the frozen station discrepancy at h-11minutes (:49). Hold it within its associated hourly interval. No time shift chosen by correlation. Dates used have constant civil offsets (-3 summer, -4 winter); no DST crossing.',
   thermal_transfer='At serialized ONSITE heights use deltaT times cubic PBL weight from reference2m. Recompute DT01=TT03-TT01 after writing rounded temperatures. Keep serialized RH fixed: this allows implicit vapor content to vary with temperature. This differs from WRF constant-specific-humidity edits and is not claimed equivalent.',
   wind_transfer='Earth east/north vector addition, full amplitude at10m; cubic taper to0 at hourly BASE MHGT; no division by original speed. Same w=1-3s^2+2s^3 as prior wind pilot.',
   other_fields='Pressure, RH, heat fluxes, UST, MHGT, surface file, upper-air soundings and all other ONSITE fields fixed. AERMET may derive new stability parameters. No WRF dynamical reintegration.',
   auxiliary='Full existing seasonal AERMET input context; apply the joint trajectory only to the seven target days. Outside them use BASE. No invented residuals outside the frozen interval. Boundary discontinuity and retained BASE auxiliary states are limitations.',
   sources=12263,receptors=len(chosen),receptor_selection=dict(method='Deterministic farthest-point sampling by existing geometry, first point nearest group centroid, ties by x/y; all four sensitive points forced. No concentrations used.',requested=rules),
   spatial_limits='Outputs concern sampled points in every existing group, including all glaciers and MINA. PANEL maxima are not full-grid/area maxima or spatial convergence. Existing full-grid results remain separate.',
   daily_cases=252,queue_order='Day-position outer loop; BASE,R01..R08 inner loop; summer and winter alternated; both pollutants paired. First complete cross-season slice before adding later days.',
   outputs='Hourly and daily point contributions, paired changes versus BASE, descriptive median/min/max/SD across the eight joint members; comparable hours only. No calibrated intervals or seasonal P95.',
   inference='Exploratory propagation, conditional on the model and transfer. Meteorological coverage/persistence deficiencies remain; 14 calendar days are not representative of all seasonal regimes.',inputs=inputs)
 save(OUT/'Diseno.json',design)
 metrics=[]
 for season,cfg in CONFIG.items():
  delta=res[season];np.save(OUT/(season+'_deltas.npy'),delta)
  met=Path(cfg['met']);lines=(met/'onsite.dat').read_text(encoding='ascii').splitlines(keepends=True);assert len(lines)%30==0
  start=datetime.fromisoformat(cfg['start']);target={(start+timedelta(hours=i)).strftime('%Y%m%d')+f'{i%24+1:02}':i for i in range(168)}
  for si,scenario in enumerate(SCENARIOS):
   folder=OUT/'Meteorologia'/season/scenario;folder.mkdir(parents=True)
   for name in ['met.IN1','upper.dat','surface.dat']:shutil.copy2(met/name,folder/name)
   rows=list(lines);expected=[];seen=[]
   for k in range(0,len(lines),30):
    stamp=lines[k][:10]
    if stamp not in target:continue
    i=target[stamp];seen.append(i);h=float(lines[k][40:50]);assert h>10
    dt,du,dv=np.zeros(3) if si==0 else delta[si-1,i]
    for lev in range(1,30):
     line=lines[k+lev];z=float(line[10:20]);nt=None;w=weight(z,h,10)
     if lev>=2:
      speed,direction=float(line[20:30]),float(line[30:40]);assert speed<99 and speed>=0 and 0<=direction<=360
      u,v=uv(speed,direction);ns,nd=wswd(u+w*du,v+w*dv);assert (w==0 or ns<50),(season,scenario,stamp,z,ns)
      if si:line=line[:20]+f'{ns:10.3f}{nd:10.3f}'+line[40:]
     wt=weight(z,h,2)
     if lev!=2:
      t=float(line[40:50]);nt=t+wt*dt
      if si:line=line[:40]+f'{nt:10.3f}'+line[50:]
     rows[k+lev]=line
     expected.append(dict(stamp=stamp,level=lev,z=z,H=h,wind_weight=w,thermal_weight=wt,delta_T=float(dt),delta_u=float(du),delta_v=float(dv)))
    if si:
     t0=float(rows[k+1][40:50]);t3=float(rows[k+3][40:50]);line=rows[k+1];rows[k+1]=line[:60]+f'{t3-t0:10.3f}'+line[70:]
    # Only WS/WD, TT, and the dependent low-level temperature difference can change.
    for lev in range(1,30):
     a,b=lines[k+lev],rows[k+lev]
     assert a[:20]==b[:20]
     if lev==1:assert a[20:40]==b[20:40] and a[50:60]==b[50:60] and a[70:]==b[70:]
     elif lev==2:assert a[40:]==b[40:]
     else:assert a[50:]==b[50:]
   assert seen==list(range(168)),(season,len(seen))
   (folder/'onsite.dat').write_text(''.join(rows),encoding='ascii',newline='')
   save(folder/'Expected.json',expected)
   save(folder/'Inputs.json',{n:sha(folder/n) for n in ['met.IN1','upper.dat','surface.dat','onsite.dat']})
   for j,var in enumerate(['T','u','v']):
    r=np.zeros(168) if si==0 else delta[si-1,:,j];metrics.append(dict(season=season,scenario=scenario,variable=var,min=float(r.min()),max=float(r.max()),mean=float(r.mean()),sd=float(r.std(ddof=1))))
 pd.DataFrame(metrics).to_csv(OUT/'Discrepancias_descriptivas.csv',index=False)
 save(OUT/'Preparacion.json',dict(status='READY_FOR_AERMET_CHECK',design=rec(OUT/'Diseno.json'),script=rec(__file__),binary=rec(OUT/'Binarios/aermet.exe')))
 print(json.dumps(dict(receptors=len(chosen),days=14,scenarios=9,daily_cases=252)),flush=True)

def run():
 for season in CONFIG:
  for scenario in SCENARIOS:
   folder=OUT/'Meteorologia'/season/scenario
   assert not (folder/'execution.json').exists(),'Existing attempt: preserve and inspect'
   assert all(sha(folder/n)==h for n,h in read(folder/'Inputs.json').items())
   print('AERMET '+season+' '+scenario,flush=True)
   with (folder/'console.log').open('xb') as log:
    p=subprocess.run([str(OUT/'Binarios/aermet.exe'),'met.IN1'],cwd=folder,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,timeout=180)
   save(folder/'execution.json',dict(returncode=p.returncode,finished_utc=now()))
   assert p.returncode==0
   er=(folder/'met.ER1').read_text();assert not re.search(r'(?m)^\s*(?:\w+\s+)?E\d{2}\s',er)
 print('AERMET completed all18 cases',flush=True)

if __name__=='__main__':globals()[sys.argv[1]]()