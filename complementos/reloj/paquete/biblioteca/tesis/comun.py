from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

PERIODOS = {
    'VERANO': ('2016-12-21 00:00', '2017-03-21 00:00'),
    'INVIERNO': ('2017-06-21 00:00', '2017-09-21 00:00'),
}

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def guardar_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def salida_nueva(path):
    """No permite sobrescribir un producto de otra ejecución."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=False)
    return p

def periodo(fechas):
    t = pd.DatetimeIndex(fechas)
    if t.tz is not None:
        raise ValueError('Se requiere fecha en el reloj de análisis explícitamente elegido, sin tz.')
    out = np.full(len(t), 'FUERA', dtype=object)
    for name, (start, end) in PERIODOS.items():
        out[(t >= start) & (t < end)] = name
    return out

def unique_times(frame, column):
    if frame[column].isna().any() or frame[column].duplicated().any():
        raise ValueError(f'{column}: hay fechas nulas o duplicadas; resolver antes de alinear.')

def finito(*arrays):
    if not all(np.isfinite(np.asarray(x, dtype=float)).all() for x in arrays):
        raise ValueError('Se recibieron valores ausentes o no finitos.')
