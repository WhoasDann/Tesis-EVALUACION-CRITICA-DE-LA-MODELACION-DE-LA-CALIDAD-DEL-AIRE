from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OLD=Path('/archivo/usuario/Documents/Codex/2026-10-08/hem')
OUT=ROOT/'outputs/Contraste_ADC160_normativa_2026-11-05'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def dump(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
f=OLD/'outputs/BASE_verano_2026-10-21/Comunes/fuentes.csv';g=pd.read_csv(f)
inc=f.with_name('fuentes_aermod.inc');lines=inc.read_text().splitlines()
types={}
for line in lines:
    a=line.split()
    if a[:2]==['SO','LOCATION']:types[a[3]]=types.get(a[3],0)+1
assert types=={'LINE':12263}
receipt=read(ROOT/'outputs/Sensibilidad_estacional_2026-10-29/Recibos/VERANO_20170116_BASE_MP10.json')
assert sha(inc)=='f4683a6530aee6ba1303fee49b17ee2733fc400cff7473c634b7cbfe2258400e'
raw=read(OLD/'outputs/BASE_invierno_2026-10-24/Emisiones_y_observaciones.json')
annual=[]
for pol in ['MP10','MP25']:
    p=Path(raw[pol]['original']);assert sha(p)==raw[pol]['sha256']
    d=pd.read_csv(p,parse_dates=['fecha']);col=f'emision_{pol.lower()}_g_dia'
    assert not d.duplicated(['fecha','id_fuente_aermod']).any()
    assert d.fecha.dt.year.eq(2017).all() and d.fecha.nunique()==365
    annual.append(dict(pollutant=pol,source=str(p),sha256=sha(p),sources=d.id_fuente_aermod.nunique(),days=d.fecha.nunique(),
        mass_tonnes=float(d[col].sum()/1e6),inventory_scope='Original road-route daily input. Not automatically the full ADC-160vi inventory.',
        ADC160_total_primary_tonnes=3308 if pol=='MP10' else 573,
        ADC160_transit_tonnes=2357.2 if pol=='MP10' else 237.1))
pd.DataFrame(annual).to_csv(OUT/'Contraste_inventarios_anuales.csv',index=False)
rc=[]
names={(380148.,6331485.):'Los Bronces',(381128.,6323667.):'Piedra Carvajal',(384254.,6324494.):'Sulfatos',(381759.,6327947.):'La Paloma'}
rp=ROOT/'outputs/Sensibilidad_estacional_2026-10-29/Comunes/receptores.inc'
for line in rp.read_text().splitlines():
    a=line.split();x,y,z,h=map(float,a[2:6])
    if (x,y) in names:rc.append(dict(receptor=names[x,y],x=x,y=y,elevation_m=z,hill_m=h))
assert len(rc)==4
pd.DataFrame(rc).to_csv(OUT/'Receptores_AERMOD_actuales.csv',index=False)
check=[]
bindings=read(ROOT/'outputs/Sensibilidad_estacional_2026-10-29/Vinculo_emisiones.json')['cases']
for season,day in [('VERANO','2017-01-16'),('INVIERNO','2017-07-09')]:
    item=next(r for r in bindings if r['season']==season and r['day']==day and r['pollutant']=='MP10')
    p=Path(item['source']['path']);assert sha(p)==item['source']['sha256']
    by_hour={}
    for line in p.read_text().splitlines():
        a=line.split();hour=int(a[5]);by_hour.setdefault(hour,[]).append((a[6],float(a[7])))
    first=by_hour[min(by_hour)]
    assert len(by_hour)==24 and len(first)==12263 and all(rows==first for rows in by_hour.values())
    check.append(dict(season=season,day=day,path=str(p),sha256=sha(p),hours=24,sources=12263,
        rates_constant_within_day=True,interpretation='Verified for these two files. Generator implements daily_mass/86400 for all days.'))
dump('Auditoria_comparabilidad.json',dict(source_geometry=str(f),source_geometry_sha256=sha(f),
     native_source_types=types,native_source_sha256=sha(inc),parent_road_arcs=int(g.id_arco_original.nunique()),
     source_network_counts=g.red.value_counts().to_dict(),inventory_annual=annual,example_hourly_files=check,
     receptors=rc,receptors_sha256=sha(rp),
     conclusion='Current case is road-source primary PM sensitivity; complete replication of total ADC-160vi project is not established.',
     native_models_rerun=0))
print(json.dumps({'annual':annual,'networks':g.red.value_counts().to_dict(),'receptors':rc,'native_source_types':types},default=str))
