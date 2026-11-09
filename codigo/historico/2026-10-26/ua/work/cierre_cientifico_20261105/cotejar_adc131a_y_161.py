"""Read the 2017 summary, two road workbooks and the contents of the local ADC-161 ZIP."""
from pathlib import Path
from collections import Counter
from datetime import date, datetime, timedelta
import hashlib
import json
import math
import zipfile
import numpy as np
import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/Contraste_ADC160_normativa_2026-11-05'
ORIG = Path('/archivo/usuario/OneDrive/Escritorio/Conglomerado/Anexo_Los_Bronces')
ANNUAL = Path('/archivo/usuario/Codigos_VSC/Codigos_oficiales/AERMOD_TODOS_LOS_CAMINOS')
DAYS = [date(2017, 1, 1) + timedelta(days=i) for i in range(365)]

def signature(p):
    with p.open('rb') as f:
        return {'path': str(p), 'bytes': p.stat().st_size, 'sha256': hashlib.file_digest(f,'sha256').hexdigest()}

def observed_inputs(pm):
    raw = pd.read_csv(ANNUAL / f'emisiones_diarias_{pm}.csv')
    mass = raw.pivot(index='id_ruta_excel', columns='fecha', values=f'emision_{pm.lower()}_g_dia')
    assert list(mass.columns) == [d.isoformat() for d in DAYS] and len(mass) == 873
    assert np.isfinite(mass.values).all()
    return mass

def compare_book(path, inputs):
    w = load_workbook(path, data_only=True, read_only=True)
    rows_by_pm = {k:{} for k in inputs}
    pm = None
    for row in w['EMISION EFICIENCIA'].values:
        if row[1] == 'ID':
            pm = {'MP10 (G/AÑO)':'MP10', 'MP2.5 (G/AÑO)':'MP25'}.get(row[0])
            if pm:
                assert [t.date() for t in row[5:370]] == DAYS
        elif pm and isinstance(row[1],int):
            route = row[1]
            assert route not in rows_by_pm[pm]
            rows_by_pm[pm][route] = (row[3], row[5:370])
    w.close()
    result = {}
    for pm, routes in rows_by_pm.items():
        frame = inputs[pm]
        assert set(frame.index) <= set(routes)
        ids = sorted(routes)
        raw = [routes[k][1] for k in ids]
        invalid = Counter(type(v).__name__ + ':' + str(v) for rr in raw for v in rr if type(v) not in (int,float))
        if invalid:
            result[pm] = {'routes':len(routes),'non_numeric_cells':dict(invalid),'status':'INCOMPLETE_CACHE'}
            continue
        arr = pd.DataFrame(np.array(raw,dtype=float),index=ids)
        assert np.isfinite(arr.values).all() and arr.values.min() >= 0
        common = arr.loc[frame.index].to_numpy()
        other = arr.loc[arr.index.difference(frame.index)]
        delta = common - frame.to_numpy()
        masses = sorted([(int(k), routes[k][0], float(v)/1e6) for k, v in other.sum(axis=1).items() if v>0],key=lambda r:-r[2])
        result[pm] = {'status':'CHECKED','routes':len(routes),'dates':365,'csv_routes':len(frame),
            'csv_total_t':float(frame.to_numpy().sum())/1e6, 'excel_all_t':float(arr.to_numpy().sum())/1e6,
            'excel_same_ids_t':float(common.sum())/1e6, 'excel_other_ids_t':float(other.to_numpy().sum())/1e6,
            'max_abs_cell_diff_g':float(np.abs(delta).max()), 'compared_cells':int(delta.size),
            'matched_cells_at_csv_precision':int(np.isclose(common,frame.to_numpy(),rtol=1e-10,atol=1e-8).sum()),
            'other_ids_with_mass':len(masses), 'other_ids_top_by_mass':masses[:12]}
    return {'source':signature(path),'sheet':'EMISION EFICIENCIA','method':'Valores almacenados, ID de ruta y 365 fechas; columnas F:NF. Masa en gramos, sumada y dividida por 1e6 para toneladas. No se recalcularon formulas.', 'comparison': result}

summary_path=next((ORIG/'ANEXO ADC-131a').glob('*.xlsx'))
workbook=load_workbook(summary_path,read_only=True,data_only=True)
s=workbook['Caso Base 2017']
summary={'source':signature(summary_path),'sheet':s.title,'cells':{c:s[c].value for c in ['C9','D9','C10','K10','N10','C16','D16','K16']}}
assert summary['cells']['C9']==2357.2 and summary['cells']['D9']==237.1
workbook.close()
inputs={k:observed_inputs(k) for k in ['MP10','MP25']}
books=[compare_book(p,inputs) for p in sorted(ORIG.glob('IE_TPTE_Caso Base 2017*.xlsx'))]
zpath=ORIG/'ANEXO ADC-161/Concentraciones.zip'
with zipfile.ZipFile(zpath) as z:
    assert z.testzip() is None
    members=[{'name':n,'bytes':len(z.read(n))} for n in z.namelist()]
    assert all(n['name'].lower().endswith('.txt') for n in members)
    assert any(b'cannot be downloaded' in z.read(n) for n in z.namelist())
alternate=[]
for p in sorted((ORIG/'Archivos de Modelación').rglob('CALPUFF.INP')):
    with p.open(encoding='cp1252') as f: header=[f.readline().strip() for n in range(3)]
    alternate.append({'relative_path':str(p.relative_to(ORIG)), 'header':header})
result={'ADC131a':summary,'ADC131a_cover':signature(ORIG/'ANEXO ADC-131a/ANEXO ADC-131a.pdf'),
        'separate_road_workbooks':books,'ADC161_archive':dict(signature(zpath),members=members,contains_model=False),
        'alternative_CALPUFF_headers':alternate,'models_run':0}
(OUT/'Cotejo_apendices_locales.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps([(b['source']['path'],{p:{k:v for k,v in c.items() if k!='other_ids_top_by_mass'} for p,c in b['comparison'].items()}) for b in books],indent=2))
