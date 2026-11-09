"""Formatos diferentes para LINE en AERMAP y AERMOD; sin conversión a RLINE."""
import argparse
from pathlib import Path
import re
import numpy as np
import pandas as pd
from .comun import finito, guardar_json, salida_nueva, sha256

def validar_id(source):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,11}',str(source)):
        raise ValueError(f'ID de fuente no admitido: {source}')

def location_aermap(source,xy,width):
    validar_id(source);finito(xy,width)
    if len(xy)!=4 or width<1:raise ValueError('LINE requiere 4 coordenadas y ancho >=1 m.')
    return f"SO LOCATION {source} LINE "+' '.join(f'{x:.2f}' for x in xy)+f' {width:.3f}\n'

def location_aermod(source,xy,z):
    validar_id(source);finito(xy,z)
    if len(xy)!=4:raise ValueError('LINE requiere 4 coordenadas y UNA cota.')
    return f"SO LOCATION {source} LINE "+' '.join(f'{x:.2f}' for x in xy)+f' {z:.3f}\n'

def leer_fuentes(path):
    s=pd.read_csv(path)
    columns=['id_fuente_aermod','id_ruta_excel','x1_utm19s_m','y1_utm19s_m','x2_utm19s_m','y2_utm19s_m']
    if not set(columns)<=set(s):raise ValueError('Esquema de fuentes incompleto.')
    if s.id_fuente_aermod.duplicated().any():raise ValueError('IDs de fuente duplicados.')
    for row in s.itertuples():validar_id(row.id_fuente_aermod)
    xy=s[columns[2:]].to_numpy(float);finito(xy)
    if np.any(np.hypot(xy[:,2]-xy[:,0],xy[:,3]-xy[:,1])<=0):raise ValueError('Fuente de longitud nula.')
    return s

def leer_cotas_aermap(path,sources):
    records={}
    for line in Path(path).read_text(encoding='utf-8',errors='replace').splitlines():
        t=line.split()
        if len(t)>2 and t[:2]==['SO','LOCATION']:
            if len(t)!=9 or t[3]!='LINE':raise ValueError('Salida AERMAP LINE debe contener xyxy y una cota.')
            if t[2] in records:raise ValueError('Cota duplicada.')
            records[t[2]]=list(map(float,t[4:]))
    if set(records)!=set(sources.id_fuente_aermod):raise ValueError('Los IDs de AERMAP y emisiones difieren.')
    elevations={}
    for row in sources.itertuples():
        xy=np.array([row.x1_utm19s_m,row.y1_utm19s_m,row.x2_utm19s_m,row.y2_utm19s_m])
        coordinates=np.array(records[row.id_fuente_aermod][:4])
        if not (np.allclose(xy,coordinates,atol=.011,rtol=0) or np.allclose(xy,coordinates[[2,3,0,1]],atol=.011,rtol=0)):
            raise ValueError(f'Coordenadas diferentes para {row.id_fuente_aermod}.')
        z=records[row.id_fuente_aermod][4]
        if not np.isfinite(z) or z<=-9999:raise ValueError('Cota inválida/nodata.')
        elevations[row.id_fuente_aermod]=z
    return elevations

def preparar(sources_csv,dem,dest,width=3):
    sources=leer_fuentes(sources_csv);dem=Path(dem).resolve()
    if not dem.is_file():raise FileNotFoundError(dem)
    widths=sources.ancho_m.to_numpy(float) if width is None else np.full(len(sources),width,dtype=float)
    finito(widths)
    if np.any(widths<1):raise ValueError('Ancho LINE >=1 m requerido.')
    if 'ancho_m' in sources and not np.allclose(widths,sources.ancho_m,rtol=0,atol=.0005):
        raise ValueError('Ancho AERMAP diferente de la geometría preparada.')
    lines=''.join(location_aermap(r.id_fuente_aermod,[r.x1_utm19s_m,r.y1_utm19s_m,r.x2_utm19s_m,r.y2_utm19s_m],w) for r,w in zip(sources.itertuples(),widths))
    out=salida_nueva(dest)
    (out/'fuentes_aermap.inc').write_text(lines,encoding='ascii')
    # Mismo sistema proyectado y extensión del proyecto; sin sustituir el datum.
    inp=f'''CO STARTING
CO TITLEONE Los Bronces - extraccion corregida de cotas LINE
CO DATATYPE NED FILLGAPS
CO DATAFILE "{dem}"
CO TERRHGTS EXTRACT
CO DOMAINXY 349000 6297500 -19 400000 6340000 -19
CO ANCHORXY 350000 6300000 350000 6300000 -19 0
CO RUNORNOT RUN
CO FINISHED
SO STARTING
SO INCLUDED fuentes_aermap.inc
SO FINISHED
OU STARTING
OU SOURCLOC aermap.src
OU FINISHED
'''
    # Ejecutable Windows de EPA: rutas de este proyecto en página ANSI occidental.
    (out/'aermap.inp').write_text(inp,encoding='cp1252')
    guardar_json(out/'manifest.json',{'fuentes':str(Path(sources_csv).resolve()),'fuentes_sha256':sha256(sources_csv),
       'dem':str(dem),'dem_sha256':sha256(dem),'ancho_LINE_m':width if width is not None else 'columna ancho_m por fuente','n_fuentes':len(sources),
       'alcance':'Extracción sólo de cotas de fuentes; no contiene receptores ni ejecuta AERMOD.'})

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fuentes',required=True);p.add_argument('--dem',required=True)
    p.add_argument('--salida',required=True)
    group=p.add_mutually_exclusive_group();group.add_argument('--ancho',type=float);group.add_argument('--ancho-por-fuente',action='store_true')
    a=p.parse_args();preparar(a.fuentes,a.dem,a.salida,None if a.ancho_por_fuente else (3 if a.ancho is None else a.ancho))

if __name__=='__main__':main()
