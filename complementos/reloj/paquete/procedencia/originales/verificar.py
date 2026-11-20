"""Control escalar independiente de tiempos, residuos y SD desde los CSV fuente."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from bisect import bisect_left
from collections import defaultdict
import csv,hashlib,json,math
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/Sensibilidad_reloj_ternas_2026-11-15'
read=lambda p:list(csv.DictReader(Path(p).open(encoding='utf-8-sig',newline='')))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
protocol=json.loads((OUT/'Protocolo.json').read_text(encoding='utf8'))
paths={k:Path(v['path']) for k,v in protocol['inputs'].items()}
for k,p in paths.items():assert sha(p)==protocol['inputs'][k]['sha256']
obs={r['Fecha_original']:r for r in read(paths['observaciones'])}
model={}
for season in ['VERANO','INVIERNO']:
    data=sorted(read(paths['wrf_'+season.lower()]),key=lambda r:r['fecha_wrf_utc'])
    times=[datetime.fromisoformat(r['fecha_wrf_utc']).replace(tzinfo=timezone.utc).timestamp() for r in data]
    assert len(set(times))==len(times)
    model[season]=(times,data)
zones={'civil_santiago':ZoneInfo('America/Santiago'),'fijo_menos3':timezone(timedelta(hours=-3)),
       'fijo_menos4':timezone(timedelta(hours=-4)),'utc':timezone.utc}
cols=['residuo_T_C','residuo_u_m_s','residuo_v_m_s','residuo_WS_m_s']
max_error=0.;count=0;groups=defaultdict(list);sets=defaultdict(set)
for r in read(OUT/'Residuos_horarios_comunes.csv'):
    clock,op=r['caso'].split('__');raw=datetime.fromisoformat(r['Fecha_original'])
    actual=raw.replace(tzinfo=zones[clock]).astimezone(timezone.utc)
    assert actual==datetime.fromisoformat(r['fecha_objetivo_utc'])
    times,data=model[r['season']];t=actual.timestamp();i=bisect_left(times,t)
    assert 0<i<len(times)
    if op=='interpolacion_instantanea':
        assert 0<times[i]-times[i-1]<=3600
        alpha=(t-times[i-1])/(times[i]-times[i-1])
        val=[(1-alpha)*float(data[i-1][c])+alpha*float(data[i][c]) for c in ['T2_C','u_earth_m_s','v_earth_m_s']]
    else:
        k=i-1 if t-times[i-1]<=times[i]-t else i
        assert abs(t-times[k])<=900
        val=[float(data[k][c]) for c in ['T2_C','u_earth_m_s','v_earth_m_s']]
    o=obs[r['Fecha_original']];ws=float(o['Velocidad_viento_m_s']);angle=math.radians(float(o['Direccion_viento_grados']))
    observed=[float(o['Temperatura_aire_C']),-ws*math.sin(angle),-ws*math.cos(angle)]
    e=[a-b for a,b in zip(observed,val)]+[ws-math.hypot(val[1],val[2])]
    max_error=max(max_error,*[abs(v-float(r[c])) for c,v in zip(cols,e)])
    assert max_error<1e-9
    for c,v in zip(cols,e):groups[r['season'],clock,op,r['day'],c].append(v)
    sets[r['season'],clock,op].add(r['Fecha_original']);count+=1
daily=defaultdict(list)
for (season,clock,op,day,c),v in groups.items():
    assert len(v)>=18
    daily[season,clock,op,c].append(math.fsum(v)/len(v))
sd_error=0.
for row in read(OUT/'Amplitudes_SD.csv'):
    c=dict(T=cols[0],u=cols[1],v=cols[2],WS=cols[3])[row['variable']]
    v=daily[row['season'],row['clock'],row['operator'],c]
    mean=math.fsum(v)/len(v);sd=math.sqrt(math.fsum((x-mean)**2 for x in v)/(len(v)-1))
    sd_error=max(sd_error,abs(sd-float(row['sd'])))
assert sd_error<1e-9 and count==8*(734+686)
for season in ['VERANO','INVIERNO']:
    assert all(s==sets[season,'civil_santiago','interpolacion_instantanea'] for (se,c,o),s in sets.items() if se==season)
out=dict(status='INDEPENDENT_SCALAR_CHECK_PASSED',hour_case_rows=count,residual_values=count*4,
         max_residual_error=max_error,max_sd_error=sd_error,shared_observation_ids_verified=True,
         arithmetic_method='datetime/zoneinfo + bisect + interpolacion escalar + math.fsum; no importacion de la biblioteca de emparejamiento',
         protocol_sha256=sha(OUT/'Protocolo.json'),script_sha256=sha(__file__))
(OUT/'Verificacion_independiente.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(out,ensure_ascii=False,indent=2))
