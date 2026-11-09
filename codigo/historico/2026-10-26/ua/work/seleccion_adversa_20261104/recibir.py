"""Independent scientific reception and common-civil-day comparison of the small batch."""
from piloto import *
import tarfile
def receive():
    root=PILOT/'Lote_local';plan=read(root/'plan.json');design=read(PILOT/'Diseno.json')
    (PILOT/'Recibos_cientificos').mkdir(exist_ok=True)
    frames=[];summary=[];nproducts=0
    for case in plan['cases']:
        rp=root/'receipts'/(case['id']+'.json')
        if not rp.exists():continue
        r=read(rp);folder=root/case['folder'];archive=root/'exports'/(case['id']+'.tar.gz')
        assert r['status']=='NATIVE_CHECK_PASSED_PENDING_SCIENTIFIC_RECEPTION' and r['inputs']==case['inputs'] and r['binary_sha256']==plan['binary_sha256']
        with tarfile.open(archive,'r:gz') as z:
            for name,h in r['outputs'].items():
                assert hashlib.sha256(z.extractfile(name).read()).hexdigest()==h
                if (folder/name).exists():assert sha(folder/name)==h
                nproducts+=1
        for name,h in case['inputs'].items():assert sha(case['input_sources'][name])==h
        rows=[]
        for line in (folder/'receptor_horas.out').read_text().splitlines():
            if not line.strip() or line.startswith('*'):continue
            a=line.split();assert a[6:8]==['1-HR','ALL']
            x,y,c=map(float,a[:3]);stamp=a[8];assert stamp in case['hour_states'] and np.isfinite(c) and c>=0
            rows.append(dict(x_m=x,y_m=y,C_bruta_ug_m3=c,fecha_AERMOD=stamp,C_ug_m3=c if case['hour_states'][stamp]=='VALIDA' else np.nan))
        h=pd.DataFrame(rows);assert len(h)==case['receptors']*len(case['hour_states']);assert not h.duplicated(['x_m','y_m','fecha_AERMOD']).any()
        stamps=h.fecha_AERMOD
        h['fin_LST']=pd.to_datetime(stamps.str[:6],format='%y%m%d')+pd.to_timedelta(stamps.str[6:].astype(int),unit='h')
        offset=4 if case['season']=='INVIERNO' else 3
        h['inicio_civil']=(h.fin_LST-pd.Timedelta(hours=1)+pd.Timedelta(hours=offset)).dt.tz_localize('UTC').dt.tz_convert('America/Santiago')
        h['day']=h.inicio_civil.dt.strftime('%Y-%m-%d')
        for k in ['season','scenario','pollutant']:h[k]=case[k]
        pts={(380148.,6331485.):'Los Bronces',(381128.,6323667.):'Piedra Carvajal',(384254.,6324494.):'Sulfatos',(381759.,6327947.):'La Paloma'}
        h['receptor']=[pts.get((x,y),'Panel') for x,y in zip(h.x_m,h.y_m)]
        frames.append(h)
        q=dict(status='SCIENTIFIC_RECEPTION_PASSED',id=case['id'],raw_values=len(h),valid_values=int(h.C_ug_m3.notna().sum()),archive_sha256=sha(archive),inputs=r['inputs'],outputs=r['outputs'],seconds=r['execution']['seconds'])
        putjson(PILOT/'Recibos_cientificos'/(case['id']+'.json'),q);summary.append(q)
    complete=len(summary)==len(plan['cases']); meta=dict(status='COMPLETE_SCIENTIFIC_RECEPTION' if complete else 'RUNNING',received=len(summary),expected=len(plan['cases']),products_verified=nproducts,raw_hourly_values=sum(x['raw_values'] for x in summary),valid_hourly_values=sum(x['valid_values'] for x in summary),updated_utc=now())
    putjson(PILOT/'Recepcion.json',meta)
    if not complete:print(json.dumps(meta));return
    h=pd.concat(frames,ignore_index=True);assert not h.duplicated(['season','scenario','pollutant','x_m','y_m','fecha_AERMOD']).any()
    eligible=h.apply(lambda r:r['day'] in design['civil_days'][r['season']],axis=1);h=h[eligible]
    keys=['season','day','scenario','pollutant','x_m','y_m','receptor']
    d=h.groupby(keys).C_ug_m3.agg(['mean','max','size','count']).reset_index()
    assert d['size'].eq(24).all() and d['count'].eq(24).all();assert len(d)==1280
    d.to_csv(PILOT/'Medias_diarias_civiles.csv',index=False,encoding='utf-8-sig')
    d0=pd.read_csv(A/'Medias_diarias_civiles.csv');base=d0[(d0.scenario=='BASE')&d0.apply(lambda r:r.day in design['civil_days'][r.season],axis=1)]
    ref=base[['season','day','pollutant','x_m','y_m','media_horas_validas_ug_m3']].rename(columns={'media_horas_validas_ug_m3':'BASE'})
    pair=d.merge(ref,on=['season','day','pollutant','x_m','y_m'],validate='many_to_one');pair['delta_ug_m3']=pair['mean']-pair.BASE;pair['delta_pct']=np.where(pair.BASE>0,100*pair.delta_ug_m3/pair.BASE,np.nan)
    pair.to_csv(PILOT/'Comparacion_pareada.csv',index=False,encoding='utf-8-sig')
    four=pair[pair.receptor.ne('Panel')];four.to_csv(PILOT/'Comparacion_cuatro_receptores.csv',index=False,encoding='utf-8-sig')
    # Rich hourly profiles for new cases, without concentration-weighted causal claims.
    parts=[]
    for r in design['prototypes']:
        met,folder=sfc(r['season'],r['scenario'],PILOT/'Meteorologia'/r['season']/r['scenario'])
        x=h[(h.season==r['season'])&(h.scenario==r['scenario'])&h.receptor.ne('Panel')].merge(met[['fin_LST','WS','WD','L','zim','ustar','H','T_K']],on='fin_LST',validate='many_to_one');parts.append(x)
    pd.concat(parts).to_csv(PILOT/'Horas_cuatro_receptores.csv',index=False,encoding='utf-8-sig')
    picks=[]
    for key,g in four.groupby(['season','pollutant','receptor']):
        season,pol,rec=key;b=base[(base.season==season)&(base.pollutant==pol)&(base.receptor==rec)].sort_values('media_horas_validas_ug_m3',ascending=False).iloc[0]
        best=g.sort_values('mean',ascending=False).iloc[0];newwins=best['mean']>b.media_horas_validas_ug_m3
        paired=g.sort_values('delta_ug_m3',ascending=False).iloc[0]
        picks.append(dict(season=season,pollutant=pol,receptor=rec,scenario=best.scenario if newwins else 'BASE',day=best.day if newwins else b.day,maximum=best['mean'] if newwins else b.media_horas_validas_ug_m3,BASE_max=b.media_horas_validas_ug_m3,BASE_max_day=b.day,increase_pct=100*(best['mean']/b.media_horas_validas_ug_m3-1) if newwins else 0,highest_new=best['mean'],highest_new_scenario=best.scenario,highest_new_day=best.day,largest_paired_absolute_day=paired.day,largest_paired_absolute_scenario=paired.scenario,largest_paired_absolute_delta=paired.delta_ug_m3,largest_paired_absolute_pct=paired.delta_pct,admission='CONDITIONAL_EMPIRICAL_SENSITIVITY_NOT_DYNAMIC_VALIDATION'))
    pd.DataFrame(picks).to_csv(PILOT/'Seleccion_episodios_con_respaldo_conjunto.csv',index=False,encoding='utf-8-sig')
    meta.update(civil_case_receptor_rows=len(d),civil_target_cases=len(d)//40,target_civil_hourly_values=len(h),full_grid=False,seasonal_new_means=False)
    putjson(PILOT/'Recepcion.json',meta)
    print(json.dumps(meta));print(pd.DataFrame(picks).query('pollutant=="MP10"').to_string(index=False))
if __name__=='__main__':receive()
