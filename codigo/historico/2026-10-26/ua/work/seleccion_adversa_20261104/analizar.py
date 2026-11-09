"""Retrospective, reproducible selection and physical diagnostics. No model dispatch."""
from pathlib import Path
import json, hashlib, sys
import numpy as np
import pandas as pd
from itertools import combinations

ROOT=Path(r'/archivo/usuario\Documents\Codex\2026-10-26\ua')
OLD=Path(r'/archivo/usuario\Documents\Codex\2026-10-08\hem')
OUT=ROOT/'outputs/Seleccion_adversa_2026-11-04'
OUT.mkdir(parents=True,exist_ok=True)
A=ROOT/'outputs/Sensibilidad_estacional_2026-10-29'
B=ROOT/'outputs/Sensibilidad_conjunta_T_WS_2026-10-30'
SC=['BASE','T_MINUS','T_PLUS','U_MINUS','U_PLUS','V_MINUS','V_PLUS','WS_PLUS','T_WS_PLUS']
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.file_digest(open(p,'rb'),'sha256').hexdigest()
def save(n,x): (OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def csv(n,x): x.to_csv(OUT/n,index=False,encoding='utf-8-sig')

def hull_planes(cloud):
    """Supporting planes of a small full-dimensional 3D empirical point cloud."""
    assert np.linalg.matrix_rank(cloud-cloud.mean(axis=0))==3
    planes=[]
    for i,j,k in combinations(range(len(cloud)),3):
        normal=np.cross(cloud[j]-cloud[i],cloud[k]-cloud[i]);norm=np.linalg.norm(normal)
        if norm<1e-10:continue
        normal=normal/norm;offset=-normal@cloud[i];side=cloud@normal+offset
        if side.max()<1e-9:planes.append([*normal,offset])
        elif side.min()>-1e-9:planes.append([*(-normal),-offset])
    assert len(planes)>=4
    return np.array(planes)

def tables():
    raw=pd.concat([pd.read_csv(p/'Medias_diarias_civiles.csv') for p in [A,B]],ignore_index=True)
    keys=['season','day','scenario','pollutant','x_m','y_m']
    dup=raw[raw.duplicated(keys,keep=False)]
    assert dup.groupby(keys).media_horas_validas_ug_m3.agg(lambda s: s.max()-s.min()).max()<1e-10
    d=raw.drop_duplicates(keys).query('receptor != "Panel"').copy()
    rawp=pd.concat([pd.read_csv(p/'Resumen_periodo_comparable.csv') for p in [A,B]],ignore_index=True)
    pk=['season','pollutant','scenario','x_m','y_m']
    p=rawp.drop_duplicates(pk).query('receptor != "Panel"').copy()
    rows=[];rank=[];episodes=set();coverage={}
    for key,g in d.groupby(['season','pollutant','receptor']):
        season,pol,rec=key
        good=g[(g.horas_validas==24)&(g.target_hours==24)&g.complete_civil_day]
        days=good.groupby('day').scenario.nunique(); days=set(days[days==9].index)
        coverage[season]=len(days)
        g=good[good.day.isin(days)]
        pg=p[(p.season==season)&(p.pollutant==pol)&(p.receptor==rec)]
        for metric in ['media_periodo','maximo_diario_24h']:
            if metric=='media_periodo':
                v=pg.set_index('scenario').mean_ug_m3
                dates={s:'' for s in SC}
            else:
                ix=g.groupby('scenario').media_horas_validas_ug_m3.idxmax()
                vmax=g.loc[ix].set_index('scenario')
                v=vmax.media_horas_validas_ug_m3
                dates=vmax.day.to_dict()
            assert v.index.is_unique and set(v.index)==set(SC)
            winner=v.idxmax();base=float(v['BASE']);value=float(v[winner])
            for j,(s,val) in enumerate(v.sort_values(ascending=False).items(),1):
                rank.append(dict(season=season,pollutant=pol,receptor=rec,metric=metric,rank=j,scenario=s,value=float(val),day=dates[s],delta_pct=100*(val/base-1)))
            paired=float(g[(g.scenario=='BASE')&(g.day==dates[winner])].media_horas_validas_ug_m3.iloc[0]) if dates[winner] else base
            row=dict(season=season,pollutant=pol,receptor=rec,metric=metric,scenario=winner,value=value,base=base,delta=value-base,delta_pct=100*(value/base-1),day=dates[winner],base_max_day=dates['BASE'],base_same_day=paired,delta_same_day=value-paired,delta_same_day_pct=100*(value/paired-1),n_days=coverage[season] if dates[winner] else int(pg.days.max()),valid_hours=int(pg.valid_hours.min()))
            rows.append(row)
            # Diagnostic episode = selected scenario's largest 24h day; include original BASE maximum.
            ep=g[g.scenario==winner].sort_values('media_horas_validas_ug_m3',ascending=False).iloc[0]
            episodes.add((season,ep.day,winner))
            base_ep=g[g.scenario=='BASE'].sort_values('media_horas_validas_ug_m3',ascending=False).iloc[0]
            episodes.add((season,base_ep.day,'BASE'))
    selected=pd.DataFrame(rows);csv('Seleccion_numerica_32_indicadores.csv',selected)
    csv('Ranking_nueve_configuraciones.csv',pd.DataFrame(rank))
    csv('Episodios_auditar.csv',pd.DataFrame(sorted(episodes),columns=['season','day','scenario']))
    return d,p,selected,episodes,coverage

def residuals():
    paths={'VERANO':OLD/'outputs/Discrepancias_ajuste_2026-10-19/Residuos_ajuste.csv','INVIERNO':OLD/'outputs/Diagnostico_meteorologico_invierno_2026-10-25/Residuos_ajuste.csv'}
    scales=read(A/'Diseno.json')['scales']; dailyall=[]; support=[]; obs={}
    for season,path in paths.items():
        x=pd.read_csv(path); cols=['residuo_T_C','residuo_u_m_s','residuo_v_m_s']
        x=x[x.valido_conjunto.eq(True)&np.isfinite(x[cols]).all(axis=1)].copy()
        x['day']=x.fecha_local.str[:10]
        x=x[x.day.le('2017-01-20' if season=='VERANO' else '2017-07-21')]
        days=x.groupby('day').size(); x=x[x.day.isin(days[days>=18].index)]
        q=x.groupby('day')[cols].mean();q['n_hours']=x.groupby('day').size(); q['season']=season
        assert len(q)==(31 if season=='VERANO' else 29)
        sd=q[cols].std().to_numpy(); assert np.allclose(sd,[scales[season][k] for k in ['T','u','v']])
        dailyall.append(q.reset_index()); clouds=q[cols].to_numpy()/sd
        hull=hull_planes(clouds)
        for s in SC:
            if 'WS' in s: continue # scalar-speed perturbation is not a constant u/v displacement.
            vec=np.zeros(3)
            if s!='BASE': vec[{'T':0,'U':1,'V':2}[s[0]]]=(-1 if s.endswith('MINUS') else 1)
            distances=np.linalg.norm(clouds-vec,axis=1); j=int(np.argmin(distances))
            excess=float(np.max(hull[:,:3]@vec+hull[:,3]))
            support.append(dict(season=season,scenario=s,delta_T_C=vec[0]*sd[0],delta_u_ms=vec[1]*sd[1],delta_v_ms=vec[2]*sd[2],inside_joint_daily_convex_hull=bool(excess<=1e-9),max_facet_excess_standardized=excess,nearest_observed_day=q.index[j],nearest_standardized_distance=float(distances[j]),nearest_T=float(q.iloc[j][cols[0]]),nearest_u=float(q.iloc[j][cols[1]]),nearest_v=float(q.iloc[j][cols[2]])))
        obs[season]=x
    csv('Discrepancias_diarias_conjuntas.csv',pd.concat(dailyall))
    csv('Soporte_conjunto_perturbaciones.csv',pd.DataFrame(support))
    return obs,pd.DataFrame(support)

def sfc(season,scenario,folder=None):
    folder=folder or (B if 'WS' in scenario else A)/'Meteorologia'/season/scenario
    names=['year','month','daynum','jday','hour','H','ustar','wstar','vptg','zic','zim','L','z0','bowen','albedo','WS','WD','zref','T_K','ztemp','ipcode','rain','RH','pressure','ccvr','WADJ','SUBflag']
    x=pd.read_csv(folder/'met.SFC',sep=r'\s+',skiprows=1,header=None,names=names)
    dates=pd.to_datetime(dict(year=x.year,month=x.month,day=x.daynum))
    x['fin_LST']=dates+pd.to_timedelta(x.hour,unit='h');x['inicio_LST']=x.fin_LST-pd.Timedelta(hours=1)
    offset=4 if season=='INVIERNO' else 3
    x['inicio_civil']=(x.inicio_LST+pd.Timedelta(hours=offset)).dt.tz_localize('UTC').dt.tz_convert('America/Santiago')
    x['day']=x.inicio_civil.dt.strftime('%Y-%m-%d')
    x['u']=-x.WS*np.sin(np.deg2rad(x.WD));x['v']=-x.WS*np.cos(np.deg2rad(x.WD))
    x['valid']=(x.WS<99)&(x.T_K<999)&(x.ustar>=0)&(x.zim>0)
    x['season']=season;x['scenario']=scenario
    return x,folder

def pfl(folder):
    names=['year','month','daynum','hour','z','top','WD','WS','T_C','sigmaA','sigmaW']
    p=pd.read_csv(folder/'met.PFL',sep=r'\s+',header=None,names=names)
    p['fin_LST']=pd.to_datetime(dict(year=p.year,month=p.month,day=p.daynum))+pd.to_timedelta(p.hour,unit='h')
    p['u']=-p.WS*np.sin(np.deg2rad(p.WD));p['v']=-p.WS*np.cos(np.deg2rad(p.WD))
    return p

def get_hourly(season,day,scenario,pol,cache,audit):
    key=(season,day,scenario,pol)
    if key in cache:return cache[key]
    folder=B if 'WS' in scenario else A
    # Civil day may straddle two LST dates after winter DST.
    dates=[day]
    if season=='INVIERNO': dates.insert(0,(pd.Timestamp(day)-pd.Timedelta(days=1)).strftime('%Y-%m-%d'))
    frames=[]
    for d in dates:
        cid=f'{season}_{d.replace("-","")}_{scenario}_{pol}';rp=folder/'Recibos'/f'{cid}.json'
        if not rp.exists():continue
        r=read(rp); hp=Path(r['result_folder'])/'Horario_con_mascara.csv'
        assert sha(hp)==r['outputs']['Horario_con_mascara.csv']
        audit[cid]={'receipt':str(rp),'hourly_sha256':sha(hp),'inputs':r['inputs']}
        frame=pd.read_csv(hp)
        if season=='VERANO':
            stamps=frame.fecha_AERMOD.astype(str).str.zfill(8)
            frame['fin_LST']=pd.to_datetime(stamps.str[:6],format='%y%m%d')+pd.to_timedelta(stamps.str[6:].astype(int),unit='h')
            frame['inicio_civil']=(frame.fin_LST-pd.Timedelta(hours=1)).dt.tz_localize('Etc/GMT+3')
            frame['dia_civil']=frame.inicio_civil.dt.strftime('%Y-%m-%d')
        frames.append(frame)
    data=pd.concat(frames);data=data[data.dia_civil==day].copy()
    data['fin_LST']=pd.to_datetime(data.fin_LST)
    cache[key]=data;return data

def diagnose(episodes,obs):
    summaries=[]; hourly=[]; profiles=[]; audit={}; cache={}; mets={}; seasonqc=[]
    targets={s:sorted({c for ss,d,c in episodes if ss==s}|{'BASE'}) for s in ['VERANO','INVIERNO']}
    for season,scenarios in targets.items():
        base,bfolder=sfc(season,'BASE'); bp=pfl(bfolder)
        for sc in scenarios:
            met,folder=sfc(season,sc); pr=pfl(folder);mets[(season,sc)]=(met,pr)
            common=met.merge(base[['fin_LST','valid','WD','WS','T_K','L','ustar','H','zim']],on='fin_LST',suffixes=('','_BASE'),validate='one_to_one')
            start,end=('2016-12-21','2017-03-20') if season=='VERANO' else ('2017-06-21','2017-09-20')
            common=common[common.day.between(start,end)]
            assert (common.valid==common.valid_BASE).all()
            g=common[common.valid];turn=((g.WD-g.WD_BASE+180)%360-180).abs()
            op=obs[season]; observedws=np.hypot(op.u_obs_m_s,op.v_obs_m_s)
            seasonqc.append(dict(season=season,scenario=sc,hours=len(g),WS_min=g.WS.min(),WS_max=g.WS.max(),WS_median=g.WS.median(),WD_turn_median=turn.median(),WD_turn_P95=turn.quantile(.95),WD_turn_max=turn.max(),hours_turn_over90=int((turn>90).sum()),stable_hours=int((g.L>0).sum()),unstable_hours=int((g.L<0).sum()),stability_sign_changes=int((np.sign(g.L)!=np.sign(g.L_BASE)).sum()),UST_changed=int((g.ustar!=g.ustar_BASE).sum()),H_changed=int((g.H!=g.H_BASE).sum()),zim_changed=int((g.zim!=g.zim_BASE).sum()),station_WS_max=observedws.max(),hours_WS_above_station_training_max=int((g.WS>observedws.max()).sum())))
    for season,day,sc in sorted(episodes):
        for scenario in sorted({sc,'BASE'}):
            met,pr=mets[(season,scenario)]; met=met[met.day==day].copy()
            assert len(met)==24 and met.valid.all(),(season,day,scenario,len(met))
            pp=pr[pr.fin_LST.isin(met.fin_LST)].copy()
            pp['season']=season;pp['day']=day;pp['scenario']=scenario;profiles.append(pp)
            # Exact 10-100 m shear and temperature gradient between 18.8 and 100 m.
            p10=pp[pp.z.eq(10)].set_index('fin_LST');p100=pp[pp.z.eq(100)].set_index('fin_LST')
            p18=pp[np.isclose(pp.z,18.8)].set_index('fin_LST')
            shear=np.hypot(p100.u-p10.u,p100.v-p10.v)/90
            theta_grad=(p100.T_C-p18.T_C)/81.2+.0098 # dry approximation only; not virtual/potential T validation.
            met['shear10_100_s_1']=met.fin_LST.map(shear);met['dry_theta_grad18_100_K_m']=met.fin_LST.map(theta_grad)
            for pol in ['MP10','MP25']:
                h=get_hourly(season,day,scenario,pol,cache,audit)
                points={(380148.,6331485.):'Los Bronces',(381128.,6323667.):'Piedra Carvajal',(384254.,6324494.):'Sulfatos',(381759.,6327947.):'La Paloma'}
                h['receptor']=[points.get((x,y),'Panel') for x,y in zip(h.x_m,h.y_m)]
                h=h[h.receptor.ne('Panel')].merge(met,on='fin_LST',validate='many_to_one');h['pollutant']=pol
                for rec,g in h.groupby('receptor'):
                    assert len(g)==24 and g.C_ug_m3.notna().all()
                    c=g.C_ug_m3.to_numpy();w=c/c.sum() if c.sum()>0 else c
                    top=g.sort_values('C_ug_m3',ascending=False).iloc[0]
                    summaries.append(dict(season=season,day=day,scenario=scenario,pollutant=pol,receptor=rec,mean_C=g.C_ug_m3.mean(),max_hour=top.inicio_civil_x,peak_C=top.C_ug_m3,peak_WS=top.WS,peak_WD_from=top.WD,peak_L=top.L,peak_zim=top.zim,peak_ustar=top.ustar,peak_H=top.H,peak_shear=top.shear10_100_s_1,C_weighted_WS=float(np.sum(w*g.WS)),C_fraction_stable=float(w[g.L>0].sum()),C_fraction_WS_lt2=float(w[g.WS<2].sum()),peak_hour_share_pct=100*float(w.max()),max_shear=float(g.shear10_100_s_1.max()),min_dry_theta_grad=float(g.dry_theta_grad18_100_K_m.min())))
                hourly.append(h[['season','day','scenario','pollutant','receptor','fin_LST','C_ug_m3','WS','WD','u','v','L','zim','ustar','H','T_K','shear10_100_s_1']])
    csv('Diagnostico_estacional_SFC.csv',pd.DataFrame(seasonqc))
    csv('Episodios_meteorologia_concentracion.csv',pd.DataFrame(summaries).drop_duplicates())
    csv('Episodios_horarios.csv',pd.concat(hourly).drop_duplicates())
    csv('Perfiles_episodios.csv',pd.concat(profiles).drop_duplicates())
    save('Trazabilidad_horas_revisadas.json',audit)
    return pd.DataFrame(summaries).drop_duplicates(),pd.DataFrame(seasonqc),audit

if __name__=='__main__':
    d,p,sel,episodes,cov=tables();obs,support=residuals(); diag,qc,audit=diagnose(episodes,obs)
    sources=[p/n for p in [A,B] for n in ['Medias_diarias_civiles.csv','Resumen_periodo_comparable.csv','Auditoria_final.json']]
    save('Verificacion.json',dict(status='ANALYSIS_PASSED_NOT_PHYSICAL_VALIDATION',selection_rows=len(sel),ranking_rows=288,common_24h_days=cov,episodes=len(episodes),verified_hourly_receipts=len(audit),sources=[dict(path=str(p),sha256=sha(p)) for p in sources],warning='Empirical convex hull and numerical profile diagnostics do not establish joint physical attainability, station transfer, or a regulatory worst condition.'))
    print(sel[sel.pollutant.eq('MP10')][['season','receptor','metric','scenario','value','delta_pct','day']].to_string(index=False))
    print(support.to_string(index=False));print(qc.to_string(index=False));print('Episodes:',sorted(episodes))
