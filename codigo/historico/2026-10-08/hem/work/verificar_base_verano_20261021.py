"""Comprueba insumos estacionales y prueba el contrato temporal sin ejecutar nativos."""
from pathlib import Path
import hashlib
import json
import tempfile
import numpy as np
import pandas as pd
import sys

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/BASE_verano_2026-10-21'
sys.path.insert(0,str(ROOT/'outputs/Biblioteca_Tesis'))
from tesis.comun import guardar_json,sha256
from tesis.receptores import leer_aermap
from ejecutar_base_verano_20261021 import met_qc,mmif_qc

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def record(p):return dict(path=str(Path(p).resolve()),sha256=sha256(p))

def emissions():
    new=pd.read_csv(OUT/'Comunes/fuentes.csv');xy=new[['x1_utm19s_m','y1_utm19s_m','x2_utm19s_m','y2_utm19s_m']].to_numpy().round(2)
    areas=np.hypot(xy[:,2]-xy[:,0],xy[:,3]-xy[:,1])*new.ancho_m.to_numpy()
    parents=pd.read_csv(ROOT/'outputs/Configuracion_fuentes_v1/eje/fuentes_central.csv')
    xy=parents[['x1_utm19s_m','y1_utm19s_m','x2_utm19s_m','y2_utm19s_m']].to_numpy().round(2)
    oldareas=np.hypot(xy[:,2]-xy[:,0],xy[:,3]-xy[:,1])*parents.ancho_m.to_numpy()
    index=pd.Index(parents.id_fuente_aermod).get_indexer(new.id_fuente_100m);assert (index>=0).all()
    inv=read(OUT/'Emisiones.json');results=[]
    for pol in ['MP10','MP25']:
        daily=pd.read_csv(ROOT/f'outputs/Configuracion_fuentes_v1/eje/emisiones_segmentadas_{pol}.csv')
        for entry in inv['resumen'][pol]['archivos']:
            p=Path(entry['path']);day=pd.Timestamp(p.parent.name);nh=entry['horas']
            assert (nh==24 and day<pd.Timestamp('2017-03-20')) or (nh==17 and day==pd.Timestamp('2017-03-20'))
            with p.open(encoding='ascii') as stream:first=[stream.readline() for _ in range(12263)]
            values=[];suffix=[]
            for line,source in zip(first,new.id_fuente_aermod):
                a=line.split();assert len(a)==8 and a[:2]==['SO','HOUREMIS']
                assert list(map(int,a[2:6]))==[day.year%100,day.month,day.day,1] and a[6]==source
                rate=float(a[7]);assert np.isfinite(rate) and rate>=0
                values.append(rate);suffix.append(f'{source:<12s} {rate:.12E}\n')
            expected=hashlib.sha256()
            for hour in range(1,nh+1):
                prefix=f'SO HOUREMIS {day.year%100:02d} {day.month:2d} {day.day:2d} {hour:2d} '
                expected.update(''.join(prefix+s for s in suffix).encode('ascii'))
            assert expected.hexdigest()==entry['sha256']==sha256(p),'Cambió hora/fuente/tasa: '+str(p)
            q=np.array(values)
            data=daily[daily.fecha==day.strftime('%Y-%m-%d')].set_index('id_fuente_aermod').reindex(parents.id_fuente_aermod)
            old=data['emision_'+pol.lower()+'_g_dia'].to_numpy()/86400
            actual=np.bincount(index,weights=q*areas,minlength=len(parents))
            np.testing.assert_allclose(actual,old,rtol=3e-10,atol=1e-11)
            mass=float(actual.sum()*3600*nh)
            np.testing.assert_allclose(mass,entry['masa_g'],rtol=1e-12,atol=1e-6)
            results.append(dict(contaminante=pol,dia=str(day.date()),horas=nh,filas=nh*12263,masa_g=mass,
                error_max_padre100m_g_s=float(np.abs(actual-old).max())))
        # Identidad de tasas con el diagnóstico previo para los siete días comunes.
        previous=ROOT/f'outputs/Diagnostico_fuentes125_2026-10-16/Fuentes125/{pol}.emi'
        seen=0
        with previous.open(encoding='ascii') as stream:
            for day in pd.date_range('2016-12-21',periods=7):
                now=OUT/'Emisiones'/day.strftime('%Y%m%d')/(pol+'.emi')
                with now.open(encoding='ascii') as check:
                    for line in check:
                        earlier=stream.readline();a=line.split();b=earlier.split()
                        assert a[:7]==b[:7]
                        assert abs(float(a[7])-float(b[7]))<=max(1e-18,2e-12*abs(float(b[7])))
                        seen+=1
            assert stream.read()==''
        assert seen==12263*168
    frame=pd.DataFrame(results);frame.to_csv(OUT/'Recepcion_emisiones.csv',index=False,encoding='utf-8-sig')
    guardar_json(OUT/'Recepcion_emisiones.json',dict(estado='180_ARCHIVOS_EMISIONES_VERIFICADOS',
        horas_por_contaminante=2153,fuentes=12263,filas_por_contaminante=12263*2153,
        error_max_padre100m_g_s=float(frame.error_max_padre100m_g_s.max()),
        coincidencia_7dias_previos=True,archivos=[record(OUT/'Recepcion_emisiones.csv'),record(OUT/'Emisiones.json'),record(__file__)]))
    print('Recepción:180 archivos, masa por padre yhora, y tasas de7d previos verificadas.',flush=True)

def tests():
    # Usar met real del ensayo previo; el nuevo lector estacional debe coincidir
    # y rechazar un hueco. No nativos ni reproducción del algoritmo de escritura.
    state=read(ROOT/'outputs/Meteorologia_comun_2026-10-20/Preprocesamiento.json')
    path=Path(next(r['path'] for r in state['BASE']['archivos'] if Path(r['path']).name.lower()=='met.sfc')).parent
    with tempfile.TemporaryDirectory(prefix='qc_verano_',dir=ROOT/'work') as temp:
        dest=Path(temp)
        sfc=(path/'met.SFC').read_text(encoding='ascii');pfl=(path/'met.PFL').read_text(encoding='ascii')
        (dest/'met.SFC').write_text(sfc,encoding='ascii');(dest/'met.PFL').write_text(pfl,encoding='ascii')
        plan=dict(inicio='2016-12-21',inicio_auxiliar='2016-12-20',fin_exclusivo='2016-12-24')
        mmif=mmif_qc(path,plan);assert mmif['horas']==96
        qc=met_qc(dest,plan);assert qc['horas_objetivo']==72 and qc['horas_auxiliares']==96
        # Ensayo de final parcial recortando entrada a17h; no completar a24.
        for kind,raw in [('SFC',sfc),('PFL',pfl)]:
            kept=[]
            for line in raw.splitlines():
                a=line.split()
                if a[:3]==['2016','12','23'] and int(a[4 if kind=='SFC' else 3])>17:continue
                kept.append(line)
            (dest/('met.'+kind)).write_text('\n'.join(kept)+'\n',encoding='ascii')
        plan['fin_exclusivo']='2016-12-23 17:00'
        qc=met_qc(dest,plan);assert qc['horas_objetivo']==65 and qc['horas_auxiliares']==89
        good_pfl=(dest/'met.PFL').read_text(encoding='ascii')
        lines=good_pfl.splitlines();cut=next(i for i,line in enumerate(lines) if line.split()[:4]==['2016','12','21','1'])
        (dest/'met.PFL').write_text('\n'.join(lines[:cut]+lines[cut+1:])+'\n',encoding='ascii')
        try:met_qc(dest,plan)
        except ValueError:pass
        else:raise AssertionError('El lector no rechazó un nivel ausente')
        (dest/'met.PFL').write_text(good_pfl,encoding='ascii')
        lines=(dest/'met.SFC').read_text(encoding='ascii').splitlines()
        (dest/'met.SFC').write_text('\n'.join(lines[:26]+lines[27:])+'\n',encoding='ascii')
        try:met_qc(dest,plan)
        except ValueError:pass
        else:raise AssertionError('El lector no rechazó una hora faltante')
    coords=leer_aermap(OUT/'Comunes/receptores.inc');assert len(coords)==6295
    qa=dict(estado='CONTRATOS_PROBADOS',met_real_96h=True,MMIF_puntos_y_horas=True,final_parcial17h=True,rechaza_hora_faltante=True,rechaza_nivel_faltante=True,
        puntos_y_zonas_conservados=True,archivos=[record(ROOT/'work/ejecutar_base_verano_20261021.py'),record(__file__)])
    guardar_json(OUT/'Pruebas_preprocesamiento.json',qa)
    print('Contratos de meteorología completa/parcial y detección de huecos aprobados.',flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('etapa',choices=['emisiones','pruebas'])
    a=p.parse_args();{'emisiones':emissions,'pruebas':tests}[a.etapa]()
