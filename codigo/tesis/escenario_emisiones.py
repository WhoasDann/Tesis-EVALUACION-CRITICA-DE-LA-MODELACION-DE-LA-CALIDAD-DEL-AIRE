"""Extensión explícita del escenario 2017 a diciembre 2016, sin doble control."""
import argparse
import numpy as np
import pandas as pd
from .comun import salida_nueva, guardar_json, sha256

def construir(diarias, *, inicio, fin, politica):
    """Usa mismo día de diciembre 2017 o promedio mensual POR FUENTE.

    No cambia 2017. No extrapola otros meses/años ni rellena faltantes con ceros.
    La entrada contiene masas diarias ya controladas; tasas/anchos derivados no se copian.
    """
    if politica not in ('diciembre_mismo_dia','diciembre_promedio_mensual'):
        raise ValueError('Seleccione una política explícita.')
    d=diarias.copy();d['fecha']=pd.to_datetime(d.fecha)
    start,end=pd.Timestamp(inicio),pd.Timestamp(fin)
    if start>=end or start!=start.normalize() or end!=end.normalize():
        raise ValueError('Se requieren días completos y fin exclusivo posterior al inicio.')
    masses=[c for c in d if c.startswith('emision_') and c.endswith('_g_dia')]
    if not masses:raise ValueError('Faltan masas diarias controladas.')
    if d.duplicated(['fecha','id_fuente_aermod']).any():raise ValueError('Fuente/fecha duplicada.')
    if (d.fecha!=d.fecha.dt.normalize()).any():raise ValueError('Fechas de inventario no diarias.')
    if not np.isfinite(d[masses]).all().all() or (d[masses]<0).any().any():
        raise ValueError('Masa ausente, infinita o negativa.')
    ids=set(d.id_fuente_aermod)
    links=d[['id_fuente_aermod','id_ruta_excel']].drop_duplicates()
    if links.id_fuente_aermod.duplicated().any():raise ValueError('Enlace fuente/arco inconsistente.')
    parts=[]
    for target in pd.date_range(start,end,freq='D',inclusive='left'):
        if target.year==2017:
            p=d.loc[d.fecha.eq(target),['id_fuente_aermod','id_ruta_excel',*masses]].copy()
            donor=target.strftime('%Y-%m-%d');rule='inventario_2017_sin_cambio'
        elif target.year==2016 and target.month==12:
            if d.fecha.eq(target).any():raise ValueError('Ya existe inventario para el destino; no se sustituye.')
            donor_date=target.replace(year=2017)
            if politica=='diciembre_mismo_dia':
                p=d.loc[d.fecha.eq(donor_date),['id_fuente_aermod','id_ruta_excel',*masses]].copy()
                donor=donor_date.strftime('%Y-%m-%d')
            else:
                dec=d.loc[(d.fecha>='2017-12-01')&(d.fecha<'2018-01-01')]
                counts=dec.groupby('id_fuente_aermod').fecha.nunique()
                if set(counts.index)!=ids or not counts.eq(31).all():
                    raise ValueError('El promedio requiere 31 días para cada fuente.')
                p=dec.groupby(['id_fuente_aermod','id_ruta_excel'],as_index=False)[masses].mean()
                donor='2017-12-01/2017-12-31'
            rule=politica
        else:raise ValueError('Transferencia autorizada sólo para diciembre de 2016.')
        if set(p.id_fuente_aermod)!=ids:raise ValueError(f'Faltan fuentes en la fecha donante de {target.date()}.')
        p['fecha']=target;p['fecha_o_intervalo_donante']=donor;p['regla_escenario']=rule
        parts.append(p)
    return pd.concat(parts,ignore_index=True)[['fecha','id_fuente_aermod','id_ruta_excel',*masses,'fecha_o_intervalo_donante','regla_escenario']]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('diarias','salida','inicio','fin'):p.add_argument('--'+name,required=True)
    p.add_argument('--politica',required=True,choices=['diciembre_mismo_dia','diciembre_promedio_mensual'])
    a=p.parse_args();d=construir(pd.read_csv(a.diarias),inicio=a.inicio,fin=a.fin,politica=a.politica)
    dest=salida_nueva(a.salida);d.to_csv(dest/'emisiones_escenario.csv',index=False,encoding='utf-8-sig',float_format='%.15g')
    cols=[c for c in d if c.endswith('_g_dia')]
    guardar_json(dest/'manifest.json',{'sha256_entrada':sha256(a.diarias),'politica':a.politica,'inicio':a.inicio,'fin_exclusivo':a.fin,
      'masa_g':{c:float(d[c].sum()) for c in cols},'registros':len(d),'control':'Ya incluido en la masa de entrada.',
      'alcance':'Escenario de operación 2017 transferido; NO inventario observado de diciembre 2016.',
      'calendario':'Copia por día de mes no conserva día de semana. La alternativa mensual elimina esa dependencia.',
      'supuestos':'Mismas fuentes y controles; geometría 2017. Las variantes meteorológicas deben compartir exactamente este escenario.'})

if __name__=='__main__':main()
