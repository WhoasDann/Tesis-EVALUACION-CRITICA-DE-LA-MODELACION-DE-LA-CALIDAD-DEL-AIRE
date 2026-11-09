from pathlib import Path
import sys,json,collections
from datetime import datetime
import numpy as np,pandas as pd
from prepare_sensitivity import ROOT,OUT,OLD,sha,read,save,rec,now,SCENARIOS
sys.stdout.reconfigure(encoding='utf-8')
master=OUT/'Lotes/master';state=read(OUT/'Estado.json')
assert state['state']=='COMPLETE_RECEIVED' and state['received']==420
assert all(x['state']=='COMPLETE' and not x['errors'] and not x['active'] for x in state['hosts'].values())
assert read(OUT/'Supervisor_cierre.json')['exit_codes']=={'local':0,'collector':0}
assert not (master/'run.lock').exists() and not (OUT/'collector.lock').exists()
for x in read(OUT/'Contrato_recepcion.json')['inputs']:assert sha(x['path'])==x['sha256'],x['path']
plans=[read(master/('plan_'+h+'.json')) for h in ['local','windows3']]
cases=[c for p in plans for c in p['cases']];assert len({c['id'] for c in cases})==420
rows=[];starts=[];ends=[];total_rows=0;valid_rows=0;overlap=0;max_native=0
for c in cases:
 rp=OUT/'Recibos'/(c['id']+'.json');r=read(rp);assert r['status']=='SCIENTIFIC_RECEPTION_PASSED'
 assert all(r[k]==c[k] for k in ['id','season','day','scenario','pollutant'])
 folder=master/c['folder'];ex=read(folder/'execution.json');assert ex['returncode']==0
 starts.append(ex['started_utc']);ends.append(ex['finished_utc'])
 # Recheck the full hourly scientific data and its case-level summaries.
 for n in ['Por_receptor.csv','Horario_con_mascara.csv','receptor_horas.out','receptor_24h.out']:
  assert sha(folder/n)==r['outputs'][n],str(folder/n)
 h=pd.read_csv(folder/'Horario_con_mascara.csv');assert len(h)==960 and not h.duplicated(['x_m','y_m','fecha_AERMOD']).any()
 total_rows+=len(h);valid_rows+=int(h.C_ug_m3.notna().sum())
 pt=h.groupby(['x_m','y_m']).C_ug_m3.agg(['sum','mean','max','count']).reset_index()
 pt.columns=['x_m','y_m','suma_horaria_ug_m3','media_horas_validas_ug_m3','maximo_1h_ug_m3','horas_validas']
 old=pd.read_csv(folder/'Por_receptor.csv');pd.testing.assert_frame_equal(pt,old,check_exact=False,rtol=1e-11,atol=1e-10)
 for k in ['season','day','scenario','pollutant']:pt[k]=c[k]
 rows.append(pt);overlap+=bool(r['qa'].get('BASE_matches_previous_pilot_all_hourly_values'))
 max_native=max(max_native,float(r['qa'].get('error_max_POSTFILE24',0)))
allp=pd.concat(rows,ignore_index=True);published=pd.read_csv(OUT/'Medias_por_caso.csv');keys=['season','day','scenario','pollutant','x_m','y_m']
pd.testing.assert_frame_equal(allp.sort_values(keys).reset_index(drop=True),published[allp.columns].sort_values(keys).reset_index(drop=True),check_exact=False,rtol=1e-11,atol=1e-10)
assert len(allp)==16800 and total_rows==403200 and valid_rows==402640 and overlap==28
for _,g in allp.groupby(['season','day','pollutant','x_m','y_m']):
 assert set(g.scenario)==set(SCENARIOS) and len(g)==7 and g.horas_validas.nunique()==1
agg=allp.groupby(['season','pollutant','scenario','x_m','y_m']).agg(sum_C=('suma_horaria_ug_m3','sum'),valid_hours=('horas_validas','sum'),days=('day','nunique')).reset_index()
agg['mean_ug_m3']=agg.sum_C/agg.valid_hours
pub=pd.read_csv(OUT/'Resumen_periodo_comparable.csv')
keys2=['season','pollutant','scenario','x_m','y_m']
pd.testing.assert_frame_equal(agg.sort_values(keys2).reset_index(drop=True),pub[agg.columns].sort_values(keys2).reset_index(drop=True),check_exact=False,rtol=1e-11,atol=1e-10)
assert agg.days.eq(15).all() and agg.groupby('season').valid_hours.agg(list).map(lambda xs:len(set(xs))).eq(1).all()
a=pd.read_csv(OUT/'Resumen_cuatro_receptores.csv');assert len(a)==112 and a.days.eq(15).all()
b=pd.read_csv(OUT/'Variabilidad_diaria_BASE.csv');b=b[b.receptor.ne('Panel')];assert len(b)==16 and b.days.eq(15).all()
b.to_csv(OUT/'Tabla_variabilidad_BASE_cuatro_receptores.csv',index=False)
summary=[]
for keys,g in a.groupby(['season','pollutant','receptor']):
 baseline=g[g.scenario.eq('BASE')].iloc[0]
 low=g.loc[g.mean_ug_m3.idxmin()];high=g.loc[g.mean_ug_m3.idxmax()]
 summary.append(dict(zip(['season','pollutant','receptor'],keys),BASE=float(baseline['BASE']),min_mean=low.mean_ug_m3,min_case=low.scenario,min_delta_pct=low.delta_pct,max_mean=high.mean_ug_m3,max_case=high.scenario,max_delta_pct=high.delta_pct))
ext=pd.DataFrame(summary);ext.to_csv(OUT/'Tabla_rangos_sensibilidad.csv',index=False)
bounds=dict(start_successful=min(starts),last_model_finished=max(ends),last_received=state['updated_utc'],simulation_and_reception_hours=(datetime.fromisoformat(state['updated_utc'])-datetime.fromisoformat(min(starts))).total_seconds()/3600)
audit=dict(status='PASSED',checked_utc=now(),cases=420,unique_cases=420,dates=30,days_per_season=15,point_day_case_records=len(allp),hourly_records=total_rows,valid_hourly_records=valid_rows,missing_hourly_records=total_rows-valid_rows,overlapping_BASE_exact_hourly_cases=overlap,max_native_24h_difference=max_native,all_hourly_csv_hashes_verified=True,all_daily_means_recomputed_from_hourly=True,all_published_case_and_period_aggregates_reproduced=True,all_configs_share_valid_hours=True,supervisor_exit_codes=read(OUT/'Supervisor_cierre.json')['exit_codes'],timing=bounds,script=rec(__file__))
save(OUT/'Auditoria_final.json',audit)
print(json.dumps(audit,ensure_ascii=False,indent=2));print('\nBASE stats\n'+b[['season','pollutant','receptor','mean_daily','median','sd_days','minimum','maximum','date_max']].to_string(index=False))
print('\nSensitivity ranges\n'+ext.to_string(index=False))
print('\nMP10 paired percentages\n'+a[a.pollutant.eq('MP10')].pivot(index=['season','receptor'],columns='scenario',values='delta_pct').round(2).to_string())

