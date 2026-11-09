"""Identidad espacial de receptores y medias por punto antes de máximos por zona."""
from pathlib import Path
import math
import re

import numpy as np
import pandas as pd


def leer_aermap(path):
    """GRIDCART XYINC y DISCCART con ELEV/HILL; conserva redes superpuestas.

    No asigna nombres geográficos a CG1/CG2, ni rellena cotas ausentes.
    Admite el fragmento histórico sin STA/END sólo para una red CG1.
    """
    grids, discrete, current = {}, [], None
    for raw in Path(path).read_text(encoding='ascii').splitlines():
        tokens = raw.split()
        if not tokens or tokens[0].startswith('*'):
            continue
        if tokens[0] == 'RE':
            tokens = tokens[1:]
        if not tokens:
            continue
        key = tokens[0]
        if key in ('STARTING', 'FINISHED'):
            continue
        if key == 'ELEVUNIT':
            if tokens != ['ELEVUNIT', 'METERS']:
                raise ValueError('Se requieren cotas en METERS.')
            continue
        if key == 'GRIDCART':
            name, op, *vals = tokens[1:]
            if op in ('STA', 'START'):
                if current is not None or name in grids:
                    raise ValueError('Red duplicada o anidada: ' + name)
                grids[name] = {'ELEV': {}, 'HILL': {}}
                current = name
                continue
            if name not in grids:
                raise ValueError('Red sin inicio: ' + name)
            if op == 'END':
                if current != name:
                    raise ValueError('Cierre de otra red.')
                current = None
                continue
            if op == 'XYINC':
                if 'xy' in grids[name]:
                    raise ValueError('XYINC duplicado.')
                grids[name]['xy'] = vals
            elif op in ('ELEV', 'HILL'):
                row, *values = vals
                grids[name][op].setdefault(int(row), []).extend(map(float, values))
            else:
                raise ValueError('GRIDCART no soportado: ' + op)
        elif key == 'XYINC':
            name = current or 'CG1'
            if current is None and grids:
                raise ValueError('XYINC sin red en archivo con varias redes.')
            grids.setdefault(name, {'ELEV': {}, 'HILL': {}})
            if 'xy' in grids[name]:
                raise ValueError('XYINC duplicado.')
            grids[name]['xy'] = tokens[1:]
        elif key == 'DISCCART':
            if len(tokens) not in (5, 6):
                raise ValueError('DISCCART requiere x y ELEV HILL [flag].')
            if len(tokens) == 6 and float(tokens[5]) != 0:
                raise ValueError('Esta cadena usa receptores a nivel del suelo; flag no cero.')
            discrete.append((*map(float, tokens[1:5]), 'DISCRETO'))
        else:
            raise ValueError('Entrada de receptor no soportada: ' + key)
    if current is not None:
        raise ValueError('Red sin END.')
    points = list(discrete)
    for name, grid in grids.items():
        if 'xy' not in grid or len(grid['xy']) != 6:
            raise ValueError('Falta XYINC en ' + name)
        x0, nx, dx, y0, ny, dy = map(float, grid['xy'])
        if not all(map(math.isfinite, (x0, nx, dx, y0, ny, dy))) or nx != int(nx) or ny != int(ny) or min(nx, ny, dx, dy) <= 0:
            raise ValueError('Dimensiones XYINC inválidas.')
        nx, ny = int(nx), int(ny)
        for key in ('ELEV', 'HILL'):
            if set(grid[key]) != set(range(1, ny+1)) or any(len(v) != nx for v in grid[key].values()):
                raise ValueError('Filas o columnas incompletas: ' + name + ' ' + key)
        for j in range(ny):
            for i in range(nx):
                points.append((x0+i*dx, y0+j*dy, grid['ELEV'][j+1][i], grid['HILL'][j+1][i], name))
    unique = {}
    for x, y, z, hill, name in points:
        if not all(map(math.isfinite, (x, y, z, hill))) or hill < z-.11 or min(z, hill) <= -9999:
            raise ValueError('Cota/relieve inválido.')
        if (x, y) in unique:
            p = unique[x, y]
            if not np.allclose([z, hill], [p['elev_m'], p['hill_m']], rtol=0, atol=.011):
                raise ValueError('Receptor superpuesto con cotas diferentes.')
            p['redes'] = sorted(set(p['redes'] + [name]))
        else:
            unique[x, y] = dict(x_m=x, y_m=y, elev_m=z, hill_m=hill, redes=[name])
    if not unique:
        raise ValueError('No hay receptores.')
    return list(unique.values())


def leer_postfile(path):
    rows = []
    for line in Path(path).read_text(encoding='ascii').splitlines():
        if not line.strip() or line.lstrip().startswith('*'):
            continue
        a = line.split()
        if len(a) not in (9, 10) or a[6:8] != ['1-HR', 'ALL'] or not re.fullmatch(r'\d{8}', a[8]):
            raise ValueError('POSTFILE requiere 1-HR ALL y fecha YYMMDDHH.')
        hour = int(a[8][-2:])
        if not 1 <= hour <= 24:
            raise ValueError('Hora final fuera de 1..24.')
        day = pd.to_datetime(a[8][:6], format='%y%m%d')
        rows.append((float(a[0]), float(a[1]), a[8], day, float(a[2])))
    d = pd.DataFrame(rows, columns=['x_m', 'y_m', 'fecha_AERMOD', 'dia', 'C_ug_m3'])
    if d.empty or not np.isfinite(d[['x_m', 'y_m', 'C_ug_m3']]).all().all() or d.C_ug_m3.lt(0).any():
        raise ValueError('Concentraciones no válidas.')
    if d.duplicated(['x_m', 'y_m', 'fecha_AERMOD']).any():
        raise ValueError('Receptor/hora duplicado.')
    return d


def resumir(d, membresia, horas_esperadas):
    """No aproxima puntos ausentes; exige misma cobertura por miembro del grupo.

    membresia: grupo,x_m,y_m. Devuelve series, medias por receptor/día y
    máximos por grupo/día. Días parciales quedan rotulados y sin media de 24h.
    """
    keys = ['x_m', 'y_m']
    required = set(horas_esperadas)
    if not required or len(required) != len(horas_esperadas):
        raise ValueError('Horas esperadas vacías/duplicadas.')
    if membresia.empty or membresia.duplicated(['grupo']+keys).any():
        raise ValueError('Membresía vacía o duplicada dentro de grupo.')
    if d.duplicated(keys+['fecha_AERMOD']).any():
        raise ValueError('Receptor/hora duplicado.')
    available = set(map(tuple, d[keys].drop_duplicates().to_numpy()))
    wanted = set(map(tuple, membresia[keys].drop_duplicates().to_numpy()))
    if not wanted <= available:
        raise ValueError('Receptor exacto ausente; no usar el vecino sin declararlo.')
    for point, group in d.groupby(keys):
        if point in wanted and set(group.fecha_AERMOD) != required:
            raise ValueError('Cobertura horaria desigual o incompleta.')
    joined = membresia.merge(d, on=keys, how='left', validate='many_to_many')
    daily = joined.groupby(['grupo', *keys, 'dia']).C_ug_m3.agg(['mean', 'max', 'count']).reset_index()
    daily = daily.rename(columns={'mean': 'media_disponible_ug_m3', 'max': 'maximo_1h_ug_m3', 'count': 'horas'})
    daily['media_24h_ug_m3'] = daily.media_disponible_ug_m3.where(daily.horas.eq(24))
    result = []
    for (label, day), group in daily.groupby(['grupo', 'dia']):
        if group.horas.nunique() != 1:
            raise ValueError('Cobertura desigual entre receptores.')
        complete = group.horas.eq(24).all()
        row = group.loc[group.media_24h_ug_m3.idxmax()] if complete else None
        result.append({'grupo': label, 'dia': day, 'n_receptores': len(group), 'horas': int(group.horas.iloc[0]),
                       'maximo_1h_ug_m3': float(group.maximo_1h_ug_m3.max()),
                       'maximo_media_24h_ug_m3': float(row.media_24h_ug_m3) if complete else np.nan,
                       'x_maximo_24h_m': float(row.x_m) if complete else np.nan,
                       'y_maximo_24h_m': float(row.y_m) if complete else np.nan})
    return joined, daily, pd.DataFrame(result)
