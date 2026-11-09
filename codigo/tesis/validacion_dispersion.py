"""Valida concentraciones horarias y cierres nativos sin mutar los archivos leídos."""
from pathlib import Path
from collections import Counter
import re
import numpy as np
import pandas as pd
from .multidia import ventana,etiqueta
from .receptores import leer_aermap,resumir


def verificar_dispersion(folder,fuentes,receptores,membresia,inicio,fin_exclusivo):
    folder=Path(folder)
    def check(ok,message):
        if not ok:raise ValueError(message)
    text=(folder/'aermod.out').read_text(encoding='ascii',errors='replace')
    fatal=re.findall(r'A Total of\s+(\d+)\s+Fatal Error',text,re.I)
    check('AERMOD Finishes Successfully' in text and fatal and not any(map(int,fatal)),'Sin cierre nativo válido')
    match=re.search(r'This Run Includes:\s+(\d+) Source\(s\);\s+\d+ Source Group\(s\); and\s+(\d+) Receptor\(s\)',text)
    check(match and tuple(map(int,match.groups()))==(fuentes,receptores),'Dimensiones nativas incorrectas')
    check(re.search(r'Output Units\s*=\s*MICROGRAMS/M\*\*3',text),'Unidades desconocidas')
    target,_,_=ventana(inicio,fin_exclusivo);hours={etiqueta(t) for t in target}
    summary=(folder/'resumen.sum').read_text(encoding='ascii')
    counts={}
    for label in ('Hours Were Processed','Calm Hours Identified','Missing Hours Identified'):
        match=re.search(r'A Total of\s+(\d+)\s+'+label,summary)
        check(match,'Falta recuento '+label);counts[label]=int(match[1])
    check(list(counts.values())==[len(hours),0,0],'Horas incompletas/calmas/faltantes')
    cols=['x_m','y_m','C_ug_m3','elev_m','hill_m','flag','average','group','fecha_AERMOD']
    data=pd.read_csv(folder/'receptor_horas.out',sep=r'\s+',comment='*',header=None,names=cols,usecols=range(9),dtype={'fecha_AERMOD':str})
    check(data.average.eq('1-HR').all() and data.group.eq('ALL').all(),'Promedio o grupo incorrecto')
    check(np.isfinite(data[cols[:6]]).all().all() and data.C_ug_m3.ge(0).all() and data.flag.eq(0).all(),'Concentraciones/cotas inválidas')
    check(data.C_ug_m3.gt(0).any(),'Todas las concentraciones del ensayo son nulas')
    check(len(data)==receptores*len(hours) and set(data.fecha_AERMOD)==hours,'Calendario/tamaño incompleto')
    check(not data.duplicated(['x_m','y_m','fecha_AERMOD']).any(),'POSTFILE duplicado')
    pts=pd.DataFrame(leer_aermap(folder/'receptores.inc'))
    joined=data.merge(pts,on=['x_m','y_m'],how='left',suffixes=('','_expected'),validate='many_to_one')
    check(len(pts)==receptores and joined.elev_m_expected.notna().all(),'Coordenadas distintas')
    check(np.allclose(joined[['elev_m','hill_m']],joined[['elev_m_expected','hill_m_expected']],rtol=0,atol=.011),'Cotas distintas')
    check(data.groupby(['x_m','y_m']).size().eq(len(hours)).all(),'Cobertura desigual')
    data['dia']=pd.to_datetime(data.fecha_AERMOD.str[:6],format='%y%m%d')
    _,daily,zones=resumir(data,membresia,sorted(hours))
    maxima={'1':float(data.C_ug_m3.max()),'24':float(daily.media_24h_ug_m3.max())}
    for avg,value in maxima.items():
        match=re.search(r'SUMMARY OF HIGHEST\s+'+avg+r'-HR RESULTS.*?ALL\s+HIGH\s+1ST HIGH VALUE IS\s+([\d.]+)',summary,re.S)
        check(match and np.isclose(float(match[1]),value,rtol=0,atol=1.1e-5),'Resumen nativo distinto')
    qa=dict(estado='VERIFICADO',fuentes=fuentes,receptores=receptores,horas=len(hours),valores=len(data),
        cobertura=counts,maximos=maxima,advertencias=dict(Counter(re.findall(r'\bW\d{3}\b',(folder/'errores.out').read_text(encoding='ascii')))))
    return qa,daily,zones
