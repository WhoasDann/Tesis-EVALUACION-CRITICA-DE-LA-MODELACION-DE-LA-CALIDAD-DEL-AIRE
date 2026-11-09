"""Criterio de trabajo v1: dimensiones asumidas explícitas, no medidas en terreno."""
import argparse
import numpy as np
import pandas as pd
from .comun import salida_nueva, guardar_json, sha256
from .terreno import leer_fuentes

LATERALES=('eje','calzada','calzada_estela')
VERTICALES=('baja','central','alta')
# Tamaños representativos asumidos por grupo; no se afirma flota homogénea real.
VEHICULOS={'MINA':{'ancho':10.,'alturas':(6.,7.,8.)},
           'OTROS':{'ancho':3.,'alturas':(2.,3.,4.)}}

def parametrizar(sources, roads, *, lateral='eje', vertical='central'):
    if lateral not in LATERALES or vertical not in VERTICALES:raise ValueError('Escenario desconocido.')
    if not {'ID','RED'}<=set(roads):raise ValueError('Faltan ID/RED del inventario.')
    if roads.ID.duplicated().any():raise ValueError('ID de ruta duplicado.')
    if set(roads.ID)!=set(sources.id_ruta_excel):raise ValueError('La clasificación no cubre exactamente las rutas.')
    out=sources.copy();out['red']=out.id_ruta_excel.map(roads.set_index('ID').RED)
    if not set(out.red)<=set(VEHICULOS):raise ValueError('Red sin criterio explícito.')
    out['ancho_vehiculo_sup_m']=out.red.map({k:v['ancho'] for k,v in VEHICULOS.items()})
    out['altura_vehiculo_sup_m']=out.red.map({k:v['alturas'][VERTICALES.index(vertical)] for k,v in VEHICULOS.items()})
    w=out.ancho_vehiculo_sup_m
    out['ancho_m']=w+6 if lateral=='eje' else 3.5*w+(6 if lateral=='calzada_estela' else 0)
    out['altura_pluma_m']=1.7*out.altura_vehiculo_sup_m
    out['altura_m']=(out.altura_pluma_m/2).round(3)
    out['sigma_z_m']=(out.altura_pluma_m/2.15).round(3)
    out['escenario_fuente']=f'{lateral}_{vertical}'
    out['criterio']='v1_supuestos_por_red_no_mediciones'
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fuentes',required=True);p.add_argument('--rutas',required=True);p.add_argument('--salida',required=True)
    a=p.parse_args();s=leer_fuentes(a.fuentes);roads=pd.read_csv(a.rutas)
    cases={f'{lat}_{ver}':parametrizar(s,roads,lateral=lat,vertical=ver) for lat in LATERALES for ver in VERTICALES}
    out=salida_nueva(a.salida)
    for name,data in cases.items():data.to_csv(out/(name+'.csv'),index=False,encoding='utf-8-sig')
    guardar_json(out/'manifest.json',{'referencia':'eje_central','criterio':'v1',
      'supuestos_vehiculos':VEHICULOS,'escenarios':list(cases),
      'fuentes_sha256':sha256(a.fuentes),'rutas_sha256':sha256(a.rutas),
      'lateral':'eje: V+6; calzada: 3.5V; calzada_estela: 3.5V+6. Corredores idealizados, no anchos observados.',
      'vertical':'Hpluma=1.7H; altura=Hpluma/2; sigma_z=Hpluma/2.15.',
      'alcance':'Referencia fija y sensibilidad; no certifica un peor caso universal ni modifica masa.'})

if __name__=='__main__':main()
