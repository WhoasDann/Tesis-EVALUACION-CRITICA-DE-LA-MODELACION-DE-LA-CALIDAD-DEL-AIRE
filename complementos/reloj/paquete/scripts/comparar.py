"""Coteja todas las celdas de las siete tablas con la referencia archivada."""
from pathlib import Path
import csv,hashlib,json,math

def comparar(root,out):
    results=[]
    for expected in sorted((root/'referencia/tablas').glob('*.csv')):
        actual=out/expected.name
        with expected.open(encoding='utf-8-sig',newline='') as f:
            er=csv.DictReader(f);fields=er.fieldnames;e=list(er)
        with actual.open(encoding='utf-8-sig',newline='') as f:
            ar=csv.DictReader(f);a=list(ar)
            if ar.fieldnames!=fields or len(a)!=len(e):
                raise ValueError(f'Estructura distinta: {expected.name}')
        maximum=0.;numeric=0;categorical=0
        for i,(want,got) in enumerate(zip(e,a),2):
            for key in fields:
                x,y=want[key],got[key]
                try:
                    fx,fy=float(x),float(y)
                except ValueError:
                    categorical+=1
                    if x!=y:
                        raise ValueError(f'Diferencia textual: {expected.name}:{i}:{key}')
                else:
                    numeric+=1
                    if math.isnan(fx) and math.isnan(fy):
                        continue
                    if not (math.isfinite(fx) and math.isfinite(fy)):
                        raise ValueError(f'Valor no finito: {expected.name}:{i}:{key}')
                    err=abs(fx-fy);maximum=max(maximum,err)
                    if err>1e-9:
                        raise ValueError(f'Diferencia numérica: {expected.name}:{i}:{key}: {err}')
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        results.append(dict(file=expected.name,rows=len(e),numeric_cells=numeric,
            text_cells=categorical,max_abs_error=maximum,byte_identical=sha(actual)==sha(expected)))
    if len(results)!=7:
        raise ValueError('Se esperaban siete tablas de referencia.')
    receipt=dict(status='ALL_TABLES_REPRODUCED',atol=1e-9,rtol=0.,
        categorical_match='exact',tables=results)
    (out/'Comparacion_referencia.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    return receipt
