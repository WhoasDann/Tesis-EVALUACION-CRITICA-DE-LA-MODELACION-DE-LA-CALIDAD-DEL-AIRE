"""Preprocesa invierno con una ausencia WRF y excluye su acumulado de lluvia posterior.
No afirma recepcion fisica final ni ejecuta concentraciones.
"""
from pathlib import Path
from datetime import datetime
import json,os,re,shutil,subprocess,sys,traceback
import pandas as pd,numpy as np
from preparar_base_invierno_20261024 import META,DATA,read,save,rec,verify
sys.path.insert(0,str(META.parent/'Biblioteca_Tesis'))
from tesis.cadena_corta import ajustar_aermet,hora_fin

def native(name,args,folder):
 print('Ejecutando '+name+' en '+str(folder),flush=True)
 with (folder/(name+'.consola.log')).open('wb') as log:
  r=subprocess.run([str(DATA/'Binarios'/name),*args],cwd=folder,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,timeout=14400)
 if r.returncode:raise ValueError(name+' termino con codigo '+str(r.returncode))
def main():
 for r in read(META/'Entrega_preprocesamiento.json')['archivos']:verify(r)
 if not (META/'Exportacion.json').exists():
  print('La exportacion WRF aun no esta completa. Consulte Actividad_exportacion.json; no se ejecutaron modelos.');return 2
 for r in read(META/'Preparacion.json')['archivos']:verify(r)
 export=read(META/'Exportacion.json')
 print('Comprobando las '+str(len(export['archivos']))+' copias WRF de invierno...',flush=True)
 for r in export['archivos']:verify(r['exportado'])
 lock=META/'preprocesamiento_invierno.lock'
 with lock.open('x') as f:f.write(str(os.getpid()))
 try:
  if (META/'Ejecucion_preprocesamiento.json').exists():
   print('Existe una ejecucion recibida para revisar. No se repite.');return 0
  saved=META/'MMIF_verificado.json'
  if saved.exists():
   previous=read(saved)
   for r in previous['archivos']:verify(r)
   folder=Path(previous['carpeta']);print('Reutilizando MMIF recibido.',flush=True)
  else:
   folder=DATA/'Meteorologia'/('MMIF_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));folder.mkdir()
   shutil.copy2(DATA/'Meteorologia/mmif.inp',folder/'mmif.inp')
   native('mmif_4.1.1.exe',['mmif.inp'],folder)
   log=(folder/'mmif_4.1.1.exe.consola.log').read_text(encoding='ascii',errors='replace')
   assert 'Reached requested ending date/hour; run completed normally.' in log,'MMIF sin cierre normal'
   pairs=re.findall(r'Hourly output written to all files at\s+(\d{10}) LST\s*=\s*(\d{10}) UTC',log)
   local=pd.DatetimeIndex([datetime.strptime(a,'%Y%m%d%H') for a,b in pairs]);utc=pd.DatetimeIndex([datetime.strptime(b,'%Y%m%d%H') for a,b in pairs])
   expected=pd.date_range('2017-06-20 01:00','2017-09-20 23:00',freq='h').difference(pd.DatetimeIndex(['2017-08-14 20:00']))
   assert local.equals(expected) and utc.equals(expected+pd.Timedelta(hours=4)),'Calendario MMIF incorrecto'
   # Sólo centros de salidas puntuales; excluir el bloque de subdominio tridimensional.
   blocks=re.findall(r'Grid parameters for: Output 1-D point\s+#\s+(\d+)\s+\S+([\s\S]*?)(?=Grid parameters for:|$)',log)
   centers=[re.search(r'I/J cell center:\s+(\d+)\s+(\d+)',b) for _,b in blocks]
   assert len(centers)==5 and all(m and m.groups()==('43','44') for m in centers),'Celda MMIF distinta'
   names=['mmif.inp','mmif_4.1.1.exe.consola.log','met.IN1','onsite.dat','upper.dat','surface.dat','met.useful.txt']
   save(saved,{'carpeta':str(folder),'horas':len(local),'hora_ausente_LST':'2017-08-14 20:00','archivos':[rec(folder/n) for n in names]})
  met=DATA/'Meteorologia'/('AERMET_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));met.mkdir()
  for name in ['upper.dat','surface.dat']:shutil.copy2(folder/name,met/name)
  lines=(folder/'onsite.dat').read_text(encoding='ascii').splitlines(keepends=True)
  blocks=[]
  for line in lines:
   if len(line)>=10 and line[:10].isdigit():blocks.append([line])
   else:
    assert blocks,'Linea ONSITE sin cabecera';blocks[-1].append(line)
  assert all(len(b)==30 for b in blocks),'Estructura ONSITE distinta'
  removed=[b for b in blocks if b[0][:10]=='2017081421'];assert len(removed)==1
  assert not any(b[0][:10]=='2017081420' for b in blocks)
  (met/'onsite.dat').write_text(''.join(''.join(b) for b in blocks if b[0][:10]!='2017081421'),encoding='ascii')
  (met/'ONSITE_excluido_2017081421.txt').write_text(''.join(removed[0]),encoding='ascii')
  original=(folder/'met.IN1').read_text(encoding='ascii')
  (met/'met.IN1.original').write_text(original,encoding='ascii')
  (met/'met.IN1').write_text(ajustar_aermet(original,'WRF'),encoding='ascii')
  save(met/'Exclusion.json',{'hora_LST':'2017-08-14 21:00','hora_UTC':'2017-08-15 01:00','razon':'Incremento de precipitacion abarca2h por hueco WRF anterior; exclusión conservadora de todo el bloque ONSITE, sin rellenar datos.','MMIF_original':rec(folder/'onsite.dat')})
  native('aermet.exe',['met.IN1'],met)
  for name in ['met.SFC','met.PFL','met.ER1','met.OU1']:assert (met/name).stat().st_size>0,name
  diagnostics=[]
  for line in (met/'met.SFC').read_text(encoding='ascii').splitlines()[1:]:
   if not line.strip():continue
   a=line.split();k=pd.Timestamp(hora_fin(*map(int,[a[0],a[1],a[2],a[4]])))
   if pd.Timestamp('2017-06-21')<k<=pd.Timestamp('2017-09-20 23:00'):
    v=np.array(a[:25],float);assert np.isfinite(v).all()
    diagnostics.append({'fin_LST':str(k),'fila_SFC':line,'ausencia_esperada':str(k) in ['2017-08-14 20:00:00','2017-08-14 21:00:00']})
  assert len(diagnostics)==2207,'Cobertura SFC objetivo inesperada'
  save(META/'Ejecucion_preprocesamiento.json',{'estado':'MMIF_Y_AERMET_EJECUTADOS_REVISION_PENDIENTE','carpeta':str(met),'horas_objetivo':len(diagnostics),'archivos':[rec(p) for p in met.iterdir() if p.is_file()],'diagnostico_SFC':diagnostics,'concentraciones_calculadas':False,'nota':'Revisar faltantes, I71, PFL, superficies y SETUP antes de aceptar meteorologia estacional.'})
  print('MMIF y AERMET terminaron. Revisar Ejecucion_preprocesamiento.json; aun no se calculan concentraciones.',flush=True)
  return 0
 except Exception:
  save(META/'Fallo_preprocesamiento.json',{'error':traceback.format_exc()});raise
 finally:lock.unlink()
if __name__=='__main__':raise SystemExit(main())
