"""Final audit of all native products, masked hours, paired means and civil calendar."""
from pathlib import Path
import sys,json,hashlib,tarfile,collections
from datetime import datetime
import numpy as np,pandas as pd
from campaign import ROOT,OUT,OLD,PILOT,SCENARIOS,read,save,sha,now,rec
sys.path.insert(0,str(OLD/'work'));sys.path.insert(0,str(OLD/'outputs/Biblioteca_Tesis'))
import salidas_invierno_20261026 as winter
POINTS={(380148.,6331485.):'Los Bronces',(381128.,6323667.):'Piedra Carvajal',(381759.,6327947.):'La Paloma',(384254.,6324494.):'Sulfatos'}

def equal(a,b,keys):
 pd.testing.assert_frame_equal(a.sort_values(keys).reset_index(drop=True),b[a.columns].sort_values(keys).reset_index(drop=True),check_exact=False,rtol=1e-10,atol=1e-10,check_dtype=False)

def main():
 state=read(OUT/'Estado.json');assert state['received']==2548 and state['state']=='COMPLETE_RECEIVED'
 assert all(s['state']=='COMPLETE' and not s['errors'] and not s['active'] for s in state['hosts'].values())
 assert read(OUT/'Supervisor_cierre.json')['exit_codes']=={'local':0,'collector':0}
 assert not (OUT/'collector.lock').exists() and not (OUT/'supervisor.lock').exists() and not (OUT/'Lotes/local/run.lock').exists()
 for x in read(OUT/'Contrato_recepcion.json')['files']:assert sha(x['path'])==x['sha256'],x['path']
 cases=read(OUT/'Casos.json')['cases'];expected=read(OUT/'Cobertura_esperada.json');assert len(cases)==len({c['id'] for c in cases})==2548
 rp=list((OUT/'Recibos').glob('*.json'));assert {p.stem for p in rp}=={c['id'] for c in cases}
 linux=read(OUT/'Verificacion_Linux_en_produccion.json');assert linux['cross_platform']['status']=='PASSED' and len(linux['canaries'])==8
 assert all(r['qa']['cross_platform']['max_absolute_error']==0 for r in linux['canaries'])
 rows=[];winter_parts=collections.defaultdict(list);raw_count=valid_count=0;starts=[];ends=[];error24=0;native_products=0
 for i,c in enumerate(cases):
  r=read(OUT/'Recibos'/(c['id']+'.json'));folder=Path(r['result_folder'])
  assert r['status']=='SCIENTIFIC_RECEPTION_PASSED' and all(r[k]==c[k] for k in ['id','host','day','season','scenario','pollutant'])
  assert (r['current_equivalent_inputs'] if r['host']=='reused' else r['inputs'])==c['inputs']
  tar=None
  if r['host']!='reused':
   archive=Path(r['archive']);assert sha(archive)==r['archive_sha256'];tar=tarfile.open(archive,'r:gz')
  for name,h in r['outputs'].items():
   if (folder/name).exists():assert sha(folder/name)==h,(c['id'],name)
   else:
    assert tar is not None;member=tar.getmember(name);assert member.isfile() and member.name==Path(name).name
    assert hashlib.sha256(tar.extractfile(member).read()).hexdigest()==h,(c['id'],name)
   native_products+=1
  if tar:tar.close()
  ex=read(folder/'execution.json');assert ex['returncode']==0
  if r['host']!='reused':starts.append(ex['started_utc']);ends.append(ex['finished_utc'])
  data=pd.read_csv(folder/'Horario_con_mascara.csv',dtype={'fecha_AERMOD':str});states=c['hour_states']
  assert len(data)==40*len(states) and not data.duplicated(['x_m','y_m','fecha_AERMOD']).any()
  assert set(data.fecha_AERMOD)==set(states) and data.estado.eq(data.fecha_AERMOD.map(states)).all()
  valid=data.estado.eq('VALIDA');assert data.C_ug_m3.notna().eq(valid).all() and data.loc[~valid,'C_bruta_ug_m3'].eq(0).all()
  assert data.loc[valid,'C_ug_m3'].equals(data.loc[valid,'C_bruta_ug_m3'])
  raw_count+=len(data);valid_count+=int(valid.sum())
  pt=data.groupby(['x_m','y_m']).C_ug_m3.agg(['sum','mean','max','count']).reset_index()
  pt.columns=['x_m','y_m','suma_horaria_ug_m3','media_horas_validas_ug_m3','maximo_1h_ug_m3','horas_validas']
  equal(pt,pd.read_csv(folder/'Por_receptor.csv'),['x_m','y_m']);assert len(pt)==40 and pt.horas_validas.nunique()==1
  for key in ['season','day','scenario','pollutant','host']:pt[key]=c[key]
  pt['target_hours']=len(states);rows.append(pt)
  if c['season']=='INVIERNO':winter_parts[c['scenario'],c['pollutant']].append(data)
  if r['qa']['error_max_POSTFILE24'] is not None:error24=max(error24,r['qa']['error_max_POSTFILE24'])
  else:assert len(states)<24
  if (i+1)%200==0:print('Audited',i+1,'cases',flush=True)
 allp=pd.concat(rows,ignore_index=True);keys=['season','day','scenario','pollutant','x_m','y_m']
 equal(allp,pd.read_csv(OUT/'Medias_por_caso_LST.csv'),keys)
 assert raw_count==expected['hourly_values']==2441600 and valid_count==expected['valid_hourly_values']==2439360
 assert raw_count-valid_count==2240 and len(allp)==101920
 for _,g in allp.groupby(['season','day','pollutant','x_m','y_m']):assert len(g)==7 and set(g.scenario)==set(SCENARIOS) and g.horas_validas.nunique()==1
 agg=allp.groupby(['season','pollutant','scenario','x_m','y_m']).agg(sum_C=('suma_horaria_ug_m3','sum'),valid_hours=('horas_validas','sum'),days=('day','nunique')).reset_index();agg['mean_ug_m3']=agg.sum_C/agg.valid_hours
 keys2=['season','pollutant','scenario','x_m','y_m'];equal(agg,pd.read_csv(OUT/'Resumen_periodo_comparable.csv'),keys2)
 for s,h,n in [('VERANO',2151,90),('INVIERNO',2205,92)]:assert agg[agg.season.eq(s)].valid_hours.eq(h).all() and agg[agg.season.eq(s)].days.eq(n).all()
 # Rebuild civil-day tables from verified hourly values, then compare the collector export.
 calendar=pd.read_csv(OUT/'Calendarios/INVIERNO.csv');members=pd.read_csv(OUT/'Comunes/membresia.csv');civil=[]
 for (scenario,pol),parts in winter_parts.items():
  pt,_,_=winter.civil_summaries(pd.concat(parts,ignore_index=True),members,calendar);assert pt.calendario_completo.all() and pt.dia_civil.nunique()==92
  assert pt[pt.dia_civil.eq('2017-08-13')].horas_calendario_esperadas.eq(23).all()
  assert pt[pt.dia_civil.eq('2017-08-14')].horas_validas.eq(22).all()
  assert pt[pt.dia_civil.eq('2017-09-20')].horas_validas.eq(24).all()
  pt['scenario']=scenario;pt['pollutant']=pol;civil.append(pt)
 winter_daily=pd.concat(civil,ignore_index=True);equal(winter_daily,pd.read_csv(OUT/'Invierno_dias_civiles.csv'),['scenario','pollutant','dia_civil','x_m','y_m'])
 # For daily variability use complete civil days only; keep summer's final17h fragment separately.
 summer=allp[allp.season.eq('VERANO')].copy();summer['complete_civil_day']=summer.target_hours.eq(24)
 win=winter_daily.rename(columns={'dia_civil':'day','horas_calendario_esperadas':'target_hours'}).copy();win['season']='INVIERNO';win['complete_civil_day']=win.calendario_completo
 columns=['season','day','scenario','pollutant','x_m','y_m','suma_horaria_ug_m3','media_horas_validas_ug_m3','maximo_1h_ug_m3','horas_validas','target_hours','complete_civil_day']
 daily=pd.concat([summer[columns],win[columns]],ignore_index=True);daily['receptor']=[POINTS.get((x,y),'Panel') for x,y in zip(daily.x_m,daily.y_m)]
 daily.to_csv(OUT/'Medias_diarias_civiles.csv',index=False)
 d=daily[daily.complete_civil_day & daily.receptor.ne('Panel')].copy();base=d[d.scenario.eq('BASE')];stats=[]
 for keys,g in base.groupby(['season','pollutant','receptor']):
  x=g.media_horas_validas_ug_m3;ix=x.idxmax();order=g.sort_values('suma_horaria_ug_m3',ascending=False);total_sum=g.suma_horaria_ug_m3.sum()
  stats.append(dict(zip(['season','pollutant','receptor'],keys),n_days=len(g),mean_daily=x.mean(),median=x.median(),sd_days=x.std(ddof=1),P10=x.quantile(.1),P25=x.quantile(.25),P75=x.quantile(.75),P90=x.quantile(.9),minimum=x.min(),maximum=x.max(),date_max=g.loc[ix,'day'],zero_days=int(x.eq(0).sum()),dominant_sum_day=order.iloc[0].day,top1_share_pct=100*order.iloc[0].suma_horaria_ug_m3/total_sum if total_sum else None,top5_share_pct=100*order.head(5).suma_horaria_ug_m3.sum()/total_sum if total_sum else None))
 stats=pd.DataFrame(stats);assert stats[stats.season.eq('VERANO')].n_days.eq(89).all() and stats[stats.season.eq('INVIERNO')].n_days.eq(92).all()
 stats.to_csv(OUT/'Tabla_variabilidad_BASE_civil.csv',index=False)
 agg=read_agg=pd.read_csv(OUT/'Resumen_cuatro_receptores.csv');ranges=[]
 for keys,g in agg.groupby(['season','pollutant','receptor']):
  low=g.loc[g.mean_ug_m3.idxmin()];high=g.loc[g.mean_ug_m3.idxmax()];baseline=g[g.scenario.eq('BASE')].iloc[0]
  ranges.append(dict(zip(['season','pollutant','receptor'],keys),BASE=baseline.mean_ug_m3,minimum=low.mean_ug_m3,min_case=low.scenario,min_delta_pct=low.delta_pct,maximum=high.mean_ug_m3,max_case=high.scenario,max_delta_pct=high.delta_pct))
 pd.DataFrame(ranges).to_csv(OUT/'Tabla_rangos_sensibilidad.csv',index=False)
 paired=d.pivot(index=['season','day','pollutant','receptor'],columns='scenario',values='media_horas_validas_ug_m3').reindex(columns=SCENARIOS);assert not paired.isna().any().any()
 differences=[]
 for scenario in SCENARIOS[1:]:
  g=paired[['BASE',scenario]].reset_index().rename(columns={scenario:'concentration'});g['scenario']=scenario;g['delta_ug_m3']=g.concentration-g.BASE;g['delta_pct']=np.where(g.BASE>0,100*g.delta_ug_m3/g.BASE,np.nan);differences.append(g)
 pd.concat(differences,ignore_index=True).to_csv(OUT/'Diferencias_pareadas_civiles_cuatro_receptores.csv',index=False)
 audit=dict(status='PASSED',checked_utc=now(),cases=2548,reused=406,new=2142,raw_hourly_records=raw_count,valid_hourly_records=valid_count,masked_hourly_records=raw_count-valid_count,case_receptor_rows=len(allp),products_hashed=native_products,all_native_and_scientific_products_rehashed=True,all_daily_and_period_means_reproduced=True,winter92civil_days_reconstructed=True,winter_DST23h_gap22h_last24h_verified=True,summer_daily_statistics_full_days=89,summer_partial_day='2017-03-20:17h, retained in2151hseasonalmean, excluded from daily-distribution stats',linux8canaries_exact=True,max_native24_error=error24,start_new_cases=min(starts),last_new_case_finished=max(ends),last_received=state['updated_utc'],hours_from_first_new_case_to_final_reception=(datetime.fromisoformat(state['updated_utc'])-datetime.fromisoformat(min(starts))).total_seconds()/3600,script=rec(__file__))
 save(OUT/'Auditoria_final.json',audit);print(json.dumps(audit,indent=2),flush=True)
 print(pd.DataFrame(ranges).to_string(index=False),flush=True);print(stats.to_string(index=False),flush=True)

if __name__=='__main__':main()
