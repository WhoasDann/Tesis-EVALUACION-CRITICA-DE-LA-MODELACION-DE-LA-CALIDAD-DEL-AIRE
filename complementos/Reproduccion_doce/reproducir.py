"""Reproduce indicadores finales desde concentraciones horarias archivadas.
Uso: python reproducir.py salida
No ejecuta WRF, MMIF, AERMET ni AERMOD. Requiere numpy, pandas y tzdata.
"""
from pathlib import Path
import sys, json, hashlib, itertools
import pandas as pd
import numpy as np

BASE=Path(__file__).resolve().parent
SC=['BASE','T_MINUS','T_PLUS','WS_MINUS','WS_PLUS','T_MINUS_WS_MINUS','T_MINUS_WS_PLUS','T_PLUS_WS_MINUS','T_PLUS_WS_PLUS','WS_MINUS_INV','T_MINUS_WS_MINUS_INV','T_PLUS_WS_MINUS_INV']
RECS=['Los Bronces','Piedra Carvajal','Sulfatos','La Paloma']

def main():
    out=Path(sys.argv[1] if len(sys.argv)>1 else 'salida').resolve()
    if out.exists(): raise SystemExit('La carpeta de salida debe ser nueva para conservar intentos previos.')
    manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    for rel,wanted in manifest['files'].items():
        p=BASE/rel
        if hashlib.sha256(p.read_bytes()).hexdigest()!=wanted: raise SystemExit('Hash distinto: '+rel)
    out.mkdir(parents=True)
    allmeans=[]; selections=[]; interactions=[]; order=[]; daily=[]; coverage=[]
    for season,pol in itertools.product(['VERANO','INVIERNO'],['MP10','MP25']):
        h=pd.read_csv(BASE/'datos'/f'Horas_comunes_{season}_{pol}.csv.gz')
        assert h.comun_doce.all() and not h.duplicated(['x_m','y_m','fecha_AERMOD']).any()
        assert h[SC].notna().all().all() and len(h)==40*(2150 if season=='VERANO' else 2205)
        stamp=h.fecha_AERMOD.astype(str).str.zfill(8)
        start=pd.to_datetime(stamp.str[:6],format='%y%m%d')+pd.to_timedelta(stamp.str[6:].astype(int)-1,unit='h')
        civil=start.dt.strftime('%Y-%m-%d') if season=='VERANO' else (start+pd.Timedelta(hours=4)).dt.tz_localize('UTC').dt.tz_convert('America/Santiago').dt.strftime('%Y-%m-%d')
        assert civil.eq(h.civil).all()
        h=h[h.receptor.isin(RECS)]
        d=h.groupby(['receptor','civil'])[SC].mean()
        n=h.groupby(['receptor','civil']).size()
        d=d[n==24].reset_index()
        assert d.groupby('receptor').size().eq(86 if season=='VERANO' else 90).all()
        means=d.groupby('receptor')[SC].mean()
        d['season']=season;d['pollutant']=pol;daily.append(d)
        coverage.append(dict(season=season,pollutant=pol,hours=len(h)//4,days=len(d)//4))
        for r in RECS:
            g=d[d.receptor==r];m=means.loc[r];mx=g[SC].max();ms=m.idxmax();ds=mx.idxmax();row=g.loc[g[ds].idxmax()]
            for sc in SC:allmeans.append(dict(season=season,pollutant=pol,receptor=r,scenario=sc,mean=float(m[sc])))
            selections.append(dict(season=season,pollutant=pol,receptor=r,mean_scenario=ms,maximum_mean=float(m[ms]),day_scenario=ds,day=row.civil,maximum_day=float(row[ds]),BASE_same_day=float(row.BASE),percent=float(100*(row[ds]/row.BASE-1))))
            for a,b in itertools.product(['MINUS','PLUS'],repeat=2):
                sc=f'T_{a}_WS_{b}'
                interactions.append(dict(season=season,pollutant=pol,receptor=r,scenario=sc,interaction=float(m[sc]-m[f'T_{a}']-m[f'WS_{b}']+m.BASE)))
            for a in ['MINUS','PLUS']:
                sc=f'T_{a}_WS_MINUS_INV'
                interactions.append(dict(season=season,pollutant=pol,receptor=r,scenario=sc,interaction=float(m[sc]-m[f'T_{a}']-m.WS_MINUS_INV+m.BASE)))
        for r1,r2 in itertools.combinations(RECS,2):
            b=float(means.loc[r1,'BASE']-means.loc[r2,'BASE'])
            for sc in SC[1:]:
                v=float(means.loc[r1,sc]-means.loc[r2,sc])
                order.append(dict(season=season,pollutant=pol,r1=r1,r2=r2,scenario=sc,base_gap=b,scenario_gap=v,reversal=bool(b*v<0)))
    tables={'Medias_recalculadas':allmeans,'Seleccion':selections,'Interacciones':interactions,'Orden_medias':order}
    for name,rows in tables.items():pd.DataFrame(rows).to_csv(out/f'{name}.csv',index=False)
    pd.concat(daily).to_csv(out/'Diarios_cuatro_receptores.csv.gz',index=False)
    comparisons=[]
    for name,keys,nums,cats in [
        ('Medias_recalculadas',['season','pollutant','receptor','scenario'],['mean'],[]),
        ('Interacciones',['season','pollutant','receptor','scenario'],['interaction'],[]),
        ('Orden_medias',['season','pollutant','r1','r2','scenario'],['base_gap','scenario_gap'],['reversal']),
        ('Seleccion',['season','pollutant','receptor'],['maximum_mean','maximum_day','BASE_same_day','percent'],['mean_scenario','day_scenario','day'])]:
        calc=pd.DataFrame(tables[name]); ref=pd.read_csv(BASE/'referencia'/f'{name}.csv')
        c=calc.merge(ref,on=keys,suffixes=('_calc','_ref'),validate='one_to_one')
        assert len(c)==len(calc)==len(ref)
        for col in nums:assert np.allclose(c[col+'_calc'],c[col+'_ref'],rtol=0,atol=1e-9)
        for col in cats:assert c[col+'_calc'].eq(c[col+'_ref']).all()
        comparisons.append(dict(table=name,rows=len(c)))
    report=dict(status='PASSED',coverage=coverage,tables=comparisons,seasonal_reversals=sum(x['reversal'] for x in order),note='La tolerancia de reproducción 1e-9 solo cubre agregación aritmética; no es delta_J de H1/H2 ni validación física.')
    (out/'Verificacion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
