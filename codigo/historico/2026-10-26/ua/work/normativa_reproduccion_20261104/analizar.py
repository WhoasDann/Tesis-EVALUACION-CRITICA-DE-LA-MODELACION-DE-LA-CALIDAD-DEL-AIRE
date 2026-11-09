"""Independent postprocessing reproduction and limited regulatory diagnostics.
No AERMOD dispatch, legal compliance decision or concentration normalization.
"""
from pathlib import Path
import sys,json,hashlib,datetime,io,tarfile,math
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/Normativa_reproduccion_2026-11-04';OUT.mkdir(exist_ok=True)
A=ROOT/'outputs/Sensibilidad_estacional_2026-10-29'
B=ROOT/'outputs/Sensibilidad_conjunta_T_WS_2026-10-30'
C=ROOT/'outputs/Seleccion_adversa_2026-11-04';P=C/'Contraste_ternas_observadas'
OLD=Path('/archivo/usuario/Documents/Codex/2026-10-08/hem')
REC={(380148.,6331485.):'Los Bronces',(381128.,6323667.):'Piedra Carvajal',(384254.,6324494.):'Sulfatos',(381759.,6327947.):'La Paloma'}
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def csv(n,d):d.to_csv(OUT/n,index=False,encoding='utf-8-sig')
def stamp(frame,season):
    stamps=frame.fecha_AERMOD.astype(str).str.zfill(8)
    frame['fin_LST']=pd.to_datetime(stamps.str[:6],format='%y%m%d')+pd.to_timedelta(stamps.str[6:].astype(int),unit='h')
    frame['inicio_civil']=(frame.fin_LST-pd.Timedelta(hours=1)+pd.Timedelta(hours=3 if season=='VERANO' else 4)).dt.tz_localize('UTC').dt.tz_convert('America/Santiago')
    frame['day']=frame.inicio_civil.dt.strftime('%Y-%m-%d')
    return frame
def native_bytes(folder,archive,receipt,name):
    p=folder/name
    if p.exists():data=p.read_bytes()
    else:
        with tarfile.open(archive,'r:gz') as z:data=z.extractfile(name).read()
    assert hashlib.sha256(data).hexdigest()==receipt['outputs'][name],str(p)
    return data
def reproduce():
    catalog={}
    for base in [A,B]:
        for path in (base/'Recibos').glob('*.json'):
            r=read(path)
            if r['id'] in catalog:
                assert r['outputs']['receptor_horas.out']==catalog[r['id']][1]['outputs']['receptor_horas.out']
            else:catalog[r['id']]=(path,r)
    assert len(catalog)==3276
    frames=[];audit=[];inputs=[];raw=valid=0
    resume=OUT/'Reproduccion_parcial.pkl'
    if resume.exists():
        state=pd.read_pickle(resume);frames=state['frames'];audit=state['audit'];inputs=state['inputs'];raw=state['raw'];valid=state['valid']
        for q in audit:assert sha(Path(q['receipt']))==q['receipt_sha256']
    done={q['case'] for q in audit}
    for i,(cid,(path,r)) in enumerate(sorted(catalog.items())):
        if cid in done:continue
        folder=Path(r['result_folder']);archive=Path(r.get('archive',str(folder/'archive_not_required_when_native_present.tar.gz')))
        data=native_bytes(folder,archive,r,'receptor_horas.out')
        h=pd.read_csv(io.BytesIO(data),sep=r'\s+',comment='*',header=None,usecols=[0,1,2,8],names=['x_m','y_m','raw','fecha_AERMOD'])
        maskpath=folder/'Horario_con_mascara.csv';assert sha(maskpath)==r['outputs']['Horario_con_mascara.csv']
        mask=pd.read_csv(maskpath,usecols=['x_m','y_m','fecha_AERMOD','C_ug_m3'])
        h=h.merge(mask,on=['x_m','y_m','fecha_AERMOD'],validate='one_to_one')
        # Pilot receipts use different QA field names; derive the native calendar independently.
        assert 0<h.fecha_AERMOD.nunique()<=24,cid
        assert len(h)==40*h.fecha_AERMOD.nunique()
        good=h.C_ug_m3.notna();assert np.allclose(h.loc[good,'raw'],h.loc[good,'C_ug_m3'],rtol=0,atol=1e-10)
        h['value']=h.raw.where(good);raw+=len(h);valid+=int(good.sum())
        h['receptor']=[REC.get((x,y)) for x,y in zip(h.x_m,h.y_m)];h=h[h.receptor.notna()].copy()
        for k in ['season','scenario','pollutant']:h[k]=r[k]
        stamp(h,r['season']);frames.append(h[['season','scenario','pollutant','receptor','day','fin_LST','value']])
        inp=native_bytes(folder,archive,{'outputs':r['inputs']},'aermod.inp').decode(errors='replace')
        inputs.append({'case':cid,'emisunit':any('EMISUNIT' in z.upper() for z in inp.splitlines()),'background':any('BACKGROUND' in z.upper() or 'BACKGRND' in z.upper() for z in inp.splitlines())})
        audit.append({'case':cid,'receipt':str(path),'receipt_sha256':sha(path),'native_hourly_sha256':hashlib.sha256(data).hexdigest(),'mask_sha256':sha(maskpath),'native_hours':h.fecha_AERMOD.nunique()})
        if (i+1)%400==0:
            pd.to_pickle({'frames':frames,'audit':audit,'inputs':inputs,'raw':raw,'valid':valid},resume)
            print(f'Reproduced {i+1}/3276 cases',flush=True)
    h=pd.concat(frames,ignore_index=True)
    h.to_pickle(OUT/'Cache_horas_reproducidas.pkl')
    save('Cache_control.json',{'source_cases':audit,'raw':raw,'valid':valid,'inputs':inputs,'cache_sha256':sha(OUT/'Cache_horas_reproducidas.pkl')})
    assert not h.duplicated(['season','scenario','pollutant','receptor','fin_LST']).any()
    keys=['season','day','scenario','pollutant','receptor']
    d=h.groupby(keys).value.agg(['mean','sum','count','size','max']).reset_index()
    original=pd.concat([pd.read_csv(x/'Medias_diarias_civiles.csv') for x in [A,B]]).query('receptor != "Panel"').drop_duplicates(keys)
    z=d.merge(original,on=keys,validate='one_to_one')
    assert len(z)==len(original)==13104
    error=float(np.max(abs(z['mean']-z.media_horas_validas_ug_m3)))
    assert error<1e-9 and (z['count']==z.horas_validas).all() and (z['size']==z.target_hours).all()
    d=z[keys+['mean','sum','count','size','max','complete_civil_day']].copy()
    csv('Diarios_reproducidos_cuatro_receptores.csv',d)
    period=h.groupby(['season','scenario','pollutant','receptor']).value.agg(['mean','sum','count']).reset_index()
    prior=pd.concat([pd.read_csv(x/'Resumen_periodo_comparable.csv') for x in [A,B]]).query('receptor != "Panel"')
    # Keep the explicit source column name in a diagnostic if schemas change.
    csv('Medias_periodo_reproducidas.csv',period)
    sel=pd.read_csv(C/'Seleccion_numerica_32_indicadores.csv');checked=[]
    common={}
    for season in ['VERANO','INVIERNO']:
        good=d[(d.season==season)&(d['count']==24)&(d['size']==24)&d.complete_civil_day]
        counts=good.groupby('day').size();days=set(counts[counts==9*2*4].index);common[season]=days
    for r in sel.itertuples():
        if r.metric=='media_periodo':g=period[(period.season==r.season)&(period.pollutant==r.pollutant)&(period.receptor==r.receptor)];value=g['mean'].max();chosen=g.set_index('scenario').loc[r.scenario,'mean']
        else:
            g=d[(d.season==r.season)&(d.pollutant==r.pollutant)&(d.receptor==r.receptor)&d.day.isin(common[r.season])];value=g['mean'].max();chosen=g[(g.scenario==r.scenario)&(g.day==r.day)]['mean'].iloc[0]
        assert np.allclose([value,chosen],[r.value,r.value],rtol=0,atol=1e-9)
        checked.append({'season':r.season,'pollutant':r.pollutant,'receptor':r.receptor,'metric':r.metric,'error':abs(value-r.value)})
    joint=pd.read_csv(B/'Tabla_conjunto_cuatro_receptores.csv')
    piv=period.pivot(index=['season','pollutant','receptor'],columns='scenario',values='mean')
    for r in joint.itertuples():
        g=piv.loc[(r.season,r.pollutant,r.receptor)]
        assert abs((g.T_WS_PLUS-g.T_PLUS-g.WS_PLUS+g.BASE)-r.interaccion_ug_m3)<1e-9
    # Descriptive order statistic in the strict common subset; never called annual legal P98.
    metrics=[]
    for key,g in d.groupby(['season','scenario','pollutant','receptor']):
        season,sc,pol,rec=key;v=g[g.day.isin(common[season])]['mean'].to_numpy();n=len(v);k=int(math.floor(.98*n+.5));assert n in [87,90]
        sortedv=np.sort(v);rounded=np.floor(v+.5)
        metrics.append(dict(season=season,scenario=sc,pollutant=pol,receptor=rec,n_days=n,k_ordinal=k,mean_strict=v.mean(),sd_strict=v.std(ddof=1),median_strict=np.median(v),P98_subset_raw=sortedv[k-1],P98_subset_rounded=np.sort(rounded)[k-1] if pol=='MP25' else np.nan,max_daily=v.max(),days_above50_raw=int((v>50).sum()) if pol=='MP25' else None,days_above50_rounded=int((rounded>50).sum()) if pol=='MP25' else None,MP10_normalization='NOT_ESTABLISHED_NO_THRESHOLD_COMPARISON' if pol=='MP10' else 'NOT_APPLICABLE',legal_compliance='NOT_EVALUATED'))
    metrics=pd.DataFrame(metrics);csv('Indicadores_descriptivos_submuestra.csv',metrics)
    # Year partition is visible; summer spans two calendar years and cannot be treated as one year.
    years=d[d.apply(lambda r:r.day in common[r.season],axis=1)].copy();years['year']=years.day.str[:4]
    yearly=years.groupby(['season','year','scenario','pollutant','receptor']).agg(n_available=('mean','size'),max_available=('mean','max')).reset_index();yearly['full_calendar_year']=False
    csv('Cobertura_por_ano_calendario.csv',yearly)
    save('Auditoria_unidades.json',{'inputs_checked':len(inputs),'emisunit_present':sum(x['emisunit'] for x in inputs),'background_in_main_input':sum(x['background'] for x in inputs),'native_units':'micrograms per cubic meter (AERMOD default)','MP10_normal_volume_conversion':'not found in audited output reconstruction; compatibility not established','normal_condition_Chile':{'T_K':298.15,'P_Pa':101325},'action':'Do not relabel raw model output as ug/m3N. No MP10 legal-threshold ratios or exceedance counts produced.','source':'AERMOD guide v26135 section 3.3.13 and audited main input/postprocessing files'})
    save('Trazabilidad_reproduccion.json',audit)
    save('Verificacion_reproduccion.json',{'status':'PASSED','checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'native_seasonal_cases':3276,'native_hourly_values':raw,'valid_hourly_values':valid,'daily_sensitive_rows':len(z),'maximum_daily_error':error,'selected_indicators_reproduced':len(checked),'joint_interactions_reproduced':16,'common_24h_days':{k:len(v) for k,v in common.items()},'source':'native receptor_horas.out values checked against receipt SHA256, with audited mask; civil calendar rebuilt independently','new_simulations':0,'MP10_legal_units_established':False})
    print(json.dumps(read(OUT/'Verificacion_reproduccion.json')))

def regimes():
    sys.path.insert(0,str(ROOT/'work/seleccion_adversa_20261104'))
    from analizar import sfc
    paths={'VERANO':OLD/'outputs/Discrepancias_ajuste_2026-10-19/Residuos_ajuste.csv','INVIERNO':OLD/'outputs/Diagnostico_meteorologico_invierno_2026-10-25/Residuos_ajuste.csv'}
    parts=[];summary=[]
    for season,day in [('VERANO','2017-01-16'),('INVIERNO','2017-07-09')]:
        obs=pd.read_csv(paths[season]);obs=obs[obs.valido_conjunto==True].copy();obs['date']=pd.to_datetime(obs.fecha_local);obs=obs[obs.date.dt.strftime('%Y-%m-%d')==day].copy()
        obs['hour_start']=obs.date.dt.floor('h');obs['WS_obs']=np.hypot(obs.u_obs_m_s,obs.v_obs_m_s);obs['WD_obs']=np.degrees(np.arctan2(-obs.u_obs_m_s,-obs.v_obs_m_s))%360
        for sc in ['BASE','OBS_U']:
            met,_=sfc(season,sc,P/'Meteorologia'/season/sc if sc=='OBS_U' else None)
            met=met[met.day==day].copy();met['hour_start']=met.inicio_civil.dt.tz_localize(None)
            j=met.merge(obs,on='hour_start',validate='one_to_one');assert len(j)>0
            j['WD_abs_diff']=abs((j.WD-j.WD_obs+180)%360-180)
            summary.append(dict(season=season,day=day,scenario=sc,paired_hours=len(j),observed_WS_mean=j.WS_obs.mean(),SFC_WS_mean=j.WS.mean(),WS_MAE_rough=np.mean(abs(j.WS-j.WS_obs)),observed_hours_WS_lt1=int((j.WS_obs<1).sum()),SFC_hours_WS_lt1=int((j.WS<1).sum()),observed_hours_WS_lt2=int((j.WS_obs<2).sum()),SFC_hours_WS_lt2=int((j.WS<2).sum()),WD_mean_absolute_difference_rough=j.WD_abs_diff.mean(),comparison='station instantaneous :49 vs model reference hourly; spatial/vertical/time-support mismatch, no independent validation'))
            j['scenario']=sc;j['season']=season;j['day']=day
            parts.append(j[['season','day','scenario','hour_start','WS_obs','WD_obs','WS','WD','L','T_K','WD_abs_diff']])
    csv('Contraste_regimen_horario.csv',pd.concat(parts));csv('Contraste_regimen_resumen.csv',pd.DataFrame(summary))
    save('Fuentes_regimen.json',[{'path':str(p),'sha256':sha(p)} for p in paths.values()])
    print(pd.DataFrame(summary).to_string(index=False))
if __name__=='__main__':
    if '--regimes' in sys.argv:regimes()
    else:reproduce();regimes()
