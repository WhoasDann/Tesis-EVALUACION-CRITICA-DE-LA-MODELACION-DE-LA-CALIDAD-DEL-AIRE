"""Reconstitución de entradas y análisis de resultados de la tesis Los Bronces."""
import argparse
from array import array
from collections import defaultdict
import csv
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
INPUTS = ROOT / 'datos/aermod'
HOURLY = ROOT / 'datos/horarios'

def read_catalog():
    with gzip.open(INPUTS/'catalogo.json.gz', 'rt', encoding='utf-8') as stream:
        return json.load(stream)

def checked(raw, digest):
    if hashlib.sha256(raw).hexdigest()!=digest:
        raise ValueError(f'El contenido difiere del SHA-256 {digest}')
    return raw

def read_object(catalog, digest):
    with zipfile.ZipFile(INPUTS/(catalog['objetos'][digest]+'.zip')) as package:
        return checked(package.read(digest),digest)

def materialize(catalog, case_id, target):
    case = catalog['casos'][case_id]
    day = date.fromisoformat(case['day'])
    if target.exists():
        raise FileExistsError(f'La carpeta de destino ya existe: {target}')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        folder=Path(temp)/'caso'; folder.mkdir()
        for name,digest in case['inputs'].items():
            if not name.endswith('.emi'):
                (folder/name).write_bytes(read_object(catalog,digest))
                continue
            hasher=hashlib.sha256()
            with (folder/name).open('wb') as fh:
                previous=None
                for hour,key in catalog['emisiones'][digest]:
                    if previous!=key:
                        rates=read_object(catalog,key)
                        previous=key
                    prefix=f'SO HOUREMIS {day.year%100:02d} {day.month:2d} {day.day:2d} {hour:2d} '.encode()
                    block=prefix+rates[:-1].replace(b'\n',b'\n'+prefix)+b'\n'
                    fh.write(block);hasher.update(block)
            if hasher.hexdigest()!=digest:raise ValueError(f'Emisiones incompatibles en {case_id}')
        folder.rename(target)

def reference_hours(case_id,case):
    with zipfile.ZipFile(HOURLY/(case['day'][:7]+'.zip')) as stream:
        values=array('q');values.frombytes(stream.read(case_id+'.i64'))
    if sys.byteorder!='little':values.byteswap()
    hours=sorted(case['hour_states'])
    if len(values)!=40*len(hours):raise ValueError(case_id)
    return hours,values

def civil_mapping():
    mapping={}
    for season in ('VERANO','INVIERNO'):
        with (ROOT/f'datos/calendarios/{season}.csv').open(encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                lst=row['inicio_local'] if season=='VERANO' else row['inicio_LST']
                civil=lst[:10] if season=='VERANO' else row['inicio_civil'][:10]
                key=lst[2:10].replace('-','')+f'{int(lst[11:13])+1:02d}'
                mapping[season,key]=civil
    return mapping

def mean_table(catalog,dest):
    coordinates=json.loads((HOURLY/'coordenadas.json').read_text())
    with (ROOT/'datos/receptores.csv').open(encoding='utf-8-sig') as f:
        receptor_indices={r['receptor']:coordinates.index([float(r['x']),float(r['y'])]) for r in csv.DictReader(f)}
    calendar=civil_mapping()
    sums=defaultdict(int);counts=defaultdict(int)
    for ident,case in catalog['casos'].items():
        if case['scenario'].startswith('OBS_'):continue
        hours,values=reference_hours(ident,case)
        for ix,hour in enumerate(hours):
            if case['hour_states'][hour]!='VALIDA':continue
            day=calendar[case['season'],hour]
            for name,ri in receptor_indices.items():
                k=(case['season'],day,case['scenario'],case['pollutant'],name)
                sums[k]+=values[ix*40+ri];counts[k]+=1
    daily={k:sums[k]/(24*100000) for k,n in counts.items() if n==24}
    groups=defaultdict(set)
    for season,day,scenario,pm,name in daily:groups[season,scenario,pm,name].add(day)
    common={s:set.intersection(*(g for k,g in groups.items() if k[0]==s)) for s in ('VERANO','INVIERNO')}
    assert {s:len(v) for s,v in common.items()}=={'VERANO':87,'INVIERNO':90}
    results={k:sum(daily[k[0],day,*k[1:]] for day in sorted(common[k[0]]))/len(common[k[0]]) for k in groups}
    with (ROOT/'resultados/Medias_propias_dias_comparables.csv').open(encoding='utf-8-sig') as f:
        expected={(r['season'],r['scenario'],r['pollutant'],r['receptor']):float(r['mean_strict']) for r in csv.DictReader(f)}
    assert results.keys()==expected.keys() and len(results)==144
    error=max(abs(v-expected[k]) for k,v in results.items());assert error<1e-9,error
    dest.mkdir(exist_ok=True,parents=True)
    with (dest/'medias.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['temporada','escenario','fraccion','receptor','dias','media_ug_m3'])
        for k,v in sorted(results.items()):w.writerow([*k,len(common[k[0]]),v])
    print(f'144 medias verificadas desde los valores horarios. Error absoluto máximo: {error:.3g} µg/m³.')

def check_case(catalog,case_id,path):
    case=catalog['casos'][case_id];hours,reference=reference_hours(case_id,case)
    coords=[tuple(p) for p in json.loads((HOURLY/'coordenadas.json').read_text())]
    records={}
    for row in path.read_bytes().splitlines():
        if not row.strip() or row.lstrip().startswith(b'*'):continue
        fields=row.split();k=(fields[8].decode().zfill(8),float(fields[0]),float(fields[1]))
        if k in records:raise ValueError(f'Hora/receptor duplicado: {k}')
        records[k]=round(float(fields[2])*100000)
    if len(records)!=len(reference):raise ValueError('Cobertura horaria distinta')
    delta=max(abs(records[(h,*p)]-reference[i*40+j]) for i,h in enumerate(hours) for j,p in enumerate(coords))
    print(f'{len(reference)} valores cotejados. Diferencia absoluta máxima: {delta/100000:.5f} µg/m³')
    if delta:raise SystemExit(1)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='operation',required=True)
    commands.add_parser('listar').add_argument('--filtro',default='')
    m=commands.add_parser('caso');m.add_argument('id');m.add_argument('carpeta',type=Path)
    c=commands.add_parser('comparar');c.add_argument('id');c.add_argument('postfile',type=Path)
    commands.add_parser('medias').add_argument('carpeta',type=Path)
    commands.add_parser('verificar')
    args=parser.parse_args()
    if args.operation=='verificar':
        with (ROOT/'MANIFIESTO.sha256').open(encoding='utf-8') as f:
            for line in f:
                digest,path=line.rstrip('\n').split('  ',1);checked((ROOT/path).read_bytes(),digest)
        print('Integridad verificada.');return
    catalog=read_catalog()
    if args.operation=='listar':
        for ident in catalog['casos']:
            if args.filtro in ident:print(ident)
    elif args.operation=='caso':materialize(catalog,args.id,args.carpeta)
    elif args.operation=='comparar':check_case(catalog,args.id,args.postfile)
    else:mean_table(catalog,args.carpeta)

if __name__=='__main__':main()
