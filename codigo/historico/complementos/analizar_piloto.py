"""Figuras y diagnóstico exploratorio del piloto WRF; no ejecuta dispersión.

Reutiliza el contrato de reloj auditado. Los CSV son tablas de datos científicos,
no un ajuste del modelo de discrepancias ni una validación independiente.
"""
from pathlib import Path
import sys, json, hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT = Path(__file__).resolve().parent
LIB = Path(r'/archivo/usuario\Documents\Codex\2026-10-08\hem\outputs\Biblioteca_Tesis')
AUDIT = LIB.parent / 'Datos_Auditados'
sys.path.insert(0, str(LIB))
from tesis.reloj import parear, comparar

OUT = ROOT / 'Piloto_meteorologico'
FIG = OUT / 'Figuras'
FIG.mkdir(exist_ok=True)
START = pd.Timestamp('2016-12-21 03:00:00')
END = pd.Timestamp('2017-01-31 03:00:00')
HASH = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':10,
                     'axes.spines.top':False,'axes.spines.right':False,
                     'axes.titleweight':'bold','axes.grid':True,'grid.alpha':.18,
                     'savefig.facecolor':'white'})
colors = {'Estacion':'#176b9d','Punto_MMIF':'#d17a23','obs':'#252b35'}

def save(fig, name, footer):
    fig.text(.02,.013,footer,fontsize=8,color='#4b5563')
    fig.tight_layout(rect=(0,.055,1,.94))
    for ext in ('png','pdf'):
        fig.savefig(FIG/f'{name}.{ext}',dpi=170)
    plt.close(fig)

data, summaries = {}, []
for site in ('Estacion','Punto_MMIF'):
    path=OUT/site/'wrf_estacion.csv'
    m=json.loads((OUT/site/'manifest.json').read_text(encoding='utf-8'))
    assert m['serie_sha256']==HASH(path)
    d=pd.read_csv(path,parse_dates=['fecha_wrf_utc'])
    assert not d.fecha_wrf_utc.duplicated().any()
    assert len(d)==984 and d.fecha_wrf_utc.min()==START and d.fecha_wrf_utc.max()==END-pd.Timedelta(hours=1)
    assert d.fecha_wrf_utc.diff().dropna().eq(pd.Timedelta(hours=1)).all()
    assert np.isfinite(d[['T2_C','u_earth_m_s','v_earth_m_s']]).all().all()
    d['WS_m_s']=np.hypot(d.u_earth_m_s,d.v_earth_m_s)
    d['hora_local_provisional']=d.fecha_wrf_utc-pd.Timedelta(hours=3)
    data[site]=d
    for col in ('T2_C','u_earth_m_s','v_earth_m_s','WS_m_s'):
        a=d[col]
        summaries.append({'sitio':site,'variable':col,'n':len(a),'media':a.mean(),
          'mediana':a.median(),'desv_estandar_temporal':a.std(ddof=1),
          'p10_temporal':a.quantile(.1),'p90_temporal':a.quantile(.9),'minimo':a.min(),'maximo':a.max()})
    cycle=d.groupby(d.hora_local_provisional.dt.hour)[['T2_C','u_earth_m_s','v_earth_m_s','WS_m_s']].agg(['count','mean','median','std'])
    cycle.to_csv(OUT/site/'ciclo_UTCmenos3_descriptivo.csv',encoding='utf-8-sig')
pd.DataFrame(summaries).to_csv(OUT/'resumen_variabilidad_temporal.csv',index=False,encoding='utf-8-sig')

# Soporte adicional para interpolar observaciones dentro de la última hora.
# El extractor ya cotejó los hashes de TODOS los WRF de este cache.
support_path=AUDIT/'WRF_Disponible'/'wrf_estacion.csv'
station_manifest=json.loads((OUT/'Estacion'/'manifest.json').read_text(encoding='utf-8'))
assert station_manifest['cache_serie_sha256']==HASH(support_path)
support=pd.read_csv(support_path,parse_dates=['fecha_wrf_utc'])
support=support.loc[support.fecha_wrf_utc.between(START,END)].copy()
assert len(support)==985
support.to_csv(OUT/'Estacion'/'soporte_interpolacion_985_tiempos.csv',index=False,encoding='utf-8-sig')
obs_path=AUDIT/'Observaciones'/'observaciones_normalizadas.csv'
obs=pd.read_csv(obs_path,parse_dates=['Fecha_original'])
obs=obs.loc[(obs.Fecha_original>=pd.Timestamp('2016-12-21')) & (obs.Fecha_original<pd.Timestamp('2017-01-31'))].copy()
assert obs.Fecha_original.is_unique
obs.to_csv(OUT/'observaciones_piloto_auditadas.csv',index=False,encoding='utf-8-sig')
p=parear(obs,support,hipotesis='civil_santiago',operador='interpolacion_instantanea')
p['par_valido_Tuv']=np.isfinite(p[['residuo_T_C','residuo_u_m_s','residuo_v_m_s']]).all(axis=1)
p.to_csv(OUT/'pares_civil_interpolacion_exploratorios.csv',index=False,encoding='utf-8-sig')
metrics=comparar(obs,support)
metrics=metrics.loc[metrics.periodo.eq('VERANO')].copy()
metrics.to_csv(OUT/'sensibilidad_reloj_muestra_comun.csv',index=False,encoding='utf-8-sig')

fig,axes=plt.subplots(2,1,figsize=(12,6.8),sharex=True)
for ax,col,label in zip(axes,('T2_C','WS_m_s'),('Temperatura WRF (°C)','Rapidez WRF (m/s)')):
    for site,name in [('Estacion','Ubicación de la estación'),('Punto_MMIF','Ubicación del punto MMIF')]:
        ax.plot(data[site].hora_local_provisional,data[site][col],lw=.8,color=colors[site],alpha=.9,label=name)
    ax.set_ylabel(label)
axes[0].legend(loc='upper left',ncol=2,fontsize=9)
axes[-1].xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d-%b'))
axes[-1].set_xlabel('Fecha en UTC−3 provisional')
fig.suptitle('WRF d03 · series del piloto | 21 dic 2016–30 ene 2017',fontsize=14,fontweight='bold')
save(fig,'01_series_WRF','984 horas por sitio. Ambas curvas son WRF; la del punto MMIF no es una salida de MMIF/AERMET. Sin observaciones en esta figura.')

fig,axes=plt.subplots(1,2,figsize=(11,4.8))
for ax,col,label in zip(axes,('T2_C','WS_m_s'),('Temperatura WRF (°C)','Rapidez WRF (m/s)')):
    for site,name in [('Estacion','Ubicación de la estación'),('Punto_MMIF','Ubicación del punto MMIF')]:
        g=data[site].groupby(data[site].hora_local_provisional.dt.hour)[col]
        x=np.array(list(g.groups))
        ax.plot(x,g.mean(),color=colors[site],lw=2,label=name)
        ax.fill_between(x,g.quantile(.1).to_numpy(),g.quantile(.9).to_numpy(),color=colors[site],alpha=.12)
    ax.set(xlabel='Hora UTC−3 provisional',ylabel=label,xticks=range(0,24,3),xlim=(0,23))
axes[0].legend(fontsize=8)
fig.suptitle('Ciclo diario WRF · media y percentiles temporales 10–90',fontsize=14,fontweight='bold')
save(fig,'02_ciclos_WRF','41 valores por hora y sitio. Las bandas describen variabilidad entre días; no son intervalos de incertidumbre ni de confianza.')

fig,axes=plt.subplots(2,2,figsize=(12,7.5))
for row,oc,mc,label in [(0,'Temperatura_aire_C','T2_C','Temperatura (°C)'),(1,'Velocidad_viento_m_s','WS_wrf_m_s','Rapidez (m/s)')]:
    valid=np.isfinite(p[[oc,mc]]).all(axis=1)
    d=p.loc[valid].copy()
    axes[row,0].plot(d.Fecha_original,d[oc],color=colors['obs'],lw=.7,label='DGA')
    axes[row,0].plot(d.Fecha_original,d[mc],color=colors['Estacion'],lw=.7,alpha=.8,label='WRF interpolado')
    g=d.groupby(d.Fecha_original.dt.hour)[[oc,mc]].mean()
    axes[row,1].plot(g.index,g[oc],color=colors['obs'],lw=2,label='DGA')
    axes[row,1].plot(g.index,g[mc],color=colors['Estacion'],lw=2,label='WRF interpolado')
    axes[row,0].set_ylabel(label);axes[row,1].set_ylabel(label)
    axes[row,0].xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    axes[row,0].xaxis.set_major_formatter(mdates.DateFormatter('%d-%b'))
    axes[row,1].set(xticks=range(0,24,3),xlim=(0,23))
axes[0,0].legend(fontsize=9);axes[0,1].legend(fontsize=9)
axes[0,0].set_title('Series emparejadas');axes[0,1].set_title('Ciclos sobre los mismos pares')
axes[1,0].set_xlabel('Fecha del registro DGA');axes[1,1].set_xlabel('Hora del registro DGA (:49)')
fig.suptitle('Comparación exploratoria · hipótesis civil + interpolación T/u/v',fontsize=13,fontweight='bold')
save(fig,'03_comparacion_DGA',f'{int(p.par_valido_Tuv.sum())} pares válidos T/u/v. Reloj y soporte instantáneo supuestos; alturas de sensores desconocidas. Sin evaluación independiente.')

sel=metrics.loc[(metrics.operador=='interpolacion_instantanea') & ~metrics.hipotesis.eq('fijo_menos3')]
fig,axes=plt.subplots(1,2,figsize=(10,4.5))
names={'civil_santiago':'Civil Santiago','fijo_menos4':'UTC−4 fijo','utc':'UTC'}
for ax,var,label in zip(axes,('T_C','WS_m_s'),('RMSE temperatura (°C)','RMSE rapidez (m/s)')):
    a=sel.loc[sel.variable.eq(var)]
    bars=ax.bar([names[x] for x in a.hipotesis],a.RMSE,color=['#176b9d','#8796a5','#d17a23'],width=.55)
    ax.bar_label(bars,fmt='%.2f',padding=3)
    ax.set_ylabel(label);ax.set_ylim(0,a.RMSE.max()*1.2)
    ax.set_title(f'Muestra común: {int(a.n_comun.iloc[0])} pares')
fig.suptitle('Sensibilidad al reloj supuesto de las observaciones',fontsize=14,fontweight='bold')
save(fig,'04_sensibilidad_reloj','Interpolación de T/u/v; rapidez derivada del vector. La menor RMSE no identifica el reloj correcto. Legado y vecino: véase CSV completo.')

report={'analisis_UTC':[str(START),str(END)],'fin_exclusivo':True,'reloj_dias':'UTC-3 provisional; coincide con hipótesis civil de verano',
  'horas_por_sitio':984,'dias_completos':41,'obs_registros_en_ventana_por_rotulo':len(obs),'pares_civil_Tuv':int(p.par_valido_Tuv.sum()),
  'horas_soporte_interpolacion':len(support),'residuo':'observado - WRF',
  'observaciones_sha256':HASH(obs_path),'script_sha256':HASH(__file__),
  'tablas_reloj_codigo_sha256':HASH(LIB/'tesis'/'reloj.py'),
  'alcance':'Descriptivos y sensibilidad de emparejamiento. No se ajustó generador estocástico ni se ejecutó MMIF/AERMET/AERMOD.',
  'restricciones':['Los pares son exploratorios y previamente expuestos en auditorías; no validación independiente.',
  'No se asignan probabilidades a hipótesis de reloj ni a escenarios.',
  'Los atributos y hashes no acreditan enlace con el trabajo NLHPC actualmente activo.',
  'Extracción bilineal terrestre en punto MMIF: diagnóstico espacial, no reproducción exacta del muestreo del ejecutable MMIF.']}
(OUT/'resumen_entrega.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
