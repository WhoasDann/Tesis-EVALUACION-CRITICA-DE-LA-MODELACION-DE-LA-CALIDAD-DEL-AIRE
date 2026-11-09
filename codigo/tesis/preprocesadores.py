"""Genera MMIF para períodos locales de fin de hora y verifica cobertura WRF UTC."""
from pathlib import Path
import argparse,json
import pandas as pd
from .comun import PERIODOS,salida_nueva,guardar_json,sha256

LAYERS=[25,50,75,100,125,150,175,200,250,300,350,400,450,500,600,700,800,900,1000,1500,2000,2500,3000,3500,4000,4500,5000]

def horas_mmif(periodo_nombre,timezone=-3,*,fin_local=None):
    start,nominal_end=map(pd.Timestamp,PERIODOS[periodo_nombre])
    end=nominal_end if fin_local is None else pd.Timestamp(fin_local)
    if pd.isna(end) or end.tz is not None or end!=end.floor('h') or not start<end<=nominal_end:
        raise ValueError('Fin local debe ser una hora entera sin zona, posterior al inicio y no superior al fin nominal.')
    # Intervalos [start,end): MMIF etiqueta su final en horas 1..24.
    local=pd.date_range(start+pd.Timedelta(hours=1),end,freq='h')
    return local,local-pd.Timedelta(hours=timezone)

def cobertura_mmif(available,periodo_nombre,timezone=-3,*,fin_local=None):
    """Incluye el extremo final y el instante previo para lluvia acumulada."""
    available=pd.DatetimeIndex(available)
    if available.tz is not None:
        available=available.tz_convert('UTC').tz_localize(None)
    if available.hasnans or available.has_duplicates:
        raise ValueError('Times WRF ausentes o duplicados.')
    if any(available!=available.floor('h')):
        raise ValueError('Se requieren instantes WRF en horas UTC enteras.')
    local,required=horas_mmif(periodo_nombre,timezone,fin_local=fin_local)
    _,nominal=horas_mmif(periodo_nombre,timezone)
    previous=required[0]-pd.Timedelta(hours=1)
    inputs=pd.date_range(previous,required[-1],freq='h')
    missing=inputs.difference(available)
    return {'periodo':periodo_nombre,'timezone_fijo_provisional':timezone,
            'inicio_local':PERIODOS[periodo_nombre][0],
            'fin_local_efectivo_exclusivo':str(local[-1]),'fin_local_nominal_exclusivo':PERIODOS[periodo_nombre][1],
            'cierre_explicito':fin_local is not None,'horas_fuera_por_cierre_efectivo':len(nominal)-len(required),
            'horas_salida_MMIF':len(required),'instantes_entrada_incluida_lluvia':len(inputs),
            'primera_etiqueta_local':str(local[0]),'ultima_etiqueta_local':str(local[-1]),
            'primera_salida_UTC':str(required[0]),'ultima_salida_UTC':str(required[-1]),
            'hora_previa_lluvia_UTC':str(previous),'hora_previa_presente':previous in available,
            'faltantes_salida_MMIF':len(required.difference(available)),
            'faltantes_entrada_UTC':[str(t) for t in missing],
            'cobertura_completa':not len(missing)}

def texto_mmif(files,periodo_nombre,*,fin_local=None):
    local,_=horas_mmif(periodo_nombre,fin_local=fin_local)
    lines=[f'START {local[0]:%Y %m %d %H}',f'STOP {local[-1]:%Y %m %d %H}','TIMEZONE -3']
    for path in files:lines.append(f'INPUT "{Path(path).resolve()}"')
    lines+=['POINT LL -33.15632248 -70.29452515','LAYERS MID '+' '.join(map(str,LAYERS)),
            'AER_MIN_SPEED 0','AER_USE_NEW T','AER_MIXHT WRF','FSL_INTERVAL 12',
            'OUTPUT AERMET BAT met.bat','OUTPUT AERMET ONSITE onsite.dat','OUTPUT AERMET FSL upper.dat',
            'OUTPUT AERMET AERSFC surface.dat','OUTPUT AERMET USEFUL met.useful.txt']
    return '\n'.join(lines)+'\n'

def preparar(folder,destination,season,*,fin_local=None):
    from netCDF4 import Dataset,chartostring
    files=sorted(p for p in Path(folder).glob('wrfout_d03_*') if p.is_file() and not p.suffix)
    local,required=horas_mmif(season,fin_local=fin_local);available=[];starts=set();used=[]
    required_inputs=pd.date_range(required[0]-pd.Timedelta(hours=1),required[-1],freq='h')
    for p in files:
        with Dataset(p) as n:
            if int(n.GRID_ID)!=3:raise ValueError('INPUT no es d03.')
            times=pd.to_datetime(chartostring(n['Times'][:]).tolist(),format='%Y-%m-%d_%H:%M:%S')
            if len(times.intersection(required_inputs)):
                starts.add(n.SIMULATION_START_DATE)
                available.extend(times);used.append(p)
                # Índices Python base cero. Evita trasladar un POINT antiguo a otra malla.
                if abs(float(n['XLAT'][0,43,42])+33.15632248)>1e-5 or abs(float(n['XLONG'][0,43,42])+70.29452515)>1e-5:
                    raise ValueError('La celda MMIF de referencia no coincide con esta malla.')
    if len(starts)!=1:raise ValueError('Debe existir una sola integración WRF que cubra el período.')
    available=pd.DatetimeIndex(available)
    if available.duplicated().any():raise ValueError('Times WRF duplicados entre INPUTs.')
    coverage=cobertura_mmif(available,season,fin_local=fin_local)
    missing=coverage['faltantes_entrada_UTC']
    if missing:raise ValueError(f'Faltan {len(missing)} instantes UTC para {season}, incluida hora previa de lluvia; primero: {missing[0]}.')
    integration_start=pd.Timestamp(next(iter(starts)).replace('_',' '))
    if required[0]-pd.Timedelta(hours=1)<integration_start+pd.Timedelta(days=20):
        raise ValueError('No se completan 20 días de spin-up antes del período local.')
    out=salida_nueva(destination);(out/'mmif.inp').write_text(texto_mmif(used,season,fin_local=fin_local),encoding='utf-8')
    guardar_json(out/'manifest.json',{'periodo':season,'timezone':-3,'horas':len(required),
       'primera_UTC':str(required[0]),'ultima_UTC':str(required[-1]),'etiqueta':'fin de hora local estándar',
       'fin_local_efectivo_exclusivo':str(local[-1]),'fin_local_nominal_exclusivo':PERIODOS[season][1],
       'point_indices_python':[42,43],'HGT_referencia_m':3469.60400390625,
       'entradas':[{'path':str(p),'sha256':sha256(p)} for p in used],
       'nota':'Control generado; ejecución MMIF/AERMET y validación física posteriores pendientes.'})

def preparar_desde_inventario(inventory,destination,season,*,fin_local=None):
    """Reutiliza hashes auditados y deja sólo el diagnóstico si falta cobertura.

    No escribe un control si falta cobertura del período explícitamente elegido. No certifica
    la lectura del formato NetCDF por el binario, ni autoriza una corrida larga.
    """
    from .piloto_wrf import comprobar_inventario
    from netCDF4 import Dataset
    inventory=Path(inventory).resolve()
    items=json.loads(inventory.read_text(encoding='utf-8'))
    timeline=comprobar_inventario(items)
    for item in items:
        st=Path(item['path']).stat()
        if (st.st_size,st.st_mtime_ns)!=(item['bytes'],item['mtime_ns']):
            raise ValueError('Archivo cambiado después de auditar: '+item['path'])
        if not item.get('sha256'):raise ValueError('Inventario sin hash de contenido.')
    coverage=cobertura_mmif(timeline.fecha_wrf_utc,season,fin_local=fin_local)
    out=salida_nueva(destination)
    coverage.update(inventario=str(inventory),inventario_sha256=sha256(inventory),
        hashes='Reutilizados del inventario; bytes y mtime_ns comprobados ahora.',
        modelo_ejecutado=False,control_ejecutable_generado=False)
    guardar_json(out/'cobertura.json',coverage)
    if not coverage['cobertura_completa']:
        return coverage
    local,required=horas_mmif(season,fin_local=fin_local)
    start=required[0]-pd.Timedelta(hours=1)
    if start<pd.Timestamp(items[0]['integration_start'])+pd.Timedelta(days=20):
        raise ValueError('No hay 20 días de preparación antes del intervalo.')
    selected=[x for x in items if any(start<=pd.Timestamp(t)<=required[-1] for t in x['times'])]
    with Dataset(selected[0]['path']) as n:
        if abs(float(n['XLAT'][0,43,42])+33.15632248)>1e-5 or abs(float(n['XLONG'][0,43,42])+70.29452515)>1e-5:
            raise ValueError('La celda MMIF vigente no coincide con la malla.')
    (out/'mmif.inp').write_text(texto_mmif([x['path'] for x in selected],season,fin_local=fin_local),encoding='utf-8')
    coverage.update(control_ejecutable_generado=True,
                    entradas=[{k:x[k] for k in ('path','sha256','bytes','mtime_ns')} for x in selected],
                    nota='BASE corta y lectura efectiva del formato por MMIF pendientes antes de ejecutar el período estacional.')
    guardar_json(out/'cobertura.json',coverage)
    return coverage

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--wrf-dir',required=True);p.add_argument('--salida',required=True)
    p.add_argument('--periodo',required=True,choices=list(PERIODOS))
    p.add_argument('--fin-local',help='Cierre efectivo explícito, hora local entera; no se infiere por archivos ausentes.')
    a=p.parse_args();preparar(a.wrf_dir,a.salida,a.periodo,fin_local=a.fin_local)

if __name__=='__main__':main()
