"""MMIF/AERMET estacionales y SETUP de extremos. No calcula concentraciones."""
from pathlib import Path
from datetime import datetime
from collections import Counter
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/BASE_verano_2026-10-21'
sys.path.insert(0,str(ROOT/'outputs/Biblioteca_Tesis'))
from tesis.comun import sha256,guardar_json
from tesis.cadena_corta import ajustar_aermet,hora_fin
from tesis.vinculo_horario import validar_vinculo_horario

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def files(paths):return [dict(path=str(Path(p).resolve()),sha256=sha256(p)) for p in paths]
def verify(entries):
    for e in entries:
        if sha256(e['path'])!=e['sha256']:raise ValueError('Archivo cambió: '+e['path'])
def check(ok,message):
    if not ok:raise ValueError(message)

def native(name,args,folder):
    print('Ejecutando '+name+' en '+str(folder),flush=True)
    with (folder/(name+'.consola.log')).open('wb') as stream:
        p=subprocess.run([str(OUT/'Binarios'/name),*args],cwd=folder,stdout=stream,stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,timeout=14400)
    check(p.returncode==0,f'{name}: código {p.returncode}')

def mmif_qc(folder,plan):
    text=(folder/'mmif_4.1.1.exe.consola.log').read_text(encoding='ascii',errors='replace')
    check('Reached requested ending date/hour; run completed normally.' in text,'MMIF sin cierre normal')
    points={};pending=None
    expected={1:'MET.BAT',2:'ONSITE.DAT',3:'UPPER.DAT',4:'SURFACE.DAT',5:'MET.USEFUL.TXT'}
    for line in text.splitlines():
        m=re.fullmatch(r'\s*Grid parameters for: Output 1-D point\s+#\s+(\d+)\s+(\S+)\s*',line)
        if m:
            check(pending is None,'Punto MMIF incompleto');pending=(int(m[1]),m[2].upper())
        m=re.fullmatch(r'\s*I/J cell center:\s+(\d+)\s+(\d+)\s*',line)
        if m:
            check(pending is not None,'Celda fuera de bloque puntual')
            number,name=pending
            check(number not in points and expected.get(number)==name,'Salida MMIF inesperada')
            points[number]=[int(m[1]),int(m[2])];pending=None
    check(pending is None and set(points)==set(expected) and all(c==[43,44] for c in points.values()),'Celda MMIF distinta del QC')
    matches=re.findall(r'Hourly output written to all files at\s+(\d{10}) LST\s*=\s*(\d{10}) UTC',text)
    local=pd.DatetimeIndex([datetime.strptime(a,'%Y%m%d%H') for a,b in matches])
    utc=pd.DatetimeIndex([datetime.strptime(b,'%Y%m%d%H') for a,b in matches])
    target=pd.date_range(pd.Timestamp(plan['inicio_auxiliar'])+pd.Timedelta(hours=1),plan['fin_exclusivo'],freq='h')
    check(local.equals(target) and utc.equals(target+pd.Timedelta(hours=3)),'Calendario MMIF incompleto')
    for name in ['met.IN1','onsite.dat','upper.dat','surface.dat','met.useful.txt']:
        check((folder/name).is_file() and (folder/name).stat().st_size>0,'Falta '+name)
    return dict(horas=len(local),puntos=points,primera=str(local[0]),ultima=str(local[-1]))

def met_qc(folder,plan):
    target=pd.date_range(pd.Timestamp(plan['inicio'])+pd.Timedelta(hours=1),plan['fin_exclusivo'],freq='h')
    aux=pd.date_range(pd.Timestamp(plan['inicio_auxiliar'])+pd.Timedelta(hours=1),plan['fin_exclusivo'],freq='h')
    # AERMET puede emitir el resto del último día como faltante; nunca se usa.
    allowed_tail=set(pd.date_range(pd.Timestamp(plan['fin_exclusivo'])+pd.Timedelta(hours=1),pd.Timestamp(plan['fin_exclusivo']).normalize()+pd.Timedelta(days=1),freq='h'))
    sfc=(folder/'met.SFC').read_text(encoding='ascii').splitlines()
    sr={};pr={}
    for line in sfc[1:]:
        if not line.strip():continue
        a=line.split();check(len(a)>=25 and '*' not in line,'SFC incompleto')
        values=np.asarray(a[:25],float);check(np.isfinite(values).all(),'SFC NaN/Inf')
        k=pd.Timestamp(hora_fin(*map(int,[a[0],a[1],a[2],a[4]])))
        check(k not in sr,'SFC duplicado');sr[k]=(values,line)
    for line in (folder/'met.PFL').read_text(encoding='ascii').splitlines():
        if not line.strip():continue
        a=np.asarray(line.split(),float);check(len(a)==11 and np.isfinite(a).all(),'PFL inválido')
        k=pd.Timestamp(hora_fin(*map(int,a[:4])));pr.setdefault(k,[]).append((a,line))
    for rows in [sr,pr]:
        check(list(rows)==sorted(rows),'Meteorología desordenada')
        check(set(aux)<=set(rows) and set(rows)-set(aux)<=allowed_tail,'Cobertura auxiliar incompleta o inesperada')
    issues=[];diagnostic=[]
    for k in target:
        v=sr[k][0];p=np.array([a for a,line in pr[k]])
        valid=(v[6]>=0 and v[10]>0 and v[12]>0 and v[15]>=0 and 0<=v[16]<=360 and v[17]>0 and
            150<v[18]<350 and v[19]>0 and abs(v[11])<99998 and (v[11]>=0 or v[9]>0))
        if not valid:issues.append(dict(hora=str(k),tipo='SFC_fisico'))
        validp=(len(p)==29 and np.all(np.diff(p[:,4])>0) and list(p[:,5])==[0]*(len(p)-1)+[1] and
                np.any((p[:,6]>=0)&(p[:,6]<=360)&(p[:,7]>=0)&(p[:,7]<99)) and np.any((p[:,8]>-123)&(p[:,8]<77)))
        if not validp:issues.append(dict(hora=str(k),tipo='PFL_fisico'))
        diagnostic.append(dict(fin_local=str(k),WS_ms=v[15],WD_grados=v[16],T_K=v[18],ZiM_m=v[10],Bowen=v[13]))
    guardar_json(folder/'Problemas_met.json',issues)
    check(not issues,'Meteorología no apta; revisar Problemas_met.json, sin rellenar ni recortar valores')
    ids={}
    for key,following in [('UA_ID','SF_ID'),('SF_ID','OS_ID'),('OS_ID','VERSION')]:
        match=re.search(key+r':\s*(.*?)\s*'+following+r':',sfc[0]);check(match is not None,'IDs ausentes')
        ids[key]=int(match[1].strip() or '0')
    calms=sum(sr[k][0][15]==0 for k in target)
    pd.DataFrame(diagnostic).to_csv(folder/'Serie_objetivo.csv',index=False,encoding='utf-8-sig')
    dest=folder/'Objetivo';dest.mkdir(exist_ok=True)
    (dest/'met.SFC').write_text('\n'.join([sfc[0],*[sr[k][1] for k in target]])+'\n',encoding='ascii')
    (dest/'met.PFL').write_text('\n'.join(line for k in target for a,line in pr[k])+'\n',encoding='ascii')
    return dict(horas_objetivo=len(target),horas_auxiliares=len(aux),filas_SFC=len(sr),
        horas_PFL=len(pr),horas_fuera_objetivo=len(sr)-len(target),calmas=calms,
        niveles_PFL=sorted({len(pr[k]) for k in target}),ids=ids,
        nota='Calmas reales se informan; no se convierten a viento artificial. Definir cobertura de concentración después del RUN.')

def setup(folder,pol,day,nh,ids):
    dest=folder/f'SETUP_{pol}_{day:%Y%m%d}';dest.mkdir()
    for name in ['fuentes_aermod.inc','receptores.inc']:shutil.copy2(OUT/'Comunes'/name,dest/name)
    source=OUT/'Emisiones'/day.strftime('%Y%m%d')/(pol+'.emi');shutil.copy2(source,dest/source.name)
    for kind in ['SFC','PFL']:
        lines=(folder/'Objetivo'/('met.'+kind)).read_text(encoding='ascii').splitlines()
        chosen=[]
        for line in (lines[1:] if kind=='SFC' else lines):
            a=line.split()
            if tuple(map(int,a[:3]))==(day.year,day.month,day.day):chosen.append(line)
        check(len(chosen)==nh if kind=='SFC' else len(chosen)>=nh*3,'Recorte diario incompleto')
        (dest/('met.'+kind)).write_text('\n'.join((lines[:1] if kind=='SFC' else [])+chosen)+'\n',encoding='ascii')
    text=f'''CO STARTING
CO TITLEONE BASE estacional - SETUP {day:%Y%m%d} - UTC-3 provisional
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
    (dest/'aermod.inp').write_text(text,encoding='ascii')
    binding=validar_vinculo_horario(dest/'aermod.inp',dest/'fuentes_aermod.inc',dest/(pol+'.emi'),
        {(day.year%100,day.month,day.day,h) for h in range(1,nh+1)})
    native('aermod.exe',[],dest)
    report=(dest/'aermod.out').read_text(encoding='ascii',errors='replace')
    fatal=re.findall(r'A Total of\s+(\d+)\s+Fatal Error',report,re.I)
    count=re.search(r'This Run Includes:\s+(\d+) Source\(s\);\s+\d+ Source Group\(s\); and\s+(\d+) Receptor\(s\)',report)
    check('SETUP Finishes Successfully' in report and fatal and not any(map(int,fatal)),'SETUP no cerró')
    check(count and tuple(map(int,count.groups()))==(12263,6295),'Dimensiones SETUP incorrectas')
    return dict(carpeta=str(dest),vinculo=binding,archivos=files(p for p in dest.iterdir() if p.is_file()))

def main():
    lock=OUT/'preprocesamiento.lock'
    with lock.open('x',encoding='ascii') as f:f.write(str(os.getpid()))
    try:
        verify(read(OUT/'Entrega.json')['archivos'])
        plan=read(OUT/'Plan.json')
        completed=OUT/'Preprocesamiento.json'
        if completed.exists():
            old=read(completed);verify(old['archivos']);print('Preprocesamiento estacional ya verificado.');return
        print('Comprobando91 archivos WRF BASE exportados...',flush=True)
        exported=read(OUT/'Exportacion.json')
        verify([r['exportado'] for r in exported['archivos']])
        saved=OUT/'MMIF_validado.json'
        if saved.exists():
            previous=read(saved);verify(previous['archivos']);folder=Path(previous['carpeta'])
            print('Reutilizando MMIF estacional verificado.',flush=True)
        else:
            folder=OUT/'Meteorologia'/('ejecucion_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));folder.mkdir()
            shutil.copy2(OUT/'Meteorologia/mmif.inp',folder/'mmif.inp')
            native('mmif_4.1.1.exe',['mmif.inp'],folder)
            qmmif=mmif_qc(folder,plan)
            shutil.copy2(folder/'met.IN1',folder/'met.IN1.original')
            saved_files=[folder/n for n in ['mmif.inp','mmif_4.1.1.exe.consola.log','met.IN1.original','onsite.dat','surface.dat','upper.dat','met.useful.txt']]
            guardar_json(saved,dict(carpeta=str(folder),qa=qmmif,archivos=files(saved_files)))
        original=(folder/'met.IN1.original').read_text(encoding='ascii')
        # Conservar cada intento AERMET; reutilizar únicamente MMIF recibido.
        met=OUT/'Meteorologia'/('aermet_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));met.mkdir()
        for name in ['onsite.dat','upper.dat','surface.dat']:shutil.copy2(folder/name,met/name)
        (met/'met.IN1.original').write_text(original,encoding='ascii')
        (met/'met.IN1').write_text(ajustar_aermet(original,'WRF'),encoding='ascii')
        native('aermet.exe',['met.IN1'],met)
        errors=(met/'met.ER1').read_text(encoding='ascii',errors='replace')
        check(not re.search(r'(?m)^\s*(?:\w+\s+)?E\d{2}\s',errors),'AERMET informa E##')
        qc=met_qc(met,plan)
        qc['advertencias_AERMET']=dict(Counter(re.findall(r'\bW\d{2}\b',errors)))
        setups=[]
        for day,nh in [(pd.Timestamp(plan['inicio']),24),(pd.Timestamp(plan['fin_exclusivo']).normalize(),17)]:
            for pol in ['MP10','MP25']:setups.append(setup(met,pol,day,nh,qc['ids']))
        guardar_json(completed,dict(estado='METEOROLOGIA_ESTACIONAL_Y_EXTREMOS_SETUP_VERIFICADOS',carpeta=str(met),qa=qc,setups=setups,
            archivos=files([p for p in met.rglob('*') if p.is_file()])+files([saved])))
        guardar_json(OUT/'Estado.json',dict(estado='BASE_ESTACIONAL_PREPROCESADO',horas=2153,fuentes=12263,receptores=6295,
            concentraciones_calculadas=False,calmas=qc['calmas'],archivos=files([completed])))
        print('Verificados:2177h auxiliares,2153h objetivo y SETUP MP10/MP2,5 para día completo y parcial.',flush=True)
        print('Meteorología lista; todavía no se calcularon concentraciones del verano.',flush=True)
    except Exception:
        guardar_json(OUT/'Fallo_preprocesamiento.json',dict(error=traceback.format_exc()))
        raise
    finally:
        lock.unlink()

if __name__=='__main__':main()
