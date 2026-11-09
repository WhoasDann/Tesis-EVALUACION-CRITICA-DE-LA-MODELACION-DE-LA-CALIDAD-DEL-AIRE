"""Invierno: preparación y exportación recibida; WRF y verano inmutables."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,json,os,shutil,traceback,threading,time
import numpy as np
import pandas as pd
from netCDF4 import Dataset,chartostring
from preparar_base_verano_20261021 import KEEP,OPTIONAL,LAYERS,sha256,XY
ROOT=Path(__file__).resolve().parents[1]
META=ROOT/'outputs/BASE_invierno_2026-10-24'
DATA=Path('D:/Tesis_Dan/BASE_invierno_2026-10-24')
SUMMER=ROOT/'outputs/BASE_verano_2026-10-21'
LST=timezone(timedelta(hours=-4))
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,x):
 p=Path(p);tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str),encoding='utf-8');os.replace(tmp,p)
def rec(p):return {'path':str(Path(p).resolve()),'sha256':sha256(p)}
def verify(r):
 if sha256(r['path'])!=r['sha256']:raise ValueError('Archivo cambiado: '+r['path'])
def prepare():
 a=read(META/'Auditoria.json')
 selection=read(META/'Seleccion_WRF.json')
 assert selection['estado']=='SELECCION_XTIME_CON_UN_HUECO' and not a['problemas']
 selected=selection['archivos']
 assert not DATA.exists(),'Directorio de entrega ya existe; no sobrescribir'
 assert shutil.disk_usage(DATA.parent).free>selection['bytes_estimados']+20*1024**3
 # Copiar exactamente la configuración ya recibida, sin ejecutar AERMAP otra vez.
 known={str(Path(x['path']).resolve()):x for x in read(SUMMER/'Entrega.json')['archivos']}
 paths=[p for folder in ['Comunes','Binarios'] for p in (SUMMER/folder).iterdir() if p.is_file()]
 for p in paths:
  assert str(p.resolve()) in known,p
  verify(known[str(p.resolve())])
 DATA.mkdir()
 for sub in ['WRF_BASE','Comunes','Binarios','Meteorologia','Emisiones','Recibos_exportacion']:(DATA/sub).mkdir()
 copied=[]
 for p in paths:
  d=DATA/p.parent.name/p.name;shutil.copy2(p,d);r=rec(d);assert r['sha256']==known[str(p.resolve())]['sha256'];copied.append(r)
 calendar=read(META/'Calendario_horario.json')
 cal=pd.DataFrame(calendar)
 local=pd.to_datetime(cal.inicio_LST).dt.tz_localize(None)
 daily=local.groupby(local.dt.normalize()).size()
 assert len(daily)==92 and (daily==24).sum()==91 and daily.iloc[-1]==23
 (META/'Calendario_LST.json').write_text(json.dumps([{'fecha_local':str(k),'horas':int(v)} for k,v in daily.items()],indent=2),encoding='utf-8')
 plan={'inicio':'2017-06-21 00:00:00','fin_exclusivo':'2017-09-20 23:00:00','inicio_auxiliar':'2017-06-20 00:00:00','horas':2207,'horas_MMIF':2231,'instantes_WRF':2231,'instantes_calendario':2232,'faltante_WRF_UTC':['2017-08-15 00:00:00'],'exclusion_ONSITE_UTC':['2017-08-15 01:00:00'],'TIMEZONE':-4,'inicio_UTC':a['inicio_UTC'],'fin_UTC':a['fin_exclusivo_UTC'],'carpeta_datos':str(DATA),'fuentes':12263,'receptores':6295,'metodo_mezcla':'WRF','modelo_discrepancias_aplicado':False,'fuentes_WRF':selected,'calendar_sha256':sha256(META/'Calendario_horario.json'),'regla_emisiones':'Masa diaria civil controlada dividida entre segundos reales del dia (23h el13ago;24h otros); mapeada a LST -4. Misma geometria y factores de verano.','entradas':[rec(META/n) for n in ['Auditoria.json','Inventario_WRF.json','Emisiones_y_observaciones.json','Calendario_horario.json','Seleccion_WRF.json']]}
 save(META/'Plan.json',plan)
 control='\n'.join(['START 2017 06 20 01','STOP 2017 09 20 23','TIMEZONE -4',*[f'INPUT "{DATA / "WRF_BASE" / r["archivo"]}"' for r in selected],'POINT LL -33.15632248 -70.29452515','LAYERS MID '+' '.join(map(str,LAYERS)),'AER_MIN_SPEED 0','AER_USE_NEW T','AER_MIXHT WRF','FSL_INTERVAL 12','OUTPUT AERMET BAT met.bat','OUTPUT AERMET ONSITE onsite.dat','OUTPUT AERMET FSL upper.dat','OUTPUT AERMET AERSFC surface.dat','OUTPUT AERMET USEFUL met.useful.txt',''])
 (DATA/'Meteorologia/mmif.inp').write_text(control,encoding='ascii')
 save(META/'Preparacion.json',{'estado':'PREPARADO','archivos':[rec(META/'Plan.json'),rec(__file__),rec(DATA/'Meteorologia/mmif.inp'),*copied]})
 print('Preparado invierno: '+str(len(selected))+' archivos seleccionados; 2207 horas objetivo.',flush=True)
def export():
 prep=read(META/'Preparacion.json')
 for r in prep['archivos']:verify(r)
 plan=read(META/'Plan.json');entries=[];lock=META/'exportacion.lock'
 with lock.open('x') as f:f.write(str(os.getpid()))
 activity={'pid':os.getpid(),'estado':'EXPORTANDO','recibidos':0,'archivo':None,'fase':'inicio'}
 stop=threading.Event()
 def heartbeat():
  while not stop.is_set():
   save(META/'Actividad_exportacion.json',dict(activity,actualizado=datetime.now().isoformat()))
   stop.wait(20)
 thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
 try:
  for row in plan['fuentes_WRF']:
   src=Path(row['path']);dst=DATA/'WRF_BASE'/row['archivo'];receipt=DATA/'Recibos_exportacion'/(row['archivo']+'.json')
   activity.update(archivo=row['archivo'],fase='comprobar')
   if receipt.exists():
    old=read(receipt);verify(old['original']);verify(old['exportado']);entries.append(old);activity['recibidos']=len(entries);continue
   if dst.exists():raise FileExistsError('Copia sin recepcion; conservar/revisar antes de repetir: '+str(dst))
   st=src.stat();assert (st.st_size,st.st_mtime_ns)==(row['bytes'],row['mtime_ns']),'WRF cambiado desde auditoria'
   activity['fase']='hash_original';original=rec(src)
   ix=row['indices_seleccionados'];assert ix==sorted(set(ix))
   assert shutil.disk_usage(DATA).free>row['bytes_NetCDF3_datos_estimados']+20*1024**3
   print('Exportando '+row['archivo'],flush=True);activity['fase']='copiar'
   with Dataset(src) as n:
    n.set_auto_mask(False)
    missing=set(KEEP)-set(n.variables);assert not missing-OPTIONAL
    with Dataset(dst,'w',format='NETCDF3_64BIT_OFFSET') as d:
     d.setncatts({a:n.getncattr(a) for a in n.ncattrs()})
     for key,dim in n.dimensions.items():d.createDimension(key,None if key=='Time' else len(dim))
     for key in KEEP:
      if key not in n.variables:continue
      v=n[key];w=d.createVariable(key,v.dtype,v.dimensions,fill_value=getattr(v,'_FillValue',False))
      w.setncatts({a:v.getncattr(a) for a in v.ncattrs() if a!='_FillValue'})
      w[:]=(np.asarray(row['times_exportados'],dtype='S19').view('S1').reshape(len(ix),19) if key=='Times' else (v[ix] if 'Time' in v.dimensions else v[:]))
    activity['fase']='verificar_campos'
    with Dataset(dst) as d:
     d.set_auto_mask(False)
     assert set(d.variables)==set(KEEP)-missing
     for key,v in d.variables.items():
      expected=(np.asarray(row['times_exportados'],dtype='S19').view('S1').reshape(len(ix),19) if key=='Times' else (n[key][ix] if 'Time' in v.dimensions else n[key][:]))
      actual=v[:];assert np.array_equal(expected,actual,equal_nan=v.dtype.kind=='f'),key
      if v.dtype.kind=='f':assert np.isfinite(actual).all(),key
     q=np.asarray(d['Q2'][:]);qv=np.asarray(d['QVAPOR'][:]);p=np.asarray(d['P'][:])+np.asarray(d['PB'][:])
     qa={'Q2_min_3x3':float(q[:,42:45,41:44].min()),'QVAPOR_min_3x3':float(qv[:,:,42:45,41:44].min()),'Q2_negativas_dominio':int((q<0).sum()),'QVAPOR_negativas_dominio':int((qv<0).sum()),'presion_min_Pa':float(p.min()),'T2_min_punto_K':float(d['T2'][:,43,42].min()),'T2_max_punto_K':float(d['T2'][:,43,42].max()),'PBLH_min_punto_m':float(d['PBLH'][:,43,42].min())}
     assert qa['Q2_min_3x3']>=0 and qa['QVAPOR_min_3x3']>=0 and qa['presion_min_Pa']>0,qa
     assert 150<qa['T2_min_punto_K']<=qa['T2_max_punto_K']<350 and qa['PBLH_min_punto_m']>0,qa
     times=[str(t) for t in chartostring(d['Times'][:])]
     assert times==row['times_exportados']
     raw_xt=pd.Timestamp('2017-06-01')+pd.to_timedelta(np.asarray(d['XTIME'][:],float),unit='min')
     assert np.max(np.abs((raw_xt-pd.to_datetime([t.replace('_',' ') for t in times])).total_seconds()))<=10
   st2=src.stat();assert (st2.st_size,st2.st_mtime_ns)==(st.st_size,st.st_mtime_ns),'Original cambio durante lectura'
   activity['fase']='hash_exportado'
   item={'original':original,'exportado':rec(dst),'bytes':dst.stat().st_size,'indices':ix,'Times':times,'QA':qa,'traza_reloj':row['traza_reloj'],'cambio_unico':'Times nominal basado en XTIME; campos fisicos y XTIME identicos al original'}
   save(receipt,item);entries.append(item);activity['recibidos']=len(entries)
  actual=pd.DatetimeIndex([pd.Timestamp(t.replace('_',' '),tz='UTC') for e in entries for t in e['Times']])
  expected=pd.date_range(pd.Timestamp(plan['inicio_auxiliar'])+pd.Timedelta(hours=4),pd.Timestamp(plan['fin_exclusivo'])+pd.Timedelta(hours=4),freq='h',tz='UTC')
  expected=expected.difference(pd.DatetimeIndex(['2017-08-15 00:00:00'],tz='UTC'))
  assert actual.equals(expected) and len(actual)==2231
  save(META/'Exportacion.json',{'estado':'BASE_NETCDF3_VERIFICADO','archivos':entries,'instantes':len(actual),'bytes':sum(e['bytes'] for e in entries),'alcance_QA':'Campos fisicos y XTIME iguales al original; Times corregido segun traza congelada. Humedad 3x3 de MMIF; no certifica todo el dominio.'})
  activity.update(estado='EXPORTACION_COMPLETA',fase='recibido')
 except Exception:
  activity.update(estado='FALLO',error=traceback.format_exc());save(META/'Fallo_exportacion.json',activity);raise
 finally:
  stop.set();thread.join();save(META/'Actividad_exportacion.json',dict(activity,actualizado=datetime.now().isoformat()));lock.unlink()
 print('Exportacion de invierno completa y verificada.',flush=True)
def emissions():
 for r in read(META/'Preparacion.json')['archivos']:verify(r)
 cal=pd.DataFrame(read(META/'Calendario_horario.json'))
 local=pd.to_datetime(cal.inicio_LST).dt.tz_localize(None)
 cal['dia_LST']=local.dt.strftime('%Y-%m-%d');cal['hora_final']=local.dt.hour+1
 cal['dia_civil']=cal.inicio_civil.str[:10]
 durations=cal.groupby('dia_civil').size().to_dict()
 assert len(durations)==92 and durations['2017-08-13']==23 and sum(durations.values())==2207
 paths=[ROOT/'outputs/Configuracion_fuentes_v1/eje/fuentes_central.csv',ROOT/'outputs/Convergencia_espacial_2026-10-15/Fuentes50/fuentes.csv',ROOT/'outputs/Refinamiento_fuentes25_2026-10-16/Fuentes25/fuentes.csv',DATA/'Comunes/fuentes.csv']
 tables=[pd.read_csv(p) for p in paths];areas=[];stages=[]
 for t in tables:
  xy=t[XY].to_numpy().round(2);areas.append(np.hypot(xy[:,2]-xy[:,0],xy[:,3]-xy[:,1])*t.ancho_m.to_numpy())
 for k in range(1,4):
  ix=tables[k-1].set_index('id_fuente_aermod').index.get_indexer(tables[k].id_fuente_padre)
  assert (ix>=0).all() and set(ix)==set(range(len(tables[k-1])));stages.append(ix)
 ids=tables[-1].id_fuente_aermod.tolist();assert ids==[f'Q{i:06d}' for i in range(1,12264)]
 rounding=lambda a:np.array([float(f'{v:.12E}') for v in a])
 results={}
 for pol in ['MP10','MP25']:
  source=META/f'emisiones_segmentadas_{pol}.csv';verify({'path':str(source),'sha256':read(META/'Emisiones_y_observaciones.json')[pol]['sha256_segmentado']})
  frame=pd.read_csv(source);col='emision_'+pol.lower()+'_g_dia';rates={};total=0;worst=0;entries=[]
  for date,part in frame.groupby('fecha',sort=True):
   part=part.set_index('id_fuente_aermod').reindex(tables[0].id_fuente_aermod)
   assert part[col].notna().all();q=rounding(part[col].to_numpy()/(durations[date]*3600*areas[0]))
   for k,ix in enumerate(stages,1):
    child=rounding(q[ix]*tables[k].factor_densidad.to_numpy())
    back=np.bincount(ix,weights=child*areas[k],minlength=len(q))
    np.testing.assert_allclose(back,q*areas[k-1],rtol=1e-10,atol=1e-11)
    worst=max(worst,float(np.abs(back-q*areas[k-1]).max()));q=child
   rates[date]=q
  for date,daycal in cal.groupby('dia_LST',sort=True):
   day=pd.Timestamp(date);folder=DATA/'Emisiones'/day.strftime('%Y%m%d');folder.mkdir(exist_ok=True)
   dest=folder/(pol+'.emi');assert not dest.exists(),'No sobrescribir emisiones existentes'
   with dest.open('w',encoding='ascii',newline='\n') as f:
    for r in daycal.itertuples():
     q=rates[r.dia_civil];total+=float(q@areas[-1]*3600)
     prefix=f'SO HOUREMIS {day.year%100:02d} {day.month:2d} {day.day:2d} {r.hora_final:2d} '
     f.writelines(prefix+f'{sid:<12s} {v:.12E}\n' for sid,v in zip(ids,q))
   entries.append(dict(rec(dest),horas=len(daycal)))
  expected=float(frame[col].sum());assert np.isclose(total,expected,rtol=1e-10,atol=1e-5)
  results[pol]={'masa_inventario_g':expected,'masa_integrada_g':total,'error_padre_g_s':worst,'archivos':entries}
  print(pol+' emisiones invierno: masa conservada '+str(total)+' g.',flush=True)
 save(META/'Emisiones.json',{'estado':'MASA_DIARIA_CIVIL_CONSERVADA','resumen':results,'entradas':[rec(p) for p in paths],'regla':'Uniforme por segundos reales del dia civil;23h el13ago,24h otros. Ningun control de abatimiento repetido.'})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('etapa',choices=['preparar','exportar','emisiones']);a=p.parse_args()
 {'preparar':prepare,'exportar':export,'emisiones':emissions}[a.etapa]()
