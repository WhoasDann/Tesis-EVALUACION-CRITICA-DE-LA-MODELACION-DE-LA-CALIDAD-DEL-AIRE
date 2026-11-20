"""Diagnóstico de hipótesis de reloj; no selecciona un huso por menor error."""
import argparse
from datetime import timezone, timedelta
import numpy as np
import pandas as pd
from .comun import periodo, unique_times, salida_nueva, guardar_json, sha256
from .validacion import componentes, direccion, diferencia_angular

HIPOTESIS = ('civil_santiago', 'fijo_menos3', 'fijo_menos4', 'utc')
VARIABLES = ('T2_C', 'u_earth_m_s', 'v_earth_m_s')

def a_utc(fechas, hipotesis):
    """Conserva minutos. No corrige automáticamente horas inexistentes/ambiguas."""
    t = pd.DatetimeIndex(pd.to_datetime(fechas))
    if t.tz is not None or t.hasnans:
        raise ValueError('Se requieren fechas originales sin zona y sin ausencias.')
    zones = {'civil_santiago': 'America/Santiago', 'fijo_menos3': timezone(timedelta(hours=-3)),
             'fijo_menos4': timezone(timedelta(hours=-4)), 'utc': 'UTC'}
    if hipotesis not in zones:
        raise ValueError('Hipótesis de reloj desconocida.')
    return t.tz_localize(zones[hipotesis], ambiguous='raise', nonexistent='raise').tz_convert('UTC')

def muestrear_wrf(model, objetivos_utc, *, operador):
    """Interpola T,u,v entre salidas separadas <=1h, o empareja a <=15min.

    Son operadores para observaciones instantáneas. Si la estación informa medias,
    debe usarse su ventana documentada: esta función no adivina esa ventana.
    """
    m = model.copy().sort_values('fecha_wrf_utc')
    m['fecha_wrf_utc'] = pd.to_datetime(m.fecha_wrf_utc, utc=True)
    unique_times(m, 'fecha_wrf_utc')
    if len(m) < 2:
        raise ValueError('Se requieren al menos dos salidas WRF.')
    target = pd.DatetimeIndex(objetivos_utc)
    if target.tz is None or target.hasnans:
        raise ValueError('Los objetivos deben llevar zona UTC explícita.')
    target = target.tz_convert('UTC')
    x = pd.DatetimeIndex(m.fecha_wrf_utc).as_unit('ns').asi8
    q = target.as_unit('ns').asi8
    right = np.searchsorted(x, q)
    ri = np.clip(right, 0, len(x)-1); le = np.clip(right-1, 0, len(x)-1)
    exact = x[ri] == q
    values = m[list(VARIABLES)].to_numpy(float)
    if operador == 'interpolacion_instantanea':
        delta = x[ri] - x[le]
        valid = exact | ((right > 0) & (right < len(x)) & (delta <= 3600*10**9) & (delta > 0))
        fraction = np.divide(q-x[le], delta, out=np.zeros(len(q), dtype=float), where=delta>0)
        result = values[le] + fraction[:, None]*(values[ri]-values[le])
        result[exact] = values[ri[exact]]
        distance = np.full(len(q), np.nan)
    elif operador == 'vecino_15min':
        # El empate exacto va al instante anterior. No mueve el reloj original.
        nearest = np.where(np.abs(q-x[le]) <= np.abs(x[ri]-q), le, ri)
        distance = (x[nearest]-q)/(60*10**9)
        valid = (q >= x[0]) & (q <= x[-1]) & (np.abs(distance) <= 15)
        result = values[nearest].copy()
    else:
        raise ValueError('Operador temporal desconocido.')
    result[~valid] = np.nan
    out = pd.DataFrame(result, columns=VARIABLES)
    out['fecha_objetivo_utc'] = target
    out['diferencia_vecino_min'] = distance
    return out

def parear(obs, model, *, hipotesis, operador):
    """Muestra diagnóstica seleccionada por fecha ORIGINAL; no calendario MMIF final."""
    o = obs.copy().reset_index(drop=True)
    o['Fecha_original'] = pd.to_datetime(o.Fecha_original)
    unique_times(o, 'Fecha_original')
    o['periodo'] = periodo(o.Fecha_original)
    o = o.loc[o.periodo != 'FUERA'].reset_index(drop=True)
    utc = a_utc(o.Fecha_original, hipotesis)
    m = muestrear_wrf(model, utc, operador=operador)
    p = pd.concat([o, m], axis=1)
    p['hipotesis'] = hipotesis; p['operador'] = operador
    p['u_obs_m_s'], p['v_obs_m_s'] = componentes(p.Velocidad_viento_m_s, p.Direccion_viento_grados)
    p['WS_wrf_m_s'] = np.hypot(p.u_earth_m_s, p.v_earth_m_s)
    p['WD_wrf_deg'] = direccion(p.u_earth_m_s, p.v_earth_m_s)
    for label, ob, wr in [('T_C','Temperatura_aire_C','T2_C'), ('WS_m_s','Velocidad_viento_m_s','WS_wrf_m_s'),
                           ('u_m_s','u_obs_m_s','u_earth_m_s'), ('v_m_s','v_obs_m_s','v_earth_m_s')]:
        p['residuo_'+label] = p[ob]-p[wr]
    p['residuo_WD_deg'] = np.where((p.Velocidad_viento_m_s>=1)&(p.WS_wrf_m_s>=1),
                                        diferencia_angular(p.Direccion_viento_grados,p.WD_wrf_deg), np.nan)
    return p

def comparar(obs, model):
    """Compara cada variable sobre los mismos registros en TODAS las hipótesis."""
    cases = []
    for h in HIPOTESIS:
        for op in ('interpolacion_instantanea','vecino_15min'):
            cases.append(parear(obs,model,hipotesis=h,operador=op))
    # El legacy es sólo un control del cálculo antiguo. No es un huso candidato.
    old = parear(obs,model,hipotesis='utc',operador='vecino_15min')
    target = pd.DatetimeIndex(pd.to_datetime(old.Fecha_original,utc=True)) + pd.Timedelta(hours=2,minutes=11)
    sampled = muestrear_wrf(model,target,operador='vecino_15min')
    for c in VARIABLES: old[c] = sampled[c]
    old['fecha_objetivo_utc'] = target
    old['hipotesis'] = 'legacy_mas2h11';old['operador'] = 'control_historico'
    old['WS_wrf_m_s'] = np.hypot(old.u_earth_m_s, old.v_earth_m_s)
    old['WD_wrf_deg'] = direccion(old.u_earth_m_s, old.v_earth_m_s)
    for label, ob, wr in [('T_C','Temperatura_aire_C','T2_C'),('WS_m_s','Velocidad_viento_m_s','WS_wrf_m_s'),
                          ('u_m_s','u_obs_m_s','u_earth_m_s'),('v_m_s','v_obs_m_s','v_earth_m_s')]:
        old['residuo_'+label] = old[ob]-old[wr]
    old['residuo_WD_deg'] = np.where((old.Velocidad_viento_m_s>=1)&(old.WS_wrf_m_s>=1),
                                        diferencia_angular(old.Direccion_viento_grados,old.WD_wrf_deg),np.nan)
    cases.append(old)
    rows = []
    for season in ('VERANO','INVIERNO'):
        for variable in ('T_C','WS_m_s','u_m_s','v_m_s','WD_deg'):
            col = 'residuo_'+variable
            mask = cases[0].periodo.eq(season).to_numpy(copy=True)
            for p in cases: mask &= np.isfinite(p[col].to_numpy())
            for p in cases:
                e = p.loc[mask,col].to_numpy(); n=len(e)
                bias = (np.rad2deg(np.arctan2(np.sin(np.deg2rad(e)).mean(),np.cos(np.deg2rad(e)).mean()))
                        if variable=='WD_deg' else e.mean()) if n else np.nan
                rows.append({'periodo':season,'hipotesis':p.hipotesis.iloc[0],'operador':p.operador.iloc[0],
                             'variable':variable,'n_comun':n,'sesgo_obs_menos_WRF':bias,
                             'MAE':np.abs(e).mean() if n else np.nan,'RMSE':np.sqrt(np.mean(e**2)) if n else np.nan})
    return pd.DataFrame(rows)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('observaciones','wrf','salida'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args();o=pd.read_csv(a.observaciones);m=pd.read_csv(a.wrf)
    metrics=comparar(o,m);dest=salida_nueva(a.salida)
    metrics.to_csv(dest/'metricas_hipotesis_muestra_comun.csv',index=False,encoding='utf-8-sig')
    t=pd.to_datetime(o.Fecha_original)
    o.loc[(t>='2017-08-12 20:00')&(t<'2017-08-13 05:00')].to_csv(dest/'evidencia_salto_agosto.csv',index=False,encoding='utf-8-sig')
    guardar_json(dest/'manifest.json',{'obs_sha256':sha256(a.observaciones),'wrf_sha256':sha256(a.wrf),
        'signo':'observacion - WRF','seleccion':'Períodos por rótulo original, muestra común entre hipótesis por variable.',
        'alcance':'Exploración de reloj y operador; no evaluación independiente ni confirmación de huso.',
        'seleccion_automatica_de_huso':False,'ventana_observacional':'Desconocida; operadores instantáneos son hipótesis.'})

if __name__=='__main__':main()
