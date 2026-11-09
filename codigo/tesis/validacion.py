"""Alineación explícita y residuos firmados observación menos WRF."""
import argparse
import numpy as np
import pandas as pd
from .comun import periodo, unique_times, guardar_json, salida_nueva, sha256

def componentes(ws, direccion):
    rad = np.deg2rad(direccion)
    return -np.asarray(ws) * np.sin(rad), -np.asarray(ws) * np.cos(rad)

def direccion(u, v):
    return (270 - np.rad2deg(np.arctan2(v, u))) % 360

def diferencia_angular(obs, model):
    return (np.asarray(obs) - np.asarray(model) + 180) % 360 - 180

def rotar_a_tierra(u, v, cosalpha, sinalpha):
    return u * cosalpha - v * sinalpha, v * cosalpha + u * sinalpha

def bilineal(a, x, y):
    """Últimas dimensiones y,x; rechaza extrapolación y valores no finitos."""
    a = np.ma.asarray(a, dtype=float).filled(np.nan)
    if a.ndim<2 or min(a.shape[-2:])<2:
        raise ValueError('La interpolación requiere al menos dos nodos por eje.')
    ny, nx = a.shape[-2:]
    if not (0 <= x <= nx-1 and 0 <= y <= ny-1):
        raise ValueError('La estación queda fuera de la malla.')
    i, j = min(int(x), nx-2), min(int(y), ny-2)
    wx, wy = x-i, y-j
    block = a[..., j:j+2, i:i+2]
    if not np.isfinite(block).all():
        raise ValueError('Nodos faltantes en la interpolación bilineal.')
    return (block * np.array([[(1-wy)*(1-wx), (1-wy)*wx], [wy*(1-wx), wy*wx]])).sum(axis=(-2,-1))

def alinear(obs, model, *, reloj, utc_offset=None, minutos_obs=11, horas_wrf=-2):
    obs, model = obs.copy(), model.copy()
    obs['Fecha_original'] = pd.to_datetime(obs.Fecha_original)
    model['fecha_wrf_utc'] = pd.to_datetime(model.fecha_wrf_utc)
    unique_times(obs, 'Fecha_original'); unique_times(model, 'fecha_wrf_utc')
    if reloj == 'legacy_provisional':
        obs['fecha_analisis'] = obs.Fecha_original + pd.Timedelta(minutes=minutos_obs)
        model['fecha_analisis'] = model.fecha_wrf_utc + pd.Timedelta(hours=horas_wrf)
    elif reloj == 'estandar_fijo':
        if utc_offset is None:
            raise ValueError('Especifique el offset UTC de la estación confirmado documentalmente.')
        # minutos_obs representa el rótulo de la medición, no un huso horario.
        obs['fecha_analisis'] = obs.Fecha_original + pd.Timedelta(minutes=minutos_obs)
        model['fecha_analisis'] = model.fecha_wrf_utc + pd.Timedelta(hours=utc_offset)
    else:
        raise ValueError('Reloj desconocido.')
    pairs = model.merge(obs, on='fecha_analisis', how='inner', validate='one_to_one')
    pairs['periodo'] = periodo(pairs.fecha_analisis)
    pairs = pairs.loc[pairs.periodo != 'FUERA'].copy()
    pairs['WS_wrf_m_s'] = np.hypot(pairs.u_earth_m_s, pairs.v_earth_m_s)
    pairs['WD_wrf_deg'] = direccion(pairs.u_earth_m_s, pairs.v_earth_m_s)
    pairs['u_obs_m_s'], pairs['v_obs_m_s'] = componentes(pairs.Velocidad_viento_m_s, pairs.Direccion_viento_grados)
    pairs['residuo_T_C'] = pairs.Temperatura_aire_C - pairs.T2_C
    pairs['residuo_WS_m_s'] = pairs.Velocidad_viento_m_s - pairs.WS_wrf_m_s
    pairs['residuo_u_m_s'] = pairs.u_obs_m_s - pairs.u_earth_m_s
    pairs['residuo_v_m_s'] = pairs.v_obs_m_s - pairs.v_earth_m_s
    valid = (pairs.Velocidad_viento_m_s >= 1) & (pairs.WS_wrf_m_s >= 1)
    pairs['residuo_WD_deg'] = np.where(valid, diferencia_angular(pairs.Direccion_viento_grados, pairs.WD_wrf_deg), np.nan)
    pairs['reloj'] = reloj
    return pairs.sort_values('fecha_analisis').reset_index(drop=True)

def metricas(pairs):
    out = []
    for name, part in pairs.groupby('periodo'):
        for var in ['T_C','WS_m_s','u_m_s','v_m_s','WD_deg']:
            e = part['residuo_'+var].dropna().to_numpy()
            if not len(e):
                continue
            bias = np.rad2deg(np.arctan2(np.sin(np.deg2rad(e)).mean(), np.cos(np.deg2rad(e)).mean())) if var=='WD_deg' else e.mean()
            out.append({'periodo':name,'variable':var,'n':len(e),'sesgo_obs_menos_WRF':float(bias),
                        'MAE':float(np.abs(e).mean()),'RMSE':float(np.sqrt(np.mean(e**2)))})
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--observaciones',required=True);p.add_argument('--wrf',required=True)
    p.add_argument('--salida',required=True)
    p.add_argument('--reloj',required=True,choices=['legacy_provisional','estandar_fijo'])
    p.add_argument('--utc-offset',type=float);p.add_argument('--minutos-obs',type=int,default=11)
    a=p.parse_args()
    pairs=alinear(pd.read_csv(a.observaciones),pd.read_csv(a.wrf),reloj=a.reloj,utc_offset=a.utc_offset,minutos_obs=a.minutos_obs)
    if pairs.empty:raise ValueError('No hay pares en los períodos de tesis.')
    dest=salida_nueva(a.salida);pairs.to_csv(dest/'residuos_firmados.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(metricas(pairs)).to_csv(dest/'metricas.csv',index=False,encoding='utf-8-sig')
    guardar_json(dest/'manifest.json',{'reloj':a.reloj,'utc_offset':a.utc_offset,'minutos_obs':a.minutos_obs,
      'signo':'observacion - WRF','pares':len(pairs),'obs_sha256':sha256(a.observaciones),'wrf_sha256':sha256(a.wrf),
      'alcance':'Diagnóstico condicionado al reloj y cobertura disponibles; no calibración final automática.'})
    print(f'{len(pairs)} pares; signo de residuos: observación menos WRF.')

if __name__=='__main__':main()
