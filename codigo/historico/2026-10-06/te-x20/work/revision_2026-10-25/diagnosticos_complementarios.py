from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
W=Path(__file__).resolve().parent;E=W/'evidencia'
r=pd.read_csv(E/'Residuos_ajuste.csv');r=r[r.valido_conjunto.eq(True)].set_index('fecha_local')
d=pd.read_csv(E/'Pares_ciclo_direccion.csv').set_index('fecha_local')
matched=r.loc[d.index]
for col,u,v in [('dir_obs','u_obs_m_s','v_obs_m_s'),('dir_WRF','u_earth_m_s','v_earth_m_s')]:
 # Reconstruction independent of the 270-arctan2(v,u) expression used by the figure.
 a=np.degrees(np.arctan2(-matched[u],-matched[v]))%360
 assert np.max(np.abs((a-d[col]+180)%360-180))<1e-10
obs_path=Path(r'/archivo/usuario\Documents\Codex\2026-10-08\hem\outputs\Datos_Auditados\Observaciones\observaciones_normalizadas.csv')
obs=pd.read_csv(obs_path).set_index('Fecha_original')
assert obs.index.is_unique
assert np.allclose(obs.loc[d.index,'Direccion_viento_grados'],d.dir_obs)
assert np.allclose(obs.loc[d.index,'Velocidad_viento_m_s'],d.WS_obs)
obs.loc[d.index,['Direccion_viento_grados','Velocidad_viento_m_s']].to_csv(E/'Observaciones_soporte_direccion.csv')
err=(d.dir_obs-d.dir_WRF+180)%360-180
assert np.allclose(abs(err),np.minimum(abs(d.dir_obs-d.dir_WRF),360-abs(d.dir_obs-d.dir_WRF)))
w=np.hypot(r.u_earth_m_s,r.v_earth_m_s);o=np.hypot(r.u_obs_m_s,r.v_obs_m_s);s=(o-w).std(ddof=1)
minus=np.maximum(w-s,0);assert np.allclose(minus-w,np.maximum(-w,-s))
pd.DataFrame({'rapidez_WRF':w,'rapidez_observada':o,'DE_residuo':s,'rapidez_hipotetica_menos_DE':minus,'incremento_efectivo':minus-w,'truncado_a_cero':w<s}).to_csv(W/'Diagnostico_limite_rapidez.csv')
pd.DataFrame({'dir_obs':d.dir_obs,'dir_WRF':d.dir_WRF,'error_angular_absoluto':abs(err)}).to_csv(W/'Diagnostico_direccion.csv')
sel=pd.read_csv(E/'Invierno_Seleccion_horaria.csv');ts=pd.DatetimeIndex(pd.to_datetime(sel.hora_cercana_UTC))
expected=pd.date_range('2017-06-20 04:00','2017-09-21 03:00',freq='h')
assert ts.is_unique and len(ts)==2231 and len(expected)==2232
assert expected.difference(ts).tolist()==[pd.Timestamp('2017-08-15 00:00')]
assert len(ts.difference(expected))==0
start=pd.Timestamp('2017-06-21',tz='America/Santiago');end=pd.Timestamp('2017-09-21',tz='America/Santiago')
assert (end-start).total_seconds()/3600==2207
assert (pd.Timestamp('2017-08-14',tz='America/Santiago')-pd.Timestamp('2017-08-13 01:00',tz='America/Santiago')).total_seconds()/3600==23
out={'n_ajuste':len(r),'sd_rapidez':float(s),'n_truncados':int((w<s).sum()),'porcentaje_truncados':float(100*(w<s).mean()),'decremento_medio_efectivo':float((minus-w).mean()),'ciclo_n':len(d),'mae_circular_grados':float(abs(err).mean()),'mediana_abs_circular_grados':float(np.median(abs(err))),'p90_abs_circular_grados':float(np.quantile(abs(err),.9)),'control_direccion':'Reconstruccion independiente desde u/v y cotejo con observacion normalizada original','hash_observaciones':hashlib.sha256(obs_path.read_bytes()).hexdigest(),'invierno_horas_civiles':2207,'invierno_instantes_con_auxiliar':2232,'invierno_instantes_seleccionados':2231,'invierno_faltante_UTC':'2017-08-15 00:00','invierno_archivos_seleccionados':int(sel.archivo.nunique()),'invierno_max_separacion_s':float(sel.separacion_hora_cercana_s.abs().max())}
(W/'diagnosticos.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
