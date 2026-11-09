"""Contratos del ensayo técnico de un día; no estima incertidumbre probabilística."""
from datetime import datetime, timedelta
from pathlib import Path
import math
import re

METODOS = ('WRF', 'MMIF', 'AERMET')
INICIO = datetime(2016, 12, 31)
FIN = datetime(2017, 1, 3)
OBJETIVO = datetime(2017, 1, 1)
TZ = -3


def horas():
    """72 etiquetas de fin de hora LST y 73 instantes WRF UTC (incluye lluvia)."""
    local = [INICIO + timedelta(hours=h) for h in range(1, 73)]
    utc = [INICIO - timedelta(hours=TZ) + timedelta(hours=h) for h in range(73)]
    return local, utc


def control_mmif(archivos, metodo):
    from .preprocesadores import LAYERS
    if metodo not in METODOS:
        raise ValueError('Método de altura de mezcla desconocido.')
    return '\n'.join([
        'START 2016 12 31 01', 'STOP 2017 01 03 00', 'TIMEZONE -3',
        *[f'INPUT "{Path(p).resolve()}"' for p in archivos],
        'POINT LL -33.15632248 -70.29452515',
        'LAYERS MID ' + ' '.join(map(str, LAYERS)),
        'AER_MIN_SPEED 0', 'AER_USE_NEW T', f'AER_MIXHT {metodo}',
        'FSL_INTERVAL 12', 'OUTPUT AERMET BAT met.bat',
        'OUTPUT AERMET ONSITE onsite.dat', 'OUTPUT AERMET FSL upper.dat',
        'OUTPUT AERMET AERSFC surface.dat', 'OUTPUT AERMET USEFUL met.useful.txt', ''])


def ajustar_aermet(texto, metodo):
    """Ajuste explícito sólo para la salida PROG OL de MMIF 4.1.1.

    En NEW, MMIF escribe MHGT también con AER_MIXHT AERMET. Se salta ese
    campo conservando columnas; así AERMET calcula la mezcla sin leerla.
    La ventana de presión se declara por altitud, antes de evaluar resultados.
    Rechaza formatos no reconocidos, en lugar de adivinar sus columnas.
    """
    if metodo not in METODOS:
        raise ValueError('Método desconocido.')
    if not re.search(r'^\s*PROG\s*$', texto, re.M) or not re.search(
            r'^\s*DATA\s+onsite\.dat\s+OL\s*$', texto, re.M | re.I):
        raise ValueError('Se esperaba PROG OL generado por MMIF 4.1.1.')
    texto, n = re.subn(r'(?m)^(\s*RANGE\s+PRES\s+)7500(\s+<\s+10999\s+99999\s*)$',
                       r'\g<1>4000\2', texto)
    if n != 1:
        raise ValueError('RANGE PRES original no reconocido o ya modificado.')
    if metodo == 'AERMET':
        texto, n = re.subn(r'(?m)^(\s*READ\s+1\s+[^\n]*?)\s+MHGT\b', r'\1', texto)
        if n != 1:
            raise ValueError('READ 1 MHGT no reconocido.')
        texto, n = re.subn(r'(?m)^(\s*FORMAT\s+1\s+\(I4,3I2\.2,)4F10\.3,',
                           r'\g<1>3F10.3,10X,', texto)
        if n != 1:
            raise ValueError('FORMAT 1 no reconocido; no es seguro omitir MHGT.')
        texto = re.sub(r'(?m)^\s*RANGE\s+MHGT[^\n]*\n', '', texto)
        texto = '\n'.join(re.sub(r'\s+MHGT\b', '', s) if s.strip().startswith('AUDIT ') else s
                          for s in texto.splitlines()) + '\n'
        if re.search(r'\bMHGT\b', texto):
            raise ValueError('Quedó una referencia MHGT en el control AERMET.')
    return texto


def receptores(path):
    """Lee todas las redes y puntos; no pierde CG2..CGn silenciosamente."""
    from .receptores import leer_aermap
    return [(p['x_m'], p['y_m'], p['elev_m'], p['hill_m']) for p in leer_aermap(path)]


def hora_fin(year,month,day,hour):
    if not 1 <= hour <= 24:
        raise ValueError('Se esperaba hora final 1..24.')
    return datetime(year if year>=100 else year+2000,month,day)+timedelta(hours=hour)


def seleccionar_met_objetivo(sfc, pfl, destination):
    """Copia sólo las 24h con emisiones; conserva las 72h AERMET de origen.

    AERMOD User's Guide 26135, 3.3.12: HOUREMIS debe coincidir con las
    fechas meteorológicas, incluidas las que STARTEND omite. No basta
    limitar STARTEND si el archivo de emisiones contiene sólo un día.
    """
    from .comun import sha256
    sfc,pfl,dest=Path(sfc),Path(pfl),Path(destination)
    if any((dest/p.name).resolve()==p.resolve() for p in (sfc,pfl)):
        raise ValueError('El recorte no puede sobrescribir meteorología de origen.')
    qa=revisar_met(sfc,pfl)
    target=[OBJETIVO+timedelta(hours=h) for h in range(1,25)]
    target_set=set(target)
    selected={}
    for path in (sfc,pfl):
        lines=path.read_text(encoding='ascii').splitlines()
        is_sfc=path==sfc
        output=[lines[0]] if is_sfc else []
        keys=[]
        for line in (lines[1:] if is_sfc else lines):
            if not line.strip():continue
            a=line.split()
            key=hora_fin(*map(int,[a[0],a[1],a[2],a[4] if is_sfc else a[3]]))
            if key in target_set:
                output.append(line);keys.append(key)
        ordered=list(dict.fromkeys(keys))
        if ordered!=target or (is_sfc and len(keys)!=24):
            raise ValueError('La selección meteorológica no conserva las 24h ordenadas.')
        result=dest/path.name
        result.write_text('\n'.join(output)+'\n',encoding='ascii')
        selected[path.name]={'origen':str(path.resolve()),'origen_sha256':sha256(path),
                             'seleccion_sha256':sha256(result),'registros':len(keys)}
    return {'horas':24,'fecha':'2017-01-01','anio_inicial':OBJETIVO.year,
            'ids':qa['ids'],'archivos':selected,
            'criterio':'Selección literal de registros 1ene horas 1..24; sin modificar valores ni interpolar.'}


def revisar_met(sfc, pfl):
    """Exige cobertura auxiliar y perfila las 24 h objetivo; no rellena datos."""
    rows={}
    lines=Path(sfc).read_text(encoding='ascii').splitlines()
    header=lines[0]
    for line in lines[1:]:
        if not line.strip():
            continue
        a=line.split()
        if len(a)<25 or '*' in line:
            raise ValueError('Registro SFC incompleto/desbordado.')
        nums=list(map(float,a[:25]))
        if not all(map(math.isfinite,nums)):
            raise ValueError('SFC contiene NaN/Inf.')
        key=hora_fin(*map(int,[a[0],a[1],a[2],a[4]]))
        if key in rows:
            raise ValueError('Hora SFC duplicada.')
        rows[key]=nums
    expected,_=horas()
    if set(rows)!=set(expected):
        raise ValueError('SFC no tiene exactamente las 72 horas auxiliares esperadas.')
    target=[OBJETIVO+timedelta(hours=h) for h in range(1,25)]
    calm=0
    for key in target:
        v=rows[key]
        # Cols: u*, ZiC, ZiM, L, z0, viento, dirección, z viento, T(K), z T.
        if not (v[6]>=0 and v[10]>0 and v[12]>0 and v[15]>=0 and 0<=v[16]<=360
                and v[17]>0 and 150<v[18]<350 and v[19]>0 and abs(v[11])<99998):
            raise ValueError(f'SFC inválido/faltante en hora objetivo: {key}.')
        if v[11]<0 and v[9]<=0:
            raise ValueError('Falta altura convectiva para L<0.')
        calm+=v[15]==0
    profiles={}
    for line in Path(pfl).read_text(encoding='ascii').splitlines():
        if not line.strip():
            continue
        a=list(map(float,line.split()))
        if len(a)!=11 or not all(map(math.isfinite,a)):
            raise ValueError('PFL inválido.')
        key=hora_fin(*map(int,a[:4]))
        profiles.setdefault(key,[]).append(a)
    if set(profiles)!=set(expected):
        raise ValueError('Horas PFL diferentes de SFC.')
    for key in target:
        p=profiles[key]
        zs=[x[4] for x in p]
        if len(p)<3 or any(b<=a for a,b in zip(zs,zs[1:])) or [x[5] for x in p] != [0]*(len(p)-1)+[1]:
            raise ValueError('Perfil no ordenado, incompleto o sin cierre.')
        # -999 es aceptable en variables ausentes de un nivel (p. ej. viento a 2m).
        if not any(0<=x[6]<=360 and 0<=x[7]<99 for x in p) or not any(-123<x[8]<77 for x in p):
            raise ValueError('Perfil sin temperatura/viento utilizables.')
    ids={}
    for key,following in [('UA_ID','SF_ID'),('SF_ID','OS_ID'),('OS_ID','VERSION')]:
        m=re.search(key+r':\s*(.*?)\s*'+following+r':',header)
        if not m or (m.group(1).strip() and not m.group(1).strip().isdigit()):
            raise ValueError('Cabecera SFC de estaciones no reconocida.')
        ids[key]=int(m.group(1).strip() or '0')
    return {'horas_SFC':72,'horas_objetivo':24,'calmas_objetivo':int(calm),'anio_inicial':INICIO.year,
            'ids':ids,'niveles_PFL':sorted(set(len(profiles[k]) for k in target)),
            'ZiC_m':[rows[k][9] for k in target],'ZiM_m':[rows[k][10] for k in target],
            'temperatura_K':[rows[k][18] for k in target],
            'velocidad_ms':[rows[k][15] for k in target]}
