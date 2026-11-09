"""Prepara BASE estacional con geometría existente; originales y entregas intactos."""
from pathlib import Path
import json
import os
import shutil
import sys
import argparse
import numpy as np
import pandas as pd
from netCDF4 import Dataset, chartostring

ROOT=Path(__file__).resolve().parents[1];O=ROOT/'outputs'
OUT=O/'BASE_verano_2026-10-21'
OLD=O/'Verano_WRF_cierre_efectivo_2026-10-13'
PHYS=O/'Diagnostico_fuentes125_2026-10-16'
JOINT=O/'Convergencia_conjunta_2026-10-16'
CHAIN=O/'Ensayo_7dias_20161221_2026-10-14'
sys.path.insert(0,str(O/'Biblioteca_Tesis'))
from tesis.comun import sha256,guardar_json
from tesis.preprocesadores import LAYERS
from tesis.receptores import leer_aermap
from tesis.geometria_line import XY

START=pd.Timestamp('2016-12-21');END=pd.Timestamp('2017-03-20 17:00')
AUX=pd.Timestamp('2016-12-20')
KEEP='Times XLAT XLONG HGT COSALPHA SINALPHA U V W PH PHB P PB T QVAPOR QCLOUD SMOIS LU_INDEX MU MUB RAINC RAINNC TSK PBLH SWDOWN GLW UST U10 V10 SST T2 Q2 PSFC HFX LH ZNW ZNU C1H C2H CLDFRA QICE ZNT ALBEDO LAI RMOL THM TH2 XTIME'.split()
OPTIONAL={'ZNT','RMOL','CLDFRA','QICE','ALBEDO','LAI'}

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def record(p):return dict(path=str(Path(p).resolve()),sha256=sha256(p))
def verify(entries):
    for r in entries:
        if sha256(r['path'])!=r['sha256']:raise ValueError('Archivo modificado: '+r['path'])

def prepare():
    if OUT.exists():raise FileExistsError('Entrega existente; no sobrescribir')
    inv=read(OLD/'inventario_archivos.json')
    required=pd.date_range(AUX+pd.Timedelta(hours=3),END+pd.Timedelta(hours=3),freq='h')
    selected=[];dates=[]
    for item in inv:
        ts=pd.to_datetime(item['times'])
        ix=np.flatnonzero(ts.isin(required))
        if not len(ix):continue
        p=Path(item['path']);st=p.stat()
        assert st.st_size==item['bytes'] and st.st_mtime_ns==item['mtime_ns'],p
        selected.append(dict(**item,indices_seleccionados=ix.tolist()))
        dates.extend(ts[ix])
    assert pd.DatetimeIndex(dates).equals(required) and len(required)==2178
    # La lista de variables y exportación procede del ensayo que sí leyó MMIF.
    estimate=len(required)*504841496/24
    assert shutil.disk_usage(ROOT).free > estimate+8*1024**3,'Espacio insuficiente para BASE y resultados'
    prior=read(PHYS/'Entrega.json')['archivos']+read(PHYS/'Terreno.json')['archivos']+read(PHYS/'Verificacion_cierre_independiente.json')['archivos']+read(JOINT/'Entrega.json')['archivos']
    sources=[PHYS/'Fuentes125/fuentes.csv',PHYS/'Fuentes125/fuentes_aermod.inc',
        JOINT/'Comunes/cotas_union.csv',JOINT/'Comunes/membresia_completa.csv',JOINT/'Comunes/zonas_UTM19S.geojson']
    known={str(Path(r['path']).resolve()):r for r in prior}
    for p in sources:
        assert str(p.resolve()) in known,p
        verify([known[str(p.resolve())]])
    OUT.mkdir()
    for name in ['Comunes','WRF_BASE','Binarios','Meteorologia','Emisiones','Controles','Casos']:(OUT/name).mkdir()
    for p in sources:shutil.copy2(p,OUT/'Comunes'/p.name)
    cotas=pd.read_csv(OUT/'Comunes/cotas_union.csv')
    members=pd.read_csv(OUT/'Comunes/membresia_completa.csv')
    assert len(cotas)==6295 and not cotas.duplicated(['x_m','y_m']).any()
    assert set(map(tuple,cotas[['x_m','y_m']].to_numpy()))==set(map(tuple,members[['x_m','y_m']].to_numpy()))
    assert not members.duplicated(['grupo','x_m','y_m']).any()
    (OUT/'Comunes/receptores.inc').write_text(''.join(f'RE DISCCART {r.x_m:.2f} {r.y_m:.2f} {r.elev_m:.2f} {r.hill_m:.2f}\n' for r in cotas.itertuples()),encoding='ascii')
    assert len(leer_aermap(OUT/'Comunes/receptores.inc'))==6295
    for group,xy in {'PCAR':(381128,6323667),'LBCEN':(380148,6331485),'SULF':(384254,6324494),'PALP':(381759,6327947)}.items():
        a=members[members.grupo==group]
        assert len(a)==1 and tuple(a[['x_m','y_m']].iloc[0])==xy
    assert members[members.grupo=='GENERAL'].shape[0]==6295
    for name in ['mmif_4.1.1.exe','aermet.exe','aermod.exe']:shutil.copy2(CHAIN/'Binarios'/name,OUT/'Binarios'/name)
    hours=pd.date_range(START,END,freq='h',inclusive='left')
    calendar=pd.DataFrame({'fecha_local':hours.normalize()}).groupby('fecha_local').size().rename('horas').reset_index()
    calendar['dia_completo']=calendar.horas==24
    calendar.to_csv(OUT/'Calendario.csv',index=False,encoding='utf-8-sig')
    plan=dict(fecha='2026-10-21',inicio=str(START),fin_exclusivo=str(END),horas=2153,
        dias_completos=89,horas_dia_parcial=17,inicio_auxiliar=str(AUX),horas_MMIF=2177,
        instantes_WRF=2178,fuentes=12263,receptores=6295,metodo_mezcla='WRF',reloj='UTC-3 fijo provisional',
        superficie='MMIF estacional común; nunca copiar Bowen de un ensayo corto. Diciembre/ marzo son fracciones de mes disponibles.',
        auxiliares='Un día previo. Sin día posterior por fin disponible. Sólo objetivo posterior a20d spinup. No rellenar.',
        geometria='Fuentes físicas12,5m y unión6295 receptores existentes; sin nuevos AERMAP/refinamientos.',
        limites='Máximos de nodos muestreados, no continuo ni convergencia espacial acreditada. Aportes sin fondo.',
        parciales='20mar17h: media del período disponible y máximo1h; nunca media24h ni completar ceros.',
        fuentes_WRF=selected,variables_exportadas=KEEP,modelo_discrepancias_aplicado=False,
        ejecucion='Preprocesamiento estacional y SETUP primero. Dispersión en lotes diarios recuperables posteriores.',
        observaciones='Ningún modelo ajustado para el BASE. Candidato meteorológico se evalúa por separado.',
        entradas=[record(p) for p in [OLD/'inventario_archivos.json',*sources]])
    guardar_json(OUT/'Plan.json',plan)
    paths=[OUT/'WRF_BASE'/r['archivo'] for r in selected]
    mmif='\n'.join(['START 2016 12 20 01','STOP 2017 03 20 17','TIMEZONE -3',*[f'INPUT "{p}"' for p in paths],
        'POINT LL -33.15632248 -70.29452515','LAYERS MID '+' '.join(map(str,LAYERS)),
        'AER_MIN_SPEED 0','AER_USE_NEW T','AER_MIXHT WRF','FSL_INTERVAL 12',
        'OUTPUT AERMET BAT met.bat','OUTPUT AERMET ONSITE onsite.dat','OUTPUT AERMET FSL upper.dat',
        'OUTPUT AERMET AERSFC surface.dat','OUTPUT AERMET USEFUL met.useful.txt',''])
    (OUT/'Meteorologia/mmif.inp').write_text(mmif,encoding='ascii')
    guardar_json(OUT/'Preparacion.json',dict(estado='PLAN_PREPARADO_EXPORTACION_PENDIENTE',archivos=[record(OUT/'Plan.json'),record(__file__)]))
    print(f'Plan fijado: {len(selected)} archivos WRF,2178 instantes,12263 fuentes y6295 receptores.',flush=True)

def export():
    verify(read(OUT/'Preparacion.json')['archivos'])
    plan=read(OUT/'Plan.json')
    cache=OUT/'Exportacion_parcial.json';items=read(cache) if cache.exists() else []
    saved={Path(r['original']['path']).name:r for r in items}
    earlier={Path(r['original']).name:r for r in read(CHAIN/'QA_WRF.json')['archivos']}
    for item in plan['fuentes_WRF']:
        name=item['archivo'];src=Path(item['path']);dst=OUT/'WRF_BASE'/name
        if name in saved:
            verify([saved[name]['exportado']]);continue
        assert not dst.exists(),'Exportación sin recepción: '+str(dst)
        assert sha256(src)==item['sha256'],'Original WRF cambiado'
        ix=item['indices_seleccionados'];s=slice(ix[0],ix[-1]+1)
        assert ix==list(range(ix[0],ix[-1]+1))
        print('Exportando/verificando '+name,flush=True)
        reused=False
        old=earlier.get(name)
        if old and [pd.Timestamp(t).isoformat() for t in np.array(item['times'])[ix]]==old['Times']:
            oldpath=CHAIN/'WRF/BASE'/name
            assert sha256(oldpath)==old['BASE_sha256']
            os.link(oldpath,dst);reused=True
        with Dataset(src) as n:
            n.set_auto_mask(False)
            missing=set(KEEP)-set(n.variables);assert not missing-OPTIONAL
            assert abs(float(n['XLAT'][0,43,42])+33.15632248)<1e-5
            assert abs(float(n['XLONG'][0,43,42])+70.29452515)<1e-5
            assert abs(float(n['HGT'][0,43,42])-3469.60400390625)<.01
            assert int(n['LU_INDEX'][0,43,42]) not in (int(n.ISWATER),int(n.ISLAKE))
            if not reused:
                with Dataset(dst,'w',format='NETCDF3_64BIT_OFFSET') as d:
                    d.setncatts({a:n.getncattr(a) for a in n.ncattrs()})
                    for key,dim in n.dimensions.items():d.createDimension(key,None if key=='Time' else len(dim))
                    for key in KEEP:
                        if key not in n.variables:continue
                        v=n[key];w=d.createVariable(key,v.dtype,v.dimensions,fill_value=getattr(v,'_FillValue',False))
                        w.setncatts({a:v.getncattr(a) for a in v.ncattrs() if a!='_FillValue'})
                    for key in d.variables:
                        v=n[key];d[key][:]=v[s] if 'Time' in v.dimensions else v[:]
            with Dataset(dst) as d:
                d.set_auto_mask(False)
                assert set(d.variables)==set(KEEP)-missing
                for key,v in d.variables.items():
                    expected=n[key][s] if 'Time' in v.dimensions else n[key][:]
                    assert np.array_equal(expected,v[:],equal_nan=v.dtype.kind=='f'),key
                    if v.dtype.kind=='f':assert np.isfinite(v[:]).all(),key
                q=np.asarray(d['Q2'][:]);qv=np.asarray(d['QVAPOR'][:])
                near=q[:,42:45,41:44]
                p=np.asarray(d['P'][:])+np.asarray(d['PB'][:])
                qa=dict(Q2_min_punto=float(q[:,43,42].min()),Q2_min_3x3=float(near.min()),
                    Q2_negativas_dominio=int((q<0).sum()),QVAPOR_min_3x3=float(qv[:,:,42:45,41:44].min()),
                    QVAPOR_negativas_dominio=int((qv<0).sum()),presion_min_Pa=float(p.min()),
                    T2_punto_min_K=float(d['T2'][:,43,42].min()),T2_punto_max_K=float(d['T2'][:,43,42].max()),
                    PBLH_punto_min_m=float(d['PBLH'][:,43,42].min()))
                assert qa['Q2_min_3x3']>=0 and qa['QVAPOR_min_3x3']>=0 and qa['presion_min_Pa']>0,qa
                assert 150<qa['T2_punto_min_K']<=qa['T2_punto_max_K']<350 and qa['PBLH_punto_min_m']>0,qa
                stamps=list(chartostring(d['Times'][:]))
        entries=dict(original=dict(path=str(src),sha256=item['sha256']),exportado=record(dst),
            bytes=dst.stat().st_size,indices=ix,Times=stamps,QA=qa,enlace_inmutable_previo=reused)
        items.append(entries);guardar_json(cache,items)
    actual=[pd.Timestamp(t.replace('_',' ')) for row in items for t in row['Times']]
    assert pd.DatetimeIndex(actual).equals(pd.date_range(AUX+pd.Timedelta(hours=3),END+pd.Timedelta(hours=3),freq='h'))
    guardar_json(OUT/'Exportacion.json',dict(estado='BASE_NETCDF3_VERIFICADO',archivos=items,instantes=len(actual),
        nota='Campos exportados idénticos al original; Q2 externa negativa documentada, celda y3x3 válidos. No valida todo el estado atmosférico.',
        bytes_logicos=sum(r['bytes'] for r in items),bytes_nuevos=sum(r['bytes'] for r in items if not r['enlace_inmutable_previo'])))
    print('BASE estacional exportado y verificado.',flush=True)

def emissions():
    verify(read(OUT/'Preparacion.json')['archivos'])
    paths=[O/'Configuracion_fuentes_v1/eje/fuentes_central.csv',O/'Convergencia_espacial_2026-10-15/Fuentes50/fuentes.csv',
        O/'Refinamiento_fuentes25_2026-10-16/Fuentes25/fuentes.csv',PHYS/'Fuentes125/fuentes.csv']
    tables=[pd.read_csv(p) for p in paths]
    areas=[]
    for table in tables:
        xy=table[XY].to_numpy().round(2)
        areas.append(np.hypot(xy[:,2]-xy[:,0],xy[:,3]-xy[:,1])*table.ancho_m.to_numpy())
    stages=[]
    for k in range(1,4):
        parent=tables[k-1].set_index('id_fuente_aermod');child=tables[k]
        ix=parent.index.get_indexer(child.id_fuente_padre);assert (ix>=0).all()
        assert set(ix)==set(range(len(parent)))
        stages.append(ix)
    ids=tables[-1].id_fuente_aermod.tolist();assert ids==[f'Q{i:06d}' for i in range(1,12264)]
    cal=pd.read_csv(OUT/'Calendario.csv',parse_dates=['fecha_local'])
    rounding=lambda a:np.array([float(f'{v:.12E}') for v in a])
    summaries={};files=[]
    for pol in ['MP10','MP25']:
        daily_path=O/f'Configuracion_fuentes_v1/eje/emisiones_segmentadas_{pol}.csv'
        daily=pd.read_csv(daily_path);col='emision_'+pol.lower()+'_g_dia'
        assert not daily.duplicated(['fecha','id_fuente_aermod']).any()
        total=0.;worst=0.;entries=[]
        for row in cal.itertuples():
            day=row.fecha_local;folder=OUT/'Emisiones'/day.strftime('%Y%m%d');folder.mkdir(exist_ok=True)
            dest=folder/(pol+'.emi');assert not dest.exists(),dest
            part=daily[daily.fecha==day.strftime('%Y-%m-%d')].set_index('id_fuente_aermod').reindex(tables[0].id_fuente_aermod)
            assert len(part)==1651 and part[col].notna().all()
            q=rounding(part[col].to_numpy()/(86400*areas[0]))
            expected_mass=q@areas[0]*3600*row.horas
            for k,ix in enumerate(stages,1):
                child=rounding(q[ix]*tables[k].factor_densidad.to_numpy())
                back=np.bincount(ix,weights=child*areas[k],minlength=len(q))
                np.testing.assert_allclose(back,q*areas[k-1],atol=1e-11,rtol=1e-10)
                worst=max(worst,float(np.abs(back-q*areas[k-1]).max()));q=child
            mass=q@areas[-1]*3600*row.horas
            assert np.isclose(mass,expected_mass,rtol=1e-10,atol=1e-6)
            total+=mass
            strings=[f'{source:<12s} {rate:.12E}\n' for source,rate in zip(ids,q)]
            with dest.open('w',encoding='ascii',newline='\n') as stream:
                for hour in range(1,row.horas+1):
                    prefix=f'SO HOUREMIS {day.year%100:02d} {day.month:2d} {day.day:2d} {hour:2d} '
                    stream.writelines(prefix+s for s in strings)
            entry=dict(**record(dest),horas=int(row.horas),filas=int(row.horas*len(ids)),masa_g=float(mass))
            entries.append(entry);files.append(entry)
            if day.day in (1,21):print(pol+': emisiones '+day.strftime('%Y-%m-%d'),flush=True)
        old=read(OLD/'Estado.json')['emisiones'][pol]['masa_periodo_g']
        assert np.isclose(total,old,rtol=1e-10,atol=1e-5),(pol,total,old)
        summaries[pol]=dict(masa_g=total,masa_entrega_estacional_previa_g=old,error_padre_hora_g_s=worst,archivos=entries)
    guardar_json(OUT/'Emisiones.json',dict(estado='MASA_ESTACIONAL_CONSERVADA',resumen=summaries,
        entradas=[record(p) for p in paths]+[record(O/f'Configuracion_fuentes_v1/eje/emisiones_segmentadas_{pol}.csv') for pol in ['MP10','MP25']],
        metodo='Misma cadenaL→N→P→Q, factores y redondeo12E de ensayos anteriores; masa padre/hora conservada.17h finales sin redistribución.'))
    print('Emisiones estacionales listas; 2153h por contaminante.',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('etapa',choices=['preparar','exportar','emisiones'])
    a=parser.parse_args();{'preparar':prepare,'exportar':export,'emisiones':emissions}[a.etapa]()
