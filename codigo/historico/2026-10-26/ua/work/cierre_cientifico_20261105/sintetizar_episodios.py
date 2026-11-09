"""Summarize all complete civil days, retaining BASE and paired comparisons.

Uses already checked hourly products. No simulation, new scenario or hybrid series.
"""
from pathlib import Path
import json, hashlib
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
C=ROOT/'outputs/Cierre_cientifico_2026-11-05'
OUT=C/'Sintesis_episodios';OUT.mkdir(exist_ok=True)
FIG=OUT/'Figuras';FIG.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,v):(OUT/n).write_text(json.dumps(v,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
def fmt(x,n=3):
    if 0<abs(x)<.001:n=6
    elif 0<abs(x)<.01:n=4
    return f'{x:.{n}f}'.replace('.',',')
paths=[C/'Diagnostico_horario_128_comparaciones.csv',C/'Horas_pareadas_con_meteorologia.csv']
d=pd.read_csv(paths[0]);h=pd.read_csv(paths[1]);assert len(d)==128 and len(h)==3072
keys=['season','day','scenario','pollutant','receptor']
means=h.groupby(keys).agg(n=('C_ug_m3','size'),b=('C_ug_m3_BASE','mean'),c=('C_ug_m3','mean')).reset_index()
q=means.merge(d,on=keys,validate='one_to_one');assert len(q)==128 and q.n.eq(24).all()
assert np.max(abs(q.b-q.BASE_mean))<1e-8 and np.max(abs(q.c-q.candidate_mean))<1e-8
base=d[['season','day','pollutant','receptor','BASE_mean']].drop_duplicates()
assert not base.duplicated(['season','day','pollutant','receptor']).any()
base=base.rename(columns={'BASE_mean':'daily_mean'});base['scenario']='BASE'
alt=d[keys+['candidate_mean']].rename(columns={'candidate_mean':'daily_mean'})
all_days=pd.concat([base,alt],ignore_index=True).sort_values(keys)
assert len(all_days)==216
all_days.to_csv(OUT/'Todas_las_medias_diarias.csv',index=False)

rows=[]
for key,g in d.groupby(['season','receptor','pollutant']):
    season,receptor,pollutant=key
    b=base[(base.season==season)&(base.receptor==receptor)&(base.pollutant==pollutant)]
    bm=b.sort_values(['daily_mean','day'],ascending=[False,True]).iloc[0]
    cm=g.sort_values(['candidate_mean','day','scenario'],ascending=[False,True,True]).iloc[0]
    change=g.sort_values(['delta_mean','day','scenario'],ascending=[False,True,True]).iloc[0]
    expected=5 if season=='VERANO' else 6
    assert b.day.nunique()==expected
    winner='BASE' if bm.daily_mean>=cm.candidate_mean else cm.scenario
    rows.append(dict(season=season,receptor=receptor,pollutant=pollutant,comparable_days=expected,
        BASE_max_episode=bm.daily_mean,BASE_max_day=bm.day,
        tuple_max_episode=cm.candidate_mean,tuple_max_scenario=cm.scenario,tuple_max_day=cm.day,
        tuple_max_minus_BASE_max=cm.candidate_mean-bm.daily_mean,
        tuple_max_vs_BASE_max_pct=100*(cm.candidate_mean/bm.daily_mean-1),
        winner_including_BASE=winner,winner_day=bm.day if winner=='BASE' else cm.day,
        paired_BASE_on_tuple_max_day=cm.BASE_mean,paired_delta_pct_on_tuple_max_day=cm.delta_pct,
        largest_paired_increase_day=change.day,largest_paired_increase_scenario=change.scenario,
        largest_paired_increase_absolute=change.delta_mean,largest_paired_increase_pct=change.delta_pct,
        cases_increasing_same_day=int(g.delta_mean.gt(1e-10).sum()),tuple_cases_compared=len(g),
        interpretation='Maximum over complete evaluated days only; physically conditional; not seasonal maximum or a mixed hourly series.'))
summary=pd.DataFrame(rows);summary.to_csv(OUT/'Maximos_y_cambios_pareados_16_grupos.csv',index=False)

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
receptors=['Los Bronces','Piedra Carvajal','Sulfatos','La Paloma']
colors={'BASE':'#263b4b','OBS_U':'#d86b28','OBS_V':'#008d80'}
for pollutant,label in [('MP10','MP10'),('MP25','MP2,5')]:
    fig,axes=plt.subplots(4,2,figsize=(14,13))
    fig.subplots_adjust(top=.85,bottom=.10,left=.08,right=.97,hspace=.68,wspace=.25)
    for row,receptor in enumerate(receptors):
        for col,season in enumerate(['VERANO','INVIERNO']):
            ax=axes[row,col]
            g=all_days[(all_days.season==season)&(all_days.receptor==receptor)&(all_days.pollutant==pollutant)]
            dates=sorted(g.day.unique());order=['BASE','OBS_U','OBS_V'] if season=='VERANO' else ['BASE','OBS_U']
            for k,sc in enumerate(order):
                gg=g[g.scenario==sc].set_index('day').loc[dates]
                ax.scatter(np.arange(len(dates))+(k-(len(order)-1)/2)*.19,gg.daily_mean,
                    c=colors[sc],s=45,marker={'BASE':'s','OBS_U':'o','OBS_V':'^'}[sc],label=sc,zorder=3)
            r=summary[(summary.season==season)&(summary.receptor==receptor)&(summary.pollutant==pollutant)].iloc[0]
            ax.set_title(f'{receptor} · {season.title()}',loc='left',fontweight='bold',fontsize=12,pad=27)
            ax.text(0,1.055,f'Máximo BASE: {fmt(r.BASE_max_episode)}   |   máximo ternas: {fmt(r.tuple_max_episode)}',
                transform=ax.transAxes,fontsize=9.5,color='#34434c')
            ax.set_xticks(np.arange(len(dates)),[pd.Timestamp(t).strftime('%d/%m') for t in dates])
            ax.set_ylim(-g.daily_mean.max()*.06,g.daily_mean.max()*1.18);ax.set_ylabel('Media diaria (µg/m³)');ax.grid(axis='y',alpha=.2)
    fig.suptitle(f'{label}: BASE y ternas en los cuatro receptores',x=.08,y=.975,ha='left',fontsize=20,fontweight='bold')
    fig.text(.08,.94,'Cada punto representa 24 horas del mismo escenario. Se incluyen aumentos y disminuciones.',fontsize=12)
    fig.text(.08,.918,'Verano: 5 días; invierno: 6 días. Estos máximos corresponden solo a los episodios evaluados.',fontsize=12)
    fig.legend(*axes[0,0].get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.5,.044),ncol=3,frameon=False)
    fig.text(.08,.027,'Escalas verticales propias por panel. Aportes modelados; no concentración total ni evaluación de cumplimiento normativo.',fontsize=10)
    fig.text(.08,.012,'OBS_U / OBS_V: ternas de discrepancias empíricas aplicadas al modelo; no atmósferas observadas ni escenarios ya validados.',fontsize=10)
    for ext in ['png','svg']:fig.savefig(FIG/f'Episodios_cuatro_receptores_{pollutant}.{ext}',dpi=180)
    plt.close(fig)

lines=['# Qué significa el máximo de las ternas en cada receptor','',
 'Se revisan los cuatro receptores en verano e invierno y ambos contaminantes. Las 128 comparaciones se recalculan desde 3072 pares horarios, todos de 24 horas. Al deduplicar BASE quedan 216 medias diarias y 16 grupos receptor–temporada–contaminante.',
 '', '## Tres preguntas que se deben distinguir','',
 '1. ¿Cuánto cambia un día? Comparar una terna con BASE de la misma fecha.',
 '2. ¿Cuál es el mayor día entre los episodios? Obtener el máximo de las medias diarias de cada escenario dentro de las mismas 5/6 fechas, conservando fecha y escenario.',
 '3. ¿La terna supera el máximo BASE de todo el período? Requiere una comparación adicional con el período estacional y no es equivalente a las dos preguntas anteriores.',
 '', 'No se construye una serie con máximos horarios mezclados. Tampoco se presenta una media o máximo estacional nuevo de las ternas.',
 '', '## Resultados de MP10','',
 '| Temporada | Receptor | Máximo BASE en episodios | Máximo de ternas en episodios | Escenario con mayor día, incluyendo BASE |',
 '|---|---|---:|---:|---|']
for season in ['VERANO','INVIERNO']:
    for receptor in receptors:
        r=summary[(summary.season==season)&(summary.receptor==receptor)&summary.pollutant.eq('MP10')].iloc[0]
        lines.append(f'| {season.title()} | {receptor} | {fmt(r.BASE_max_episode)} ({r.BASE_max_day}) | {fmt(r.tuple_max_episode)} ({r.tuple_max_day}, {r.tuple_max_scenario}) | {r.winner_including_BASE} |')
lines += ['', 'Unidades: µg/m³, aporte modelado. Las fechas de los dos máximos pueden diferir. Los cambios pareados exactos están en la tabla de 16 grupos.',
 '', '**Sulfatos ilustra la diferencia:** OBS_V aumenta el 12 de enero de 0,960 a 1,815 µg/m³, pero no supera el máximo BASE entre los cinco episodios, de 4,046 µg/m³ el 26 de enero. El máximo de las ternas es 3,336 µg/m³ ese 26 de enero. Por eso no se debe presentar el aumento del 12 como un nuevo máximo del período.',
 '', '**Invierno:** la terna OBS_U no supera el máximo BASE entre los seis episodios en ninguno de los cuatro receptores. La tabla conserva todos los días y todas las disminuciones. Para Los Bronces, el pequeño aumento del 2 de agosto se distingue del máximo BASE de otro día. Un aumento pareado no garantiza superar ese máximo.',
 '', 'MP2,5 está comprobado por separado en las tablas y en su figura, sin copiar porcentajes de MP10. Los dos contaminantes producen la misma identificación de escenario máximo dentro de estos episodios; sus magnitudes se mantienen independientes.',
 '', '## Qué cambió al revisar el WRF original','',
 'Se recuperó la cobertura original de observaciones del 26 de enero y 20 de febrero. Se reprodujeron las tres ternas y se cuantificó el contraste entre estación, columna MMIF y cuatro receptores en 14 días. Consultar ../Transferencia_WRF/Resultados_transferencia.md y sus tres figuras. La heterogeneidad espacial no constituye por sí sola validación o rechazo físico.',
 '', '## Decisión y siguientes brechas','',
 '- Cálculo numérico y resumen de episodios: completos y verificados.',
 '- Admisión física: pendiente. La coincidencia empírica de T/u/v en un día no acredita transferencia entre lugares, alturas y regímenes. Hace falta justificar esa hipótesis y la aplicabilidad de la columna en el relieve, además de metadatos del sensor y reloj.',
 '- Comparabilidad con EIA: modelo diferente y equivalencia de inventario, representación de fuentes, horarios y período pendiente de acreditar. No atribuir diferencias únicamente a meteorología.',
 '- Comparación normativa: los gráficos son de aportes y de episodios; no sustituyen concentraciones totales, indicadores anuales ni la acreditación de la base volumétrica MP10.',
 '- Ampliar las ternas a 506 casos pendientes solo extendería temporalmente una hipótesis. Se mantiene condicionada a una justificación física y a que la pregunta de tesis necesite medias/máximos estacionales de esas ternas.',
 '', 'Con la evidencia actual se puede defender sensibilidad prescrita y máximos entre escenarios evaluados, con condiciones explícitas. No se declara un peor caso físico/legal ni incertidumbre probabilística calibrada.']
(OUT/'Lectura_de_resultados.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
dump('Verificacion.json',{'status':'NUMERICALLY_CHECKED_VISUAL_PENDING','created_utc':datetime.now(timezone.utc).isoformat(),
 'source_files':[{ 'path':str(p),'sha256':sha(p)} for p in paths],
 'hourly_pairs':len(h),'comparisons':len(d),'hours_each':24,'daily_values_including_unique_BASE':len(all_days),
 'receptor_season_pollutant_groups':len(summary),'new_model_runs':0,'figures':2,
 'scope':'Complete evaluated civil days only; no mixed hourly maximum or new seasonal/annual summary.'})
print(summary[['season','receptor','pollutant','BASE_max_episode','tuple_max_episode','winner_including_BASE']].to_string(index=False))
