"""Extrae T2 y viento terrestre por interpolación bilineal de WRF d03 LCC."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from netCDF4 import Dataset, chartostring
from pyproj import CRS, Transformer
from .validacion import bilineal,rotar_a_tierra
from .comun import salida_nueva,guardar_json,sha256,unique_times

def punto_malla(nc,lon,lat):
    if int(nc.MAP_PROJ)!=1:raise ValueError('Sólo se verificó la proyección Lambert de este proyecto.')
    crs=CRS.from_proj4(f'+proj=lcc +lat_1={nc.TRUELAT1} +lat_2={nc.TRUELAT2} +lat_0={nc.CEN_LAT} +lon_0={nc.STAND_LON} +a=6370000 +b=6370000 +units=m')
    tr=Transformer.from_crs(CRS.from_proj4('+proj=longlat +a=6370000 +b=6370000'),crs,always_xy=True)
    lats=np.asarray(nc['XLAT'][0]);lons=np.asarray(nc['XLONG'][0])
    x0,y0=tr.transform(float(lons[0,0]),float(lats[0,0]));x,y=tr.transform(lon,lat)
    fx,fy=(x-x0)/nc.DX,(y-y0)/nc.DY
    # Prueba independiente de dos esquinas proyectadas contra DX/DY.
    xc,yc=tr.transform(float(lons[-1,-1]),float(lats[-1,-1]))
    if abs((xc-x0)/nc.DX-(lons.shape[1]-1))>.05 or abs((yc-y0)/nc.DY-(lons.shape[0]-1))>.05:
        raise ValueError('La malla no coincide con la proyección y el espaciado declarados.')
    return float(fx),float(fy)

def extraer(folder,destination,*,lon,lat,spinup_days=20,limit=None,hash_inputs=False,
            files_override=None,inicio_utc=None,fin_utc=None):
    # El piloto inventaría/valida los archivos antes de pasar esta lista explícita.
    files=sorted(Path(p) for p in files_override) if files_override is not None else sorted(
        p for p in Path(folder).glob('wrfout_d03_*') if p.is_file() and p.suffix in ('','.nc'))
    if spinup_days<0:raise ValueError('Spin-up negativo.')
    first=pd.Timestamp(inicio_utc) if inicio_utc is not None else None
    last=pd.Timestamp(fin_utc) if fin_utc is not None else None
    if any(x is not None and x.tz is not None for x in (first,last)):
        raise ValueError('Límites de extracción expresados como UTC sin sufijo de zona.')
    if first is not None and last is not None and first>=last:raise ValueError('Ventana UTC inválida.')
    if limit is not None:files=files[:limit]
    if not files:raise FileNotFoundError('No se encontraron wrfout d03 sin extensión.')
    records=[];inputs=[];starts=set();grid=None
    for path in files:
        with Dataset(path) as nc:
            start=pd.Timestamp(nc.SIMULATION_START_DATE.replace('_',' '));starts.add(str(start))
            if len(starts)!=1:raise ValueError('Se mezclaron integraciones WRF distintas.')
            if int(nc.GRID_ID)!=3:raise ValueError('GRID_ID no es d03.')
            fx,fy=punto_malla(nc,lon,lat)
            current=(round(fx,5),round(fy,5),float(nc.DX),float(nc.DY),tuple(nc['T2'].shape[-2:]))
            if grid is not None and current!=grid:raise ValueError('La malla cambia entre archivos.')
            grid=current
            hgt=float(bilineal(nc['HGT'][0],fx,fy))
            times=pd.to_datetime(chartostring(nc['Times'][:]).tolist(),format='%Y-%m-%d_%H:%M:%S')
            for i,date in enumerate(times):
                # SIMULATION_START_DATE permanece válido a través de reinicios; START_DATE no.
                if date<start+pd.Timedelta(days=spinup_days):continue
                if first is not None and date<first:continue
                if last is not None and date>=last:continue
                c=np.asarray(nc['COSALPHA'][0 if nc['COSALPHA'].shape[0]==1 else i])
                s=np.asarray(nc['SINALPHA'][0 if nc['SINALPHA'].shape[0]==1 else i])
                u,v=rotar_a_tierra(np.ma.asarray(nc['U10'][i]).filled(np.nan),np.ma.asarray(nc['V10'][i]).filled(np.nan),c,s)
                records.append({'fecha_wrf_utc':date,'T2_C':float(bilineal(nc['T2'][i],fx,fy)-273.15),
                                'u_earth_m_s':float(bilineal(u,fx,fy)),'v_earth_m_s':float(bilineal(v,fx,fy)),
                                'HGT_bilineal_m':hgt,'x_fraccion':fx,'y_fraccion':fy,'archivo':path.name})
            inputs.append({'path':str(path.resolve()),'bytes':path.stat().st_size,'mtime_ns':path.stat().st_mtime_ns,
                           'sha256':sha256(path) if hash_inputs else None})
    frame=pd.DataFrame(records)
    if frame.empty:raise ValueError('No quedan datos después del spin-up explícito.')
    unique_times(frame,'fecha_wrf_utc');frame=frame.sort_values('fecha_wrf_utc')
    dest=salida_nueva(destination);frame.to_csv(dest/'wrf_estacion.csv',index=False,encoding='utf-8-sig')
    guardar_json(dest/'manifest.json',{'lon':lon,'lat':lat,'spinup_dias':spinup_days,'integration_start':list(starts),
        'n_horas':len(frame),'primera_utc':str(frame.fecha_wrf_utc.min()),'ultima_utc':str(frame.fecha_wrf_utc.max()),
        'direccion':'componentes rotadas a Tierra antes de interpolar','fuentes':inputs,
        'inicio_filtro_utc':str(first) if first is not None else None,
        'fin_filtro_utc_exclusivo':str(last) if last is not None else None,
        'hashes_completos':hash_inputs,'uso':'Extracción; verificar cobertura y representatividad antes de calibrar.'})
    print(f'{len(frame)} horas extraídas de {len(files)} archivos d03.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--wrf-dir',required=True);p.add_argument('--salida',required=True)
    p.add_argument('--lon',required=True,type=float);p.add_argument('--lat',required=True,type=float)
    p.add_argument('--spinup-dias',type=int,default=20);p.add_argument('--hash-inputs',action='store_true')
    a=p.parse_args()
    if a.spinup_dias<0:raise ValueError('Spin-up negativo.')
    extraer(a.wrf_dir,a.salida,lon=a.lon,lat=a.lat,spinup_days=a.spinup_dias,hash_inputs=a.hash_inputs)

if __name__=='__main__':main()
