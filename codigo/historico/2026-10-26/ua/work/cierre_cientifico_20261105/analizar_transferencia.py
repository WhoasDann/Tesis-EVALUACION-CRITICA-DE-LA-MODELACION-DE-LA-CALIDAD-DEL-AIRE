"""Compare compatible WRF locations and original observations; no model dispatch."""
from pathlib import Path
import sys,json,hashlib,re
from datetime import datetime,timezone
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
ROOT=Path(__file__).resolve().parents[2]
OLD=Path('/archivo/usuario/Documents/Codex/2026-10-08/hem')
OUT=ROOT/'outputs/Cierre_cientifico_2026-11-05/Transferencia_WRF'
P=ROOT/'outputs/Seleccion_adversa_2026-11-04/Contraste_ternas_observadas'
sys.path.insert(0,str(ROOT/'work/seleccion_adversa_20261104'))
from analizar import sfc,pfl
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def csv(n,d):d.to_csv(OUT/n,index=False)
def fmt(x,n=2):return f'{x:.{n}f}'.replace('.',',')
ex=read(OUT/'Recepcion_extraccion.json');assert ex['status']=='EXTRACTED_CHECKED'
for f in ex['files']:assert sha(OUT/f['name'])==f['sha256']
w=pd.read_csv(OUT/'WRF_superficie_seis_puntos.csv',parse_dates=['time_UTC'])
pr=pd.read_csv(OUT/'WRF_perfiles_seis_puntos.csv',parse_dates=['time_UTC'])
pts=pd.read_csv(OUT/'Ubicacion_puntos.csv')
design=read(P/'Diseno.json');prot=read(OUT/'Protocolo.json')
obs_path=OLD/'outputs/Datos_Auditados/Observaciones/observaciones_normalizadas.csv'
obs=pd.read_csv(obs_path);obs['date']=pd.to_datetime(obs.Fecha_original);obs['day']=obs.date.dt.strftime('%Y-%m-%d')
obs['u_obs']=-obs.Velocidad_viento_m_s*np.sin(np.deg2rad(obs.Direccion_viento_grados))
obs['v_obs']=-obs.Velocidad_viento_m_s*np.cos(np.deg2rad(obs.Direccion_viento_grados))
obs['valid']=np.isfinite(obs[['Temperatura_aire_C','u_obs','v_obs']]).all(axis=1)&obs.Velocidad_viento_m_s.ge(0)&obs.Direccion_viento_grados.between(0,360)
met={};bridge=[];spatial=[];spatial_hours=[];pairs=[];coverage=[]
for season in ['VERANO','INVIERNO']:
    off=3 if season=='VERANO' else 4
    m=sfc(season,'BASE')[0];m['time_UTC']=m.fin_LST+pd.Timedelta(hours=off);met[(season,'BASE')]=m
    col=w[w.season.eq(season)&w.point.eq('Columna_MMIF')]
    b=col.merge(m[['time_UTC','WS','WD','T_K','valid']],on='time_UTC',validate='one_to_one')
    b['SFC_u']=-b.WS*np.sin(np.deg2rad(b.WD));b['SFC_v']=-b.WS*np.cos(np.deg2rad(b.WD))
    b['err_vector']=np.hypot(b.SFC_u-b.u10,b.SFC_v-b.v10);b['err_T']=abs(b.T_K-(b.T2_C+273.15))
    # Only adjustments explicitly recorded by the original AERMET run are admitted.
    base_folder=ROOT/'outputs/Sensibilidad_estacional_2026-10-29/Meteorologia'/season/'BASE'
    log=base_folder/'met.ER1';onsite=base_folder/'ONSITE.DAT'
    oslines=onsite.read_text().splitlines()
    osindex={line[:10]:i for i,line in enumerate(oslines) if re.match(r'^\d{10}',line)}
    adjustments=[]
    b['documented_minimum_speed_m_s']=np.nan
    for lineno,line in enumerate(log.read_text().splitlines(),1):
        found=re.search(r'RESET WIND TO ([\d.]+) M/S FOR DATE: (\d{8}) HR\s+(\d+)',line)
        if not found:continue
        speed,date,hour=found.groups()
        stamp=pd.to_datetime(date,format='%Y%m%d')+pd.Timedelta(hours=int(hour)+off)
        idx=b.index[b.time_UTC.eq(stamp)]
        if len(idx)==0:continue
        assert len(idx)==1
        key=date+f'{int(hour):02d}';i=osindex[key];level=oslines[i+2]
        height,original_ws,original_wd=map(float,[level[10:20],level[20:30],level[30:40]])
        row=b.loc[idx[0]]
        assert height==10 and abs(original_ws-row.WS10)<.0006
        assert abs((original_wd-row.WD10+180)%360-180)<.0006
        assert original_ws<float(speed) and abs(row.WS-float(speed))<.006
        b.loc[idx,'documented_minimum_speed_m_s']=float(speed)
        adjustments.append(dict(time_UTC=stamp,ONSITE_original_speed_m_s=original_ws,
            WRF_original_speed_m_s=row.WS10,AERMET_documented_speed_m_s=float(speed),
            SFC_rounded_speed_m_s=row.WS,log_line_number=lineno,log_line=line.strip(),
            onsite_line_number=i+3,onsite_line=level))
    expected_speed=b.documented_minimum_speed_m_s.fillna(b.WS10)
    expected_u=-expected_speed*np.sin(np.deg2rad(b.WD10))
    expected_v=-expected_speed*np.cos(np.deg2rad(b.WD10))
    b['err_vector_after_documented_processing']=np.hypot(b.SFC_u-expected_u,b.SFC_v-expected_v)
    b['explained_by_log_or_rounding']=(b.err_vector_after_documented_processing<.04)&(b.err_T<.061)
    assert b.explained_by_log_or_rounding.all(),b.loc[~b.explained_by_log_or_rounding]
    bridge.append(dict(season=season,matched=len(b),max_wind_vector_rounding_error_m_s=b.err_vector.max(),max_temperature_difference_K=b.err_T.max(),
                       endpoint_UTC='fin_LST plus fixed offset 3 summer, 4 winter',
                       direct_match_within_rounding=bool(b.err_vector.max()<.04 and b.err_T.max()<.061),
                       documented_low_wind_adjustments=adjustments,
                       max_difference_after_documented_processing_m_s=b.err_vector_after_documented_processing.max(),
                       unexplained_differences=int((~b.explained_by_log_or_rounding).sum()),
                       source_log=str(log),source_log_sha256=sha(log),
                       source_onsite_sha256=sha(onsite),source_control_sha256=sha(base_folder/'met.IN1')))
    csv(f'Puente_WRF_SFC_{season}.csv',b)
    for sc in [p['scenario'] for p in design['prototypes'] if p['season']==season]:
        m=sfc(season,sc,P/'Meteorologia'/season/sc)[0];m['time_UTC']=m.fin_LST+pd.Timedelta(hours=off);met[(season,sc)]=m
    for day in prot['days'][season]:
        start=pd.Timestamp(day,tz='America/Santiago').tz_convert('UTC').tz_localize(None)
        end=(pd.Timestamp(day)+pd.Timedelta(days=1)).tz_localize('America/Santiago').tz_convert('UTC').tz_localize(None)
        g=w[w.season.eq(season)&w.time_UTC.gt(start)&w.time_UTC.le(end)]
        c=g[g.point.eq('Columna_MMIF')]
        assert len(c)==24
        for point in g.point.unique():
            q=g[g.point.eq(point)].merge(c[['time_UTC','u10','v10','WS10','WD10','T2_C']],on='time_UTC',suffixes=('','_column'),validate='one_to_one')
            q['day']=day;q['vector_difference']=np.hypot(q.u10-q.u10_column,q.v10-q.v10_column)
            q['direction_difference']=abs((q.WD10-q.WD10_column+180)%360-180)
            directional=q.WS10.ge(1)&q.WS10_column.ge(1)
            spatial.append(dict(season=season,day=day,point=point,hours=len(q),
                wind_vector_RMS_difference_m_s=float(np.sqrt((q.vector_difference**2).mean())),
                wind_vector_mean_difference_m_s=q.vector_difference.mean(),
                mean_speed_difference_m_s=(q.WS10-q.WS10_column).mean(),
                mean_T2_difference_C=(q.T2_C-q.T2_C_column).mean(),
                direction_valid_hours=int(directional.sum()),
                mean_abs_direction_difference_deg=q.loc[directional,'direction_difference'].mean(),
                note='WRF spatial contrast at equal times and nominal heights; not observed model error or automatic rejection.'))
            spatial_hours.append(q)
        o=obs[obs.day.eq(day)].copy()
        coverage.append(dict(season=season,day=day,raw_rows=len(o),valid_joint_rows=int(o.valid.sum()),source=str(obs_path)))
        for r in o[o.valid].itertuples():
            t=pd.Timestamp(r.date).tz_localize('America/Santiago').tz_convert('UTC').tz_localize(None)
            t0=t.floor('h');t1=t0+pd.Timedelta(hours=1);f=(t-t0).total_seconds()/3600.
            vals={}
            for name in ['Estacion_PC','Columna_MMIF']:
                q=w[w.season.eq(season)&w.point.eq(name)].set_index('time_UTC')
                assert t0 in q.index and t1 in q.index
                for field in ['T2_C','u10','v10']:
                    vals[f'{name}_{field}']=(1-f)*q.loc[t0,field]+f*q.loc[t1,field]
            pairs.append(dict(season=season,day=day,observed_local=str(r.date),time_UTC=t,
                 observed_T_C=r.Temperatura_aire_C,observed_WS=r.Velocidad_viento_m_s,observed_WD=r.Direccion_viento_grados,
                 observed_u=r.u_obs,observed_v=r.v_obs,**vals,
                 comparison='Station :49 under H-CIVIL. Sensor height/time metadata provisional. MMIF point has no colocated observation.'))
sp=pd.DataFrame(spatial);csv('Contrastes_espaciales_diarios.csv',sp)
csv('Contrastes_espaciales_horarios.csv',pd.concat(spatial_hours,ignore_index=True))
paired=pd.DataFrame(pairs)
for axis,obsvar,wrfvar in [('T','observed_T_C','T2_C'),('u','observed_u','u10'),('v','observed_v','v10')]:
    paired[f'delta_{axis}_station']=paired[obsvar]-paired[f'Estacion_PC_{wrfvar}']
    paired[f'delta_{axis}_MMIF_diagnostic']=paired[obsvar]-paired[f'Columna_MMIF_{wrfvar}']
csv('Observaciones_y_WRF_al_instante_original.csv',paired)
cov=pd.DataFrame(coverage);csv('Cobertura_observaciones_originales.csv',cov)
res=paired.groupby(['season','day']).agg(n=('observed_T_C','size'),delta_T=('delta_T_station','mean'),delta_u=('delta_u_station','mean'),delta_v=('delta_v_station','mean')).reset_index()
csv('Discrepancias_diarias_estacion_recalculadas.csv',res)
checks=[]
for p in design['prototypes']:
    r=res[res.season.eq(p['season'])&res.day.eq(p['source_day'])].iloc[0]
    error=np.max(abs(np.array([r.delta_T,r.delta_u,r.delta_v])-p['delta']))
    checks.append(dict(season=p['season'],scenario=p['scenario'],source_day=p['source_day'],n=int(r.n),max_abs_difference=error))
dump('Comprobacion_ternas_desde_WRF_original.json',checks)
assert max(c['max_abs_difference'] for c in checks)<1e-6,checks

# Verification against an independent previously extracted winter station series.
old=pd.read_csv(OLD/'outputs/BASE_invierno_2026-10-24/Estacion/wrf_estacion.csv',parse_dates=['fecha_wrf_utc'])
cmp=w[w.season.eq('INVIERNO')&w.point.eq('Estacion_PC')].merge(old,on=None,left_on='time_UTC',right_on='fecha_wrf_utc',suffixes=('','_prior'),validate='one_to_one')
max_prior=max(abs(cmp.T2_C-cmp.T2_C_prior).max(),abs(cmp.u10-cmp.u_earth_m_s).max(),abs(cmp.v10-cmp.v_earth_m_s).max())
assert len(cmp)>0 and max_prior<1e-6

fichas=pd.read_csv(OUT.parent/'Fichas_cuatro_receptores.csv')
updated=[]
for r in fichas.itertuples():
    t=pd.Timestamp(r.peak_positive_delta_start_civil).tz_convert('UTC').tz_localize(None)+pd.Timedelta(hours=1)
    target=w[w.season.eq(r.season)&w.time_UTC.eq(t)].set_index('point')
    c=target.loc['Columna_MMIF'];q=target.loc[r.receptor];st=target.loc['Estacion_PC']
    v=sp[(sp.season==r.season)&(sp.day==r.day)&(sp.point==r.receptor)].iloc[0]
    vv=sp[(sp.season==r.season)&(sp.day==r.day)&(sp.point=='Estacion_PC')].iloc[0]
    nr=paired[(paired.season==r.season)&(paired.day==r.day)].shape[0]
    row=r._asdict();row.pop('Index',None)
    row.update(observed_rows_same_day=nr,observed_coverage_scope='Original normalized station dataset, same day, H-CIVIL hypothesis.',
        spatial_diagnostic='COMPLETED_AT_EQUAL_WRF_HEIGHTS_AND_TIMES; not validation of uniform transfer',
        station_to_column_and_vertical_transfer='SPATIAL_HETEROGENEITY_QUANTIFIED; PHYSICAL_ADMISSION_PENDING',
        receptor_column_vector_RMS_m_s=v.wind_vector_RMS_difference_m_s,
        station_column_vector_RMS_m_s=vv.wind_vector_RMS_difference_m_s,
        critical_WRF_MMIF_WS=c.WS10,critical_WRF_station_WS=st.WS10,critical_WRF_receptor_WS=q.WS10,
        critical_WRF_receptor_direction=q.WD10,
        critical_vector_difference_receptor_column=np.hypot(q.u10-c.u10,q.v10-c.v10),
        admission='NUMERICAL_SENSITIVITY_RETAINED; NOT_YET_PHYSICALLY_ADMITTED')
    updated.append(row)
u=pd.DataFrame(updated);csv('Fichas_actualizadas_transferencia.csv',u)

# Legible scientific figures, without replacing the original reports.
FIG=OUT/'Figuras';FIG.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
colors={'Columna_MMIF':'#263b4b','Estacion_PC':'#889299','receptor':'#2c7fb8','candidate':'#d86b28','observed':'#832f78'}
fig,axes=plt.subplots(2,2,figsize=(15,9));fig.subplots_adjust(top=.86,bottom=.16,hspace=.42,wspace=.18)
for ax,r in zip(axes.flat,u[u.pollutant.eq('MP10')].itertuples()):
    start=pd.Timestamp(r.day,tz='America/Santiago').tz_convert('UTC').tz_localize(None)
    end=start+pd.Timedelta(hours=24)
    for point,col,ls,label in [('Columna_MMIF',colors['Columna_MMIF'],'-','WRF: columna MMIF'),('Estacion_PC',colors['Estacion_PC'],'--','WRF: estación'),(r.receptor,colors['receptor'],'-','WRF: receptor')]:
        q=w[w.season.eq(r.season)&w.point.eq(point)&w.time_UTC.between(start,end)]
        ax.plot((q.time_UTC-start).dt.total_seconds()/3600,q.WS10,c=col,ls=ls,lw=1.5,label=label)
    m=met[(r.season,r.scenario)];q=m[m.time_UTC.gt(start)&m.time_UTC.le(end)]
    ax.plot((q.time_UTC-start).dt.total_seconds()/3600,q.WS,c=colors['candidate'],lw=1.8,label='SFC: terna en columna MMIF')
    q=paired[paired.season.eq(r.season)&paired.day.eq(r.day)]
    ax.scatter((q.time_UTC-start).dt.total_seconds()/3600,q.observed_WS,s=19,facecolors='none',edgecolors=colors['observed'],label='Observación en estación (:49)',zorder=4)
    t=pd.Timestamp(r.peak_positive_delta_start_civil).hour+1
    ax.axvline(t,color=colors['candidate'],ls=':',alpha=.6)
    ax.set_title(f'{r.receptor} · {r.day} · {r.scenario}',loc='left',fontweight='bold')
    ax.set_xlim(0,24);ax.set_xticks(range(0,25,4));ax.set_ylabel('Rapidez (m/s)');ax.set_xlabel('Hora local (0–24)');ax.grid(alpha=.18)
fig.suptitle('¿Es representativa la meteorología trasladada a cada receptor?',x=.05,ha='left',fontsize=18,fontweight='bold')
fig.text(.05,.91,'WRF a 10 m en tres ubicaciones; SFC a 10 m. Observación: altura de sensor pendiente de acreditar.',fontsize=11)
handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,.035),ncol=3,frameon=False)
fig.text(.05,.013,'Línea vertical: fin de la hora con mayor incremento. Las curvas de lugares distintos no son mediciones equivalentes.',fontsize=10)
for ext in ['png','svg']:fig.savefig(FIG/f'Viento_cuatro_receptores.{ext}',dpi=180)
plt.close(fig)

fig,axes=plt.subplots(1,2,figsize=(14,6));fig.subplots_adjust(top=.8,bottom=.22,wspace=.25)
for ax,(season,targets) in zip(axes,[('VERANO',design['civil_days']['VERANO']),('INVIERNO',design['civil_days']['INVIERNO'])]):
    for point in ['Estacion_PC','Los Bronces','Piedra Carvajal','Sulfatos','La Paloma']:
        q=sp[(sp.season==season)&(sp.point==point)&sp.day.isin(targets)].sort_values('day')
        ax.plot(pd.to_datetime(q.day).dt.strftime('%d/%m'),q.wind_vector_RMS_difference_m_s,'o-',ms=5,label=point.replace('Estacion_PC','Estación'))
    ax.set_title(season.title(),loc='left',fontweight='bold');ax.set_ylabel('Diferencia vectorial RMS frente a columna (m/s)');ax.set_ylim(bottom=0);ax.grid(alpha=.2)
fig.suptitle('Heterogeneidad del viento WRF entre lugares',x=.06,ha='left',fontsize=18,fontweight='bold')
fig.text(.06,.87,'Mismas 24 horas y altura de 10 m. Es contraste espacial del modelo, no error frente a observaciones.',fontsize=11)
fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.5,.06),ncol=5,frameon=False)
fig.text(.06,.025,'La cercanía de estación y Piedra Carvajal puede superponer sus curvas. Ninguna línea define un umbral de admisión.',fontsize=10)
for ext in ['png','svg']:fig.savefig(FIG/f'Heterogeneidad_espacial.{ext}',dpi=180)
plt.close(fig)

fig,axes=plt.subplots(1,4,figsize=(15,6));fig.subplots_adjust(top=.78,bottom=.2,wspace=.3)
for ax,r in zip(axes,u[u.pollutant.eq('MP10')].itertuples()):
    t=pd.Timestamp(r.peak_positive_delta_start_civil).tz_convert('UTC').tz_localize(None)+pd.Timedelta(hours=1)
    for point,col,label in [('Columna_MMIF',colors['Columna_MMIF'],'WRF: columna MMIF'),('Estacion_PC',colors['Estacion_PC'],'WRF: estación'),(r.receptor,colors['receptor'],'WRF: receptor')]:
        q=pr[(pr.season==r.season)&pr.time_UTC.eq(t)&pr.point.eq(point)]
        ax.plot(np.hypot(q.u,q.v),q.z_AGL_m,'o-',color=col,label=label)
    folder=P/'Meteorologia'/r.season/r.scenario
    pp=pfl(folder);off=3 if r.season=='VERANO' else 4
    q=pp[(pp.fin_LST==t-pd.Timedelta(hours=off))&pp.z.between(50,1000)]
    ax.plot(q.WS,q.z,'o-',color=colors['candidate'],ms=3,label='PFL: terna MMIF')
    ax.set_title(r.receptor+'\n'+r.day,fontsize=12,loc='left');ax.set_xlabel('Rapidez (m/s)');ax.grid(alpha=.18);ax.set_ylim(0,1050);ax.set_xlim(left=0)
axes[0].set_ylabel('Altura sobre terreno (m)')
fig.suptitle('Perfiles en la hora de mayor incremento por receptor',x=.06,ha='left',fontsize=18,fontweight='bold')
fig.text(.06,.87,'WRF: interpolación a alturas comunes. PFL: perfiles procesados por MMIF/AERMET; operadores verticales distintos.',fontsize=11)
fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.5,.05),ncol=4,frameon=False)
for ext in ['png','svg']:fig.savefig(FIG/f'Perfiles_horas_criticas.{ext}',dpi=180)
plt.close(fig)

point=pts[pts.season=='VERANO'].set_index('point');station=point.loc['Estacion_PC'];column=point.loc['Columna_MMIF']
dist=np.hypot(station.x_utm-column.x_utm,station.y_utm-column.y_utm)/1000
height=station.HGT_m-column.HGT_m
lines=['# Contraste espacial y vertical WRF: avance verificado','',
 'El disco D se reconectó y se completó la extracción de WRF original en la estación, columna MMIF y cuatro receptores. Se mantienen los resultados de las simulaciones; esta etapa no modifica WRF, MMIF, AERMET ni AERMOD.',
 '',f'Cobertura: {len(w)} filas de superficie y {len(pr)} filas de perfiles, en 14 días (episodios y días fuente de las ternas), {ex["source_files"]} archivos WRF y seis ubicaciones. Se usó la selección XTIME auditada de invierno; se registran diferencias de segundos y hashes de los campos extraídos.',
 '', '## Qué se resolvió','',
 '- Las observaciones del 26 de enero y 20 de febrero sí están en la tabla normalizada original. Quedan incorporadas a la revisión de La Paloma y Piedra Carvajal. La ausencia anterior era de los archivos parciales inventariados.',
 f'- Las tres ternas se reprodujeron desde los WRF originales y las observaciones, con diferencia máxima {max(x["max_abs_difference"] for x in checks):.3g}. La extracción nueva en la estación de invierno coincide con la anterior, con error máximo {max_prior:.3g}.',
 f'- La estación y la columna MMIF están separadas aproximadamente {fmt(dist)} km. El terreno WRF interpolado en la estación difiere {fmt(height,0)} m del terreno de la columna. Esto es elevación del modelo, no cota medida del sensor.',
 '- Se compararon lugares a la misma hora y alturas nominales de 2 m (T) y 10 m (viento). Las observaciones :49 se comparan con WRF interpolado al instante, conservando la hipótesis H-CIVIL y sus metadatos pendientes.',
 '', '## Qué muestran los episodios de los cuatro receptores','']
for r in u[u.pollutant.eq('MP10')].itertuples():
    lines.append(f'- **{r.receptor}, {r.day}:** diferencia vectorial RMS diaria receptor–columna = {fmt(r.receptor_column_vector_RMS_m_s)} m/s; estación–columna = {fmt(r.station_column_vector_RMS_m_s)} m/s. En el fin de la hora que más aumenta el aporte, rapidez WRF de columna = {fmt(r.critical_WRF_MMIF_WS)}, estación = {fmt(r.critical_WRF_station_WS)} y receptor = {fmt(r.critical_WRF_receptor_WS)} m/s; la terna SFC usada tenía {fmt(r.WS_at_largest_increase)} m/s.')
lines += ['', 'Las diferencias espaciales no son errores observados ni pruebas automáticas de imposibilidad de la terna. Muestran que trasladar una discrepancia de estación a una columna y usarla en todo el dominio es una hipótesis sustantiva. El estado WRF en otro punto tampoco es una observación independiente.',
 '', '## Admisión física: decisión actual','',
 '**Se conservan las ternas como sensibilidad prescrita y candidatos condicionados. No se declara cerrada su admisión física ni identificado un peor caso legal.** El soporte empírico de la amplitud y la integridad se verifican, pero no aseguran coherencia dinámica ni transferencia a todos los lugares y episodios.',
 '', 'La comparación espacial/vertical ya está calculada. Falta interpretar sus regímenes y documentar una hipótesis de aplicación compatible con esa heterogeneidad, contrastar metadatos del sensor/reloj y horarios de emisiones, y revisar aplicabilidad de la columna única en este relieve. No usar mejorar MAE como regla necesaria o suficiente. No introducir umbrales después de ver qué casos elevan la concentración.',
 '', 'La ampliación de 506 casos permanece sin iniciar: completaría fechas de las mismas hipótesis, pero no resolvería por sí sola estas brechas. Tampoco se modifica la comparación EIA ni se normaliza MP10 arbitrariamente.',
 '', '## Puente WRF–SFC','']
for b in bridge:
    lines.append(f'- {b["season"]}: {b["matched"]} tiempos comunes; diferencia vectorial bruta máxima = {b["max_wind_vector_rounding_error_m_s"]:.6f} m/s; diferencia T máxima = {b["max_temperature_difference_K"]:.6f} K. Se explican {len(b["documented_low_wind_adjustments"])} ajustes de viento mínimo mediante el log nativo. Tras esos ajustes documentados, diferencia vectorial máxima = {b["max_difference_after_documented_processing_m_s"]:.6f} m/s y diferencias sin explicar = {b["unexplained_differences"]}.')
    for a in b['documented_low_wind_adjustments']:
        lines.append(f'  - {a["time_UTC"]} UTC: WRF = {a["WRF_original_speed_m_s"]:.6f} m/s; ONSITE = {a["ONSITE_original_speed_m_s"]:.3f}; AERMET registra mínimo {a["AERMET_documented_speed_m_s"]:.3f}; SFC guarda {a["SFC_rounded_speed_m_s"]:.2f} m/s.')
lines += ['', 'El mínimo de AERMET para estimar parámetros de capa límite es independiente de THRESHOLD. Las dos excepciones de invierno están acreditadas por los registros originales met.ER1 y ONSITE.DAT; no se atribuyen a un desfase horario ni se fuerza un ajuste general a posteriori. Se tolera el redondeo de los archivos de texto (0,04 m/s vectorial y 0,061 K, controles numéricos, no criterios físicos). [Guía oficial AERMET, sección 3.5.12](https://gaftp.epa.gov/Air/aqmg/SCRAM/models/met/aermet/aermet_userguide.pdf).']
lines += ['', 'Los perfiles WRF se desescalonan y rotan a coordenadas terrestres; se interpolan primero a alturas AGL comunes en cada nodo y después horizontalmente. Los PFL provienen de promedios/procesamiento MMIF-AERMET y no se fuerza igualdad con la interpolación WRF puntual. Se reconstruyen geopotencial y temperatura según las variables nativas; los campos originales permanecen intactos. [Documentación WRF](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/output.html).',
 '', 'Archivos: Fichas_actualizadas_transferencia.csv, Contrastes_espaciales_diarios.csv, Observaciones_y_WRF_al_instante_original.csv, WRF_superficie_seis_puntos.csv, WRF_perfiles_seis_puntos.csv, Trazabilidad_WRF.json y Figuras. Las gráficas son diagnósticas; no muestran probabilidades ni intervalos de incertidumbre calibrada.']
(OUT/'Resultados_transferencia.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
dump('Verificacion_analisis.json',{'status':'NUMERICAL_DIAGNOSTICS_PASSED_VISUAL_PENDING','created_utc':datetime.now(timezone.utc).isoformat(),
    'all_source_product_hashes_verified':True,'source_ternas_reproduced':checks,'independent_winter_station_max_error':max_prior,
    'independent_winter_station_rows':len(cmp),'source_observations_sha256':sha(obs_path),'observed_pairs':len(paired),
    'bridge':bridge,'station_MMIF_distance_km':dist,'station_minus_MMIF_WRF_terrain_m':height,
    'new_model_runs':0,'physical_admission':'NOT_ESTABLISHED','figure_count':3})
print(json.dumps({'observed_pairs':len(paired),'distance_km':dist,'height_difference_m':height,'bridge':bridge,'prototype_checks':checks},default=str),flush=True)
