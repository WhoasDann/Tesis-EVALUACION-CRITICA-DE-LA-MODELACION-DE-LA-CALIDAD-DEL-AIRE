"""Reproduce el diseño anterior y contrasta reloj/operador en muestra común."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys
import numpy as np
import pandas as pd
from entorno import ROOT, OUT, paths
sys.path.insert(0,str(ROOT/'biblioteca'))
from tesis.reloj import parear
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
protocol=json.loads((OUT/'Protocolo.json').read_text(encoding='utf8'))
# Rutas relativas verificadas por entorno.py; protocolo original conservado.
for k,p in paths.items():assert sha(p)==protocol['inputs'][k]['sha256']
scale=json.loads(paths['amplitudes'].read_text())['scales']
scalar=json.loads(paths['amplitud_WS'].read_text())['scales']
prototypes=json.loads(paths['ternas'].read_text())['prototypes']
obs=pd.read_csv(paths['observaciones']);obs['Fecha_original']=pd.to_datetime(obs.Fecha_original)
assert not obs.Fecha_original.duplicated().any()
columns=['residuo_T_C','residuo_u_m_s','residuo_v_m_s','residuo_WS_m_s']
variables=['T','u','v','WS']
save=lambda n,x:(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
write=lambda n,x:pd.DataFrame(x).to_csv(OUT/n,index=False)

def daily(frame):
    d=frame.groupby('day')[columns].mean();d['n']=frame.groupby('day').size()
    return d[d.n>=18].sort_index()

def select(d,sd,target):
    scores=np.linalg.norm(d[columns[:3]].to_numpy()/sd-target,axis=1)
    order=np.argsort(scores,kind='stable');ties=np.where(np.abs(scores-scores[order[0]])<=1e-12)[0]
    return dict(selected_day=str(d.index[order[0]]),ties=';'.join(str(d.index[i]) for i in ties),
      dT=float(d.iloc[order[0]][columns[0]]),du=float(d.iloc[order[0]][columns[1]]),dv=float(d.iloc[order[0]][columns[2]]),
      distance=float(scores[order[0]]),second_day=str(d.index[order[1]]),second_distance=float(scores[order[1]]),gap=float(scores[order[1]]-scores[order[0]]))

audits=[];scales=[];selections=[];fixed=[];pairs_all=[];daily_all=[];historical=[];coverage=[]
for season,(start,end) in protocol['windows'].items():
    o=obs[obs.Fecha_original.ge(start)&obs.Fecha_original.lt(end)].copy().reset_index(drop=True)
    m=pd.read_csv(paths['wrf_'+season.lower()])
    cases={}
    for clock in protocol['clocks']:
        for operator in protocol['operators']:
            p=parear(o,m,hipotesis=clock,operador=operator)
            assert len(p)==len(o) and p.Fecha_original.equals(o.Fecha_original)
            p['season']=season;p['day']=p.Fecha_original.dt.strftime('%Y-%m-%d')
            p['joint_valid']=np.isfinite(p[columns]).all(axis=1)
            cases[clock,operator]=p
    base=cases[tuple(protocol['baseline'])]
    reference=pd.read_csv(paths['residuos_'+season.lower()])
    reference['Fecha_original']=pd.to_datetime(reference.fecha_local)
    reference=reference[reference.valido_conjunto.eq(True)].copy()
    bvalid=base[base.joint_valid].copy()
    join=bvalid.merge(reference,on='Fecha_original',suffixes=('','_archived'),validate='one_to_one')
    assert len(join)==len(reference)==len(bvalid),(season,len(join),len(reference),len(bvalid))
    error=max(float(np.abs(join[c]-join[c+'_archived']).max()) for c in columns[:3])
    assert error<1e-9,(season,error)
    q=daily(bvalid);sd=q[columns].std(ddof=1).to_numpy()
    expected=np.array([scale[season][k] for k in variables[:3]]+[scalar[season]['WS_m_s']])
    assert np.max(np.abs(sd-expected))<1e-9
    assert len(q)==(31 if season=='VERANO' else 29)
    for proto in [r for r in prototypes if r['season']==season]:
        target=np.array([0,1,0] if proto['target']=='U_PLUS' else [0,0,-1])
        got=select(q,expected[:3],target)
        assert got['selected_day']==proto['source_day']
        assert np.max(np.abs([got['dT'],got['du'],got['dv']]-np.array(proto['delta'])))<1e-9
        historical.append(dict(season=season,prototype=proto['scenario'],**got))
    common=np.logical_and.reduce([p.joint_valid.to_numpy() for p in cases.values()])
    counts=base.loc[common].groupby('day').size()
    days=set(counts[counts>=18].index)
    mask=common&base.day.isin(days).to_numpy()
    qb=daily(base.loc[mask]);baseline_sd=qb[columns].std(ddof=1).to_numpy()
    for (clock,operator),p in cases.items():
        chosen=p.loc[mask].copy();chosen['caso']=clock+'__'+operator
        pairs_all.append(chosen[['season','caso','Fecha_original','fecha_objetivo_utc','day',*columns]])
        d=daily(chosen);assert d.index.equals(qb.index)
        ds=d[columns].std(ddof=1).to_numpy()
        daily_all.append(d.reset_index().assign(season=season,clock=clock,operator=operator))
        coverage.append(dict(season=season,clock=clock,operator=operator,original_records=len(o),
          valid_own=int(p.joint_valid.sum()),common_hours=int(mask.sum()),common_days=len(d),
          min_hours_day=int(d.n.min()),excluded_first_records=';'.join(base.loc[~mask,'Fecha_original'].dt.strftime('%Y-%m-%d %H:%M'))))
        for i,var in enumerate(variables):
            scales.append(dict(season=season,clock=clock,operator=operator,variable=var,
              sd=float(ds[i]),civil_common_sd=float(baseline_sd[i]),original_sd=float(expected[i]),
              delta_pct_same_sample=float(100*(ds[i]/baseline_sd[i]-1)),
              sample_only_delta_pct=float(100*(baseline_sd[i]/expected[i]-1)),common_days=len(d),common_hours=int(mask.sum())))
        for proto in [r for r in prototypes if r['season']==season]:
            target=np.array([0,1,0] if proto['target']=='U_PLUS' else [0,0,-1])
            for rule,denominator in [('objetivo_y_escala_fijos',expected[:3]),('regla_recalculada',ds[:3])]:
                result=select(d,denominator,target)
                selections.append(dict(season=season,prototype=proto['scenario'],original_day=proto['source_day'],
                  clock=clock,operator=operator,rule=rule,changed_day=result['selected_day']!=proto['source_day'],**result))
            row=d.loc[proto['source_day']]
            fixed.append(dict(season=season,prototype=proto['scenario'],source_day=proto['source_day'],clock=clock,operator=operator,
              dT=float(row[columns[0]]),du=float(row[columns[1]]),dv=float(row[columns[2]]),
              change_T=float(row[columns[0]]-proto['delta'][0]),change_u=float(row[columns[1]]-proto['delta'][1]),change_v=float(row[columns[2]]-proto['delta'][2]),
              original_dT=proto['delta'][0],original_du=proto['delta'][1],original_dv=proto['delta'][2]))
    # Clock identities in the training window are consistency controls, not evidence for a clock.
    equivalent='fijo_menos3' if season=='VERANO' else 'fijo_menos4'
    for op in protocol['operators']:
        assert np.array_equal(cases['civil_santiago',op][columns].to_numpy(),cases[equivalent,op][columns].to_numpy(),equal_nan=True)
    audits.append(dict(season=season,original_records=len(o),original_valid_hours=len(bvalid),original_days=len(q),
      original_hours_on_eligible_days=int(q.n.sum()),joint_common_before_daily_filter=int(common.sum()),max_residual_reproduction_error=error,
      max_sd_reproduction_error=float(np.max(np.abs(sd-expected))),common_hours=int(mask.sum()),common_days=len(qb),
      clocks_identical_in_training=equivalent))

write('Amplitudes_SD.csv',scales);write('Seleccion_ternas.csv',selections);write('Ternas_fechas_originales.csv',fixed)
write('Reproduccion_ternas_originales.csv',historical);write('Cobertura.csv',coverage)
pd.concat(daily_all,ignore_index=True).to_csv(OUT/'Medias_diarias_comunes.csv',index=False)
pd.concat(pairs_all,ignore_index=True).to_csv(OUT/'Residuos_horarios_comunes.csv',index=False)
files=['Amplitudes_SD.csv','Seleccion_ternas.csv','Ternas_fechas_originales.csv','Reproduccion_ternas_originales.csv','Cobertura.csv','Medias_diarias_comunes.csv','Residuos_horarios_comunes.csv']
save('Verificacion_analisis.json',dict(status='REPRODUCED_AND_COMPARED',finished_utc=datetime.now(timezone.utc).isoformat(),
  protocol_sha256=sha(OUT/'Protocolo.json'),script_sha256=sha(__file__),audit=audits,outputs={n:sha(OUT/n) for n in files},
  no_model_runs=True,no_clock_selected=True,no_concentration_changes=True,physical_validation=False))
print(json.dumps(audits,indent=2))
print(pd.DataFrame(selections).query("rule=='objetivo_y_escala_fijos'")[['season','prototype','clock','operator','selected_day','gap']].to_string(index=False))
