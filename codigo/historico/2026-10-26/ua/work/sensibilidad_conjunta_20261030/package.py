"""Freeze new seasonal inputs; reuse the two audited comparison corners."""
from pathlib import Path
import sys, copy, hashlib, re, shutil, zipfile
import pandas as pd
from campaign import ROOT, OUT, PILOT, OLD, WORK, CONFIG, NEW, SCENARIOS, read, save, sha, rec, now
WINROOT='C:/Users/Daniel/Documents/Tesis_Calculo_20261027'
ROCKROOT='/home/usuario/tesis_aermod_20261026'
REMOTE={'windows3':WINROOT+'/jobs/joint_T_WS_20261030','rocky':ROCKROOT+'/joint_T_WS_20261030'}
CANARY_DAYS=['2017-02-11','2017-08-02']

def main():
    assert read(OUT/'Verificacion_meteorologia.json')['status']=='PASSED'
    assert not (OUT/'Reparto.json').exists()
    (OUT/'Inputs').mkdir();(OUT/'Lotes').mkdir()
    oldcases=read(PILOT/'Casos.json')['cases']; oldcatalog=read(PILOT/'Catalogo_inputs.json')
    catalog={}; cases=[]; reuse=[]
    def existing(h):
        if h not in catalog:
            meta=oldcatalog[h]; assert sha(meta['path'])==h
            catalog[h]=meta
        return h
    def put(text):
        data=text.encode('ascii');h=hashlib.sha256(data).hexdigest();p=OUT/'Inputs'/h
        if not p.exists():p.write_bytes(data)
        assert sha(p)==h;catalog[h]=dict(path=str(p),bytes=len(data));return h
    for c in oldcases:
        if c['scenario'] not in ['BASE','T_PLUS']:continue
        cc=copy.deepcopy(c);rpath=PILOT/'Recibos'/(c['id']+'.json');r=read(rpath)
        assert r['status']=='SCIENTIFIC_RECEPTION_PASSED'
        cc.update(host='reused',result_folder=r['result_folder'])
        for h in cc['inputs'].values():existing(h)
        reuse.append(dict(id=c['id'],receipt=rec(rpath),result_folder=r['result_folder']))
        cases.append(cc)
    assert len(cases)==728
    for season in CONFIG:
        full={sc:{k:(OUT/'Meteorologia'/season/sc/('met.'+k)).read_text().splitlines() for k in ['SFC','PFL']} for sc in NEW}
        for old in [c for c in oldcases if c['season']==season and c['scenario']=='BASE']:
            day=pd.Timestamp(old['day']);hours=[int(k[-2:]) for k in old['hour_states']]
            for sc in NEW:
                c=copy.deepcopy(old);c.pop('result_folder',None)
                c.update(scenario=sc,id=f"{season}_{day:%Y%m%d}_{sc}_{old['pollutant']}")
                c['folder']='Casos/'+c['id'];c.pop('host',None)
                inputs={n:existing(h) for n,h in old['inputs'].items() if n not in ['met.SFC','met.PFL','aermod.inp']}
                for kind in ['SFC','PFL']:
                    raw=full[sc][kind]
                    lines=[l for l in (raw[1:] if kind=='SFC' else raw) if tuple(map(int,l.split()[:3]))==(day.year,day.month,day.day) and int(l.split()[4 if kind=='SFC' else 3]) in hours]
                    assert len(lines)==len(hours)*(1 if kind=='SFC' else 29)
                    inputs['met.'+kind]=put('\n'.join((raw[:1] if kind=='SFC' else [])+lines)+'\n')
                source=Path(oldcatalog[old['inputs']['aermod.inp']]['path']);assert sha(source)==old['inputs']['aermod.inp']
                inp=re.sub(r'CO TITLEONE.*',f'CO TITLEONE Joint T WS {season} {day:%Y%m%d} {sc} panel40',source.read_text())
                assert re.sub(r'CO TITLEONE.*','',inp)==re.sub(r'CO TITLEONE.*','',source.read_text())
                inputs['aermod.inp']=put(inp);c['inputs']=inputs;cases.append(c)
    assert len(cases)==1456 and len({c['id'] for c in cases})==1456
    weights={'local':.37,'rocky':.37,'windows3':.26};counts={s:{h:0 for h in weights} for s in CONFIG};assignments={}
    for s in CONFIG:
        days=sorted({c['day'] for c in cases if c['season']==s})
        # Reference canaries are ordinary local production cases, never duplicated locally.
        days.sort(key=lambda d:(d not in CANARY_DAYS,d))
        for day in days:
            h='local' if day in CANARY_DAYS else min(weights,key=lambda h:counts[s][h]/weights[h])
            counts[s][h]+=1;assignments[s,day]=h
    for c in cases:
        if c['host'] if 'host' in c else False:continue
        c['host']=assignments[c['season'],c['day']]
    olda=read(PILOT/'Reparto.json');hosts={}
    for h in weights:
        target=OUT/'Lotes'/h;target.mkdir()
        for name,src in [('batch_runner.py',WORK/'batch_runner.py'),('membresia.csv',OUT/'Comunes/membresia.csv')]:shutil.copy2(src,target/name)
        root=str(target) if h=='local' else REMOTE[h]
        selected=copy.deepcopy([c for c in cases if c['host']==h])
        selected.sort(key=lambda c:(c['day'] not in CANARY_DAYS,(pd.Timestamp(c['day'])-pd.Timestamp(CONFIG[c['season']]['start'])).days,c['season'],NEW.index(c['scenario']),c['pollutant']))
        for c in selected:c['input_sources']={n:catalog[hh]['path'] if h=='local' else root+'/blobs/'+hh for n,hh in c['inputs'].items()}
        pp=read(olda['hosts'][h]['plan'])
        pp.update(cases=selected,dependencies={n:sha(target/n) for n in ['batch_runner.py','membresia.csv']},allowed_input_roots=[str(OLD/'outputs'),str(PILOT),str(OUT),'D:/Tesis_Dan/BASE_invierno_2026-10-24/Emisiones'] if h=='local' else [root+'/blobs'])
        if h=='local':pp['binary']=str(OUT/'Binarios/aermod.exe')
        save(target/'plan.json',pp)
        hosts[h]=dict(root=root,plan=str(target/'plan.json'),plan_sha256=sha(target/'plan.json'),assigned=len(selected),days_by_season=counts and {s:counts[s][h] for s in CONFIG})
    canaries=[c['id'] for c in cases if c['day'] in CANARY_DAYS and c['scenario'] in NEW and c['pollutant']=='MP10']
    assert len(canaries)==4 and all(next(c for c in cases if c['id']==cid)['host']=='local' for cid in canaries)
    save(OUT/'Canarios_planificados.json',dict(reference_local_case_ids=canaries,linux_gate='All4native comparisons must pass before Linux production. Old8canaries remain archived separately.'))
    save(OUT/'Casos.json',dict(cases=cases));save(OUT/'Catalogo_inputs.json',catalog)
    save(OUT/'Reutilizacion.json',dict(status='FROZEN_REFERENCES_TO_AUDITED_RESULTS',count=728,cases=reuse))
    for h in ['rocky','windows3']:
        target=OUT/'Lotes'/h;extra=[c for c in cases if c['id'] in canaries] if h=='rocky' else []
        hashes={hh for c in read(target/'plan.json')['cases']+extra for hh in c['inputs'].values()}
        archive=OUT/(h+'.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
            for f in target.iterdir():z.write(f,f.name)
            for hh in sorted(hashes):z.write(catalog[hh]['path'],'blobs/'+hh)
        hosts[h]['archive']=rec(archive)
    save(OUT/'Reparto.json',dict(created_utc=now(),total=1456,new=728,reused=728,hosts=hosts,canaries=4,exclusive_whole_days=True,weights=weights))
    records=sum(len(c['hour_states'])*40 for c in cases);valid=sum(sum(v=='VALIDA' for v in c['hour_states'].values())*40 for c in cases)
    save(OUT/'Cobertura_esperada.json',dict(comparison_cases=1456,new_cases=728,reused_cases=728,hourly_values=records,valid_hourly_values=valid,masked_hourly_values=records-valid,new_hourly_values=records//2,new_valid_hourly_values=valid//2,new_masked_hourly_values=(records-valid)//2,winter_civil_days=92))
    print({h:v['assigned'] for h,v in hosts.items()},flush=True)

if __name__=='__main__':main()
