"""Genera HOUREMIS desde masas DIARIAS YA CONTROLADAS; no aplica otro abatimiento."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from .comun import finito, salida_nueva, guardar_json, sha256
from .terreno import leer_fuentes, leer_cotas_aermap, location_aermod

def masa_controlada(flujo,fe,longitud_km,eficiencia_pct):
    finito(flujo,fe,longitud_km,eficiencia_pct)
    if any(np.any(np.asarray(x)<0) for x in [flujo,fe,longitud_km,eficiencia_pct]) or np.any(np.asarray(eficiencia_pct)>100):
        raise ValueError('Entradas físicas inválidas; no se sustituyen ausencias por cero.')
    return np.asarray(flujo)*np.asarray(fe)*np.asarray(longitud_km)*(1-np.asarray(eficiencia_pct)/100)

def tasa_line(masa_g_dia,longitud_m,ancho_m):
    finito(masa_g_dia,longitud_m,ancho_m)
    if np.any(np.asarray(masa_g_dia)<0) or np.any(np.asarray(longitud_m)<=0) or np.any(np.asarray(ancho_m)<1):
        raise ValueError('Masa, longitud o ancho inválidos.')
    return np.asarray(masa_g_dia)/(86400*np.asarray(longitud_m)*ancho_m)

def houremis_line(date,hour,source,q):
    # Para LINE la tasa es g/(s m²). Se omiten altura/sigma variables:
    # constantes se declaran en SRCPARAM, y el ancho NO va en HOUREMIS.
    if not 1<=hour<=24:raise ValueError('AERMOD usa horas 1 a 24.')
    finito(q)
    if q<0:raise ValueError('Tasa negativa.')
    return f'SO HOUREMIS {date.year%100:02d} {date.month:2d} {date.day:2d} {hour:2d} {source:<12s} {q:.12E}\n'

def generar(sources_csv,daily_csv,aermap_src,destination,*,inicio,fin,pollutant,width=3,height=.5,sigma_z=0,parametros_por_fuente=False):
    """[inicio,fin) en horas enteras; conserva tasa diaria incluso en días parciales."""
    if pollutant not in ('MP10','MP25'):raise ValueError('Contaminante no admitido.')
    start,end=pd.Timestamp(inicio),pd.Timestamp(fin)
    if (pd.isna(start) or pd.isna(end) or start.tz is not None or end.tz is not None
            or start!=start.floor('h') or end!=end.floor('h') or start>=end):
        raise ValueError('Límites horarios inválidos: usar horas enteras en el reloj local elegido.')
    intervals=pd.date_range(start,end,freq='h',inclusive='left')
    hours_by_day={day:[t.hour+1 for t in intervals if t.normalize()==day] for day in intervals.normalize().unique()}
    sources=leer_fuentes(sources_csv);z=leer_cotas_aermap(aermap_src,sources)
    if parametros_por_fuente:
        names=['ancho_m','altura_m','sigma_z_m']
        if not set(names)<=set(sources):raise ValueError('Faltan parámetros por fuente.')
        parameters=np.round(sources[names].to_numpy(float),3)
    else:
        finito(width,height,sigma_z)
        parameters=np.tile(np.round([width,height,sigma_z],3),(len(sources),1))
    finito(parameters)
    if np.any(parameters[:,0]<1) or np.any(parameters[:,1:]<0):raise ValueError('Parámetros de fuente inválidos.')
    widths,heights,sigmas=parameters.T
    d=pd.read_csv(daily_csv);d['fecha']=pd.to_datetime(d.fecha)
    mass_col='emision_'+pollutant.lower()+'_g_dia'
    if mass_col not in d:raise ValueError(f'Falta masa controlada {mass_col}.')
    d=d.loc[(d.fecha>=start.normalize())&(d.fecha<end)].copy()
    if d.duplicated(['fecha','id_fuente_aermod']).any():raise ValueError('Fuente/fecha duplicada.')
    days=pd.DatetimeIndex(hours_by_day)
    if set(d.fecha)!=set(days):raise ValueError('Faltan días de inventario: no se rellenan ni extrapolan.')
    expected=set(sources.id_fuente_aermod)
    for day,part in d.groupby('fecha'):
        if set(part.id_fuente_aermod)!=expected:raise ValueError(f'Fuentes diferentes en {day}.')
    maps=sources.set_index('id_fuente_aermod')
    if 'id_ruta_excel' in d and not np.array_equal(d.id_ruta_excel.to_numpy(),d.id_fuente_aermod.map(maps.id_ruta_excel).to_numpy()):
        raise ValueError('El enlace fuente-arco cambió.')
    xy=np.round(sources[['x1_utm19s_m','y1_utm19s_m','x2_utm19s_m','y2_utm19s_m']].to_numpy(float),2)
    lengths=np.hypot(xy[:,2]-xy[:,0],xy[:,3]-xy[:,1])
    if np.any(lengths<=0):raise ValueError('Dimensiones serializadas inválidas.')
    if np.any(np.maximum(lengths/widths,widths/lengths)>100+1e-9):
        raise ValueError('Relación de lados >100:1: subdividir antes de generar. Criterio conservador del proyecto; EPA emite advertencia no fatal.')
    if 'ancho_m' in sources and not np.allclose(sources.ancho_m,widths,rtol=0,atol=.0005):
        raise ValueError('El ancho difiere del usado al preparar la geometría.')
    length_map=dict(zip(sources.id_fuente_aermod,lengths))
    width_map=dict(zip(sources.id_fuente_aermod,widths))
    d['q']=tasa_line(d[mass_col].to_numpy(),d.id_fuente_aermod.map(length_map).to_numpy(),d.id_fuente_aermod.map(width_map).to_numpy())
    dest=salida_nueva(destination)
    with (dest/'fuentes_aermod.inc').open('w',encoding='ascii') as f:
        for r in sources.itertuples():
            f.write(location_aermod(r.id_fuente_aermod,[r.x1_utm19s_m,r.y1_utm19s_m,r.x2_utm19s_m,r.y2_utm19s_m],z[r.id_fuente_aermod]))
        for source,width,height,sigma_z in zip(sources.id_fuente_aermod,widths,heights,sigmas):
            f.write(f'SO SRCPARAM {source} 0.0 {height:.3f} {width:.3f} {sigma_z:.3f}\n')
    mass_back=0.0
    with (dest/f'{pollutant}.emi').open('w',encoding='ascii') as f:
        for day,part in d.groupby('fecha',sort=True):
            rows=list(part[['id_fuente_aermod','q']].itertuples(index=False,name=None))
            hours=hours_by_day[day]
            for hour in hours:
                for source,q in rows:f.write(houremis_line(day,hour,source,q))
            mass_back+=sum(float(f'{q:.12E}')*length_map[source]*width_map[source]*3600*len(hours) for source,q in rows)
    total=float((d[mass_col]*d.fecha.map({day:len(h)/24 for day,h in hours_by_day.items()})).sum())
    if not np.isclose(mass_back,total,rtol=1e-10,atol=1e-6):raise RuntimeError('Falló conservación de masa serializada.')
    guardar_json(dest/'manifest.json',{'inicio':str(start),'fin_exclusivo':str(end),'pollutant':pollutant,
       'masa_controlada_entrada_g':total,'masa_reconstruida_g':mass_back,
       'masa_diaria_completa_dias_involucrados_g':float(d[mass_col].sum()),
       'horas':len(intervals),'fuentes_por_hora':len(sources),'filas_horarias':len(intervals)*len(sources),
       'horas_por_dia':{str(day.date()):len(h) for day,h in hours_by_day.items()},
       'modo_parametros':'por_fuente' if parametros_por_fuente else 'uniforme',
       'ancho_m':None if parametros_por_fuente else float(widths[0]),
       'altura_m':None if parametros_por_fuente else float(heights[0]),
       'sigma_z_m':None if parametros_por_fuente else float(sigmas[0]),
       'abatimiento':'La entrada ya está controlada; no se reaplica.',
       'reparto_temporal':'Tasa constante masa diaria/24; en días parciales sólo se integra el número de horas incluidas, sin redistribuir masa.',
       'fuentes':[{'path':str(Path(p).resolve()),'sha256':sha256(p)} for p in [sources_csv,daily_csv,aermap_src]]})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['fuentes','diarias','cotas','salida','inicio','fin']:p.add_argument('--'+name,required=True)
    p.add_argument('--contaminante',required=True,choices=['MP10','MP25']);p.add_argument('--sigma-z',type=float)
    p.add_argument('--ancho',type=float);p.add_argument('--altura',type=float);p.add_argument('--parametros-por-fuente',action='store_true')
    a=p.parse_args()
    supplied=[a.ancho is not None,a.altura is not None,a.sigma_z is not None]
    if a.parametros_por_fuente and any(supplied):p.error('No mezclar parámetros uniformes y por fuente.')
    if not a.parametros_por_fuente and not all(supplied):p.error('Declarar ancho, altura y sigma-z, o --parametros-por-fuente.')
    generar(a.fuentes,a.diarias,a.cotas,a.salida,inicio=a.inicio,fin=a.fin,pollutant=a.contaminante,sigma_z=a.sigma_z,width=a.ancho,height=a.altura,parametros_por_fuente=a.parametros_por_fuente)

if __name__=='__main__':main()
