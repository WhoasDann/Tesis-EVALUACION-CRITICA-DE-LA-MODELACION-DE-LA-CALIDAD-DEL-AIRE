"""Frozen one-at-a-time sensitivity pilot; serialized MMIF interface, not WRF reintegration."""
from pathlib import Path
from datetime import datetime,timedelta
import sys,json,shutil,re,subprocess,os
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'work/piloto_conjunto'))
from prepare_joint import CONFIG as OLD_CONFIG,sha,read,save,rec,now,weight,uv,wswd
OLD=Path(r'/archivo/usuario\Documents\Codex\2026-10-08\hem');O=OLD/'outputs'
OUT=ROOT/'outputs/Sensibilidad_simple_2026-10-29'
CONFIG={s:dict(c) for s,c in OLD_CONFIG.items()}
DAYS=15;HOURS=DAYS*24
SCENARIOS=['BASE','T_MINUS','T_PLUS','U_MINUS','U_PLUS','V_MINUS','V_PLUS']
STAT=ROOT/'outputs/Revision_Huneeus_2026-10-28/Estadisticas_discrepancias_locales.json'
def prepare():
 assert not OUT.exists(),'Preserve existing attempt'
 stats=read(STAT);scales={}
 for season in CONFIG:
  label=season.title();src=stats['sources'][label];assert sha(src['source'])==src['sha256']
  scales[season]={x['variable']:x['sd_diaria_ddof1'] for x in stats['daily_statistics'] if x['temporada']==label}
  assert set(scales[season])=={'T','u','v'}
 old=ROOT/'outputs/Piloto_conjunto_14dias_2026-10-27'
 prior=read(old/'Diseno.json')
 for x in prior['inputs']:
  if Path(x['path']).name in ['onsite.dat','upper.dat','surface.dat','met.IN1','met.SFC','met.PFL']:assert sha(x['path'])==x['sha256']
 OUT.mkdir();(OUT/'Binarios').mkdir();(OUT/'Comunes').mkdir()
 for name in ['receptores.inc','membresia.csv','membresia_original.csv']:shutil.copy2(old/'Comunes'/name,OUT/'Comunes'/name)
 assert len((OUT/'Comunes/receptores.inc').read_text().splitlines())==40
 for name in ['aermet.exe','aermod.exe']:shutil.copy2(O/'BASE_verano_2026-10-21/Binarios'/name,OUT/'Binarios'/name)
 inputs=[rec(STAT)]+[rec(s['source']) for s in stats['sources'].values()]
 inputs += [rec(Path(c['met'])/n) for c in CONFIG.values() for n in ['onsite.dat','upper.dat','surface.dat','met.IN1','met.SFC','met.PFL']]
 design=dict(created_utc=now(),status='FROZEN_BEFORE_CONCENTRATIONS',seasons=CONFIG,days_per_season=DAYS,daily_cases=DAYS*2*7*2,
  scenarios=SCENARIOS,scales=scales,amplitude='Sample SD of daily mean signed Obs-WRF discrepancy; fixed original training windows; >=18 joint valid hours/day. No bias correction, fitting or scenario selection on concentrations.',
  date_selection='15 consecutive days beginning at the already frozen pilot dates: Feb1-15 and Jul25-Aug8. Extension chosen before results; no claim of seasonal representativeness. No DST transition.',
  interface='MMIF serialized ONSITE profiles -> rerun AERMET -> AERMOD. Controlled input sensitivity at this interface. Does NOT claim equivalence to altered wrfout -> MMIF or dynamically consistent WRF.',
  transfer='Station-scale amplitude applied to MMIF column I43/J44, a spatial transfer hypothesis. A single vertical operator: deltaX*w, w=1-3s^2+2s^3, s=clip((z-zref)/(BASE_MHGT-zref),0,1); zref=2m for T and10m for wind. Full amplitude below reference, zero above BASE PBL.',
  thermal='Perturb serialized TT; recompute DT01 from rounded TT03-TT01. Retain RH, pressure, heat flux, UST and MHGT and original sounding/surface inputs. This is prescribed profile sensitivity, not thermal energy balance or constant water-vapor mixing ratio.',
  wind='Convert serialized meteorological direction/speed to east/north u,v; add only selected component; recompute speed/direction. No arbitrary clipping. Temperature and all auxiliary inputs fixed for u/v cases.',
  other_fields='Auxiliary BASE states retained. AERMET regenerates its dependent outputs. Technical QC checks numerical admissibility, not physical validation of mountain flow or station transfer.',
  boundary='Perturb target360h only; original seasonal AERMET context outside. AERMOD steady hourly response; boundary and fixed auxiliary-state limitations retained.',
  comparison='Same dates, emissions, binary,40receptors, common valid hours. Daily paired differences and absolute means. No calibrated intervals, scenario probabilities, worst possible state, full-grid maxima or seasonal conclusions.',
  panel='Same geometrically selected40points as previous pilot, including LBCEN/PCAR/PALP/SULF and all existing zones; no selection on concentrations.',
  queue='Day-position first, seven scenarios, alternating seasons, paired MP10/MP25. Pair assigned to one Windows worker host; disjoint batches. Linux retains full BASE.',
  inputs=inputs)
 save(OUT/'Diseno.json',design);metrics=[]
 for season,cfg in CONFIG.items():
  met=Path(cfg['met']);lines=(met/'onsite.dat').read_text(encoding='ascii').splitlines(keepends=True);assert len(lines)%30==0
  start=datetime.fromisoformat(cfg['start']);target={(start+timedelta(hours=i)).strftime('%Y%m%d')+f'{i%24+1:02}':i for i in range(HOURS)}
  for scenario in SCENARIOS:
   delta=np.zeros(3)
   if scenario!='BASE':
    j=['T','U','V'].index(scenario[0]);var=['T','u','v'][j];delta[j]=scales[season][var]*(-1 if scenario.endswith('MINUS') else 1)
   dt,du,dv=delta;folder=OUT/'Meteorologia'/season/scenario;folder.mkdir(parents=True)
   for n in ['met.IN1','upper.dat','surface.dat']:shutil.copy2(met/n,folder/n)
   rows=list(lines);expected=[];seen=[];tvals=[];wvals=[]
   for k in range(0,len(lines),30):
    stamp=lines[k][:10]
    if stamp not in target:continue
    seen.append(target[stamp]);h=float(lines[k][40:50]);assert h>10
    for lev in range(1,30):
     line=lines[k+lev];z=float(line[10:20]);w=weight(z,h,10);wt=weight(z,h,2)
     if lev>=2:
      speed,direction=float(line[20:30]),float(line[30:40]);assert 0<=speed<99 and 0<=direction<=360
      u,v=uv(speed,direction);ns,nd=wswd(u+w*du,v+w*dv);assert ns>=0 and (w==0 or ns<50), (season,scenario,stamp,z,h,ns)
      if du or dv:line=line[:20]+f'{ns:10.3f}{nd:10.3f}'+line[40:]
      wvals.append(ns)
     if lev!=2:
      t=float(line[40:50]);nt=t+wt*dt;assert -80<nt<65
      if dt:line=line[:40]+f'{nt:10.3f}'+line[50:]
      tvals.append(nt)
     rows[k+lev]=line
     expected.append(dict(stamp=stamp,level=lev,z=z,H=h,wind_weight=w,thermal_weight=wt,delta_T=float(dt),delta_u=float(du),delta_v=float(dv)))
    if dt:
     t0=float(rows[k+1][40:50]);t3=float(rows[k+3][40:50]);line=rows[k+1];rows[k+1]=line[:60]+f'{t3-t0:10.3f}'+line[70:]
    for lev in range(1,30):
     a,b=lines[k+lev],rows[k+lev];assert a[:20]==b[:20]
     if lev==1:assert a[20:40]==b[20:40] and a[50:60]==b[50:60] and a[70:]==b[70:]
     elif lev==2:assert a[40:]==b[40:]
     else:assert a[50:]==b[50:]
     if not dt:assert a[40:]==b[40:]
     if not (du or dv):assert a[20:40]==b[20:40]
   assert seen==list(range(HOURS)),(season,len(seen))
   (folder/'onsite.dat').write_text(''.join(rows),encoding='ascii',newline='')
   save(folder/'Expected.json',expected);save(folder/'Inputs.json',{n:sha(folder/n) for n in ['met.IN1','upper.dat','surface.dat','onsite.dat']})
   metrics.append(dict(season=season,scenario=scenario,delta_T=dt,delta_u=du,delta_v=dv,profile_T_min=min(tvals),profile_T_max=max(tvals),profile_WS_min=min(wvals),profile_WS_max=max(wvals)))
 pd.DataFrame(metrics).to_csv(OUT/'Diagnostico_entradas.csv',index=False)
 save(OUT/'Preparacion.json',dict(status='READY_FOR_AERMET',design=rec(OUT/'Diseno.json'),script=rec(__file__)))
 print('Prepared420cases; fourteen meteorological configurations',flush=True)
def run():
 for season in CONFIG:
  for scenario in SCENARIOS:
   folder=OUT/'Meteorologia'/season/scenario
   assert not (folder/'execution.json').exists()
   assert all(sha(folder/n)==h for n,h in read(folder/'Inputs.json').items())
   print('AERMET '+season+' '+scenario,flush=True)
   with (folder/'console.log').open('xb') as log:
    p=subprocess.run([str(OUT/'Binarios/aermet.exe'),'met.IN1'],cwd=folder,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,timeout=240)
   save(folder/'execution.json',dict(returncode=p.returncode,finished_utc=now()));assert p.returncode==0
   assert not re.search(r'(?m)^\s*(?:\w+\s+)?E\d{2}\s',(folder/'met.ER1').read_text())
 print('AERMET completed all14 cases',flush=True)
if __name__=='__main__':globals()[sys.argv[1]]()


