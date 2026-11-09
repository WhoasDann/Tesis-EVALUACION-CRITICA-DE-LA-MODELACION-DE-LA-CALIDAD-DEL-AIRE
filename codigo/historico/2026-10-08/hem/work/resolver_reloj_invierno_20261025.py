"""Seleccion horaria reproducible a partir de XTIME. No edita WRF."""
from pathlib import Path
import json,hashlib
import pandas as pd,numpy as np
from netCDF4 import Dataset
from preparar_base_verano_20261021 import KEEP
ties_checked=[]
O=Path('outputs/BASE_invierno_2026-10-24')
a=json.loads((O/'Auditoria.json').read_text());inv=json.loads((O/'Inventario_WRF.json').read_text())
assert not a['problemas']
f=pd.read_csv(O/'Diagnostico_XTIME.csv')
f['hora']=pd.to_datetime(f.hora_cercana_UTC)
f['inicio_run']=pd.to_datetime(f.START_DATE.str.replace('_',' '))
target=pd.date_range('2017-06-20 04:00','2017-09-21 03:00',freq='h')
near=f.loc[f.hora.isin(target)&f.separacion_hora_cercana_s.le(10)&f.inicio_run.le(f.hora)].copy()
# Priorizar la continuacion mas reciente desde restart; dentro de ella, estado mas cercano.
near=near.sort_values(['hora','inicio_run','separacion_hora_cercana_s','XTIME_min'],ascending=[True,False,True,True])
chosen=near.drop_duplicates('hora').sort_values('hora')
for hour,part in near.groupby('hora'):
 top=part.iloc[0]
 ties=part.loc[part.inicio_run.eq(top.inicio_run)&part.separacion_hora_cercana_s.eq(top.separacion_hora_cercana_s)&part.XTIME_min.eq(top.XTIME_min)]
 if len(ties)>1:
  base=ties.iloc[0]
  for other in ties.iloc[1:].itertuples():
   with Dataset(Path('D:/Tesis_Dan/wrfoutInv')/base.archivo) as na,Dataset(Path('D:/Tesis_Dan/wrfoutInv')/other.archivo) as nb:
    na.set_auto_mask(False);nb.set_auto_mask(False)
    for key in KEEP:
     if key not in na.variables or key=='Times':continue
     va=np.asarray(na[key][int(base.indice)]);vb=np.asarray(nb[key][int(other.indice)])
     assert np.array_equal(va,vb,equal_nan=va.dtype.kind=='f'),('Empate no equivalente',hour,key)
   ties_checked.append({'hora':str(hour),'archivo_a':base.archivo,'indice_a':int(base.indice),'archivo_b':other.archivo,'indice_b':int(other.indice),'equivalencia':'Todos los campos exportables excepto etiqueta Times iguales; XTIME igual'})
missing=target.difference(pd.DatetimeIndex(chosen.hora))
assert missing.equals(pd.DatetimeIndex(['2017-08-15 00:00'])) and len(chosen)==2231
selected=[]
for r in inv:
 c=chosen.loc[chosen.archivo.eq(r['archivo'])].sort_values('hora')
 if c.empty:continue
 x=dict(r);x['indices_seleccionados']=c.indice.astype(int).tolist();x['times_exportados']=[t.strftime('%Y-%m-%d_%H:%M:%S') for t in c.hora]
 x['traza_reloj']=c.drop(columns=['hora','inicio_run']).to_dict('records')
 x['bytes_NetCDF3_datos_estimados']=int(r['bytes_NetCDF3_datos_estimados']*len(c)/len(r['indices_objetivo_auxiliar']))
 selected.append(x)
selected.sort(key=lambda r:r['times_exportados'][0])
flat=[pd.Timestamp(t.replace('_',' ')) for r in selected for t in r['times_exportados']]
assert pd.DatetimeIndex(flat).equals(target.difference(missing))
chosen.drop(columns=['hora','inicio_run']).to_csv(O/'Seleccion_horaria.csv',index=False,encoding='utf-8-sig')
result={'empates_verificados':ties_checked,'estado':'SELECCION_XTIME_CON_UN_HUECO','criterio':'Estado a <=10s de hora UTC; prioridad al START_DATE mas reciente, luego menor distancia; a igual distancia antes/despues, instante anterior. Empates de XTIME solo admitidos tras igualdad de campos y XTIME. Times se corrige solo en copia MMIF; campos y XTIME intactos. No se interpola WRF.','limite_segundos':10,'max_desviacion_seleccionada_s':float(chosen.separacion_hora_cercana_s.max()),'instantes':len(chosen),'archivos':selected,'bytes_estimados':sum(r['bytes_NetCDF3_datos_estimados'] for r in selected),'hora_WRF_ausente_UTC':list(map(str,missing)),'horas_exclusion_conservadora_AERMET_UTC':['2017-08-15 00:00:00','2017-08-15 01:00:00'],'razon_exclusion_segunda':'La diferencia de precipitacion acumulada al01 abarca dos horas por ausencia del00; conservar para reiniciar acumulador MMIF y excluir esa hora del ONSITE entregado a AERMET. Verificar nativamente antes de produccion.','confirmacion_usuario':'25oct: no conserva restart ni salida original del15ago00UTC. No completar ese estado.','registros_Times_corregidos':int(sum(r.Times!=r.hora.strftime('%Y-%m-%d %H:%M:%S') for r in chosen.itertuples())),'sha256_diagnostico':hashlib.sha256((O/'Diagnostico_XTIME.csv').read_bytes()).hexdigest(),'sha256_script':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(O/'Seleccion_WRF.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print({k:v for k,v in result.items() if k not in ['archivos','criterio','razon_exclusion_segunda']})


