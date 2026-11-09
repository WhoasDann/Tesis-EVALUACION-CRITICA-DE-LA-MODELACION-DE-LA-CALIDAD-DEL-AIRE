from pathlib import Path
import sys,json,re
import numpy as np,pandas as pd
from prepare_joint import OUT,CONFIG,SCENARIOS,read,save,sha,rec,uv

def main():
 cfg_rows=[];all_sfc={};common=[]
 for season,cfg in CONFIG.items():
  source=Path(cfg['met']);start=pd.Timestamp(cfg['start']);days=pd.date_range(start,periods=7).strftime('%Y-%m-%d').tolist()
  original_s=np.loadtxt(source/'met.SFC',skiprows=1,usecols=range(25));original_p=np.loadtxt(source/'met.PFL')
  bfolder=OUT/'Meteorologia'/season/'BASE';bs=np.loadtxt(bfolder/'met.SFC',skiprows=1,usecols=range(25));bp=np.loadtxt(bfolder/'met.PFL')
  np.testing.assert_array_equal(bs,original_s);np.testing.assert_array_equal(bp,original_p)
  # July dates precede DST, so the canonical winter calendar and civil days agree here.
  native_mask=pd.read_csv(Path(cfg['base'])/cfg['qc']/'Cobertura_horaria.csv');daycol='dia' if season=='VERANO' else 'dia_LST';mask=native_mask[native_mask[daycol].isin(days)].copy();assert len(mask)==168
  assert set(mask.estado)<= {'VALIDA','FALTANTE_AERMET_I71'} if season=='VERANO' else mask.estado.eq('VALIDA').all()
  if season=='INVIERNO':assert (mask.dia_civil==mask.dia_LST).all()
  sm=np.array([f'{int(r[0]):04}-{int(r[1]):02}-{int(r[2]):02}' in days for r in bs]);pm=np.array([f'{int(r[0]):04}-{int(r[1]):02}-{int(r[2]):02}' in days for r in bp]);assert sm.sum()==168 and pm.sum()==168*29
  base_invalid=(bs[:,15]>=99)|(bs[:,18]>=999)|(bs[:,6]<0)|(bs[:,10]<=0)
  assert int(base_invalid[sm].sum())==(1 if season=='VERANO' else 0)
  for scenario in SCENARIOS:
   folder=OUT/'Meteorologia'/season/scenario;assert read(folder/'execution.json')['returncode']==0
   assert all(sha(folder/n)==h for n,h in read(folder/'Inputs.json').items())
   ss=np.loadtxt(folder/'met.SFC',skiprows=1,usecols=range(25));pp=np.loadtxt(folder/'met.PFL')
   np.testing.assert_array_equal(ss[:,:5],bs[:,:5]);np.testing.assert_array_equal(pp[:,:6],bp[:,:6])
   assert np.isfinite(ss).all() and np.isfinite(pp).all()
   invalid=(ss[:,15]>=99)|(ss[:,18]>=999)|(ss[:,6]<0)|(ss[:,10]<=0)
   # Keep the established valid/missing-hour coverage; never reinterpret native zeros.
   np.testing.assert_array_equal(invalid,base_invalid)
   assert np.all(ss[sm & ~invalid,15]>0),'New calm hour: requires separate review'
   e=read(folder/'Expected.json');assert len(e)==168*29
   b,p=bp[pm],pp[pm];wt=np.array([x['thermal_weight']*x['delta_T'] for x in e]);wwu=np.array([x['wind_weight']*x['delta_u'] for x in e]);wwv=np.array([x['wind_weight']*x['delta_v'] for x in e])
   temp=np.array([x['level']!=2 for x in e]);wind=np.array([x['level']>=2 for x in e]);valid_wind=wind & (b[:,7]<99)&(p[:,7]<99)
   te=abs(p[temp,8]-b[temp,8]-wt[temp]);assert np.all(te<=.0111),(season,scenario,float(te.max()))
   bu,bv=uv(b[valid_wind,7],b[valid_wind,6]);pu,pv=uv(p[valid_wind,7],p[valid_wind,6]);we=np.maximum(abs(pu-bu-wwu[valid_wind]),abs(pv-bv-wwv[valid_wind]));tol=.013+(p[valid_wind,7]+b[valid_wind,7])*np.deg2rad(.051)
   assert np.all(we<=tol),(season,scenario,float((we/tol).max()))
   unchanged=np.array([x['wind_weight']==0 and x['thermal_weight']==0 for x in e]);np.testing.assert_array_equal(p[unchanged],b[unchanged])
   surface_temp=np.array([x['delta_T'] for x in e if x['level']==1]);st=ss[sm,18]-bs[sm,18];okay=~invalid[sm];terr=abs(st[okay]-surface_temp[okay]);assert np.all(terr<=.1011),(season,scenario,float(terr.max()))
   messages=(folder/'met.ER1').read_text();assert not re.search(r'(?m)^\s*(?:\w+\s+)?E\d{2}\s',messages)
   # Record informational messages rather than silently assuming all fields are unchanged.
   info={code:len(re.findall(r'\b'+code+r'\b',messages)) for code in ['I69','I71','I74','I81','I82']}
   cfg_rows.append(dict(season=season,scenario=scenario,valid_hours=int(okay.sum()),missing_hours=int((~okay).sum()),max_profile_T_error=float(te.max()),max_surface_T_error=float(terr.max()),max_wind_error_over_tolerance=float((we/tol).max()),exact_unchanged_upper_records=int(unchanged.sum()),information=info,files={n:sha(folder/n) for n in ['met.SFC','met.PFL','met.ER1']}))
  (OUT/'Calendarios').mkdir(exist_ok=True);mask.to_csv(OUT/'Calendarios'/(season+'.csv'),index=False)
  common.append(dict(season=season,days=days,valid_hours=int((~base_invalid[sm]).sum()),missing_hours=int(base_invalid[sm].sum())))
 save(OUT/'Verificacion_meteorologia.json',dict(status='PASSED',base_reproduction_exact=True,coverage_identical_all_members=True,common_calendars=common,cases=cfg_rows,verifier=rec(__file__)))
 print(json.dumps(dict(status='PASSED',cases=len(cfg_rows),calendars=common)),flush=True)
if __name__=='__main__':main()