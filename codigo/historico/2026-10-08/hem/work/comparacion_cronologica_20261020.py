"""Comparación interna expansiva: referencia por bloques y sesgo condicional.

Desarrollo retrospectivo dentro del ajuste ya inspeccionado. No evaluación externa.
Tres etapas separan diseño, predicciones y cálculo de métricas.
"""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/Comparacion_cronologica_2026-10-20'
FIT=ROOT/'outputs/Discrepancias_ajuste_2026-10-19/Residuos_ajuste.csv'
sys.path.insert(0,str(ROOT/'outputs/Biblioteca_Tesis'))
from tesis.comun import sha256,guardar_json
from generador_meteorologico_20261020 import crps,starts_complete,correlation

OBS=['Temperatura_aire_C','u_obs_m_s','v_obs_m_s']
BASE=['T2_C','u_earth_m_s','v_earth_m_s']
RES=['residuo_T_C','residuo_u_m_s','residuo_v_m_s']
LABELS=['T','u','v']
MODELS=['BASE','SES_GLOBAL','CICLO','RIDGE','G1_24','RIDGE_24']
MEMBERS,ALPHA,SEED=1024,.1,20261020
FOLDS=[
    dict(id=1,fin_ajuste='2017-01-04',inicio_validacion='2017-01-07',fin_validacion='2017-01-11'),
    dict(id=2,fin_ajuste='2017-01-08',inicio_validacion='2017-01-11',fin_validacion='2017-01-15'),
    dict(id=3,fin_ajuste='2017-01-12',inicio_validacion='2017-01-15',fin_validacion='2017-01-19'),
    dict(id=4,fin_ajuste='2017-01-16',inicio_validacion='2017-01-19',fin_validacion='2017-01-21')]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def records(paths):
    return [dict(path=str(Path(p).resolve()),sha256=sha256(p)) for p in paths]


def verify(entries):
    for row in entries:
        if sha256(row['path'])!=row['sha256']:
            raise ValueError('Archivo congelado cambiado: '+row['path'])


def load():
    d=pd.read_csv(FIT,parse_dates=['fecha_local'])
    assert len(d)==744 and d.fecha_local.is_unique
    expected=pd.date_range('2016-12-21 00:49','2017-01-20 23:49',freq='h')
    assert np.array_equal(d.fecha_local.to_numpy(),expected.to_numpy())
    valid=np.isfinite(d[OBS+BASE+RES].to_numpy(float)).all(axis=1)
    assert valid.sum()==737 and np.array_equal(valid,d.valido_conjunto.to_numpy(bool))
    np.testing.assert_allclose(d.loc[valid,OBS].to_numpy()-d.loc[valid,BASE].to_numpy(),
                               d.loc[valid,RES].to_numpy(),atol=1e-10,rtol=0)
    return d


def features(d):
    hour=d.fecha_local.dt.hour.to_numpy()+d.fecha_local.dt.minute.to_numpy()/60
    return np.c_[d[BASE].to_numpy(float),np.sin(2*np.pi*hour/24),np.cos(2*np.pi*hour/24)]


def fit_ridge(x,r):
    ok=np.isfinite(np.c_[x,r]).all(axis=1)
    a,y=x[ok],r[ok]
    mu=a.mean(axis=0); scale=a.std(axis=0); scale[scale<1e-12]=1
    z=(a-mu)/scale; intercept=y.mean(axis=0)
    coef=np.linalg.solve(z.T@z/len(z)+ALPHA*np.eye(z.shape[1]),z.T@(y-intercept)/len(z))
    return dict(mu=mu,scale=scale,intercept=intercept,coef=coef,n=len(z))


def conditional(x,model):
    return model['intercept']+(x-model['mu'])/model['scale']@model['coef']


def predict_fold(d,fold):
    t=d.fecha_local
    tr=np.flatnonzero((t<pd.Timestamp(fold['fin_ajuste'])).to_numpy())
    va=np.flatnonzero((t.ge(pd.Timestamp(fold['inicio_validacion']))&t.lt(pd.Timestamp(fold['fin_validacion']))).to_numpy())
    assert tr[0]==0 and np.all(np.diff(tr)==1) and np.all(np.diff(va)==1)
    assert va[0]-tr[-1]-1==72 and len(va)%24==0
    train=d.iloc[tr]; target=d.iloc[va]
    x=features(train); xt=features(target); r=train[RES].to_numpy(float)
    base=target[BASE].to_numpy(float)
    model=fit_ridge(x,r)
    meanfit,meantarget=conditional(x,model),conditional(xt,model)
    eps=r-meanfit
    starts=starts_complete(r,24)
    assert len(starts)>=10 and np.isfinite(eps[starts[:,None]+np.arange(24)]).all()
    rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED,fold['id'],24])))
    chosen=rng.choice(starts,size=(MEMBERS,len(va)//24),replace=True)
    idx=(chosen[:,:,None]+np.arange(24)).reshape(MEMBERS,len(va))
    assert np.all(idx<tr[-1]+1) and np.all(idx%24==va[None,:]%24)
    pool=eps[starts[:,None]+np.arange(24)]
    center=pool.mean(axis=(0,1))
    # Sólo un centrado vectorial global del pool elegible. Se mantiene ciclo residual.
    innovations=eps[idx]-center
    cycle=train.groupby(train.fecha_local.dt.hour)[RES].mean().loc[target.fecha_local.dt.hour].to_numpy()
    predictions=dict(BASE=base,SES_GLOBAL=base+np.nanmean(r,axis=0),CICLO=base+cycle,
        RIDGE=base+meantarget,G1_24=base[None]+r[idx],RIDGE_24=base[None]+meantarget[None]+innovations)
    valid=np.isfinite(base).all(axis=1)
    for pred in predictions.values():
        assert np.isfinite(pred[...,valid,:]).all()
    finite=np.isfinite(x).all(axis=1)
    lo,hi=x[finite,:3].min(axis=0),x[finite,:3].max(axis=0)
    outside=(xt[:,:3]<lo)|(xt[:,:3]>hi)
    starts48=starts_complete(r,48)
    n48,last=0,-1
    for s in starts48:
        if s>=last:n48+=1;last=s+48
    meta=dict(fold=fold,filas_ajuste=len(tr),ternas_ajuste=int(np.isfinite(r).all(axis=1).sum()),
        horas_validacion=len(va),bloques24=len(starts),bloques48_no_solapados=n48,
        predictor_media=model['mu'].tolist(),predictor_escala=model['scale'].tolist(),
        intercepto=model['intercept'].tolist(),coeficiente=model['coef'].tolist(),
        centro_innovaciones_pool=center.tolist(),media_residuo_ajuste=np.nanmean(r,axis=0).tolist(),
        media_residuo_pool=r[starts[:,None]+np.arange(24)].mean(axis=(0,1)).tolist(),
        horas_predictor_fuera_rango=int((outside.any(axis=1)&valid).sum()),
        fuera_rango_por_variable={name:int((outside[:,j]&valid).sum()) for j,name in enumerate(LABELS)},
        media_innovacion_por_hora=(pool.mean(axis=0)-center).tolist(),
        base_comun_finito=int(valid.sum()),ajuste_antes_validacion=True,lambda_fijo=ALPHA)
    return predictions,dict(indices=idx,starts=starts,chosen=chosen,train_rows=tr,target_rows=va,
        residual_fit=r,innovations_fit=eps,pool_center=center,mean_train=meanfit,mean_target=meantarget,
        mu=model['mu'],scale=model['scale'],coef=model['coef'],intercept=model['intercept']),meta


def tests(d):
    # Verificador alternativo de ridge: mínimos cuadrados con filas de penalización.
    x=np.array([[0,1],[1,3],[2,2],[3,6],[4,4]],float)
    y=np.c_[x[:,0]+2*x[:,1],3-x[:,1],x[:,0]*.3]
    model=fit_ridge(x,y); z=(x-model['mu'])/model['scale']
    direct=np.linalg.lstsq(np.r_[z,np.sqrt(len(z)*ALPHA)*np.eye(2)],
        np.r_[y-model['intercept'],np.zeros((2,3))],rcond=None)[0]
    np.testing.assert_allclose(direct,model['coef'],atol=1e-12,rtol=0)
    np.testing.assert_allclose(fit_ridge(x,y+10)['coef'],model['coef'],atol=1e-12,rtol=0)
    pred,a,meta=predict_fold(d,FOLDS[0])
    poison=d.copy(); mask=poison.fecha_local>=pd.Timestamp(FOLDS[0]['fin_ajuste'])
    poison.loc[mask,OBS+RES]=1e8
    changed,_,other=predict_fold(poison,FOLDS[0])
    for name in MODELS:
        np.testing.assert_array_equal(pred[name],changed[name])
    assert meta==other
    assert np.all(np.diff(a['indices'].reshape(MEMBERS,-1,24),axis=-1)==1)
    xx=np.array([[0.,2.],[2.,4.],[5.,1.]])
    yy=np.array([1.,3.])
    np.testing.assert_allclose(crps(xx,yy),np.abs(xx-yy).mean(axis=0)-.5*np.abs(xx[:,None]-xx[None,:]).mean(axis=(0,1)),atol=1e-14)
    return dict(ridge_vs_minimos_cuadrados=True,intercepto_no_penalizado=True,
        sin_fuga_observaciones_futuras=True,ternas_conjuntas=True,bloques_contiguos=True,
        CRPS_vs_definicion=True)


def prepare():
    if OUT.exists():raise FileExistsError('No sobrescribir diseño congelado')
    source=read(ROOT/'outputs/Discrepancias_ajuste_2026-10-19/Recepcion_independiente.json')
    expected=next(r for r in source['archivos'] if Path(r['path']).name==FIT.name)
    verify([expected])
    d=load();checks=tests(d)
    OUT.mkdir()
    plan=dict(fecha='2026-10-20',tipo='DESARROLLO_INTERNO_RETROSPECTIVO',folds=FOLDS,
        exposicion_previa='Los31 días se inspeccionaron descriptivamente. Cronología evita fuga computacional, no borra exposición ni garantiza validación externa.',
        ventana='Ajuste21dic2016–20ene2017 únicamente; evaluación24–30ene no se lee.',
        separacion_h=72,longitud_bloques_h=24,minimo_bloques=10,miembros=MEMBERS,semilla=SEED,
        motivo_L24='Alternativa ya documentada del generador1.0.48h sólo ofrece5,7,8,10 bloques no solapados en prefijos;24h ofrece11,15,17,21. No reducir mínimo ni elegirL por métricas.',
        modelos=MODELS,predictores=['T2_C','u_earth_m_s','v_earth_m_s','sin24h','cos24h'],
        ridge='Minimiza mean(||r-b-ZB||²)+0.1||B||². Z estandarizado sólo con prefijo; b no penalizado. Tres respuestas ajustadas conjuntamente con misma matriz. Sin selección de lambda.',
        bloques='T/u/v juntos, inicios00:49, bloques24h completos. Misma matriz de sorteos paraG1_24 yRIDGE_24. No conectar huecos ni escoger miembros por resultados.',
        condicional='X*=WRF+m(X)+[epsilon_bloque-media_pool_epsilon]. Un solo centrado vectorial global del pool; ciclo residual conservado. No se suma otro sesgo. Media por hora del pool registrada.',
        referencias='BASE; sesgo global; ciclo24medias horarias; ridge determinista; G1_24 con residuos crudos del prefijo. No reusar modelo1.0 entrenado con días futuros del fold.',
        metricas=['CRPS_por_variable','sesgo_predicho-observado','RMSE_media','cobertura_50_80_90','anchura_50_80_90','correlacion_conjunta','persistencia1_6_24_48h','soporte_predictor'],
        reporte='Pooled ponderado por horas válidas y cada fold/franja. Variables en unidades propias; no sumarCRPS°C y m/s. Sin pruebas de significación con horas independientes.',
        criterio='Registrar mejoras y deterioros por variable/fold; no adopción automática como calibrado. Conservar candidato sin reajustarlo tras ver métricas. No elegir por concentración.',
        limitaciones='24h corta dependencia entre días; innovación ajustada puede subestimar dispersión. Sin incertidumbre de parámetros ni varianza condicional; escalas/corrección constantes fuera de entrenamiento no garantizadas. Transferencia física sigue hipótesis.',
        referencias_bibliograficas=['https://doi.org/10.1111/ecog.02881','https://acp.copernicus.org/articles/23/12477/2023/'])
    guardar_json(OUT/'Diseno.json',plan)
    guardar_json(OUT/'Pruebas.json',checks)
    method='''# Comparación cronológica interna del modelo de discrepancias

Se fija este diseño antes de calcular su desempeño. Usa sólo el ajuste21dic–20ene ya inspeccionado: desarrollo retrospectivo, no reserva nueva. Los cuatro períodos de validación no se solapan; cada modelo aprende únicamente de su prefijo anterior, con72h de separación. Días evaluados antes pueden entrar como entrenamiento de un fold posterior; los folds no son réplicas independientes.

Se comparan BASE, sesgo global, ciclo horario, regresión ridge condicional y dos conjuntos de1024 trayectorias: el algoritmo de bloques crudos1.0 reajustado a cada prefijo y una alternativa con media condicional. Ridge usa T,u,v WRF y primer armónico diario; parámetros, escala y centrado se estiman sólo en el prefijo. Lambda0,1 queda fijo como regularización de trabajo, sin optimizar contra esta comparación.

Los bloques son de24h, alternativa ya documentada. Cada prefijo ofrece al menos diez días completos; no hay ese soporte para48h en los primeros tres. Esto no cambia el generador1.0 congelado ni demuestra que24h reproduzca la persistencia entre días. Las innovaciones de las tres variables se extraen juntas y mantienen su orden dentro del día. El corte entre bloques pierde parte de la dependencia temporal.

Para la alternativa: r=observado−WRF; epsilon=r−m(X); X*=WRF+m(X)+epsilon*−media_pool. Se resta una única media vectorial del pool elegible. Puede quedar un ciclo horario medio de innovaciones y la media del conjunto puede diferir de la regresión; se registra. No se separan variables ni se duplica el sesgo. La distribución de innovaciones no depende del estado, por lo que todavía puede fallar en dispersión condicional; tampoco incluye incertidumbre paramétrica.

Se congelan predicciones y hashes antes de calcular métricas. La máscara válida es común; los huecos no se comprimen para persistencia. Se informan CRPS, sesgo, RMSE de la media, cobertura y anchura50/80/90 por variable, fold y franja; correlaciones conjuntas y temporales son diagnósticas. Los rangos de predictores del entrenamiento señalan extrapolación, sin eliminar horas para mejorar métricas. No se suman puntuaciones con unidades distintas.

No se adopta automáticamente un ganador ni se calculan concentraciones con estos miembros. Una mejora interna permite estudiar el candidato; no acredita cobertura futura, transferencia espacial o dinámica meteorológica. El reloj H-CIVIL y los minutos:49 se mantienen. Fuentes y geometría permanecen fijas.

Fundamento: [Roberts et al.(2017)](https://doi.org/10.1111/ecog.02881) explica el riesgo de ignorar estructura temporal al validar; no prescribe nuestros días ni lambda. [Jones et al.(2023)](https://acp.copernicus.org/articles/23/12477/2023/) examina dispersión y calibración en otros conjuntos atmosféricos: ampliar dispersión no equivale a validar esta cadena. Los detalles numéricos anteriores son decisiones explícitas del ensayo.
'''
    (OUT/'Metodo.md').write_text(method,encoding='utf-8')
    guardar_json(OUT/'Congelacion.json',dict(estado='DISENO_CONGELADO_ANTES_METRICAS',archivos=records([
        FIT,Path(__file__),ROOT/'work/generador_meteorologico_20261020.py',
        OUT/'Diseno.json',OUT/'Pruebas.json',OUT/'Metodo.md'])))
    print('Diseño congelado: cuatro folds, seis modelos,24h y72h de separación.')


def predict():
    verify(read(OUT/'Congelacion.json')['archivos'])
    folder=OUT/'Predicciones'
    if folder.exists():raise FileExistsError('Predicciones existentes; no sobrescribir')
    folder.mkdir();d=load();files=[]
    for fold in FOLDS:
        pred,arrays,meta=predict_fold(d,fold)
        path=folder/f"fold{fold['id']}.npz"
        np.savez_compressed(path,**pred,**arrays)
        param=folder/f"fold{fold['id']}.json"
        guardar_json(param,meta)
        files.extend([path,param])
        print('Predicciones congeladas fold'+str(fold['id'])+'; bloques='+str(meta['bloques24']),flush=True)
    guardar_json(OUT/'Predicciones_congeladas.json',dict(estado='PREDICCIONES_CONGELADAS_ANTES_METRICAS',
        diseno_sha256=sha256(OUT/'Congelacion.json'),archivos=records(files)))


def evaluate():
    verify(read(OUT/'Congelacion.json')['archivos'])
    verify(read(OUT/'Predicciones_congeladas.json')['archivos'])
    dest=OUT/'Evaluacion'
    if dest.exists():raise FileExistsError('Evaluación existente; no sobrescribir')
    d=load();hourly=[];dependencies=[];support=[];physical=[]
    for fold in FOLDS:
        f=fold['id']; a=np.load(OUT/'Predicciones'/f'fold{f}.npz')
        meta=read(OUT/'Predicciones'/f'fold{f}.json');support.append(meta)
        target=d.iloc[a['target_rows']]; obs=target[OBS].to_numpy(float);base=target[BASE].to_numpy(float)
        ok=np.isfinite(np.c_[obs,base]).all(axis=1)
        hours=target.fecha_local.dt.hour.to_numpy()
        for name in MODELS:
            pred=a[name]; ensemble=pred if pred.ndim==3 else pred[None]
            mean=ensemble.mean(axis=0)
            score=np.full_like(base,np.nan);score[ok]=crps(ensemble[:,ok],obs[ok])
            intervals={level:np.quantile(ensemble,[(1-level)/2,(1+level)/2],axis=0) for level in (.5,.8,.9)}
            for t in np.flatnonzero(ok):
                for j,var in enumerate(LABELS):
                    row=dict(fold=f,modelo=name,fecha_local=str(target.fecha_local.iloc[t]),variable=var,
                        franja='06_17' if 6<=hours[t]<18 else '18_05',observado=obs[t,j],BASE=base[t,j],
                        media=mean[t,j],error=mean[t,j]-obs[t,j],CRPS=score[t,j])
                    for level,bounds in intervals.items():
                        key=str(int(level*100));lo,hi=bounds[:,t,j]
                        row['inferior'+key]=lo;row['superior'+key]=hi
                        row['cobertura'+key]=int(lo<=obs[t,j]<=hi);row['anchura'+key]=hi-lo
                    hourly.append(row)
            if pred.ndim!=3:continue
            syn=pred-base[None]; actual=obs-base
            syn[:,~ok,:]=np.nan;actual[~ok]=np.nan
            for j,k in ((0,1),(0,2),(1,2)):
                samples=np.array([correlation(s[:,j],s[:,k]) for s in syn])
                dependencies.append(dict(fold=f,modelo=name,tipo='conjunta',variable=LABELS[j]+'/'+LABELS[k],lag=0,
                    pares=int(ok.sum()),observada=correlation(actual[:,j],actual[:,k]),
                    mediana=float(np.nanmedian(samples)),p05=float(np.nanquantile(samples,.05)),p95=float(np.nanquantile(samples,.95))))
            for j,var in enumerate(LABELS):
                for lag in (1,6,24,48):
                    if len(target)<=lag+2:continue
                    validpairs=int((ok[:-lag]&ok[lag:]).sum())
                    samples=np.array([correlation(s[:-lag,j],s[lag:,j]) for s in syn])
                    dependencies.append(dict(fold=f,modelo=name,tipo='temporal',variable=var,lag=lag,pares=validpairs,
                        observada=correlation(actual[:-lag,j],actual[lag:,j]),mediana=float(np.nanmedian(samples)),
                        p05=float(np.nanquantile(samples,.05)),p95=float(np.nanquantile(samples,.95))))
            physical.append(dict(fold=f,modelo=name,n_miembros=MEMBERS,temperatura_min=float(pred[:,ok,0].min()),
                temperatura_max=float(pred[:,ok,0].max()),rapidez_max=float(np.hypot(pred[:,ok,1],pred[:,ok,2]).max()),
                bajo_cero_absoluto=int((pred[:,ok,0]<-273.15).sum()),recortes=0))
    h=pd.DataFrame(hourly)
    assert h.groupby(['modelo','variable']).size().eq(334).all()
    def aggregate(groups):
        rows=[]
        for key,part in h.groupby(groups):
            key=key if isinstance(key,tuple) else (key,)
            row=dict(zip(groups,key));row.update(n=len(part),CRPS=part.CRPS.mean(),sesgo=part.error.mean(),
                RMSE_media=float(np.sqrt(np.mean(part.error**2))))
            for level in (50,80,90):
                row['cobertura'+str(level)]=part['cobertura'+str(level)].mean()
                row['anchura'+str(level)]=part['anchura'+str(level)].mean()
            rows.append(row)
        return pd.DataFrame(rows)
    pooled=aggregate(['modelo','variable']);byfold=aggregate(['fold','modelo','variable'])
    byhour=aggregate(['modelo','variable','franja'])
    contrasts=[]
    for f in [0,1,2,3,4]:
        table=pooled if f==0 else byfold[byfold.fold==f]
        lookup=table.set_index(['modelo','variable'])
        for var in LABELS:
            v=lookup.loc[('RIDGE_24',var),'CRPS']
            for ref in ['BASE','G1_24','RIDGE']:
                b=lookup.loc[(ref,var),'CRPS']
                contrasts.append(dict(fold=f,variable=var,referencia=ref,CRPS_referencia=b,CRPS_condicional=v,
                    cambio_porcentaje=100*(v-b)/b))
    dest.mkdir()
    for name,table in [('Horario',h),('Metricas_globales',pooled),('Metricas_por_fold',byfold),
                       ('Metricas_por_franja',byhour),('Contrastes_CRPS',pd.DataFrame(contrasts)),
                       ('Dependencia',pd.DataFrame(dependencies)),('Rangos',pd.DataFrame(physical))]:
        table.to_csv(dest/(name+'.csv'),index=False,encoding='utf-8-sig')
    guardar_json(dest/'Soporte.json',support)
    lines=['# Comparación cronológica interna','',
        'Cuatro folds expansivos,72h de separación,336 posiciones de validación y334 ternas válidas. '
        'Seis modelos, misma máscara; dos conjuntos de1024 trayectorias con bloques conjuntos24h. '
        'Diseño y predicciones congelados antes de calcular métricas. No se leyeron datos24–30ene. '
        'Desarrollo retrospectivo dentro del ajuste previamente inspeccionado; no validación externa.','',
        '| Modelo | CRPS T (°C) | CRPS u (m/s) | CRPS v (m/s) |','|---|---:|---:|---:|']
    for model in MODELS:
        part=pooled[pooled.modelo==model].set_index('variable')
        lines.append('| '+model+' | '+' | '.join(f'{part.loc[v,"CRPS"]:.4f}' for v in LABELS)+' |')
    lines+=['','CRPS menor indica menor puntuación de error; las variables conservan unidades distintas. '
        'Para referencias deterministas CRPS coincide con MAE. Cobertura y anchura sólo tienen interpretación '
        'de conjunto para G1_24 yRIDGE_24; los demás tienen intervalos degenerados.','',
        'Consultar Metricas_por_fold.csv y Metricas_por_franja.csv: el promedio global puede ocultar deterioros. '
        'Los folds no son réplicas independientes. No hay p-valores ni prueba de equivalencia. '
        'Soporte.json registra extrapolación de predictores, diferencias por selección de días completos '
        'y centrado de innovaciones. Dependencia.csv contrasta correlaciones conjuntas y persistencia '
        'sin comprimir huecos. Los cuantiles entre miembros son descriptores del conjunto, no intervalos '
        'de confianza sobre la correlación observada.','',
        'No se adopta automáticamente un modelo ni se generan concentraciones. Los bloques24h no '
        'resuelven dependencia de varios días; la incertidumbre de parámetros y la heterocedasticidad '
        'condicional quedan fuera. Una mejora interna requiere discutir cobertura, dependencia y '
        'soporte antes de una nueva evaluación. El generador1.0 y su evaluación fallida permanecen intactos.','',
        'Método, justificación de períodos y fuentes bibliográficas: ../Metodo.md.']
    (dest/'Resultados.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    guardar_json(OUT/'Estado.json',dict(estado='COMPARACION_CRONOLOGICA_CALCULADA',folds=4,
        horas_esperadas=336,ternas_evaluadas=334,modelos=6,miembros_por_ensemble=MEMBERS,
        validacion_externa=False,modelo_final_adoptado=False,AERMOD_ejecutado=False,
        archivos=records([OUT/'Congelacion.json',OUT/'Predicciones_congeladas.json',*sorted(dest.iterdir())])))
    print(pooled[['modelo','variable','n','CRPS','sesgo','cobertura90','anchura90']].to_string(index=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('etapa',choices=['preparar','predecir','evaluar'])
    args=parser.parse_args();{'preparar':prepare,'predecir':predict,'evaluar':evaluate}[args.etapa]()
