"""Inventario WRF d03, extracción incremental verificada y QA; no ejecuta modelos."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from netCDF4 import Dataset, chartostring
from .comun import guardar_json, salida_nueva, sha256, unique_times
from .extraer_wrf import extraer

ATTRS=('TITLE','SIMULATION_START_DATE','GRID_ID','PARENT_ID','MAP_PROJ','DX','DY',
       'TRUELAT1','TRUELAT2','CEN_LAT','CEN_LON','STAND_LON','MP_PHYSICS','RA_LW_PHYSICS',
       'RA_SW_PHYSICS','SF_SFCLAY_PHYSICS','SF_SURFACE_PHYSICS','BL_PBL_PHYSICS',
       'CU_PHYSICS','BLDT','RADT','DT','USE_THETA_M','DIFF_OPT','KM_OPT','DAMP_OPT',
       'HYBRID_OPT','PARENT_GRID_RATIO','I_PARENT_START','J_PARENT_START')
STATIC=('XLAT','XLONG','HGT','COSALPHA','SINALPHA','ZNU','ZNW')
FIELDS=('T2_C','u_earth_m_s','v_earth_m_s','HGT_bilineal_m')

def utc_naive(value):
    t=pd.Timestamp(value)
    if pd.isna(t):raise ValueError('Fecha UTC ausente.')
    return t.tz_convert('UTC').tz_localize(None) if t.tz is not None else t

def _native(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    return value

def huella_estable(signature):
    # DT es el paso efectivo escrito por WRF y cambia con el paso adaptativo.
    # Se conserva en el inventario, pero no identifica una física/malla distinta.
    stable={**signature,'atributos':{k:v for k,v in signature['atributos'].items() if k!='DT'}}
    return hashlib.sha256(json.dumps(stable,sort_keys=True,ensure_ascii=True).encode()).hexdigest()

def inspeccionar(path):
    """Huella de cabecera y malla más hash completo; detecta escritura concurrente."""
    path=Path(path).resolve();before=path.stat()
    with Dataset(path) as nc:
        if int(nc.GRID_ID)!=3:raise ValueError(f'GRID_ID distinto de d03: {path.name}')
        for name in ('Times','T2','U10','V10',*STATIC):
            if name not in nc.variables:raise ValueError(f'Falta {name} en {path.name}')
        times=pd.DatetimeIndex(pd.to_datetime(chartostring(nc['Times'][:]).tolist(),format='%Y-%m-%d_%H:%M:%S'))
        if not len(times) or times.hasnans or times.has_duplicates or not times.is_monotonic_increasing:
            raise ValueError(f'Times vacío, duplicado o desordenado: {path.name}')
        if any(times!=times.floor('h')):raise ValueError('El piloto requiere salidas en horas UTC enteras.')
        attrs={k:_native(getattr(nc,k,None)) for k in ATTRS}
        start=utc_naive(str(nc.SIMULATION_START_DATE).replace('_',' '))
        if times.min()<start:raise ValueError('Times anterior a SIMULATION_START_DATE.')
        dims={k:len(v) for k,v in nc.dimensions.items() if k!='Time'}
        static={}
        for name in STATIC:
            var=nc[name];data=var[0] if var.dimensions[0]=='Time' else var[:]
            a=np.ascontiguousarray(np.ma.asarray(data).filled(np.nan))
            static[name]={'shape':list(a.shape),'dtype':str(a.dtype),'sha256':hashlib.sha256(a.tobytes()).hexdigest()}
        signature={'atributos':attrs,'dimensiones':dims,'campos_estaticos':static,
                   'unidades':{k:getattr(nc[k],'units',None) for k in ('T2','U10','V10')}}
        fingerprint=huella_estable(signature)
        restart_start=getattr(nc,'START_DATE',None)
    digest=sha256(path);after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError(f'El archivo cambió mientras se leía; copiar una salida cerrada: {path}')
    return {'path':str(path),'archivo':path.name,'bytes':after.st_size,'mtime_ns':after.st_mtime_ns,
            'sha256':digest,'huella_cabecera_malla':fingerprint,'signature':signature,
            'integration_start':str(start),'START_DATE':restart_start,'times':[str(t) for t in times]}

def comprobar_inventario(items):
    if not items:raise FileNotFoundError('No hay archivos wrfout_d03 sin extensión o .nc en la carpeta.')
    if len({x['huella_cabecera_malla'] for x in items})!=1:
        raise ValueError('Cabecera, física, inicio o malla diferentes: no mezclar integraciones/reinicios sin resolver su procedencia.')
    rows=[{'fecha_wrf_utc':t,'archivo':x['archivo']} for x in items for t in x['times']]
    frame=pd.DataFrame(rows);frame['fecha_wrf_utc']=pd.to_datetime(frame.fecha_wrf_utc)
    unique_times(frame,'fecha_wrf_utc')
    return frame.sort_values('fecha_wrf_utc').reset_index(drop=True)

def comprobar_cache(meta,items,*,corrida_id,estado_origen,lon,lat,spinup_days):
    if meta.get('corrida_id') not in (None,corrida_id):raise ValueError('El cache pertenece a otra corrida_id.')
    if meta.get('corrida_id') is None and estado_origen!='historica_no_confirmada':
        raise ValueError('Cache anterior sin identidad: sólo reutilizable como histórico no confirmado.')
    if (meta['lon'],meta['lat'],meta['spinup_dias'])!=(lon,lat,spinup_days):
        raise ValueError('Punto o spin-up del cache diferente.')
    current={x['path']:x for x in items}
    for old in meta['fuentes']:
        name=str(Path(old['path']).resolve())
        if name not in current:raise ValueError('Falta un archivo previo del cache; no unir colecciones distintas.')
        if not old.get('sha256') or old['sha256']!=current[name]['sha256']:
            raise ValueError(f'Archivo del cache reemplazado o sin hash: {name}')
    if meta.get('huella_cabecera_malla') not in (None,items[0]['huella_cabecera_malla']):
        raise ValueError('La cabecera/malla difiere del cache.')

def resumir(frame,inicio,fin):
    d=frame.copy();d['fecha_wrf_utc']=pd.to_datetime(d.fecha_wrf_utc)
    unique_times(d,'fecha_wrf_utc');d=d.sort_values('fecha_wrf_utc')
    expected=pd.date_range(inicio,fin,freq='h',inclusive='left')
    q=pd.DataFrame({'fecha_wrf_utc':expected}).merge(d,on='fecha_wrf_utc',how='left',validate='one_to_one')
    q['presente']=q.archivo.notna()
    q['valido_Tuv']=np.isfinite(q[['T2_C','u_earth_m_s','v_earth_m_s']].to_numpy(float)).all(axis=1)
    q['WS_m_s']=np.hypot(q.u_earth_m_s,q.v_earth_m_s)
    rows=[]
    for hour in range(24):
        part=q.loc[q.fecha_wrf_utc.dt.hour==hour]
        for col in ('T2_C','u_earth_m_s','v_earth_m_s','WS_m_s'):
            a=part[col].to_numpy(float);a=a[np.isfinite(a)]
            rows.append({'hora_UTC':hour,'variable':col,'n':len(a),'n_esperado':len(part),
                         'media':np.mean(a) if len(a) else np.nan,
                         'mediana':np.median(a) if len(a) else np.nan,
                         'desv_estandar':np.std(a,ddof=1) if len(a)>1 else np.nan,
                         'p10':np.quantile(a,.1) if len(a) else np.nan,
                         'p90':np.quantile(a,.9) if len(a) else np.nan})
    # Reindexar antes de lag: las ausencias no se convierten en horas contiguas.
    variability=[]
    for col in ('T2_C','u_earth_m_s','v_earth_m_s','WS_m_s'):
        for lag in (1,6,24):
            a=q[col].to_numpy(float);x=a[:-lag];y=a[lag:]
            valid=np.isfinite(x)&np.isfinite(y);x=x[valid];y=y[valid]
            r=float(np.corrcoef(x,y)[0,1]) if len(x)>2 and np.std(x)>0 and np.std(y)>0 else np.nan
            variability.append({'variable':col,'lag_horas':lag,'n_pares':len(x),'correlacion':r})
    daily=q.groupby(q.fecha_wrf_utc.dt.date).agg(horas_esperadas=('presente','size'),horas_presentes=('presente','sum'),
         horas_validas_Tuv=('valido_Tuv','sum'),T2_media_C=('T2_C','mean'),WS_media_m_s=('WS_m_s','mean')).reset_index()
    return q,pd.DataFrame(rows),daily,pd.DataFrame(variability)

def ejecutar(folder,destination,*,inicio_utc,fin_utc,corrida_id,estado_origen,lon,lat,spinup_days=20,cache=None,inventario_previo=None):
    if not corrida_id.strip():raise ValueError('Identificar la corrida, sin inferir su procedencia por fechas.')
    if estado_origen not in ('historica_no_confirmada','actual_confirmada'):raise ValueError('Estado de procedencia desconocido.')
    if spinup_days<0:raise ValueError('Spin-up negativo.')
    first,last=utc_naive(inicio_utc),utc_naive(fin_utc)
    if first>=last or first!=first.floor('h') or last!=last.floor('h'):raise ValueError('Ventana UTC horaria inválida.')
    folder=Path(folder).resolve()
    files=sorted(p for p in folder.glob('wrfout_d03_*') if p.is_file() and p.suffix in ('','.nc'))
    dest=salida_nueva(destination)
    items=[]
    if inventario_previo is not None:
        # Reanudar una lectura completa ya guardada tras una interrupción.
        # El manifiesto diferencia hashes heredados de hashes recalculados ahora.
        items=json.loads(Path(inventario_previo).read_text(encoding='utf-8'))
        if {x['path'] for x in items}!={str(p.resolve()) for p in files}:raise ValueError('Inventario previo no cubre los archivos actuales.')
        for item in items:
            st=Path(item['path']).stat()
            if (st.st_size,st.st_mtime_ns)!=(item['bytes'],item['mtime_ns']):raise ValueError('Cambió un archivo desde el inventario previo.')
            if not item.get('sha256'):raise ValueError('Inventario previo sin SHA-256 completo.')
            item['huella_cabecera_malla']=huella_estable(item['signature'])
    else:
        for i,p in enumerate(files,1):
            items.append(inspeccionar(p))
            print(f'Inventario y SHA-256: {i}/{len(files)}',flush=True)
    guardar_json(dest/'inventario_archivos.json',items)
    timeline=comprobar_inventario(items)
    timeline.to_csv(dest/'inventario_horas_UTC.csv',index=False,encoding='utf-8-sig')
    effective=max(first,pd.Timestamp(items[0]['integration_start'])+pd.Timedelta(days=spinup_days))
    if effective>=last:raise ValueError('Toda la ventana cae en el spin-up; no hay tramo analítico.')
    needed=timeline.loc[(timeline.fecha_wrf_utc>=effective)&(timeline.fecha_wrf_utc<last)]
    if needed.empty:raise ValueError('No hay salidas en el tramo post spin-up solicitado.')
    old=pd.DataFrame();cache_meta=None;cache_digest=None
    if cache is not None:
        cache=Path(cache).resolve();cache_meta=json.loads((cache/'manifest.json').read_text(encoding='utf-8'))
        comprobar_cache(cache_meta,items,corrida_id=corrida_id,estado_origen=estado_origen,lon=lon,lat=lat,spinup_days=spinup_days)
        cache_digest=sha256(cache/'wrf_estacion.csv')
        if cache_meta.get('serie_sha256') not in (None,cache_digest):raise ValueError('Serie del cache alterada.')
        old=pd.read_csv(cache/'wrf_estacion.csv');old['fecha_wrf_utc']=pd.to_datetime(old.fecha_wrf_utc)
        unique_times(old,'fecha_wrf_utc')
        old=old.loc[(old.fecha_wrf_utc>=effective)&(old.fecha_wrf_utc<last)].copy()
    reused=[];new=[]
    for name,part in needed.groupby('archivo'):
        available=set(old.loc[old.archivo==name,'fecha_wrf_utc']) if not old.empty else set()
        (reused if set(part.fecha_wrf_utc)<=available else new).append(name)
    parts=[]
    if reused:parts.append(old.loc[old.archivo.isin(reused)])
    if new:
        selected=[p for p in files if p.name in new]
        extraer(folder,dest/'Extraccion_nueva',lon=lon,lat=lat,spinup_days=spinup_days,hash_inputs=False,
                files_override=selected,inicio_utc=effective,fin_utc=last)
        fresh=pd.read_csv(dest/'Extraccion_nueva'/'wrf_estacion.csv');fresh['fecha_wrf_utc']=pd.to_datetime(fresh.fecha_wrf_utc)
        parts.append(fresh)
    frame=pd.concat(parts,ignore_index=True).sort_values('fecha_wrf_utc').reset_index(drop=True)
    unique_times(frame,'fecha_wrf_utc')
    if set(frame.fecha_wrf_utc)!=set(needed.fecha_wrf_utc):raise ValueError('La extracción/cache no cubre los Times inventariados.')
    # No publicar resultados obtenidos de archivos que se modificaron durante la extracción.
    for item in items:
        st=Path(item['path']).stat()
        if (st.st_size,st.st_mtime_ns)!=(item['bytes'],item['mtime_ns']):raise ValueError('Archivo cambiado durante el piloto.')
    frame.to_csv(dest/'wrf_estacion.csv',index=False,encoding='utf-8-sig')
    q,cycle,daily,variability=resumir(frame,effective,last)
    for name,data in [('QA_horario_UTC',q),('ciclo_diurno_UTC',cycle),('resumen_diario_UTC',daily),('variabilidad_lags_UTC',variability)]:
        data.to_csv(dest/(name+'.csv'),index=False,encoding='utf-8-sig')
    valid=np.isfinite(frame[list(FIELDS)].to_numpy(float))
    manifest={'corrida_id':corrida_id,'estado_origen':estado_origen,'carpeta_wrf':str(folder),
       'lon':lon,'lat':lat,'spinup_dias':spinup_days,'integration_start':[items[0]['integration_start']],
       'huella_cabecera_malla':items[0]['huella_cabecera_malla'],
       'inicio_solicitado_utc':str(first),'inicio_analitico_utc':str(effective),'fin_utc_exclusivo':str(last),
       'primera_utc':str(frame.fecha_wrf_utc.min()),'ultima_utc':str(frame.fecha_wrf_utc.max()),
       'n_horas':len(frame),'horas_esperadas_post_spinup':len(q),'horas_ausentes':int((~q.presente).sum()),
       'horas_no_validas_Tuv':int((q.presente&~q.valido_Tuv).sum()),
       'campos_no_finitos':dict(zip(FIELDS,(~valid).sum(axis=0).astype(int).tolist())),
       'fuentes':[{k:x[k] for k in ('path','bytes','mtime_ns','sha256')} for x in items],
       'cache':str(cache) if cache else None,'cache_serie_sha256':cache_digest,
       'archivos_reutilizados':reused,'archivos_extraidos_ahora':new,
       'serie_sha256':sha256(dest/'wrf_estacion.csv'),'hashes_completos':True,
       'inventario_reanudado_desde':str(Path(inventario_previo).resolve()) if inventario_previo else None,
       'hashes_recalculados_en_esta_invocacion':inventario_previo is None,
       'DT_efectivo_segundos':[x['signature']['atributos'].get('DT') for x in items],
       'alcance':'Piloto UTC de WRF en la estación; variabilidad del modelo, sin validación observacional ni incertidumbre de concentración.',
       'identidad':'Huella consistente y hashes no prueban por sí solos pertenencia a la corrida activa: requiere procedencia confirmada.',
       'ciclo':'Hora UTC; percentiles descriptivos, no intervalos de confianza. No promediar dirección angular como escalar.',
       'estado_QA':'COBERTURA_COMPLETA_EN_VENTANA' if q.presente.all() and q.valido_Tuv.all() else 'PARCIAL_O_INVALIDO'}
    guardar_json(dest/'manifest.json',manifest)
    print(json.dumps({k:manifest[k] for k in ('corrida_id','n_horas','horas_ausentes','estado_QA')},ensure_ascii=False),flush=True)
    return manifest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('wrf-dir','salida','inicio-utc','fin-utc','corrida-id'):p.add_argument('--'+name,required=True)
    p.add_argument('--estado-origen',required=True,choices=('historica_no_confirmada','actual_confirmada'))
    p.add_argument('--lon',type=float,required=True);p.add_argument('--lat',type=float,required=True)
    p.add_argument('--spinup-dias',type=int,default=20);p.add_argument('--cache');p.add_argument('--inventario-previo')
    a=p.parse_args();ejecutar(a.wrf_dir,a.salida,inicio_utc=a.inicio_utc,fin_utc=a.fin_utc,corrida_id=a.corrida_id,
        estado_origen=a.estado_origen,lon=a.lon,lat=a.lat,spinup_days=a.spinup_dias,cache=a.cache,inventario_previo=a.inventario_previo)

if __name__=='__main__':main()
