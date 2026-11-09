"""P90 complementario y bloques multivariados; no define un modelo de incertidumbre completo."""
import argparse
import numpy as np
import pandas as pd
from .comun import unique_times, periodo, salida_nueva, guardar_json, sha256

def tabla_p90(pairs, minimo=20):
    if minimo < 20:
        raise ValueError('El mínimo metodológico es 20 pares válidos por período y hora.')
    d=pairs.copy();d['fecha_analisis']=pd.to_datetime(d.fecha_analisis)
    unique_times(d,'fecha_analisis');d['periodo']=periodo(d.fecha_analisis);d['hora']=d.fecha_analisis.dt.hour
    rows=[]
    for season in ['VERANO','INVIERNO']:
        for hour in range(24):
            sub=d.loc[(d.periodo==season)&(d.hora==hour)]
            for variable in ['T_C','WS_m_s']:
                e=pd.to_numeric(sub['residuo_'+variable],errors='raise').dropna().to_numpy()
                e=e[np.isfinite(e)]
                rows.append({'periodo':season,'hora':hour,'variable':variable,'n':len(e),
                             'P90_abs':float(np.quantile(abs(e),.9,method='linear')) if len(e)>=minimo else np.nan,
                             'estado':'DISPONIBLE' if len(e)>=minimo else 'INSUFICIENTE'})
    return pd.DataFrame(rows)

def bloques_validos(calibracion, longitud):
    """Índices de bloques completos, horarios y de una misma estación.

    La entrada debe ser sólo la muestra de calibración elegida externamente.
    No se eliminan huecos antes de buscar bloques; T,u,v viajan juntos.
    """
    if not isinstance(longitud,int) or longitud<1:raise ValueError('Longitud entera positiva requerida.')
    d=calibracion.copy().reset_index(drop=True);d['fecha_analisis']=pd.to_datetime(d.fecha_analisis)
    unique_times(d,'fecha_analisis')
    if not d.fecha_analisis.is_monotonic_increasing:raise ValueError('Ordene la calibración por fecha.')
    t=d.fecha_analisis.to_numpy();season=periodo(t)
    finite=np.isfinite(d[['residuo_T_C','residuo_u_m_s','residuo_v_m_s']].to_numpy(float)).all(axis=1)
    blocks=[]
    for start in range(len(d)-longitud+1):
        end=start+longitud
        if finite[start:end].all() and season[start]!='FUERA' and np.all(season[start:end]==season[start]) and np.all(np.diff(t[start:end])==np.timedelta64(1,'h')):
            blocks.append(np.arange(start,end))
    return blocks

def muestrear_bloque(calibracion, longitud, *, periodo_objetivo, hora_inicio, semilla):
    """Un bloque piloto condicionado a período y hora; conserva covariación."""
    d=calibracion.reset_index(drop=True);times=pd.to_datetime(d.fecha_analisis)
    candidates=[b for b in bloques_validos(d,longitud)
                if periodo([times.iloc[b[0]]])[0]==periodo_objetivo and times.iloc[b[0]].hour==hora_inicio]
    if not candidates:raise ValueError('No hay bloques válidos para este período, hora y longitud.')
    selected=candidates[np.random.default_rng(semilla).integers(len(candidates))]
    return d.iloc[selected].copy()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--residuos',required=True);p.add_argument('--salida',required=True)
    a=p.parse_args();tab=tabla_p90(pd.read_csv(a.residuos));dest=salida_nueva(a.salida)
    tab.to_csv(dest/'p90_por_periodo_hora.csv',index=False,encoding='utf-8-sig')
    guardar_json(dest/'manifest.json',{'residuos_sha256':sha256(a.residuos),'minimo_pares':20,'cuantil':'numpy linear',
        'uso':'Sensibilidad complementaria; ±P90 no es intervalo predictivo de cobertura 90%.',
        'celdas_insuficientes':int((tab.estado=='INSUFICIENTE').sum())})
    print('P90 calculado sin interpolar ni rellenar horas insuficientes.')

if __name__=='__main__':main()
