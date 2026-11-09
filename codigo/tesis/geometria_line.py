"""Subdivide ejes LINE sin ensancharlos y conserva el enlace al arco emisor."""
import argparse
import numpy as np
import pandas as pd
from .terreno import leer_fuentes
from .comun import finito, salida_nueva, guardar_json, sha256

XY=['x1_utm19s_m','y1_utm19s_m','x2_utm19s_m','y2_utm19s_m']

def subdividir(sources, *, ancho=None, razon_maxima=100, largo_maximo=None):
    finito(razon_maxima)
    if razon_maxima<1:raise ValueError('Razón >=1 requerida.')
    if ancho is None and 'ancho_m' not in sources:raise ValueError('Falta ancho por fuente.')
    if ancho is not None:
        finito(ancho)
        if ancho<1:raise ValueError('Ancho >=1 m requerido.')
    if largo_maximo is not None:
        finito(largo_maximo)
        if largo_maximo<=0:raise ValueError('Longitud máxima positiva requerida.')
    if sources.id_fuente_aermod.duplicated().any():raise ValueError('Fuentes duplicadas.')
    result=[]
    for r in sources.to_dict('records'):
        width=round(float(r['ancho_m'] if ancho is None else ancho),3)
        finito(width)
        if width<1:raise ValueError('Ancho serializado >=1 m requerido.')
        a=np.round(np.array([r[XY[0]],r[XY[1]]],float),2)
        b=np.round(np.array([r[XY[2]],r[XY[3]]],float),2)
        finito(a,b);length=np.linalg.norm(b-a)
        if length<=0:raise ValueError('Fuente nula después de redondear coordenadas.')
        # Los segmentos cortos se conservan. No se alargan para simular un camino.
        if width/length>razon_maxima:raise ValueError('Fuente más ancha que larga: revisar el eje corto; subdividirlo no corrige la relación.')
        limit=min(width*razon_maxima,largo_maximo) if largo_maximo is not None else width*razon_maxima
        count=max(1,int(np.ceil(length/limit)))
        while True:
            points=np.round(a+np.linspace(0,1,count+1)[:,None]*(b-a),2)
            lengths=np.linalg.norm(np.diff(points,axis=0),axis=1)
            if np.any(lengths<=0):raise ValueError('Segmento nulo por precisión de coordenadas.')
            if lengths.max()<=limit+1e-9:break
            count+=1
        for k,L in enumerate(lengths):
            row=dict(r);row['id_fuente_padre']=r['id_fuente_aermod']
            row['id_fuente_aermod']=f'L{len(result)+1:06d}'
            row.update(dict(zip(XY,[*points[k],*points[k+1]])))
            row.update(fraccion_masa=float(L/lengths.sum()),largo_line_m=float(L),ancho_m=width,
                       razon_largo_ancho=float(L/width),numero_segmentos_padre=count)
            result.append(row)
    return pd.DataFrame(result)

def repartir_masas(diarias, segments):
    """Masa del padre distribuida por longitud ESCRITA, nunca duplicada por hijo."""
    if diarias.duplicated(['fecha','id_fuente_aermod']).any():raise ValueError('Fuente/fecha duplicada.')
    if set(diarias.id_fuente_aermod)!=set(segments.id_fuente_padre):raise ValueError('Padres distintos.')
    fractions=segments.groupby('id_fuente_padre').fraccion_masa.sum()
    if not np.allclose(fractions,1,rtol=0,atol=1e-12):raise ValueError('Fracciones no suman uno.')
    masses=[c for c in diarias if c.startswith('emision_') and c.endswith('_g_dia')]
    if not masses:raise ValueError('No hay masas.')
    if not np.isfinite(diarias[masses]).all().all() or (diarias[masses]<0).any().any():raise ValueError('Masas inválidas.')
    mapping=segments[['id_fuente_padre','id_fuente_aermod','id_ruta_excel','fraccion_masa']]
    # El id_ruta_excel se verifica antes de unir; no se toleran enlaces nuevos.
    parent_route=segments[['id_fuente_padre','id_ruta_excel']].drop_duplicates().set_index('id_fuente_padre').id_ruta_excel
    if not np.array_equal(diarias.id_ruta_excel.to_numpy(),diarias.id_fuente_aermod.map(parent_route).to_numpy()):
        raise ValueError('El enlace al arco del inventario cambió.')
    # Desecha tasas y áreas históricas; se deben recalcular para cada geometría.
    keep=['fecha','id_fuente_aermod',*masses]+[c for c in ('fecha_o_intervalo_donante','regla_escenario') if c in diarias]
    base=diarias[keep].rename(columns={'id_fuente_aermod':'id_fuente_padre'})
    out=base.merge(mapping,on='id_fuente_padre',validate='many_to_many')
    for c in masses:
        out[c]*=out.fraccion_masa
        before=base.groupby(['fecha','id_fuente_padre'])[c].sum().sort_index()
        after=out.groupby(['fecha','id_fuente_padre'])[c].sum().sort_index()
        if not np.allclose(before,after,rtol=1e-12,atol=1e-8):raise RuntimeError('Masa del arco no conservada.')
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fuentes',required=True);p.add_argument('--ancho',type=float,required=True)
    p.add_argument('--salida',required=True);p.add_argument('--diarias')
    a=p.parse_args();s=leer_fuentes(a.fuentes);out=subdividir(s,ancho=a.ancho)
    mass=repartir_masas(pd.read_csv(a.diarias),out) if a.diarias else None
    dest=salida_nueva(a.salida);out.to_csv(dest/'fuentes_segmentadas.csv',index=False,encoding='utf-8-sig',float_format='%.15g')
    if mass is not None:mass.to_csv(dest/'emisiones_segmentadas.csv',index=False,encoding='utf-8-sig',float_format='%.15g')
    guardar_json(dest/'manifest.json',{'fuentes_sha256':sha256(a.fuentes),'diarias_sha256':sha256(a.diarias) if a.diarias else None,
      'ancho_m':a.ancho,'arcos_originales':len(s),'segmentos':len(out),'max_largo_ancho':float(out.razon_largo_ancho.max()),
      'alcance':'Subdivisión numérica; NO justificación física del ancho. Regenerar AERMAP y HOUREMIS con estos IDs.',
      'masa':'Distribuida por longitud serializada; control no reaplicado.'})

if __name__=='__main__':main()
