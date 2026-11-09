"""Contrato explícito entre geometría, selección HOUREMIS y serie horaria.

El ensayo usa una única selección contigua de identificadores. Se rechazan
otras sintaxis, en lugar de interpretar silenciosamente controles generales.
"""
from pathlib import Path
import math
import re


def validar_vinculo_horario(control, fuentes, emisiones, horas):
    control, fuentes, emisiones = map(Path, (control, fuentes, emisiones))
    locations = [s[2] for line in fuentes.read_text(encoding='ascii').splitlines()
                 if (s := line.split())[:2] == ['SO', 'LOCATION']]
    if not locations or len(locations) != len(set(locations)):
        raise ValueError('Identificadores LOCATION ausentes o duplicados')
    ids = set(locations)
    selections = [s for line in control.read_text(encoding='ascii').splitlines()
                  if (s := line.split())[:2] == ['SO', 'HOUREMIS']]
    if len(selections) != 1 or len(selections[0]) != 4:
        raise ValueError('Se requiere una selección HOUREMIS explícita')
    _, _, filename, span = selections[0]
    if filename != emisiones.name:
        raise ValueError('HOUREMIS apunta a otro archivo de emisiones')
    match = re.fullmatch(r'([A-Z]+)(\d+)-([A-Z]+)(\d+)', span)
    if not match:
        raise ValueError('Rango HOUREMIS no soportado por este ensayo')
    p1, n1, p2, n2 = match.groups()
    if p1 != p2 or len(n1) != len(n2) or int(n2) < int(n1):
        raise ValueError('Rango HOUREMIS inconsistente')
    # Limita la expansión antes de construir un conjunto potencialmente enorme.
    if int(n2)-int(n1)+1 != len(ids):
        raise ValueError('Rango HOUREMIS no cubre todas las fuentes LOCATION')
    selected = {f'{p1}{n:0{len(n1)}d}' for n in range(int(n1), int(n2)+1)}
    if selected != ids:
        raise ValueError('Identificadores HOUREMIS distintos de LOCATION')
    seen = {tuple(h): set() for h in horas}
    positive = False
    rows = 0
    with emisiones.open(encoding='ascii') as stream:
        for line in stream:
            if not line.strip() or line.lstrip().startswith('**'):
                continue
            fields = line.split()
            if len(fields) != 8 or fields[:2] != ['SO', 'HOUREMIS']:
                raise ValueError('Registro de emisiones no reconocido')
            hour = tuple(map(int, fields[2:6]))
            source, rate = fields[6], float(fields[7])
            if hour not in seen or source not in ids:
                raise ValueError('Hora o fuente de emisiones fuera del contrato')
            if source in seen[hour]:
                raise ValueError('Emisión duplicada para fuente/hora')
            if not math.isfinite(rate) or rate < 0:
                raise ValueError('Tasa de emisión inválida')
            seen[hour].add(source)
            rows += 1
            positive |= rate > 0
    if not seen or any(s != ids for s in seen.values()):
        raise ValueError('Faltan fuentes en al menos una hora de emisiones')
    if not positive:
        raise ValueError('Todas las emisiones del ensayo son nulas')
    return dict(fuentes=len(ids), horas=len(seen), filas=rows,
                seleccion=span, archivo=filename, vinculo_completo=True)
