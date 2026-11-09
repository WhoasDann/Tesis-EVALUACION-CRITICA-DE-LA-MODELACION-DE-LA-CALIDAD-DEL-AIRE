"""Recibe meteorologia invernal y verifica cuatro SETUP sin calcular concentraciones."""
from pathlib import Path
from datetime import datetime
from collections import Counter
import argparse,json,re,shutil,sys,subprocess
import numpy as np,pandas as pd
R=Path(__file__).resolve().parents[1];O=R/'outputs/BASE_invierno_2026-10-24';Q=O/'Revision_QC_2026-10-25';DATA=Path('D:/Tesis_Dan/BASE_invierno_2026-10-24')
sys.path.insert(0,str(R/'outputs/Biblioteca_Tesis'))
from tesis.comun import sha256
from tesis.cadena_corta import hora_fin
from tesis.vinculo_horario import validar_vinculo_horario
MISSING={pd.Timestamp('2017-08-14 20:00'),pd.Timestamp('2017-08-14 21:00')}
TAIL={pd.Timestamp('2017-09-21 00:00')}
TARGET=pd.date_range('2017-06-21 01:00','2017-09-20 23:00',freq='h')
AUX=pd.date_range('2017-06-20 01:00','2017-09-20 23:00',freq='h')
HEIGHTS=np.array([2,10,18.75,50,75,100,125,150,175,206.25,250,300,350,400,450,512.5,600,700,800,900,1100,1500,2000,2500,3000,3500,4000,4500,5000])

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def rec(p):return dict(path=str(Path(p).resolve()),sha256=sha256(p))
def verify(entries):
 for e in entries:check(sha256(e['path'])==e['sha256'],'Archivo congelado cambiado: '+e['path'])
def check(ok,msg):
 if not ok:raise ValueError(msg)

def parse(folder):
 lines=(folder/'met.SFC').read_text(encoding='ascii').splitlines();sr={};pr={}
 for line in lines[1:]:
  a=line.split();check(len(a)>=25 and '*' not in line,'SFC incompleto');v=np.array(a[:25],float);check(np.isfinite(v).all(),'SFC NaN/Inf')
  k=pd.Timestamp(hora_fin(*map(int,[a[0],a[1],a[2],a[4]])));check(k not in sr,'SFC duplicado');sr[k]=(v,line)
 for line in (folder/'met.PFL').read_text(encoding='ascii').splitlines():
  a=np.array(line.split(),float);check(len(a)==11 and np.isfinite(a).all(),'PFL no numerico completo')
  k=pd.Timestamp(hora_fin(*map(int,a[:4])));pr.setdefault(k,[]).append((a,line))
 return lines[0],sr,pr

def validate(sr,pr):
 for rows in [sr,pr]:
  check(list(rows)==sorted(rows),'Calendario desordenado');check(set(rows)==set(AUX)|TAIL,'Calendario auxiliar/cola incorrecto')
 missing=set();valid=[]
 for k in sr:
  v=sr[k][0];p=np.array([a for a,_ in pr[k]])
  check(len(p)==29 and np.all(np.diff(p[:,4])>0) and np.max(np.abs(p[:,4]-HEIGHTS))<=.051,'Alturas PFL incorrectas: '+str(k))
  check(list(p[:,5])==[0]*28+[1],'Indicador superior PFL incorrecto')
  if k in MISSING|TAIL:
   check(np.array_equal(v[5:12],[-999,-9,-9,-9,-999,-999,-99999]),'Sentinel SFC de hueco cambiado: '+str(k))
   check(np.array_equal(v[15:20],[999,999,-9,999,-9]) and v[24]==99,'Viento/temperatura faltantes no identificados')
   check(np.all(p[:,6]==999) and np.all(p[:,7:]==99),'PFL faltante no conservado')
   check('NAD' in sr[k][1].split(),'Falta traza NAD');missing.add(k)
   continue
  check(v[6]>=0 and v[10]>0 and abs(v[11])<99998 and (v[11]>=0 or v[9]>0),'Turbulencia/mezcla faltante no prevista: '+str(k))
  check(v[12]>0 and v[15]>=0 and 0<=v[16]<=360 and v[17]>0 and 150<v[18]<350 and v[19]>0,'SFC viento/temperatura invalido: '+str(k))
  check(0<=v[14]<=1 and v[13]>0,'Superficie invalida')
  check('PROG-OS' in sr[k][1].split(),'Origen superficial inesperado')
  check(np.all((p[1:,6]>=0)&(p[1:,6]<=360)&(p[1:,7]>=0)&(p[1:,7]<99)),'PFL viento incompleto: '+str(k))
  temps=p[np.r_[0,2:29],8];check(np.all((temps>-123)&(temps<77)),'PFL temperatura incompleta: '+str(k))
  check(abs(v[13]-{6:1.29,7:2.07,8:4.35,9:4.41}[k.month if k.hour else (k-pd.Timedelta(hours=1)).month])<.0051,'Bowen distinto de la superficie mensual')
  valid.append(k)
 check(missing==MISSING|TAIL,'Faltantes no coinciden con lo previsto')
 return valid

def review():
 check(not (Q/'Recepcion_meteorologia.json').exists(),'Recepcion QC ya creada')
 execution=read(O/'Ejecucion_preprocesamiento.json');verify(execution['archivos']);folder=Path(execution['carpeta'])
 check('AERMET FINISHED SUCCESSFULLY' in (folder/'aermet.exe.consola.log').read_text(),'AERMET sin cierre exitoso')
 errors=(folder/'met.ER1').read_text();report=(folder/'met.OU1').read_text()
 check(not re.search(r'(?m)^\s*\w+\s+E\d{2}\s',errors),'AERMET reporta errores')
 check('I71' not in errors,'I71 nuevo no revisado')
 check(re.search(r'ERROR MESSAGES\s+0 MESSAGES',report),'AERMET reporta errores en resumen')
 check(re.search(r'SUBSTITUTIONS \(INTERPOLATION\) FOR MISSING TEMPERATURE:\s+0',report),'Hubo sustitucion de temperatura')
 header,sr,pr=parse(folder);valid=validate(sr,pr)
 tests={}
 def rejected(name,s,p):
  try:validate(s,p)
  except ValueError:tests[name]=True
  else:raise ValueError('Control no rechazo: '+name)
 s=sr.copy();del s[TARGET[0]];rejected('hora_ausente_rechazada',s,pr)
 p=pr.copy();p[TARGET[0]]=p[TARGET[0]][:-1];rejected('nivel_ausente_rechazado',sr,p)
 s=sr.copy();k=min(MISSING);v=s[k][0].copy();v[15]=0;s[k]=(v,s[k][1]);rejected('faltante_como_cero_rechazado',s,pr)
 s=sr.copy();v=s[TARGET[0]][0].copy();v[10]=-999;s[TARGET[0]]=(v,s[TARGET[0]][1]);rejected('tercer_faltante_rechazado',s,pr)
 frame=[]
 for k in TARGET:
  v=sr[k][0];utc=(k+pd.Timedelta(hours=4)).tz_localize('UTC');civil_start=(utc-pd.Timedelta(hours=1)).tz_convert('America/Santiago')
  state='AUSENCIA_WRF' if k==min(MISSING) else 'EXCLUSION_PRECIPITACION_2H' if k==max(MISSING) else 'CALMA' if v[15]==0 else 'VALIDA'
  frame.append(dict(fin_LST=str(k),inicio_LST=str(k-pd.Timedelta(hours=1)),fin_UTC=str(utc),inicio_civil=str(civil_start),dia_LST=str((k-pd.Timedelta(hours=1)).date()),dia_civil=str(civil_start.date()),estado=state,apta_dispersion=state=='VALIDA',WS_ms=float(v[15]) if k not in MISSING else None,T_K=float(v[18]) if k not in MISSING else None,Bowen=float(v[13])))
 frame=pd.DataFrame(frame);check(int(frame.apta_dispersion.sum())==2205,'Conteo apto inesperado')
 daily={}
 for clock in ['LST','civil']:
  f=frame.groupby('dia_'+clock).agg(horas_calendario=('estado','size'),horas_aptas=('apta_dispersion','sum')).reset_index()
  f['horas_no_validas']=f.horas_calendario-f.horas_aptas;f['cobertura_porcentaje']=100*f.horas_aptas/f.horas_calendario;daily[clock]=f
 check(len(daily['civil'])==92 and daily['civil'].loc[daily['civil'].dia_civil=='2017-08-13','horas_calendario'].item()==23,'Dia DST civil incorrecto')
 check((daily['civil'].horas_calendario==24).sum()==91,'Calendario civil de invierno incorrecto')
 # Exact source absence and conservative next-hour exclusion remain visible in input.
 stamps=[]
 for ln in (folder/'onsite.dat').read_text().splitlines():
  if ln[:10].isdigit():stamps.append(pd.Timestamp(hora_fin(int(ln[:4]),int(ln[4:6]),int(ln[6:8]),int(ln[8:10]))))
 check(pd.DatetimeIndex(stamps).equals(AUX.difference(pd.DatetimeIndex(sorted(MISSING)))),'ONSITE y mascara no coinciden')
 ids={}
 for key,following in [('UA_ID','SF_ID'),('SF_ID','OS_ID'),('OS_ID','VERSION')]:
  match=re.search(key+r':\s*(.*?)\s*'+following+r':',header);check(match is not None,'IDs ausentes');ids[key]=int(match[1].strip() or '0')
 native_wind=[dict(fecha=d,hora=int(h),piso_m_s=.282) for d,h in re.findall(r'I74\s+WINDS\s+RESET WIND TO 0.282 M/S FOR DATE:\s+(\d{8}) HR\s+(\d+)',errors)]
 check(len(native_wind)==2,'Cambió ajuste nativo de viento; revisar')
 Q.mkdir();dest=Q/'Objetivo';dest.mkdir()
 (dest/'met.SFC').write_text('\n'.join([header,*[sr[k][1] for k in TARGET]])+'\n',encoding='ascii')
 (dest/'met.PFL').write_text('\n'.join(line for k in TARGET for a,line in pr[k])+'\n',encoding='ascii')
 frame.to_csv(Q/'Cobertura_horaria.csv',index=False,encoding='utf-8-sig')
 for clock,f in daily.items():f.to_csv(Q/f'Cobertura_diaria_{clock}.csv',index=False,encoding='utf-8-sig')
 monthly=frame.assign(mes=frame.dia_civil.str[:7]).groupby('mes').agg(horas=('estado','size'),aptas=('apta_dispersion','sum')).reset_index();monthly.to_csv(Q/'Cobertura_mensual.csv',index=False,encoding='utf-8-sig')
 qc={'horas_objetivo':2207,'horas_aptas':2205,'faltantes':2,'calmas':int((frame.estado=='CALMA').sum()),'cobertura_porcentaje':100*2205/2207,'filas_SFC_original':len(sr),'horas_auxiliares':len(AUX),'niveles_PFL':29,'cola_excluida':[str(k) for k in TAIL],'faltantes_LST':[str(k) for k in sorted(MISSING)],'ids':ids,'advertencias_AERMET':dict(Counter(re.findall(r'\bW\d{2}\b',errors))),'ajustes_nativos_viento':native_wind,'sustituciones_temperatura':0,'Bowen_mensual':{'junio':1.29,'julio':2.07,'agosto':4.35,'septiembre':4.41},'pruebas':tests,'nota':'Se conservan sentinels nativos y se exige mascara de concentracion. Dos pisos de viento I74 son tratamiento nativo AERMET, no imputacion aplicada por Python. Dias LST distintos de civiles tras cambio DST; reconstruir dias civiles desde resultados horarios.'}
 products=[Q/n for n in ['Cobertura_horaria.csv','Cobertura_diaria_LST.csv','Cobertura_diaria_civil.csv','Cobertura_mensual.csv','Objetivo/met.SFC','Objetivo/met.PFL']]
 result={'estado':'METEOROLOGIA_INVIERNO_RECIBIDA_CON_DOS_AUSENCIAS','qa':qc,'carpeta_AERMET':str(folder),'archivos':[rec(p) for p in products]+[rec(O/'Ejecucion_preprocesamiento.json'),rec(O/'MMIF_verificado.json')],'script':rec(__file__),'concentraciones_calculadas':False}
 save(Q/'Recepcion_meteorologia.json',result)
 print(json.dumps(qc,ensure_ascii=False,indent=2),flush=True)

def setups():
 received=read(Q/'Recepcion_meteorologia.json');verify(received['archivos']);verify([received['script']]);ids=received['qa']['ids']
 verify(read(O/'Preparacion.json')['archivos'])
 results=[]
 for day,nh in [(pd.Timestamp('2017-06-21'),24),(pd.Timestamp('2017-09-20'),23)]:
  for pol in ['MP10','MP25']:
   receipt=Q/f'Recibo_SETUP_{pol}_{day:%Y%m%d}.json'
   if receipt.exists():
    result=read(receipt);verify(result['archivos']);results.append(result);continue
   dest=Q/f'SETUP_{pol}_{day:%Y%m%d}';dest.mkdir()
   for name in ['fuentes_aermod.inc','receptores.inc']:shutil.copy2(DATA/'Comunes'/name,dest/name)
   shutil.copy2(DATA/'Emisiones'/day.strftime('%Y%m%d')/(pol+'.emi'),dest/(pol+'.emi'))
   for kind in ['SFC','PFL']:
    lines=(Q/'Objetivo'/('met.'+kind)).read_text(encoding='ascii').splitlines();chosen=[]
    for line in (lines[1:] if kind=='SFC' else lines):
     a=line.split()
     if tuple(map(int,a[:3]))==(day.year,day.month,day.day):chosen.append(line)
    check(len(chosen)==nh if kind=='SFC' else len(chosen)==nh*29,'Recorte diario incompleto')
    (dest/('met.'+kind)).write_text('\n'.join((lines[:1] if kind=='SFC' else [])+chosen)+'\n',encoding='ascii')
   inp=f'''CO STARTING
CO TITLEONE BASE invierno - SETUP {day:%Y%m%d} - LST UTC-4
CO MODELOPT DFAULT CONC
CO AVERTIME {'1 24 PERIOD' if nh==24 else '1 PERIOD'}
CO POLLUTID {pol}
CO RUNORNOT NOT
CO ERRORFIL errores.out
CO FINISHED
SO STARTING
SO ELEVUNIT METERS
SO INCLUDED fuentes_aermod.inc
SO HOUREMIS {pol}.emi Q000001-Q012263
SO SRCGROUP ALL
SO FINISHED
RE STARTING
RE INCLUDED receptores.inc
RE FINISHED
ME STARTING
ME SURFFILE met.SFC FREE
ME PROFFILE met.PFL FREE
ME SURFDATA {ids['SF_ID']} {day.year}
ME UAIRDATA {ids['UA_ID']} {day.year}
ME SITEDATA {ids['OS_ID']} {day.year}
ME PROFBASE 3469.60 METERS
ME STARTEND {day:%Y %m %d} 1 {day:%Y %m %d} {nh}
ME FINISHED
OU STARTING
OU RECTABLE ALLAVE 1ST
OU POSTFILE 1 ALL PLOT receptor_horas.out
OU SUMMFILE resumen.sum
OU FINISHED
'''
   (dest/'aermod.inp').write_text(inp,encoding='ascii')
   binding=validar_vinculo_horario(dest/'aermod.inp',dest/'fuentes_aermod.inc',dest/(pol+'.emi'),{(day.year%100,day.month,day.day,h) for h in range(1,nh+1)})
   print('Ejecutando solo SETUP '+pol+' '+str(day.date()),flush=True)
   with (dest/'aermod.exe.consola.log').open('wb') as log:
    p=subprocess.run([str(DATA/'Binarios/aermod.exe')],cwd=dest,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,timeout=300)
   check(p.returncode==0,'AERMOD SETUP error')
   text=(dest/'aermod.out').read_text(encoding='ascii',errors='replace');fatal=re.findall(r'A Total of\s+(\d+)\s+Fatal Error',text,re.I)
   count=re.search(r'This Run Includes:\s+(\d+) Source\(s\);\s+\d+ Source Group\(s\); and\s+(\d+) Receptor\(s\)',text)
   check('SETUP Finishes Successfully' in text and fatal and not any(map(int,fatal)),'SETUP sin cierre correcto')
   check(count and tuple(map(int,count.groups()))==(12263,6295),'Dimensiones incorrectas')
   result={'carpeta':str(dest),'vinculo':binding,'horas':nh,'contaminante':pol,'concentraciones_calculadas':False,'archivos':[rec(p) for p in dest.iterdir() if p.is_file()]};save(receipt,result);results.append(result)
 final={'estado':'METEOROLOGIA_INVIERNO_Y_CUATRO_SETUP_VERIFICADOS','qa':received['qa'],'carpeta':str(Q),'setups':results,'archivos':[rec(Q/'Recepcion_meteorologia.json'),*received['archivos'],rec(__file__),*[f for r in results for f in r['archivos']]],'concentraciones_calculadas':False}
 save(O/'Preprocesamiento.json',final)
 print('Invierno preprocesado:2205/2207 horas aptas; cuatro SETUP verificados. Sin concentraciones nuevas.',flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('etapa',choices=['revisar','setup']);a=p.parse_args()
 if a.etapa=='revisar':review()
 else:setups()
