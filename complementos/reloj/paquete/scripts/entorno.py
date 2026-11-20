"""Rutas del paquete; las rutas históricas del protocolo son solo procedencia."""
from pathlib import Path
import json,os
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ['TESIS_RELOJ_SALIDA']).resolve()
mapping=json.loads((ROOT/'Entradas_portatiles.json').read_text(encoding='utf8'))
paths={k:(ROOT/v['relative_path']).resolve() for k,v in mapping.items()}
for p in paths.values():
    if not p.is_relative_to(ROOT):
        raise ValueError('Un insumo queda fuera del paquete.')
