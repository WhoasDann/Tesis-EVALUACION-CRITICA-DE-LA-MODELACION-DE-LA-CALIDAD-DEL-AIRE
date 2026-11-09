from pathlib import Path
import json,re
import numpy as np,pandas as pd
from campaign import OUT,PILOT,SCENARIOS,sha,read,save,rec,uv
CONFIG=read(OUT/'Diseno.json')['seasons']
def stamp_s(a):return [f'{int(r[0]):04}{int(r[1]):02}{int(r[2]):02}{int(r[4]):02}' for r in a]
def stamp_p(a):return [f'{int(r[0]):04}{int(r[1]):02}{int(r[2]):02}{int(r[3]):02}' for r in a]
def main():
 result=[];calendar_results=[]
 for season,cfg in CONFIG.items():
  met=Path(cfg['met']);basefolder=OUT/'Meteorologia'/season/'BASE'
  bs=np.loadtxt(basefolder/'met.SFC',skiprows=1,usecols=range(25));bp=np.loadtxt(basefolder/'met.PFL')
  np.testing.assert_array_equal(bs,np.loadtxt(met/'met.SFC',skiprows=1,usecols=range(25)))
  np.testing.assert_array_equal(bp,np.loadtxt(met/'met.PFL'))
  cal=pd.read_csv(OUT/'Calendarios'/(season+'.csv'));dc='dia' if season=='VERANO' else 'dia_LST';ec='fin_local' if season=='VERANO' else 'fin_LST'
  keys=pd.to_datetime(cal[dc]).dt.strftime('%Y%m%d')+pd.to_datetime(cal[ec]).dt.hour.replace(0,24).map('{:02}'.format)
  sidx={k:i for i,k in enumerate(stamp_s(bs))};target=np.array([sidx[k] for k in keys])
  invalid=(bs[:,15]>=99)|(bs[:,18]>=999)|(bs[:,6]<0)|(bs[:,10]<=0)
  assert np.array_equal(invalid[target],~cal.estado.eq('VALIDA').to_numpy())
  pidx={}
  for i,k in enumerate(stamp_p(bp)):pidx.setdefault(k,[]).append(i)
  for sc in SCENARIOS:
   folder=OUT/'Meteorologia'/season/sc
   assert read(folder/'execution.json')['returncode']==0
   assert all(sha(folder/n)==h for n,h in read(folder/'Inputs.json').items())
   s=np.loadtxt(folder/'met.SFC',skiprows=1,usecols=range(25));p=np.loadtxt(folder/'met.PFL')
   assert np.isfinite(s).all() and np.isfinite(p).all()
   np.testing.assert_array_equal(s[:,:5],bs[:,:5]);np.testing.assert_array_equal(p[:,:6],bp[:,:6])
   bad=(s[:,15]>=99)|(s[:,18]>=999)|(s[:,6]<0)|(s[:,10]<=0);np.testing.assert_array_equal(bad,invalid)
   assert (s[target[~invalid[target]],15]>0).all()
   ex=read(folder/'Expected.json')
   indices=np.array([pidx[x['stamp']][x['level']-1] for x in ex])
   bpart=bp[indices];part=p[indices]
   tmask=np.array([x['level']!=2 for x in ex]);wmask=np.array([x['level']>=2 for x in ex])&(bpart[:,7]<99)&(part[:,7]<99)
   dt=np.array([x['thermal_weight']*x['delta_T'] for x in ex]);du=np.array([x['wind_weight']*x['delta_u'] for x in ex]);dv=np.array([x['wind_weight']*x['delta_v'] for x in ex])
   terr=np.abs(part[tmask,8]-bpart[tmask,8]-dt[tmask]);assert (terr<=.0111).all(),(season,sc,terr.max())
   u,v=uv(bpart[wmask,7],bpart[wmask,6]);up,vp=uv(part[wmask,7],part[wmask,6]);err=np.maximum(abs(up-u-du[wmask]),abs(vp-v-dv[wmask]))
   tol=.013+(part[wmask,7]+bpart[wmask,7])*np.deg2rad(.051);assert (err<=tol).all(),(season,sc,(err/tol).max())
   upper=np.array([x['thermal_weight']==0 and x['wind_weight']==0 for x in ex]);np.testing.assert_array_equal(part[upper],bpart[upper])
   surface={x['stamp']:x['delta_T'] for x in ex if x['level']==1}
   goodkeys=[k for k in keys if not invalid[sidx[k]]];inds=[sidx[k] for k in goodkeys]
   sterr=np.abs(s[inds,18]-bs[inds,18]-np.array([surface[k] for k in goodkeys]));assert (sterr<=.1011).all(),(season,sc,sterr.max())
   er=(folder/'met.ER1').read_text();assert not re.search(r'(?m)^\s*(?:\w+\s+)?E\d{2}\s',er)
   result.append(dict(season=season,scenario=sc,valid_hours=int((~invalid[target]).sum()),missing_hours=int(invalid[target].sum()),expected_profile_rows=len(ex),max_profile_T_error=float(terr.max()),max_surface_T_error=float(sterr.max()),max_wind_error_over_tolerance=float((err/tol).max()),info={c:len(re.findall(r'\b'+c+r'\b',er)) for c in ['I69','I71','I74','I81','I82']},files={n:sha(folder/n) for n in ['met.SFC','met.PFL','met.ER1']}))
  calendar_results.append(dict(season=season,days=cfg['days'],target_hours=len(cal),valid_hours=int(cal.estado.eq('VALIDA').sum()),hour_states=cal.estado.value_counts().to_dict(),clock='localUTC-3' if season=='VERANO' else 'fixedLST UTC-4; reconstruct civil includingDST'))
 save(OUT/'Verificacion_meteorologia.json',dict(status='PASSED',base_reproduction_exact=True,coverage_identical_all_members=True,common_calendars=calendar_results,cases=result,verifier=rec(__file__)))
 print(json.dumps(dict(status='PASSED',configs=len(result),calendars=calendar_results)),flush=True)
if __name__=='__main__':main()

