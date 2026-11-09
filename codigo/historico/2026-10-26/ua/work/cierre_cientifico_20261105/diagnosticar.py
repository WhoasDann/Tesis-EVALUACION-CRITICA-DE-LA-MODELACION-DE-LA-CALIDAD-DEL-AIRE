"""Diagnostico adicional de resultados existentes. Sin ejecucion de modelos."""
from pathlib import Path
import sys, json, hashlib
from datetime import datetime, timezone
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/Cierre_cientifico_2026-11-05'; OUT.mkdir(exist_ok=True)
OLD=Path('/archivo/usuario/Documents/Codex/2026-10-08/hem/outputs')
P=ROOT/'outputs/Seleccion_adversa_2026-11-04/Contraste_ternas_observadas'
A=ROOT/'outputs/Sensibilidad_estacional_2026-10-29'
sys.path.insert(0,str(ROOT/'work/seleccion_adversa_20261104'))
from analizar import get_hourly,sfc
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str),encoding='utf-8')

new=pd.read_csv(P/'Horas_cuatro_receptores.csv');new.fin_LST=pd.to_datetime(new.fin_LST)
pair=pd.read_csv(P/'Comparacion_cuatro_receptores.csv')
assert len(new)==128*24 and len(pair)==128
rows=[];allhours=[];cache={};audit={};met={}
for season in ['VERANO','INVIERNO']: met[season]=sfc(season,'BASE')[0]
for key,g in new.groupby(['season','day','scenario','pollutant','receptor']):
    season,day,sc,pol,rec=key
    b=get_hourly(season,day,'BASE',pol,cache,audit)
    b=b.loc[b.x_m.eq(g.x_m.iloc[0])&b.y_m.eq(g.y_m.iloc[0]),['fin_LST','C_ug_m3']]
    assert len(g)==len(b)==24
    z=g.merge(b,on='fin_LST',suffixes=('','_BASE'),validate='one_to_one')
    z=z.merge(met[season][['fin_LST','WS','WD','L','T_K','zim']],on='fin_LST',suffixes=('','_BASE'),validate='one_to_one')
    z['delta']=z.C_ug_m3-z.C_ug_m3_BASE
    z['turn_abs_deg']=abs((z.WD-z.WD_BASE+180)%360-180)
    z['positive_delta']=z.delta.clip(lower=0)
    target=pair.loc[pair.season.eq(season)&pair.day.eq(day)&pair.scenario.eq(sc)&pair.pollutant.eq(pol)&pair.receptor.eq(rec)]
    assert len(target)==1
    assert np.isclose(z.C_ug_m3.mean(),target.iloc[0]['mean'],rtol=1e-11,atol=1e-12)
    assert np.isclose(z.C_ug_m3_BASE.mean(),target.iloc[0]['BASE'],rtol=1e-11,atol=1e-12)
    pos=z.positive_delta.sum();total=z.C_ug_m3.sum();base_total=z.C_ug_m3_BASE.sum()
    i=z.delta.idxmax();peak=z.loc[i]
    peak_c=z.loc[z.C_ug_m3.idxmax()]
    concentration_top1=100*peak_c.C_ug_m3/total if total>0 else None
    rows.append(dict(season=season,day=day,scenario=sc,pollutant=pol,receptor=rec,
        BASE_mean=z.C_ug_m3_BASE.mean(),candidate_mean=z.C_ug_m3.mean(),delta_mean=z.delta.mean(),
        delta_pct=100*z.delta.sum()/base_total if base_total>0 else None,
        hours_positive=int((z.delta>0).sum()),hours_negative=int((z.delta<0).sum()),
        peak_positive_delta_end_LST=peak.fin_LST if pos>0 else None,
        peak_positive_delta_start_civil=peak.inicio_civil if pos>0 else None,
        peak_positive_delta=peak.delta if pos>0 else None,
        top1_positive_share_pct=100*peak.positive_delta/pos if pos>0 else None,
        top3_positive_share_pct=100*z.positive_delta.nlargest(3).sum()/pos if pos>0 else None,
        candidate_top1_concentration_share_pct=concentration_top1,
        candidate_peak_end_LST=peak_c.fin_LST,
        WS_at_largest_increase=peak.WS if pos>0 else None,
        BASE_WS_at_largest_increase=peak.WS_BASE if pos>0 else None,
        turn_at_largest_increase_deg=peak.turn_abs_deg if pos>0 else None,
        L_at_largest_increase=peak.L if pos>0 else None,
        candidate_WS_below1_hours=int((z.WS<1).sum()),BASE_WS_below1_hours=int((z.WS_BASE<1).sum()),
        note='Descriptive diagnosis, not rejection criterion, probability, independent validation or source attribution'))
    allhours.append(z)
summary=pd.DataFrame(rows);summary.to_csv(OUT/'Diagnostico_horario_128_comparaciones.csv',index=False)
hourly=pd.concat(allhours,ignore_index=True);hourly.to_csv(OUT/'Horas_pareadas_con_meteorologia.csv',index=False)

# Inventario de observaciones ya guardadas: no confundir archivos de ajuste con toda la cobertura disponible.
obs_paths=[('VERANO',OLD/'Discrepancias_ajuste_2026-10-19/Residuos_ajuste.csv'),
 ('VERANO',OLD/'Evaluacion_febrero_2026-10-21/Evaluacion/Pares.csv'),
 ('INVIERNO',OLD/'BASE_invierno_2026-10-24/Estacion/pares_HCIVIL.csv')]
cover=[];obs_records=[]
for season,path in obs_paths:
    df=pd.read_csv(path)
    timecol='fecha_local' if 'fecha_local' in df.columns else 'Fecha_original'
    t=pd.to_datetime(df[timecol]);df['day_audit']=t.dt.strftime('%Y-%m-%d')
    cols=['u_obs_m_s','v_obs_m_s']
    tcol=next(c for c in ['Temperatura_aire_C','T_obs_C'] if c in df.columns)
    valid=np.isfinite(df[cols+[tcol]]).all(axis=1)
    if 'valido_conjunto' in df:valid &= df.valido_conjunto.eq(True)
    # Temperatura y viento presentes; no declara metadatos de sensor/reloj validados.
    cover.append(dict(season=season,path=str(path),start=str(t.min()),end=str(t.max()),rows=len(df),
                      valid_joint_values=int(valid.sum()),timestamp_column=timecol,sha256=sha(path)))
    for day,g in df[valid].groupby('day_audit'):
        obs_records.append(dict(season=season,day=day,valid_joint_rows=len(g),path=str(path)))
coverage=pd.DataFrame(obs_records)
coverage.to_csv(OUT/'Cobertura_observaciones_disponibles.csv',index=False)
dump('Inventario_observaciones.json',cover)

examples=pd.read_csv(ROOT/'outputs/Informe_presentacion_2026-11-05/Tablas/09_ejemplos_pareados_cuatro_receptores.csv')
selected=pd.read_csv(P/'Seleccion_episodios_con_respaldo_conjunto.csv')
fichas=[]
for _,e in examples.iterrows():
    q=summary.loc[summary.season.eq('VERANO')&summary.day.eq(e.day)&summary.scenario.eq(e.scenario)&summary.receptor.eq(e.receptor)&summary.pollutant.eq(e.pollutant)].iloc[0]
    candidates=coverage.loc[coverage.season.eq('VERANO')&coverage.day.eq(e.day)]
    sel=selected.loc[selected.season.eq('VERANO')&selected.receptor.eq(e.receptor)&selected.pollutant.eq(e.pollutant)].iloc[0]
    fichas.append(dict(season='VERANO',receptor=e.receptor,pollutant=e.pollutant,scenario=e.scenario,day=e.day,
        BASE_mean=q.BASE_mean,candidate_mean=q.candidate_mean,delta_pct=q.delta_pct,
        original_BASE_maximum=sel.BASE_max,exceeds_original_BASE_max=bool(q.candidate_mean>sel.BASE_max),
        numeric_integrity='VERIFIED',joint_daily_amplitude='EMPIRICAL_VECTOR_VERIFIED',
        compatible_regime='PENDING',station_to_column_and_vertical_transfer='PENDING',
        model_applicability='PENDING',emission_timing='PENDING',
        observed_rows_same_day=int(candidates.valid_joint_rows.max()) if len(candidates) else 0,
        observed_coverage_scope='Only the three inventoried saved files, not proof that observations do not exist elsewhere.',
        peak_positive_delta_start_civil=q.peak_positive_delta_start_civil,
        top1_positive_share_pct=q.top1_positive_share_pct,
        top3_positive_share_pct=q.top3_positive_share_pct,
        WS_at_largest_increase=q.WS_at_largest_increase,turn_at_largest_increase_deg=q.turn_at_largest_increase_deg,
        admission='CONDITIONAL_SENSITIVITY; physical admission unresolved'))
fichas=pd.DataFrame(fichas);fichas.to_csv(OUT/'Fichas_cuatro_receptores.csv',index=False)

# Recuento condicional, sin crear colas: completar exactamente las tres ternas actuales.
completed={(x['season'],x['day'],x['scenario'],x['pollutant']) for x in read(P/'Casos.json')['cases']}
targets=[]
for season,start,end,scenarios in [('VERANO','2016-12-21','2017-03-20',['OBS_U','OBS_V']),('INVIERNO','2017-06-21','2017-09-20',['OBS_U'])]:
    for day in pd.date_range(start,end).strftime('%Y-%m-%d'):
        for sc in scenarios:
            for pol in ['MP10','MP25']:
                key=(season,day,sc,pol)
                targets.append(dict(season=season,day_LST=day,scenario=sc,pollutant=pol,already_calculated=key in completed))
target=pd.DataFrame(targets)
assert len(target)==544 and target.already_calculated.sum()==38
target.to_csv(OUT/'Cobertura_condicional_ternas_NO_ES_COLA.csv',index=False)
missing=target[~target.already_calculated].groupby('season').size().to_dict()
assert missing=={'INVIERNO':166,'VERANO':340}
dump('Ampliacion_solo_si_se_justifica.json',{'status':'NOT_DISPATCHED','purpose':'Conditional full-season coverage of unchanged empirical tuples on same 40-receptor panel',
      'total_cases':544,'existing':38,'remaining':506,'remaining_by_season':missing,
      'condition':'Resolve physical admission and need for seasonal tuple indicators before dispatch. Counts do not establish physical validity.',
      'new_WRF_required_for_count':False,'existing_seasonal_9_scenarios_repeated':False,'queues_created':0})

lines=['# Cierre científico: diagnóstico retomado el 5 de noviembre de 2026','',
 'Las 3276 corridas estacionales y las 38 de ternas están terminadas y reproducidas. Eso completa el experimento numérico definido; no equivale a haber identificado el peor caso físico o legal del proyecto. No se asigna un porcentaje artificial al cierre científico.',
 '', '## Trabajo nuevo realizado en esta continuación','',
 'Se reconstruyeron 128 comparaciones horarias de ternas frente a BASE (3072 pares de valores), se cotejaron sus medias y se añadieron las condiciones SFC de la hora que más aumenta. Se prepararon ocho fichas de los cuatro receptores, una por contaminante, y se inventarió la cobertura observacional guardada. No se lanzó ninguna simulación.',
 '', '## Hallazgos para orientar la revisión física','']
for q in fichas[fichas.pollutant.eq('MP10')].itertuples():
    lines.append(f'- **{q.receptor}, {q.day}, {q.scenario}:** BASE {q.BASE_mean:.3f}, alternativa {q.candidate_mean:.3f} µg/m³ ({q.delta_pct:+.2f}%). La hora con mayor incremento concentra {q.top1_positive_share_pct:.1f}% de la suma de incrementos positivos; las tres mayores, {q.top3_positive_share_pct:.1f}%. Rapidez SFC en esa hora: {q.WS_at_largest_increase:.2f} m/s; giro frente a BASE: {q.turn_at_largest_increase_deg:.1f}°. Observaciones conjuntas de ese día en los archivos inventariados: {q.observed_rows_same_day}.')
lines += ['', 'Los porcentajes de concentración horaria de los incrementos positivos son descriptivos: no son porcentajes del cambio neto ni pruebas de causalidad. Si existen horas con disminución, estas también se conservan en las tablas. La meteorología SFC es compartida por el dominio; no constituye viento observado en cada receptor.',
 '', '## Qué falta para cerrar los resultados','',
 '1. **Admisión física de candidatos en los cuatro receptores.** Comprobar circulación, alturas y tiempos compatibles entre estación, columna MMIF y zona de fuentes/receptores; revisar perfiles y las horas que sostienen los aumentos. Clasificar evidencia favorable, contraria o indeterminada, sin exigir mejora del MAE del mismo día ni fijar filtros para favorecer concentraciones altas.',
 '2. **Equivalencia con el caso del EIA.** Cotejar inventario, geometría, horarios, períodos, receptores y cota. La BASE propia es AERMOD y el anexo usa CALPUFF. Aumentar respecto de nuestra BASE no prueba subestimación del titular. No están disponibles las referencias PM equivalentes de Los Bronces MP2,5 y La Paloma en las tablas ya cotejadas.',
 '3. **Cierre de unidades y comparación ambiental.** Rastrear el volumen de salida MP10, sustentar una eventual conversión, separar aporte y fondo, y utilizar el indicador y período correspondiente. La etiqueta µg/m³ de AERMOD no acredita por sí sola µg/m³N. No convertir usando una temperatura/presión arbitraria de estación ni producir un P98 anual de una submuestra.',
 '4. **Alcance temporal de las ternas.** Las nueve configuraciones ya cubren las ventanas estacionales; las ternas cubren solo 5/6 días civiles. Para afirmar su máximo o media estacional falta completar el período de las alternativas admitidas. Para un contraejemplo acotado frente a BASE puede bastar un episodio defendible. No es obligatorio ejecutar todas las combinaciones ni volver a crear 1024 trayectorias.',
 '5. **Síntesis final.** Integrar las decisiones por receptor, medias, máximos diarios, diferencias pareadas, método reproducible y límites. Verificar cifras, gráficos y conclusiones contra los objetivos; conservar datos y versión final para el profesor.',
 '', '## Ampliación calculada, todavía no iniciada','',
 'Si después de la admisión se desea completar las tres ternas sin cambiarlas: 544 casos en total, 38 existentes y **506 adicionales (340 de verano y 166 de invierno)**. Incluye el conteo por fecha LST y los auxiliares de invierno ya calculados. Mantiene 40 receptores y dos contaminantes; no proporciona un máximo anual ni de toda la malla. Es un recuento condicional, no una cola ni un compromiso de ejecutar casos que puedan quedar sin respaldo.',
 '', '## Disponibilidad actual','',
 f'WRF de verano en D:/Tesis_Dan/wrfoutVer accesible: {Path("D:/Tesis_Dan/wrfoutVer").exists()}. WRF de invierno en D:/Tesis_Dan/wrfoutInv accesible: {Path("D:/Tesis_Dan/wrfoutInv").exists()}. Se solicitó a Daniel reconectar o indicar ruta. Las series y perfiles locales permiten continuar diagnósticos; no sustituyen la extracción espacial pendiente.',
 '', 'La cobertura observacional inventariada es parcial. Que un día falte en esos archivos no prueba que no exista en la fuente original. Sensor, reloj y representatividad mantienen sus pendientes documentados. Ninguna ficha se declara físicamente validada.',
 '', '## Fuentes de referencia','',
 '- Resultados y reproducción: outputs/Normativa_reproduccion_2026-11-04, Seleccion_adversa_2026-11-04 y Graficos_BASE_EIA_2026-11-05.',
 '- [MMA, ficha vigente MP10](https://normasaire.mma.gob.cl/nambientales/normas-de-calidad-del-aire/norma-primaria-de-calidad-del-aire-para-material-particulado-respirable-mp10/).',
 '- [EPA, AERMOD User Guide, julio 2026](https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/aermod_userguide.pdf).',
 '- Revisión metodológica independiente del 5 de noviembre en el proyecto auditor-a-t-cnica-y-reorganizaci.',
 '', 'Las fuentes oficiales se consultaron en esta continuación; el criterio legal y la normalización no se infieren de los porcentajes de sensibilidad.']
(OUT/'Que_falta_y_avance.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
dump('Verificacion.json',{'status':'PASSED_FOR_ADDITIONAL_DIAGNOSTICS','checked_utc':datetime.now(timezone.utc).isoformat(),
     'groups_checked':len(summary),'paired_hourly_rows':len(hourly),'fichas':len(fichas),
     'base_receipt_products_rehashed':len(audit),'new_model_runs':0,'physical_admission':'PENDING',
     'source_hashes':{'tuple_hours':sha(P/'Horas_cuatro_receptores.csv'),'tuple_daily_pairs':sha(P/'Comparacion_cuatro_receptores.csv')},
     'base_audit':audit})
dump('Estado.json',{'status':'ANALYSIS_RESUMED','authorization':'Daniel requested continuation of complete analysis on 2026-11-05.',
     'current_result':'Four receptor admission files and all 128 hourly diagnostics prepared.',
     'numerical_campaign':'3314 cases previously completed and reproduced; not rerun.',
     'pending_dependency':'WRF D drive not currently accessible; requested location/reconnection.',
     'queues_started':0,'conditional_expansion_cases':506,'physical_admission':'PENDING'})
print(summary[summary.pollutant.eq('MP10')&summary.day.eq('2017-01-16')&summary.receptor.eq('Los Bronces')][['scenario','candidate_mean','delta_pct','top1_positive_share_pct','top3_positive_share_pct']].to_string(index=False))
print(fichas[fichas.pollutant.eq('MP10')][['receptor','observed_rows_same_day','top1_positive_share_pct','top3_positive_share_pct']].to_string(index=False))
print(json.dumps({'groups':len(summary),'paired_hours':len(hourly),'additional_conditional_cases':missing}))
