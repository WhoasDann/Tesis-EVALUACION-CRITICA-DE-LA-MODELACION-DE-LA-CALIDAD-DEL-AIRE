"""WRF read-only extraction at station, MMIF column and four receptors.
Run with the existing wrf_env Python; no model execution or source-file mutation.
"""
from pathlib import Path
import sys,json,hashlib
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from netCDF4 import Dataset,chartostring
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[2]
OLD=Path('/archivo/usuario/Documents/Codex/2026-10-08/hem')
OUT=ROOT/'outputs/Cierre_cientifico_2026-11-05/Transferencia_WRF'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(OLD/'outputs/Biblioteca_Tesis'))
from tesis.extraer_wrf import punto_malla
from tesis.validacion import bilineal,rotar_a_tierra
P=ROOT/'outputs/Seleccion_adversa_2026-11-04/Contraste_ternas_observadas'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str),encoding='utf-8')

design=read(P/'Diseno.json')
days={s:sorted(set(design['civil_days'][s])|{p['source_day'] for p in design['prototypes'] if p['season']==s}) for s in ['VERANO','INVIERNO']}
hrs=pd.read_csv(ROOT/'outputs/Cierre_cientifico_2026-11-05/Horas_pareadas_con_meteorologia.csv')
fichas=pd.read_csv(ROOT/'outputs/Cierre_cientifico_2026-11-05/Fichas_cuatro_receptores.csv')
profile_times={s:set() for s in days}
for q in fichas[fichas.pollutant.eq('MP10')].itertuples():
    g=hrs[(hrs.season==q.season)&(hrs.day==q.day)&(hrs.scenario==q.scenario)&(hrs.receptor==q.receptor)&(hrs.pollutant=='MP10')]
    for t in pd.to_datetime(g.nlargest(3,'delta').fin_LST):profile_times[q.season].add(t+pd.Timedelta(hours=3 if q.season=='VERANO' else 4))
for day in ['2017-06-28','2017-07-09']:
    g=hrs[(hrs.season=='INVIERNO')&(hrs.day==day)&(hrs.scenario=='OBS_U')&(hrs.receptor=='Los Bronces')&(hrs.pollutant=='MP10')]
    for t in pd.to_datetime(g.nlargest(3,'delta').fin_LST):profile_times['INVIERNO'].add(t+pd.Timedelta(hours=4))
protocol=dict(created_utc=datetime.now(timezone.utc).isoformat(),scope='Existing WRF snapshots; retrospective diagnostic, no new dispersion or parameter fitting.',
 days=days,profile_times_UTC={s:sorted(map(str,t)) for s,t in profile_times.items()},
 points=['Estacion_PC','Columna_MMIF','Los Bronces','Piedra Carvajal','Sulfatos','La Paloma'],
 methods=['Surface comparison at matching WRF instants: T2 and earth-relative U10/V10.',
 'MMIF exact cell: Python x=42,y=43, equivalent I=43,J=44; station/receptors: bilinear rotation-before-interpolation.',
 'Observed instant :49: interpolate bracketing hourly WRF states to original time under H-CIVIL; do not shift to optimize scores.',
 'Original winter selection uses previously audited XTIME nominal-hour mapping (<=10 s), preserving actual offsets.',
 'Vertical wind: destagger, rotate at nodes, interpolate in AGL height at nodes then horizontally; no extrapolation.',
 'No admission threshold chosen from concentration. Report spatial contrasts and incomplete evidence; MAE improvement is not an admission criterion.'],
 standard_profile_heights_m=[50,100,250,500,1000],source_WRF_modified=False,models_run=0,
 reference='https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/output.html')
if (OUT/'Protocolo.json').exists():
    old=read(OUT/'Protocolo.json');assert old['days']==protocol['days'] and old['profile_times_UTC']==protocol['profile_times_UTC']
else:dump('Protocolo.json',protocol)
assert not (OUT/'Recepcion_extraccion.json').exists(),'Extraction already complete; use analysis without rerunning.'
coords={'Los Bronces':(380148,6331485),'Piedra Carvajal':(381128,6323667),'Sulfatos':(384254,6324494),'La Paloma':(381759,6327947)}
utm_to_ll=Transformer.from_crs(32719,4326,always_xy=True)
ll_to_utm=Transformer.from_crs(4326,32719,always_xy=True)
surfaces=[];profiles=[];sources=[];points_meta=[]
for season in days:
    folder=Path('D:/Tesis_Dan/wrfoutVer' if season=='VERANO' else 'D:/Tesis_Dan/wrfoutInv')
    desired=set()
    for day in days[season]:
        start=pd.Timestamp(day,tz='America/Santiago').tz_convert('UTC').tz_localize(None)
        end=(pd.Timestamp(day)+pd.Timedelta(days=1)).tz_localize('America/Santiago').tz_convert('UTC').tz_localize(None)
        desired.update(pd.date_range(start,end,freq='h'))
    file_index=[]
    if season=='INVIERNO':
        selection=read(OLD/'outputs/BASE_invierno_2026-10-24/Seleccion_WRF.json')
        for r in selection['archivos']:
            times=pd.to_datetime(r['times_exportados'],format='%Y-%m-%d_%H:%M:%S')
            chosen=[(i,t) for i,t in zip(r['indices_seleccionados'],times) if t in desired]
            if chosen:file_index.append((folder/r['archivo'],chosen,r))
    else:
        for path in sorted(folder.glob('wrfout_d03_*')):
            # Filename narrows I/O only; Times still verifies exact indices below.
            day=pd.Timestamp(path.name[11:21])
            if not any(day<=t<day+pd.Timedelta(days=2) for t in desired):continue
            with Dataset(path) as n:ts=pd.to_datetime(chartostring(n['Times'][:]).tolist(),format='%Y-%m-%d_%H:%M:%S')
            chosen=[(i,t) for i,t in enumerate(ts) if t in desired]
            if chosen:file_index.append((path,chosen,None))
    points=None;seen=set()
    for path,chosen,sel in file_index:
        st=path.stat()
        if sel:assert st.st_size==sel['bytes'] and st.st_mtime_ns==sel['mtime_ns']
        with Dataset(path) as n:
            n.set_auto_mask(False)
            assert int(n.GRID_ID)==3 and int(n.MAP_PROJ)==1
            lat=np.asarray(n['XLAT'][0],float);lon=np.asarray(n['XLONG'][0],float);hgt=np.asarray(n['HGT'][0],float)
            if points is None:
                points={'Estacion_PC':{'lon':-70.27406281695315,'lat':-33.22172401465386},
                        'Columna_MMIF':{'lon':lon[43,42],'lat':lat[43,42],'fx':42.,'fy':43.}}
                for name,(x,y) in coords.items():
                    lo,la=utm_to_ll.transform(x,y);points[name]={'lon':lo,'lat':la}
                for name,p in points.items():
                    if 'fx' not in p:p['fx'],p['fy']=punto_malla(n,p['lon'],p['lat'])
                    p['x_utm'],p['y_utm']=ll_to_utm.transform(p['lon'],p['lat'])
                    p['HGT_m']=float(bilineal(hgt,p['fx'],p['fy']))
                    points_meta.append(dict(season=season,point=name,**p,DX=float(n.DX),DY=float(n.DY)))
                np.savez_compressed(OUT/f'Malla_{season}.npz',lat=lat,lon=lon,HGT=hgt)
            else:
                assert abs(lat[43,42]-points['Columna_MMIF']['lat'])<1e-7
                assert abs(lon[43,42]-points['Columna_MMIF']['lon'])<1e-7
            indices=[i for i,t in chosen]
            # Small surface fields are read once per file and hashed independently.
            names=['T2','U10','V10','COSALPHA','SINALPHA','PBLH','PSFC','HFX','UST']
            arr={k:np.asarray(n[k][indices],float) for k in names}
            ue,ve=rotar_a_tierra(arr['U10'],arr['V10'],arr['COSALPHA'],arr['SINALPHA'])
            stored_times=chartostring(n['Times'][:]).tolist()
            xtbase=pd.Timestamp(str(n['XTIME'].units).split('since ')[1].replace('_',' '))
            times_audit=[]
            for j,(i,t) in enumerate(chosen):
                assert t not in seen,(season,t);seen.add(t)
                actual=xtbase+pd.Timedelta(minutes=float(n['XTIME'][i]));offset=(actual-t).total_seconds()
                assert abs(offset)<=10,(path,t,actual)
                times_audit.append(dict(index=i,nominal_UTC=str(t),Times=stored_times[i],XTIME_UTC=str(actual),offset_seconds=offset))
                for name,p in points.items():
                    x,y=p['fx'],p['fy'];u=float(bilineal(ue[j],x,y));v=float(bilineal(ve[j],x,y))
                    row=dict(season=season,point=name,time_UTC=t,T2_C=float(bilineal(arr['T2'][j],x,y)-273.15),
                        u10=u,v10=v,WS10=float(np.hypot(u,v)),WD10=float(np.degrees(np.arctan2(-u,-v))%360),
                        HGT_m=p['HGT_m'],PBLH_m=float(bilineal(arr['PBLH'][j],x,y)),PSFC_Pa=float(bilineal(arr['PSFC'][j],x,y)),
                        HFX_W_m2=float(bilineal(arr['HFX'][j],x,y)),UST_m_s=float(bilineal(arr['UST'][j],x,y)),
                        source_file=path.name,source_index=i,actual_offset_s=offset)
                    surfaces.append(row)
                if t in profile_times[season]:
                    # Whole 3D frame read only for preselected diagnostic hours.
                    fields={k:np.asarray(n[k][i],float) for k in ['PH','PHB','T','P','PB','U','V']}
                    field_hash={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in fields.items()}
                    zf=(fields['PH']+fields['PHB'])/9.81-hgt[None,:,:]
                    zm=(zf[1:]+zf[:-1])/2
                    ug=(fields['U'][:,:,:-1]+fields['U'][:,:,1:])/2
                    vg=(fields['V'][:,:-1,:]+fields['V'][:,1:,:])/2
                    u,v=rotar_a_tierra(ug,vg,arr['COSALPHA'][j][None,:,:],arr['SINALPHA'][j][None,:,:])
                    theta=fields['T']+300.;pres=fields['P']+fields['PB'];temp=theta*(pres/100000.)**(287./1004.)-273.15
                    assert np.isfinite(temp).all() and np.all(np.diff(zm,axis=0)>0)
                    for name,p in points.items():
                        ix,iy=int(p['fx']),int(p['fy']);wx,wy=p['fx']-ix,p['fy']-iy
                        nodes=[(iy,ix,(1-wx)*(1-wy)),(iy,ix+1,wx*(1-wy)),(iy+1,ix,(1-wx)*wy),(iy+1,ix+1,wx*wy)]
                        for z in protocol['standard_profile_heights_m']:
                            vals={k:0. for k in ['u','v','T_C','theta_K']}
                            for yy,xx,w in nodes:
                                if w==0:continue
                                assert zm[0,yy,xx]<=z<=zm[-1,yy,xx]
                                for k,a in [('u',u),('v',v),('T_C',temp),('theta_K',theta)]: vals[k]+=w*np.interp(z,zm[:,yy,xx],a[:,yy,xx])
                            profiles.append(dict(season=season,point=name,time_UTC=t,z_AGL_m=z,**vals))
                    times_audit[-1]['profile_frame_float64_sha256']=field_hash
            sources.append(dict(season=season,path=str(path),bytes=st.st_size,mtime_ns=st.st_mtime_ns,
                slices=times_audit,surface_array_float64_sha256={k:hashlib.sha256(a.tobytes()).hexdigest() for k,a in arr.items()},
                note='Hashes cover extracted arrays, not the full native file. Source opened read-only.'))
        print(f'{season}: {path.name}, {len(chosen)} instantes',flush=True)
    assert seen==desired,(season,len(seen),len(desired),sorted(desired-seen))
surface=pd.DataFrame(surfaces).sort_values(['season','point','time_UTC'])
profile=pd.DataFrame(profiles).sort_values(['season','point','time_UTC','z_AGL_m'])
assert not surface.duplicated(['season','point','time_UTC']).any()
assert not profile.duplicated(['season','point','time_UTC','z_AGL_m']).any()
surface.to_csv(OUT/'WRF_superficie_seis_puntos.csv',index=False)
profile.to_csv(OUT/'WRF_perfiles_seis_puntos.csv',index=False)
pd.DataFrame(points_meta).to_csv(OUT/'Ubicacion_puntos.csv',index=False)
dump('Trazabilidad_WRF.json',sources)
dump('Recepcion_extraccion.json',{'status':'EXTRACTED_CHECKED','time_utc':datetime.now(timezone.utc).isoformat(),
     'surface_rows':len(surface),'profile_rows':len(profile),'source_files':len(sources),'points':6,
     'dates':days,'profile_hours':{s:len(t) for s,t in profile_times.items()},'models_run':0,
     'source_files_modified':False,'source_hash_kind':'selected arrays; source size/mtime; not full-file hash',
     'files':[{'name':p.name,'sha256':digest(p)} for p in [OUT/'WRF_superficie_seis_puntos.csv',OUT/'WRF_perfiles_seis_puntos.csv',OUT/'Ubicacion_puntos.csv']]})
print(json.dumps(read(OUT/'Recepcion_extraccion.json'),ensure_ascii=False),flush=True)
