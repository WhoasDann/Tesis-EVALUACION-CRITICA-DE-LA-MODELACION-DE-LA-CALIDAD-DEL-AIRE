from pathlib import Path
import json,hashlib,io,datetime
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'outputs/Seleccion_adversa_2026-11-04/Contraste_ternas_observadas'
OUT=ROOT/'outputs/Normativa_reproduccion_2026-11-04'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
design=read(P/'Diseno.json');plan=read(P/'Lote_local/plan.json');parts=[];raw=valid=0
for c in plan['cases']:
    r=read(P/'Recibos_cientificos'/(c['id']+'.json'))
    data=(P/'Lote_local'/c['folder']/'receptor_horas.out').read_bytes()
    assert hashlib.sha256(data).hexdigest()==r['outputs']['receptor_horas.out']
    h=pd.read_csv(io.BytesIO(data),sep=r'\s+',comment='*',header=None,usecols=[0,1,2,8],names=['x_m','y_m','C','stamp'])
    h['stamp']=h.stamp.astype(str).str.zfill(8);assert h.stamp.map(c['hour_states']).eq('VALIDA').all()
    assert len(h)==960 and np.isfinite(h.C).all();raw+=len(h);valid+=len(h)
    end=pd.to_datetime(h.stamp.str[:6],format='%y%m%d')+pd.to_timedelta(h.stamp.str[6:].astype(int),unit='h')
    begin=(end-pd.Timedelta(hours=1)+pd.Timedelta(hours=3 if c['season']=='VERANO' else 4)).dt.tz_localize('UTC').dt.tz_convert('America/Santiago')
    h['day']=begin.dt.strftime('%Y-%m-%d')
    h=h[h.day.isin(design['civil_days'][c['season']])].copy()
    for k in ['season','scenario','pollutant']:h[k]=c[k]
    parts.append(h)
h=pd.concat(parts);assert len(h)==30720
keys=['season','day','scenario','pollutant','x_m','y_m']
d=h.groupby(keys).C.agg(['mean','count']).reset_index();assert len(d)==1280 and d['count'].eq(24).all()
old=pd.read_csv(P/'Medias_diarias_civiles.csv');z=d.merge(old,on=keys,validate='one_to_one',suffixes=('_new','_old'))
assert len(z)==1280;err=float(abs(z.mean_new-z.mean_old).max());assert err<1e-9
result={'status':'PASSED','checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'native_cases':len(parts),'raw_hourly_values':raw,'valid_hourly_values':valid,'civil_target_values':len(h),'civil_daily_rows':len(d),'sensitive_daily_rows':int(z.receptor.ne('Panel').sum()),'maximum_absolute_error':err,'simulations_repeated':0}
(OUT/'Verificacion_ternas.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
