"""Refinamiento anidado y contrastes de resolución; conserva entradas históricas."""
import math
from pathlib import Path
import numpy as np
import pandas as pd
from shapely.geometry import Point
from .geometria_line import subdividir, XY


def refinar_fuentes(base, limite=50):
    """Subdivide cada segmento escrito, manteniendo vínculo al segmento y arco."""
    parent = base.copy()
    parent['id_arco_original'] = parent['id_fuente_padre']
    fine = subdividir(parent, largo_maximo=limite)
    fine['id_fuente_aermod'] = [f'N{i+1:06d}' for i in range(len(fine))]
    pxy = np.round(parent[XY].to_numpy(float), 2)
    areas = pd.Series(np.hypot(pxy[:,2]-pxy[:,0],pxy[:,3]-pxy[:,1])*parent.ancho_m.to_numpy(),
                      index=parent.id_fuente_aermod)
    fine['area_m2'] = fine.largo_line_m*fine.ancho_m
    sums = fine.groupby('id_fuente_padre').area_m2.sum()
    fine['factor_densidad'] = fine.id_fuente_padre.map(areas/sums)
    if not np.isfinite(fine[['area_m2','factor_densidad']]).all().all():
        raise ValueError('Geometría no finita')
    for key, group in fine.groupby('id_fuente_padre',sort=False):
        row = parent.set_index('id_fuente_aermod').loc[key]
        if not np.allclose(group[['ancho_m','altura_m','sigma_z_m']],
                           row[['ancho_m','altura_m','sigma_z_m']].to_numpy(float),rtol=0,atol=1e-12):
            raise ValueError('Cambió un parámetro físico al subdividir')
        coords = group[XY].to_numpy(float)
        if not np.array_equal(coords[:-1,2:],coords[1:,:2]):
            raise ValueError('Eje discontinuo')
        if not np.array_equal(np.r_[coords[0,:2],coords[-1,2:]],np.round(row[XY].to_numpy(float),2)):
            raise ValueError('Cambió un extremo original')
    return fine


def nuevos_receptores(existentes, zonas, paso=250, origen=(370000,6320000)):
    """Lattice local dentro de polígonos; excluye duplicados con puntos existentes."""
    if not np.isfinite(paso) or paso<=0 or not zonas:
        raise ValueError('Paso positivo y zonas requeridos')
    old={tuple(x) for x in np.asarray(existentes,float)}
    nodes={}
    for name,geom in zonas.items():
        if not geom.is_valid or geom.is_empty:
            raise ValueError('Polígono inválido: '+name)
        x0,y0,x1,y1=geom.bounds
        for i in range(math.ceil((x0-origen[0])/paso),math.floor((x1-origen[0])/paso)+1):
            for j in range(math.ceil((y0-origen[1])/paso),math.floor((y1-origen[1])/paso)+1):
                xy=(origen[0]+i*paso,origen[1]+j*paso)
                if xy not in old and geom.covers(Point(xy)):
                    nodes.setdefault(xy,[]).append(name)
    return [dict(x_m=float(x),y_m=float(y),zonas=sorted(names)) for (x,y),names in sorted(nodes.items())]


def repartir_houremis(entrada, salida, base, fine, horas):
    """Conserva por segmento padre/hora la masa ya serializada en BASE.

    q_hijo=q_padre*A_padre/sum(A_hijos): corrige sólo el redondeo geométrico.
    No aplica de nuevo abatimiento ni modifica distribución temporal.
    """
    parents=base.set_index('id_fuente_aermod')
    children={p:list(g.itertuples(index=False)) for p,g in fine.groupby('id_fuente_padre',sort=False)}
    if set(children)!=set(parents.index):
        raise ValueError('Padres incompletos')
    areas={r.id_fuente_aermod:float(np.hypot(round(r.x2_utm19s_m,2)-round(r.x1_utm19s_m,2),
                                          round(r.y2_utm19s_m,2)-round(r.y1_utm19s_m,2))*r.ancho_m)
           for r in base.itertuples()}
    seen=set();counts={};mass_old=mass_new=worst_abs=worst_rel=0.;lines=0
    with Path(entrada).open(encoding='ascii') as src, Path(salida).open('x',encoding='ascii') as dst:
        for raw in src:
            t=raw.split()
            if len(t)!=8 or t[:2]!=['SO','HOUREMIS']:
                raise ValueError('HOUREMIS inesperado')
            date=tuple(map(int,t[2:6]));p=t[6];q=float(t[7]);key=(*date,p)
            if p not in children or date not in horas or key in seen or not np.isfinite(q) or q<0:
                raise ValueError('Hora/fuente/tasa inválida o duplicada')
            seen.add(key);counts[date]=counts.get(date,0)+1
            mass0=q*areas[p];mass1=0.
            for c in children[p]:
                written=float(f'{q*c.factor_densidad:.12E}')
                dst.write(f'SO HOUREMIS {date[0]:02d} {date[1]:2d} {date[2]:2d} {date[3]:2d} {c.id_fuente_aermod:<12s} {written:.12E}\n')
                mass1+=written*c.area_m2;lines+=1
            error=abs(mass1-mass0)
            if not np.isclose(mass1,mass0,rtol=1e-10,atol=1e-12):
                raise ValueError('Masa no conservada por padre/hora')
            worst_abs=max(worst_abs,error);worst_rel=max(worst_rel,error/mass0 if mass0 else 0)
            mass_old+=mass0*3600;mass_new+=mass1*3600
    if set(counts)!=set(horas) or any(n!=len(base) for n in counts.values()):
        raise ValueError('Cobertura horaria/fuentes incompleta')
    return dict(horas=len(counts),fuentes_base=len(base),fuentes_refinadas=len(fine),filas=lines,
                masa_base_g=mass_old,masa_refinada_g=mass_new,
                error_max_padre_hora_g_s=worst_abs,error_relativo_max_padre_hora=worst_rel)


def clasificar_cambio(base, fino, relativa=.05, absoluta=2e-5):
    """Umbrales declarados antes de las corridas; baja concentración no prueba convergencia."""
    if not all(map(np.isfinite,(base,fino,relativa,absoluta))) or min(base,fino)<0 or min(relativa,absoluta)<=0:
        raise ValueError('Concentraciones y tolerancias inválidas')
    delta=fino-base
    low=max(base,fino)<=absoluta/relativa
    if low:
        status='DIFERENCIA_BAJO_PRECISION_OPERATIVA' if abs(delta)<=absoluta else 'DIFERENCIA_ABSOLUTA_RELEVANTE'
    else:
        status='CUMPLE_CRITERIO_OPERATIVO' if abs(delta)<=max(relativa*base,absoluta) else 'REQUIERE_REFINAMIENTO'
    return dict(delta_ug_m3=delta,cambio_pct=100*delta/base if base>absoluta/relativa else None,
                limite_ug_m3=max(relativa*base,absoluta),baja_concentracion=low,estado=status)
