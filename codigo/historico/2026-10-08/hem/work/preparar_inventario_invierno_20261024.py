from pathlib import Path
import pandas as pd,numpy as np,json,sys,hashlib
sys.path.insert(0,str(Path.cwd()/'outputs/Biblioteca_Tesis'))
from tesis.geometria_line import repartir_masas
from tesis.comun import sha256
O=Path('outputs/BASE_invierno_2026-10-24');O.mkdir(exist_ok=True)
G=Path('outputs/Configuracion_fuentes_v1/eje/fuentes_central.csv')
s=pd.read_csv(G)
result={}
for pol in ['MP10','MP25']:
 p=Path('/archivo/usuario/Codigos_VSC/Codigos_oficiales/AERMOD_TODOS_LOS_CAMINOS')/('emisiones_diarias_'+pol+'.csv')
 d=pd.read_csv(p);col='emision_'+pol.lower()+'_g_dia';h=sha256(p)
 expected=json.loads(Path('outputs/Actualizacion_2026-10-09/Emisiones_'+pol+'_MismoDia/manifest.json').read_text(encoding='utf-8'))['sha256_entrada']
 assert h==expected,'Inventario cambio desde auditoria verano'
 selected=d.loc[(d.fecha>='2017-06-21')&(d.fecha<'2017-09-21')].copy()
 assert not selected.duplicated(['fecha','id_fuente_aermod']).any()
 assert selected.groupby('fecha').size().eq(873).all()
 assert selected.fecha.nunique()==92
 assert np.isfinite(selected[col]).all() and selected[col].ge(0).all()
 mass=repartir_masas(selected,s)
 output=O/('emisiones_segmentadas_'+pol+'.csv')
 assert not output.exists()
 mass.to_csv(output,index=False,encoding='utf-8-sig',float_format='%.15g')
 check=pd.read_csv(output)
 before=selected.groupby(['fecha','id_fuente_aermod'])[col].sum().sort_index()
 after=check.groupby(['fecha','id_fuente_padre'])[col].sum().sort_index()
 np.testing.assert_allclose(before.to_numpy(),after.to_numpy(),rtol=1e-12,atol=1e-8)
 totals=selected.groupby('fecha')[col].sum()
 result[pol]={'original':str(p),'sha256':h,'segmentado':str(output.resolve()),'sha256_segmentado':sha256(output),'dias':92,'fuentes_padre':873,'fuentes_100m':1651,'filas':len(mass),'masa_92_dias_g':float(totals.sum()),'masa_13agosto_g':float(totals.loc['2017-08-13']),'max_error_arco_dia_g':float(np.max(np.abs(before.to_numpy()-after.to_numpy()))),'variacion_total_diaria':{'min':float(totals.min()),'max':float(totals.max())}}
obs_path=Path('outputs/Datos_Auditados/Observaciones/observaciones_normalizadas.csv')
o=pd.read_csv(obs_path);t=pd.to_datetime(o.Fecha_original)
o=o.loc[(t>='2017-06-21')&(t<'2017-09-21')].copy();t=pd.DatetimeIndex(pd.to_datetime(o.Fecha_original))
u=t.tz_localize('America/Santiago',ambiguous='raise',nonexistent='raise').tz_convert('UTC')
expected=pd.date_range(pd.Timestamp('2017-06-21 00:49',tz='America/Santiago').tz_convert('UTC'),pd.Timestamp('2017-09-21 00:49',tz='America/Santiago').tz_convert('UTC'),inclusive='left',freq='h')
result['observaciones']={'path':str(obs_path.resolve()),'sha256':sha256(obs_path),'registros':len(o),'esperados':len(expected),'faltan':len(expected.difference(u)),'horas_repetidas':int(u.duplicated().sum()),'validos':o[['Temperatura_aire_C','Velocidad_viento_m_s','Direccion_viento_grados']].count().to_dict(),'por_mes':o.groupby(t.strftime('%Y-%m')).size().to_dict(),'salto_agosto':o.loc[(t>='2017-08-12 22:00')&(t<'2017-08-13 03:00'),'Fecha_original'].tolist(),'hipotesis':'H-CIVIL conserva :49, sin filtros de velocidad; no certifica huso ni ventana instrumental'}
(O/'Emisiones_y_observaciones.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=int),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2,default=int))
