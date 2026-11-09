"""Contratos multidiarios explícitos; no modifica el ensayo histórico de un día."""
from datetime import datetime, timedelta
from pathlib import Path
import re
import math

from .cadena_corta import METODOS, hora_fin
from .comun import sha256


def ventana(inicio, fin, margen_dias=1):
    start, end = datetime.fromisoformat(inicio), datetime.fromisoformat(fin)
    if start >= end or any((d.hour, d.minute, d.second, d.microsecond) != (0, 0, 0, 0)
                           or d.tzinfo is not None for d in (start, end)) or margen_dias < 0:
        raise ValueError('Se requieren días completos, límites locales sin zona y margen no negativo.')
    aux_start, aux_end = start-timedelta(days=margen_dias), end+timedelta(days=margen_dias)
    target = [start+timedelta(hours=h) for h in range(1, int((end-start).total_seconds()/3600)+1)]
    auxiliary = [aux_start+timedelta(hours=h) for h in range(1, int((aux_end-aux_start).total_seconds()/3600)+1)]
    utc = [aux_start+timedelta(hours=3+h) for h in range(len(auxiliary)+1)]
    return target, auxiliary, utc


def etiqueta(stamp):
    d = stamp-timedelta(hours=1)
    return d.strftime('%y%m%d')+f'{d.hour+1:02d}'


def revisar_log_mmif(texto, inicio, fin):
    """Distingue puntos 1-D de los límites I/J de la subgrilla 3-D."""
    expected_names = {1: 'MET.BAT', 2: 'ONSITE.DAT', 3: 'UPPER.DAT',
                      4: 'SURFACE.DAT', 5: 'MET.USEFUL.TXT'}
    points = {}
    pending = None
    for line in texto.splitlines():
        header = re.fullmatch(r'\s*Grid parameters for: Output 1-D point\s+#\s+(\d+)\s+(\S+)\s*', line)
        if header:
            if pending is not None:
                raise ValueError('Bloque de punto MMIF sin celda I/J')
            pending = (int(header[1]), header[2].upper())
        # Anclado a toda la línea: excluye Low-Lft/Upr-Rgt I/J cell center.
        cell = re.fullmatch(r'\s*I/J cell center:\s+(\d+)\s+(\d+)\s*', line)
        if cell:
            if pending is None:
                raise ValueError('Celda puntual MMIF fuera de un bloque 1-D')
            number, name = pending
            if number in points or expected_names.get(number) != name:
                raise ValueError('Punto/salida MMIF duplicado o inesperado')
            points[number] = {'archivo': name, 'i': int(cell[1]), 'j': int(cell[2])}
            pending = None
    if pending is not None or set(points) != set(expected_names):
        raise ValueError('Faltan bloques de los cinco puntos/salidas MMIF')
    cells = {(p['i'], p['j']) for p in points.values()}
    if cells != {(43, 44)}:
        raise ValueError(f'MMIF extrajo otra celda puntual {sorted(cells)}; se esperaba I/J43/44')
    if 'Reached requested ending date/hour; run completed normally.' not in texto:
        raise ValueError('MMIF no confirmó cierre normal')
    matches = re.findall(r'Hourly output written to all files at\s+(\d{10}) LST\s*=\s*(\d{10}) UTC', texto)
    _, expected, _ = ventana(inicio, fin)
    local = [datetime.strptime(a, '%Y%m%d%H') for a, _ in matches]
    utc = [datetime.strptime(b, '%Y%m%d%H') for _, b in matches]
    if local != expected or utc != [t+timedelta(hours=3) for t in expected]:
        raise ValueError('Cobertura/orden de salida MMIF no corresponde al calendario')
    return {'puntos': points, 'horas_salida': len(local), 'cierre_normal': True,
            'primero_local': local[0].isoformat(), 'ultimo_local': local[-1].isoformat()}


def control_mmif(files, method, inicio, fin):
    from .preprocesadores import LAYERS
    if method not in METODOS:
        raise ValueError('Método desconocido')
    _, aux, _ = ventana(inicio, fin)
    return '\n'.join([
        'START '+aux[0].strftime('%Y %m %d %H'), 'STOP '+aux[-1].strftime('%Y %m %d %H'),
        'TIMEZONE -3', *[f'INPUT "{Path(p).resolve()}"' for p in files],
        'POINT LL -33.15632248 -70.29452515', 'LAYERS MID '+' '.join(map(str, LAYERS)),
        'AER_MIN_SPEED 0', 'AER_USE_NEW T', f'AER_MIXHT {method}', 'FSL_INTERVAL 12',
        'OUTPUT AERMET BAT met.bat', 'OUTPUT AERMET ONSITE onsite.dat',
        'OUTPUT AERMET FSL upper.dat', 'OUTPUT AERMET AERSFC surface.dat',
        'OUTPUT AERMET USEFUL met.useful.txt', ''])


def revisar_met(sfc, pfl, inicio, fin):
    target, auxiliary, _ = ventana(inicio, fin)
    rows = {}
    lines = Path(sfc).read_text(encoding='ascii').splitlines()
    for line in lines[1:]:
        if not line.strip():
            continue
        a = line.split()
        if len(a) < 25 or '*' in line:
            raise ValueError('Registro SFC incompleto')
        v = list(map(float, a[:25]))
        if not all(map(math.isfinite, v)):
            raise ValueError('SFC contiene NaN/Inf')
        k = hora_fin(*map(int, [a[0], a[1], a[2], a[4]]))
        if k in rows:
            raise ValueError('Hora SFC duplicada')
        rows[k] = v
    if list(rows) != auxiliary:
        raise ValueError('Cobertura/orden SFC diferente de ventana auxiliar')
    for k in target:
        v = rows[k]
        if not (v[6] >= 0 and v[10] > 0 and v[12] > 0 and v[15] >= 0 and 0 <= v[16] <= 360
                and v[17] > 0 and 150 < v[18] < 350 and v[19] > 0 and abs(v[11]) < 99998):
            raise ValueError(f'SFC inválido/faltante: {k}')
        if v[11] < 0 and v[9] <= 0:
            raise ValueError('Falta altura convectiva para L<0')
    profiles = {}
    for line in Path(pfl).read_text(encoding='ascii').splitlines():
        if not line.strip():
            continue
        a = list(map(float, line.split()))
        if len(a) != 11 or not all(map(math.isfinite, a)):
            raise ValueError('PFL inválido')
        profiles.setdefault(hora_fin(*map(int, a[:4])), []).append(a)
    if list(profiles) != auxiliary:
        raise ValueError('Horas/orden PFL diferentes de SFC')
    for k in target:
        p = profiles[k]
        if (len(p) < 3 or any(b[4] <= a[4] for a, b in zip(p, p[1:]))
                or [x[5] for x in p] != [0]*(len(p)-1)+[1]):
            raise ValueError('Perfil incompleto o sin cierre')
        if not any(0 <= x[6] <= 360 and 0 <= x[7] < 99 for x in p) or not any(-123 < x[8] < 77 for x in p):
            raise ValueError('Perfil sin viento/temperatura utilizables')
    ids = {}
    for key, following in [('UA_ID', 'SF_ID'), ('SF_ID', 'OS_ID'), ('OS_ID', 'VERSION')]:
        m = re.search(key+r':\s*(.*?)\s*'+following+r':', lines[0])
        if not m or (m[1].strip() and not m[1].strip().isdigit()):
            raise ValueError('Cabecera de estaciones desconocida')
        ids[key] = int(m[1].strip() or '0')
    return {'horas_SFC': len(auxiliary), 'horas_objetivo': len(target), 'ids': ids,
            'calmas_objetivo': sum(rows[k][15] == 0 for k in target),
            'niveles_PFL': sorted({len(profiles[k]) for k in target}),
            'serie_objetivo': [{'fin_local': k.isoformat(), 'ZiC_m': rows[k][9], 'ZiM_m': rows[k][10],
                               'T_K': rows[k][18], 'WS_ms': rows[k][15], 'WD_deg': rows[k][16]} for k in target]}


def seleccionar_met(sfc, pfl, destination, inicio, fin):
    target, _, _ = ventana(inicio, fin)
    qa = revisar_met(sfc, pfl, inicio, fin)
    dest = Path(destination)
    selected = {}
    for path in map(Path, (sfc, pfl)):
        if (dest/path.name).resolve() == path.resolve():
            raise ValueError('No sobrescribir meteorología original')
        lines = path.read_text(encoding='ascii').splitlines()
        is_sfc = path == Path(sfc)
        output = [lines[0]] if is_sfc else []
        keys = []
        for line in (lines[1:] if is_sfc else lines):
            if not line.strip():
                continue
            a = line.split()
            key = hora_fin(*map(int, [a[0], a[1], a[2], a[4] if is_sfc else a[3]]))
            if key in target:
                output.append(line)
                keys.append(key)
        if list(dict.fromkeys(keys)) != target or (is_sfc and len(keys) != len(target)):
            raise ValueError('Recorte meteorológico incompleto')
        (dest/path.name).write_text('\n'.join(output)+'\n', encoding='ascii')
        selected[path.name] = {'origen': str(path), 'origen_sha256': sha256(path),
                                    'sha256': sha256(dest/path.name), 'registros': len(keys)}
    return dict(horas=len(target), ids=qa['ids'], archivos=selected)


def control_aermod(pol, ids, inicio, fin):
    target, _, _ = ventana(inicio, fin)
    if pol not in ('MP10', 'MP25'):
        raise ValueError('Contaminante inválido')
    last_day = target[-1]-timedelta(hours=1)
    start = datetime.fromisoformat(inicio)
    return f'''CO STARTING
CO TITLEONE Los Bronces - ensayo multidiario {inicio[:10]} UTC-3 provisional
CO MODELOPT DFAULT CONC
CO AVERTIME 1 24 PERIOD
CO POLLUTID {pol}
CO RUNORNOT RUN
CO ERRORFIL errores.out
CO FINISHED
SO STARTING
SO ELEVUNIT METERS
SO INCLUDED fuentes_aermod.inc
SO HOUREMIS {pol}.emi L000001-L001651
SO SRCGROUP ALL
SO FINISHED
RE STARTING
RE INCLUDED receptores.inc
RE FINISHED
ME STARTING
ME SURFFILE met.SFC FREE
ME PROFFILE met.PFL FREE
ME SURFDATA {ids['SF_ID']} {start.year}
ME UAIRDATA {ids['UA_ID']} {start.year}
ME SITEDATA {ids['OS_ID']} {start.year}
ME PROFBASE 3469.60 METERS
ME STARTEND {start:%Y %m %d} 1 {last_day:%Y %m %d} 24
ME FINISHED
OU STARTING
OU RECTABLE ALLAVE 1ST
OU POSTFILE 1 ALL PLOT receptor_horas.out
OU SUMMFILE resumen.sum
OU FINISHED
'''
