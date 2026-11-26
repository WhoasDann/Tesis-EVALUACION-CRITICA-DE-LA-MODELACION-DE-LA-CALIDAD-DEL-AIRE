from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd
from integridad import verificar
root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description='SD muestral horaria observada del diseño final.')
parser.add_argument('salida',type=Path);args=parser.parse_args()
verificar(root)
data=pd.read_csv(root/'datos/Observaciones_validas_T_WS.csv.gz')
ref=json.loads((root/'referencia/Amplitudes.json').read_text(encoding='utf-8'))
records=[]
for season,frame in data.groupby('season'):
    assert frame.Fecha_original.is_unique
    assert frame.groupby('day').size().ge(18).all()
    assert len(frame)==ref['coverage'][season]['admitted_hours']
    assert frame.day.nunique()==ref['coverage'][season]['admitted_days']
    assert np.isfinite(frame[['T','WS']]).all().all()
    for variable in ['T','WS']:
        value=float(frame[variable].std(ddof=1))
        np.testing.assert_allclose(value,ref['scales'][season][variable],rtol=0,atol=1e-12)
        records.append(dict(season=season,variable=variable,sd=value,hours=len(frame),days=frame.day.nunique()))
args.salida.mkdir(parents=True,exist_ok=False)
(args.salida/'Amplitudes.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
(args.salida/'Verificacion.json').write_text(json.dumps(dict(status='PASSED',registros=len(data),amplitudes=len(records))),encoding='utf-8')
print(json.dumps(records))
