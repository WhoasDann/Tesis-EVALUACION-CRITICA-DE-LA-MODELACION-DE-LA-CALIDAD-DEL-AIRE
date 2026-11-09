"""Evaluación temporal adicional con candidato fijo; diseño, predicción y métrica separados."""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
import pandas as pd
from netCDF4 import Dataset,chartostring

ROOT=Path(__file__).resolve().parents[1];O=ROOT/'outputs'
OUT=O/'Evaluacion_febrero_2026-10-21'
sys.path.insert(0,str(O/'Biblioteca_Tesis'))
from tesis.comun import sha256,guardar_json
from tesis.extraer_wrf import punto_malla
from tesis.validacion import bilineal,rotar_a_tierra,componentes
from tesis.reloj import muestrear_wrf,a_utc
from comparacion_cronologica_20261020 import fit_ridge,conditional,features
from generador_meteorologico_20261020 import crps,correlation
from revisar_generador_20261020 import crps_cdf

FIT=O/'Discrepancias_ajuste_2026-10-19/Residuos_ajuste.csv'
OBS_PATH=O/'Datos_Auditados/Observaciones/observaciones_normalizadas.csv'
BASE=['T2_C','u_earth_m_s','v_earth_m_s'];OBS=['Temperatura_aire_C','u_obs_m_s','v_obs_m_s']
RES=['residuo_T_C','residuo_u_m_s','residuo_v_m_s']
START='2017-02-01';END='2017-02-08'

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def rec(p):return dict(path=str(Path(p).resolve()),sha256=sha256(p))
def verify(items):
    for r in items:assert sha256(r['path'])==r['sha256'],r['path']

def prepare():
    assert not OUT.exists(),'No sobrescribir diseño'
    prior=O/'Comparacion_cronologica_2026-10-20'
    verify(read(prior/'Congelacion.json')['archivos'])
    verify(read(prior/'Recepcion/Verificacion.json')['archivos'])
    clock=read(O/'Actualizacion_2026-10-09/Reloj/manifest.json')
    assert sha256(OBS_PATH)==clock['obs_sha256']
    histories=[O/'Datos_Auditados/WRF_Disponible/manifest.json',
        Path(r'/archivo/usuario\Documents\Codex\2026-10-10\ten\outputs\Piloto_meteorologico\resumen_entrega.json'),
        prior/'Diseno.json',O/'Generador_meteorologico_2026-10-20/Diseno.json']
    histories=[p for p in histories if p.exists()]
    old=read(histories[0]);assert pd.Timestamp(old['ultima_utc'])<pd.Timestamp(START+' 03:00')
    inv=read(O/'Verano_WRF_cierre_efectivo_2026-10-13/inventario_archivos.json')
    desired=pd.date_range(START+' 03:00',END+' 03:00',freq='h')
    selected=[r for r in inv if pd.DatetimeIndex(pd.to_datetime(r['times'])).isin(desired).any()]
    stamps=[t for r in selected for t in pd.to_datetime(r['times']) if t in desired]
    assert pd.DatetimeIndex(stamps).equals(desired)
    OUT.mkdir()
    audit=dict(estado='AUDITORIA_USO_ADICIONAL',ultima_extraccion_anterior_UTC=old['ultima_utc'],
        piloto_anterior='21dic–30ene; pares y evaluación abierta24–30ene.',
        observaciones='La tabla completa de observaciones ya tuvo auditorías de rangos, faltantes y procedencia; no es una muestra nunca vista.',
        conclusion='1–7feb queda fuera de entrenamiento y comparaciones de discrepancias documentadas. Evaluación adicional temporal con exposición descriptiva previa, no validación externa plenamente ciega.',
        alcance_auditoria='Manifiestos y códigos locales revisados; no certifica ausencia de uso fuera de estos registros.',
        evidencia=[rec(p) for p in histories])
    guardar_json(OUT/'Historial_uso.json',audit)
    plan=dict(fecha='2026-10-21',ajuste=['2016-12-21','2017-01-20'],inicio=START,fin_exclusivo=END,
        motivo='Primera semana completa de febrero, mes siguiente al piloto; elegida sin puntuaciones de esta semana.',
        separacion_dias=11,horas_esperadas=168,modelo='Ridge0.1 con T/u/v WRF y sin/cos24h; innovaciones conjuntas L24; mismo candidato de comparación interna.',
        cambios_tras_metricas='Ninguno; no retocar parámetros, reloj, ventanas o bandas para esta evaluación.',
        miembros=1024,semilla=[20261021,20170201,24],modelos=['BASE','RIDGE','G1_24','RIDGE_24'],
        predicciones='Se congelan antes de leer valores observados de evaluación; no se ocultan errores ni extrapolación.',
        exposicion_previa=True,validacion_externa=False,reloj='H-CIVIL, :49, WRF interpolado al instante; sin -2h/+11min',
        punto_estacion=dict(lon=-70.27406281695315,lat=-33.22172401465386),
        limite='Estación de meteorología, no receptor de concentración. Muestreo bilineal terrestre igual al ajuste. No acredita transferencia al dominio/perfil.',
        reglas='Misma máscara conjunta; huecos conservados; CRPS por variable, cobertura/anchura, sesgo, persistencia y soporte. No selección por concentración.',
        WRF=selected)
    guardar_json(OUT/'Diseno.json',plan)
    guardar_json(OUT/'Congelacion.json',dict(estado='DISENO_FIJO_ANTES_EVALUACION',archivos=[rec(p) for p in
        [Path(__file__),FIT,OBS_PATH,OUT/'Diseno.json',OUT/'Historial_uso.json',ROOT/'work/comparacion_cronologica_20261020.py',
         ROOT/'work/generador_meteorologico_20261020.py',ROOT/'work/revisar_generador_20261020.py',O/'Biblioteca_Tesis/tesis/reloj.py',O/'Biblioteca_Tesis/tesis/extraer_wrf.py']]))
    print('Diseño1–7feb congelado, sin métricas observadas.',flush=True)

def predict():
    verify(read(OUT/'Congelacion.json')['archivos'])
    assert not (OUT/'Predicciones.npz').exists()
    plan=read(OUT/'Diseno.json');rows=[]
    desired=pd.date_range(START+' 03:00',END+' 03:00',freq='h')
    for item in plan['WRF']:
        path=Path(item['path']);assert sha256(path)==item['sha256']
        with Dataset(path) as n:
            n.set_auto_mask(False)
            point=plan['punto_estacion'];fx,fy=punto_malla(n,point['lon'],point['lat'])
            assert int(n.GRID_ID)==3
            for t,stamp in enumerate(chartostring(n['Times'][:])):
                when=pd.Timestamp(str(stamp).replace('_',' '))
                if when not in desired:continue
                c=n['COSALPHA'][0 if n['COSALPHA'].shape[0]==1 else t]
                s=n['SINALPHA'][0 if n['SINALPHA'].shape[0]==1 else t]
                u,v=rotar_a_tierra(np.asarray(n['U10'][t],float),np.asarray(n['V10'][t],float),np.asarray(c,float),np.asarray(s,float))
                rows.append(dict(fecha_wrf_utc=str(when),T2_C=float(bilineal(n['T2'][t],fx,fy)-273.15),
                    u_earth_m_s=float(bilineal(u,fx,fy)),v_earth_m_s=float(bilineal(v,fx,fy))))
    hourly=pd.DataFrame(rows);assert pd.DatetimeIndex(pd.to_datetime(hourly.fecha_wrf_utc)).equals(desired)
    hourly.to_csv(OUT/'WRF_estacion_horario.csv',index=False,encoding='utf-8-sig')
    times=pd.date_range(START+' 00:49',periods=168,freq='h')
    base=muestrear_wrf(hourly,a_utc(times,'civil_santiago'),operador='interpolacion_instantanea')
    base['fecha_local']=times;base.to_csv(OUT/'Predictores.csv',index=False,encoding='utf-8-sig')
    fit=pd.read_csv(FIT,parse_dates=['fecha_local']);assert len(fit)==744
    x,xt=features(fit),features(base);r=fit[RES].to_numpy()
    model=fit_ridge(x,r);m=conditional(x,model);mt=conditional(xt,model)
    eps=r-m
    starts=np.array([i for i in range(0,len(r)-23,24) if np.isfinite(r[i:i+24]).all()]);assert len(starts)==26
    rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence(plan['semilla'])))
    chosen=rng.choice(starts,size=(1024,7),replace=True)
    indices=(chosen[:,:,None]+np.arange(24)).reshape(1024,168)
    pool=eps[starts[:,None]+np.arange(24)];center=pool.mean(axis=(0,1))
    b=base[BASE].to_numpy();pred=dict(BASE=b,RIDGE=b+mt,G1_24=b[None]+r[indices],RIDGE_24=b[None]+mt[None]+eps[indices]-center)
    assert all(np.isfinite(v).all() for v in pred.values())
    # Reconstrucción independiente del ajuste por mínimos cuadrados aumentados.
    ok=np.isfinite(np.c_[x,r]).all(axis=1);z=(x[ok]-model['mu'])/model['scale']
    coef=np.linalg.lstsq(np.r_[z,np.sqrt(ok.sum()*.1)*np.eye(5)],np.r_[r[ok]-model['intercept'],np.zeros((5,3))],rcond=None)[0]
    np.testing.assert_allclose(coef,model['coef'],atol=1e-12,rtol=0)
    np.savez_compressed(OUT/'Predicciones.npz',**pred,indices=indices,starts=starts,chosen=chosen,mean_train=m,mean_target=mt,
        pool_center=center,mu=model['mu'],scale=model['scale'],coef=model['coef'],intercept=model['intercept'])
    support=((xt[:,:3]<np.nanmin(x[:,:3],axis=0))|(xt[:,:3]>np.nanmax(x[:,:3],axis=0)))
    guardar_json(OUT/'Modelo_y_soporte.json',dict(n_ajuste=model['n'],bloques24=len(starts),
        horas_fuera_rango=int(support.any(axis=1).sum()),fuera_rango_por_variable=support.sum(axis=0).tolist(),
        modelo={k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in model.items()},
        centro_pool=center.tolist(),huella_predictores=rec(OUT/'Predictores.csv')))
    guardar_json(OUT/'Predicciones_congeladas.json',dict(estado='PREDICCIONES_ANTES_OBSERVACIONES',archivos=[rec(OUT/n) for n in
        ['Congelacion.json','Predicciones.npz','Predictores.csv','WRF_estacion_horario.csv','Modelo_y_soporte.json']]))
    print('Predicciones fijas:168h,1024 miembros. Valores observados aún no leídos.',flush=True)

def evaluate():
    verify(read(OUT/'Congelacion.json')['archivos']);verify(read(OUT/'Predicciones_congeladas.json')['archivos'])
    assert not (OUT/'Evaluacion').exists()
    dest=OUT/'Evaluacion';dest.mkdir()
    obs=pd.read_csv(OBS_PATH,parse_dates=['Fecha_original'])
    obs=obs[(obs.Fecha_original>=START)&(obs.Fecha_original<END)].copy()
    assert not obs.Fecha_original.duplicated().any() and obs.Fecha_original.dt.minute.eq(49).all()
    obs['u_obs_m_s'],obs['v_obs_m_s']=componentes(obs.Velocidad_viento_m_s,obs.Direccion_viento_grados)
    pred=pd.read_csv(OUT/'Predictores.csv',parse_dates=['fecha_local'])
    d=pred.merge(obs,left_on='fecha_local',right_on='Fecha_original',how='left',validate='one_to_one')
    valid=np.isfinite(d[BASE+OBS].to_numpy()).all(axis=1)
    assert not ((d.Velocidad_viento_m_s<0)|((d.Direccion_viento_grados<0)|(d.Direccion_viento_grados>360))).any()
    d['valido_conjunto']=valid;d.to_csv(dest/'Pares.csv',index=False,encoding='utf-8-sig')
    arrays=np.load(OUT/'Predicciones.npz');actual=d[OBS].to_numpy();base=d[BASE].to_numpy()
    metrics=[];hourly=[];deps=[];maxdiff=0.
    for name in ['BASE','RIDGE','G1_24','RIDGE_24']:
        a=arrays[name];p=a if a.ndim==3 else a[None];mean=p.mean(axis=0)
        score=crps(p[:,valid],actual[valid])
        independent=np.array([[crps_cdf(p[:,t,j],actual[t,j]) for j in range(3)] for t in np.flatnonzero(valid)])
        np.testing.assert_allclose(score,independent,atol=2e-12,rtol=0);maxdiff=max(maxdiff,float(np.abs(score-independent).max()))
        for j,var in enumerate(['T','u','v']):
            errors=mean[valid,j]-actual[valid,j]
            row=dict(modelo=name,variable=var,n=int(valid.sum()),CRPS=float(score[:,j].mean()),sesgo=float(errors.mean()),RMSE=float(np.sqrt(np.mean(errors**2))))
            for level in [.5,.8,.9]:
                lo,hi=np.quantile(p[:,valid,j],[(1-level)/2,(1+level)/2],axis=0)
                row[f'cobertura{int(level*100)}']=float(((actual[valid,j]>=lo)&(actual[valid,j]<=hi)).mean())
                row[f'anchura{int(level*100)}']=float((hi-lo).mean())
            metrics.append(row)
            lo,hi=np.quantile(p[:,:,j],[.05,.95],axis=0)
            for i,t in enumerate(np.flatnonzero(valid)):
                hourly.append(dict(modelo=name,variable=var,fecha_local=str(d.fecha_local.iloc[t]),observado=actual[t,j],media=mean[t,j],inferior90=lo[t],superior90=hi[t],CRPS=score[i,j]))
        if a.ndim==3:
            syn=p-base[None];real=actual-base;syn[:,~valid,:]=np.nan;real[~valid]=np.nan
            for j,var in enumerate(['T','u','v']):
                for lag in [1,6,24,48]:
                    values=[correlation(member[:-lag,j],member[lag:,j]) for member in syn]
                    deps.append(dict(modelo=name,variable=var,lag=lag,pares=int((valid[:-lag]&valid[lag:]).sum()),
                        observada=correlation(real[:-lag,j],real[lag:,j]),mediana=float(np.nanmedian(values)),p05=float(np.nanquantile(values,.05)),p95=float(np.nanquantile(values,.95))))
    table=pd.DataFrame(metrics);table.to_csv(dest/'Metricas.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(hourly).to_csv(dest/'Horario.csv',index=False,encoding='utf-8-sig');pd.DataFrame(deps).to_csv(dest/'Dependencia.csv',index=False,encoding='utf-8-sig')
    guardar_json(dest/'Verificacion.json',dict(estado='EVALUACION_ADICIONAL_CALCULADA',horas=168,validas=int(valid.sum()),
        diferencia_max_CRPS_independiente=maxdiff,modelo_reajustado=False,validacion_externa=False,
        archivos=[rec(p) for p in dest.iterdir() if p.is_file()]))
    print(table[['modelo','variable','n','CRPS','sesgo','cobertura90']].to_string(index=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('etapa',choices=['preparar','predecir','evaluar'])
    a=p.parse_args();{'preparar':prepare,'predecir':predict,'evaluar':evaluate}[a.etapa]()
