"""Recepcion invernal: faltantes explicitos y dias civiles sobre reloj LST UTC-4."""
from pathlib import Path
import json,re,sys
import numpy as np,pandas as pd
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'outputs/Biblioteca_Tesis'))
from tesis.receptores import leer_aermap
from tesis.comun import sha256
COLS=['x_m','y_m','C_bruta_ug_m3','elev_m','hill_m','flag','average','group','fecha_AERMOD']
STATES={'VALIDA','CALMA','AUSENCIA_WRF','EXCLUSION_PRECIPITACION_2H'}

def check(ok,msg):
 if not ok:raise ValueError(msg)
def postfile(path):return pd.read_csv(path,sep=r'\s+',comment='*',names=COLS,usecols=range(9),dtype={'fecha_AERMOD':str})

def calendar(mask):
 d=mask.copy();check(len(d)>0 and set(d.estado)<=STATES,'Mascara vacia o estado no revisado')
 end=pd.to_datetime(d.fin_LST);start=end-pd.Timedelta(hours=1)
 check(end.is_unique and end.is_monotonic_increasing,'Horas duplicadas/desordenadas')
 check(pd.DatetimeIndex(pd.to_datetime(d.inicio_LST)).equals(pd.DatetimeIndex(start)),'Inicio y fin LST incorrectos')
 utc=pd.DatetimeIndex(end).tz_localize('UTC')+pd.Timedelta(hours=4)
 check(utc.equals(pd.DatetimeIndex(pd.to_datetime(d.fin_UTC,utc=True))),'LST y UTC no coinciden')
 civil_start=(utc-pd.Timedelta(hours=1)).tz_convert('America/Santiago')
 check((civil_start.strftime('%Y-%m-%d')==d.dia_civil.to_numpy()).all(),'Dias civiles incorrectos')
 check(pd.DatetimeIndex(pd.to_datetime(d.inicio_civil,utc=True)).equals(civil_start.tz_convert('UTC')),'Inicio civil incorrecto')
 check((start.dt.strftime('%Y-%m-%d')==d.dia_LST).all(),'Dia LST incorrecto')
 check(np.array_equal(d.apta_dispersion.to_numpy(),d.estado.eq('VALIDA').to_numpy()),'Mascara de validez inconsistente')
 d['fecha_AERMOD']=start.dt.strftime('%y%m%d')+end.dt.hour.replace(0,24).map('{:02d}'.format)
 return d

def summarize(data,members,hours_expected,hours_present,complete):
 check(not members.duplicated(['grupo','x_m','y_m']).any(),'Membresia duplicada')
 points=data.groupby(['x_m','y_m']).C_ug_m3.agg(['sum','mean','max','count']).reset_index()
 points.columns=['x_m','y_m','suma_horaria_ug_m3','media_horas_validas_ug_m3','maximo_1h_ug_m3','horas_validas']
 check(points.horas_validas.nunique()==1,'Cobertura desigual por receptor')
 points['horas_calendario_esperadas']=hours_expected;points['horas_calendario_recibidas']=hours_present
 points['calendario_completo']=bool(complete);points['cobertura_porcentaje']=100*points.horas_validas/hours_expected
 # A civil day may have 23 hours. This is a mean of valid hours, not a regulatory 24-hour claim.
 points['media_dia_civil_disponible_ug_m3']=points.media_horas_validas_ug_m3 if complete else np.nan
 joined=members.merge(points,on=['x_m','y_m'],how='left',validate='many_to_one')
 check(joined.horas_validas.notna().all(),'Receptor de membresia ausente')
 zones=[]
 for name,g in joined.groupby('grupo',sort=True):
  row=g.sort_values(['media_horas_validas_ug_m3','x_m','y_m'],ascending=[False,True,True]).iloc[0]
  zones.append(dict(grupo=name,n_receptores=len(g),horas_validas=int(row.horas_validas),horas_calendario_esperadas=hours_expected,horas_calendario_recibidas=hours_present,calendario_completo=bool(complete),maximo_media_horas_validas_ug_m3=float(row.media_horas_validas_ug_m3),maximo_media_dia_civil_ug_m3=float(row.media_dia_civil_disponible_ug_m3),maximo_1h_ug_m3=float(g.maximo_1h_ug_m3.max()),x_maximo_media_m=float(row.x_m),y_maximo_media_m=float(row.y_m)))
 return points,joined,pd.DataFrame(zones)

def civil_summaries(data,members,full_calendar):
 full=calendar(full_calendar)
 check(not data.duplicated(['x_m','y_m','fecha_AERMOD']).any(),'Receptor/hora repetido al combinar lotes LST')
 all_points=[];all_members=[];all_zones=[]
 for day,g in data.groupby('dia_civil',sort=True):
  expected=set(full.loc[full.dia_civil.eq(day),'fecha_AERMOD']);got=set(g.fecha_AERMOD)
  check(expected and got<=expected,'Horas fuera del dia civil esperado')
  check(g.groupby(['x_m','y_m']).size().eq(len(got)).all(),'Cobertura civil desigual')
  pt,mp,z=summarize(g,members,len(expected),len(got),got==expected)
  for f in [pt,mp,z]:f.insert(0,'dia_civil',day)
  all_points.append(pt);all_members.append(mp);all_zones.append(z)
 return tuple(pd.concat(parts,ignore_index=True) for parts in [all_points,all_members,all_zones])

def receive(folder,mask,members,full_calendar,sources=12263,receptors=6295):
 folder=Path(folder);mask=calendar(mask);full=calendar(full_calendar)
 check(mask.dia_LST.nunique()==1,'Se recibe una corrida LST a la vez')
 ref=full.set_index('fecha_AERMOD');actual=mask.set_index('fecha_AERMOD')
 check(set(actual.index)<=set(ref.index),'Mascara fuera de temporada')
 for col in ['estado','dia_civil','fin_LST']:
  check(actual[col].equals(ref.loc[actual.index,col]),'Mascara cambiada frente al calendario recibido')
 text=(folder/'aermod.out').read_text(encoding='ascii');summary=(folder/'resumen.sum').read_text(encoding='ascii')
 fatal=re.findall(r'A Total of\s+(\d+)\s+Fatal Error',text)
 check('AERMOD Finishes Successfully' in text and fatal and not any(map(int,fatal)),'AERMOD no completo')
 sizes=re.search(r'This Run Includes:\s+(\d+) Source\(s\);\s+\d+ Source Group\(s\); and\s+(\d+) Receptor\(s\)',text)
 check(sizes and tuple(map(int,sizes.groups()))==(sources,receptors),'Dimensiones distintas')
 check(re.search(r'Output Units\s*=\s*MICROGRAMS/M\*\*3',text),'Unidades distintas')
 counts={}
 for name in ['Hours Were Processed','Calm Hours Identified','Missing Hours Identified']:
  m=re.search(r'A Total of\s+(\d+)\s+'+name,summary);check(m is not None,'Falta recuento nativo');counts[name]=int(m[1])
 expected=[len(mask),int(mask.estado.eq('CALMA').sum()),int(mask.estado.isin(['AUSENCIA_WRF','EXCLUSION_PRECIPITACION_2H']).sum())]
 check(list(counts.values())==expected,'Recuentos nativos y mascara no coinciden')
 data=postfile(folder/'receptor_horas.out')
 check(data.average.eq('1-HR').all() and data.group.eq('ALL').all(),'Promedio/grupo inesperado')
 check(np.isfinite(data[COLS[:6]]).all().all() and data.C_bruta_ug_m3.ge(0).all() and data.flag.eq(0).all(),'POSTFILE invalido')
 check(len(data)==receptors*len(mask) and set(data.fecha_AERMOD)==set(mask.fecha_AERMOD),'POSTFILE incompleto')
 check(not data.duplicated(['x_m','y_m','fecha_AERMOD']).any(),'Receptor/hora duplicado')
 pts=pd.DataFrame(leer_aermap(folder/'receptores.inc'))
 j=data.merge(pts,on=['x_m','y_m'],validate='many_to_one',suffixes=('','_esperado'),how='left')
 check(len(pts)==receptors and j.elev_m_esperado.notna().all(),'Coordenadas inesperadas')
 check(np.allclose(j[['elev_m','hill_m']],j[['elev_m_esperado','hill_m_esperado']],rtol=0,atol=.011),'Cotas inesperadas')
 check(data.groupby(['x_m','y_m']).size().eq(len(mask)).all(),'Cobertura desigual')
 data=data.merge(mask[['fecha_AERMOD','fin_LST','fin_UTC','inicio_civil','dia_LST','dia_civil','estado']],on='fecha_AERMOD',validate='many_to_one')
 valid=data.estado.eq('VALIDA');check(data.loc[~valid,'C_bruta_ug_m3'].eq(0).all(),'Faltante/calmas no escrito como cero interno')
 data['C_ug_m3']=data.C_bruta_ug_m3.where(valid)
 points=data.groupby(['x_m','y_m']).C_ug_m3.agg(['sum','mean','max','count']).reset_index()
 max1=float(points['max'].max())
 m=re.search(r'SUMMARY OF HIGHEST\s+1-HR RESULTS.*?ALL\s+HIGH\s+1ST HIGH VALUE IS\s+([\d.]+)',summary,re.S)
 check(m and np.isclose(float(m[1]),max1,rtol=0,atol=1.1e-5),'Maximo horario no coincide')
 error24=None
 if len(mask)==24:
  check(set(pd.to_datetime(mask.fin_LST).dt.hour)==set(range(24)),'Ventana LST no es un dia completo')
  native=postfile(folder/'receptor_24h.out');tag=mask.fecha_AERMOD.iloc[0][:6]+'24'
  check(len(native)==receptors and native.average.eq('24-HR').all() and native.group.eq('ALL').all() and native.fecha_AERMOD.eq(tag).all(),'POSTFILE24 incompleto')
  j=points.merge(native,on=['x_m','y_m'],validate='one_to_one');check(len(j)==receptors,'Receptores24 distintos')
  error24=float(abs(j['sum']/np.maximum(j['count'],18)-j.C_bruta_ug_m3).max());check(error24<=1.1e-5,'Denominador nativo24 inesperado')
 civil=civil_summaries(data,members,full)
 qa=dict(horas_calendario_LST=len(mask),horas_validas=int(valid.sum()/receptors),valores_enmascarados=int((~valid).sum()),recuentos_nativos=counts,error_max_POSTFILE24=error24,maximo_1h_ug_m3=max1,fuentes=sources,receptores=receptors)
 return qa,data,*civil

def tests():
 o=R/'outputs/BASE_invierno_2026-10-24';q=o/'Revision_QC_2026-10-25';full=pd.read_csv(q/'Cobertura_horaria.csv');cal=calendar(full)
 native=q/'Prueba_faltantes_AERMOD';record=json.loads((native/'Verificacion.json').read_text())
 for f in record['archivos']:check(sha256(f['path'])==f['sha256'],'Prueba nativa modificada')
 selected=full.loc[full.dia_LST.eq('2017-08-14')&pd.to_datetime(full.fin_LST).dt.hour.between(19,22)]
 members=pd.DataFrame([dict(grupo='GENERAL',x_m=380148.,y_m=6331485.)])
 qa,data,pt,mp,z=receive(native,selected,members,full,1,1)
 check(qa['valores_enmascarados']==2 and data.C_ug_m3.isna().sum()==2 and pt.horas_validas.iloc[0]==2,'Mascara nativa incorrecta')
 check(data.loc[data.estado.eq('VALIDA'),'C_ug_m3'].eq(0).all(),'Se perdieron ceros fisicos validos')
 rejected={}
 def bad(name,fun):
  try:fun()
  except ValueError:rejected[name]=True
  else:raise ValueError('Prueba no rechazada: '+name)
 wrong=selected.copy();wrong['estado']='VALIDA';wrong['apta_dispersion']=True
 bad('faltantes_como_ceros_validos',lambda:receive(native,wrong,members,full,1,1))
 wrong=full.copy();wrong.loc[wrong.dia_civil.eq('2017-08-13'),'dia_civil']='2017-08-12'
 bad('desfase_de_dia_civil',lambda:calendar(wrong))
 toy=cal.copy();toy['x_m']=380148.;toy['y_m']=6331485.;toy['C_ug_m3']=np.where(toy.estado.eq('VALIDA'),2.,np.nan)
 pts,_,_=civil_summaries(toy,members,full)
 check(len(pts)==92 and pts.calendario_completo.all(),'Calendario civil no completo')
 dst=pts.loc[pts.dia_civil.eq('2017-08-13')].iloc[0];check(dst.horas_calendario_esperadas==23 and dst.horas_validas==23 and dst.media_dia_civil_disponible_ug_m3==2,'Dia DST no conserva23h')
 gap=pts.loc[pts.dia_civil.eq('2017-08-14')].iloc[0];check(gap.horas_calendario_esperadas==24 and gap.horas_validas==22 and gap.media_dia_civil_disponible_ug_m3==2,'Dia con huecos no conserva22h')
 frag=toy.loc[toy.dia_LST.eq('2017-09-20')];partial,_,_=civil_summaries(frag,members,full)
 check(len(partial)==1 and not partial.calendario_completo.iloc[0] and partial.horas_calendario_recibidas.iloc[0]==23 and pd.isna(partial.media_dia_civil_disponible_ug_m3.iloc[0]),'FragmentoLST confundido con dia civil completo')
 joined=toy.loc[toy.dia_LST.isin(['2017-09-19','2017-09-20'])];combined,_,_=civil_summaries(joined,members,full);last=combined.loc[combined.dia_civil.eq('2017-09-20')].iloc[0]
 check(last.calendario_completo and last.horas_validas==24 and last.media_dia_civil_disponible_ug_m3==2,'Ultimo dia civil no recuperado desde dos archivosLST')
 bad('duplicado_entre_lotes',lambda:civil_summaries(pd.concat([joined,joined.iloc[:1]]),members,full))
 alternating=pd.DataFrame(dict(x_m=[0,0,1,1],y_m=[0]*4,C_ug_m3=[10,0,0,10]))
 two=pd.DataFrame(dict(grupo=['MINA','MINA'],x_m=[0,1],y_m=[0,0]));_,_,zones=summarize(alternating,two,2,2,True)
 check(zones.maximo_media_dia_civil_ug_m3.iloc[0]==5 and zones.maximo_1h_ug_m3.iloc[0]==10,'Se maximizo antes de promediar')
 return dict(estado='LECTOR_INVIERNO_VERIFICADO',prueba_nativa=qa,ceros_validos_conservados=True,dia_DST_23h=True,dia_con_huecos_22h=True,ultimo_dia_civil_recompuesto_24h=True,fragmentos_no_publicados_como_dias_completos=True,promedio_por_receptor_antes_de_maximo=True,rechazos=rejected,datos_de_calendario_sinteticos_no_son_concentraciones=True)

if __name__=='__main__':print(json.dumps(tests(),ensure_ascii=False,indent=2))
