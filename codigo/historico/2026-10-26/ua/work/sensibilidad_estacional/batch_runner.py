"""Portable AERMOD batch executor. Scientific post-processing remains in the original verified Windows reader."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import collections, hashlib, json, math, os, re, shutil, subprocess, sys, tarfile, threading, time, traceback

def now(): return datetime.now(timezone.utc).isoformat()
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()
def save(p,d):
    p=Path(p);tmp=p.with_name(p.name+'.tmp')
    tmp.write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8')
    os.replace(tmp,p)
def check(ok,msg):
    if not ok:raise ValueError(msg)
def safe(root,rel):
    p=(root/rel).resolve()
    check(p.is_relative_to(root.resolve()),'Path outside batch')
    return p
def validate(folder,case):
    text=(folder/'aermod.out').read_text(encoding='ascii')
    check('AERMOD Finishes Successfully' in text,'No successful AERMOD completion')
    fatal=re.findall(r'A Total of\s+(\d+)\s+Fatal Error',text)
    check(fatal and not any(map(int,fatal)),'Fatal error or missing fatal-error count')
    dims=re.search(r'This Run Includes:\s+(\d+) Source\(s\);\s+\d+ Source Group\(s\); and\s+(\d+) Receptor\(s\)',text)
    check(dims and tuple(map(int,dims.groups()))==(case['sources'],case['receptors']),'Wrong dimensions')
    check(re.search(r'Output Units\s*=\s*MICROGRAMS/M\*\*3',text),'Wrong output units')
    summary=(folder/'resumen.sum').read_text(encoding='ascii')
    states=case['hour_states']
    check(set(states.values()) <= {'VALIDA','CALMA','FALTANTE_AERMET_I71','AUSENCIA_WRF','EXCLUSION_PRECIPITACION_2H'},'Unknown meteorological state')
    check(bool(states),'Empty calendar')
    counts={}
    for label,expected in [('Hours Were Processed',len(states)),('Calm Hours Identified',sum(v=='CALMA' for v in states.values())),
                           ('Missing Hours Identified',sum(v not in ('VALIDA','CALMA') for v in states.values()))]:
        m=re.search(r'A Total of\s+(\d+)\s+'+label,summary)
        check(m and int(m[1])==expected,'Wrong native count: '+label)
        counts[label]=int(m[1])
    coords={}
    for line in (folder/'receptores.inc').read_text(encoding='ascii').splitlines():
        t=line.split()
        check(t[:2]==['RE','DISCCART'],'Unexpected receptor syntax')
        xy=tuple(map(float,t[2:4]))
        check(xy not in coords,'Duplicate receptor')
        coords[xy]=tuple(map(float,t[4:6]))
    check(len(coords)==case['receptors'],'Receptor count mismatch')
    seen=set();sums=collections.defaultdict(float);maxc=0.0
    validhours=sum(v=='VALIDA' for v in states.values());check(validhours>0,'No valid hours')
    for line in (folder/'receptor_horas.out').open(encoding='ascii'):
        if not line.strip() or line.startswith('*'):continue
        t=line.split();check(len(t)>=9,'Invalid POSTFILE row')
        x,y,c,elev,hill,flag=map(float,t[:6]);xy=(x,y);date=t[8]
        check(all(math.isfinite(v) for v in (x,y,c,elev,hill,flag)) and c>=0 and flag==0,'Invalid concentration or coordinates')
        check(xy in coords and date in states and t[6:8]==['1-HR','ALL'],'Unexpected receptor/hour/group')
        check(abs(elev-coords[xy][0])<=.011 and abs(hill-coords[xy][1])<=.011,'Terrain mismatch')
        key=(xy,date);check(key not in seen,'Duplicate receptor/hour');seen.add(key)
        if states[date]=='VALIDA':
            sums[xy]+=c;maxc=max(maxc,c)
        else:check(c==0,'Missing or calm hour must retain native zero')
    check(len(seen)==len(coords)*len(states),'Incomplete POSTFILE')
    m=re.search(r'SUMMARY OF HIGHEST\s+1-HR RESULTS.*?ALL\s+HIGH\s+1ST HIGH VALUE IS\s+([\d.]+)',summary,re.S)
    check(m and abs(float(m[1])-maxc)<=1.1e-5,'Native hourly maximum mismatch')
    error24=None
    if len(states)==24:
        seen24=set();error24=0.0
        for line in (folder/'receptor_24h.out').open(encoding='ascii'):
            if not line.strip() or line.startswith('*'):continue
            t=line.split();xy=tuple(map(float,t[:2]));c=float(t[2])
            check(xy in coords and xy not in seen24 and t[6:8]==['24-HR','ALL'],'Invalid 24h output')
            check(t[8]==min(states)[:6]+'24','Incorrect 24h date')
            check(math.isfinite(c) and c>=0,'Invalid 24h value')
            seen24.add(xy);error24=max(error24,abs(c-sums[xy]/max(validhours,18)))
        check(seen24==coords.keys() and error24<=1.1e-5,'Incomplete or inconsistent daily average')
    return dict(status='NATIVE_CHECK_PASSED',hours=len(states),valid_hours=validhours,native_counts=counts,
                values=len(seen),masked_values=(len(states)-validhours)*len(coords),max_1h=maxc,max_24h_error=error24,
                warning_codes=dict(collections.Counter(re.findall(r'\bW\d{3}\b',(folder/'errores.out').read_text()))))


def source_for(plan,c,name):
    source=Path(c['input_sources'][name]).resolve()
    check(any(source.is_relative_to(Path(p).resolve()) for p in plan['allowed_input_roots']),'Input source outside frozen roots')
    check(source.is_file(),'Missing input source '+name)
    return source

def product_hash(root,folder,cid,name):
    if (folder/name).exists():return sha(folder/name)
    archive=root/'exports'/(cid+'.tar.gz')
    with tarfile.open(archive,'r:gz') as tar:
        member=tar.getmember(name);check(member.isfile() and member.name==Path(name).name,'Invalid archive product')
        return hashlib.sha256(tar.extractfile(member).read()).hexdigest()

def compact(root,folder,c):
    archive=root/'exports'/(c['id']+'.tar.gz')
    r=json.loads((folder/'receipt.json').read_text())
    compacted=[]
    for name in ['aermod.out','errores.out']:
        check(sha(folder/name)==r['outputs'][name],'Product changed before compacting')
        with tarfile.open(archive,'r:gz') as tar:
            data=tar.extractfile(name).read()
            check(hashlib.sha256(data).hexdigest()==r['outputs'][name],'Archive not identical')
        (folder/name).unlink();compacted.append(name)
    ephemeral=[]
    for name in c['inputs']:
        if name.endswith('.emi') or name=='fuentes_aermod.inc':
            check(sha(folder/name)==c['inputs'][name],'Staged input changed')
            (folder/name).unlink();ephemeral.append(name)
    save(folder/'Storage.json',dict(archive=str(archive),archive_sha256=sha(archive),compacted_products=compacted,temporary_inputs_removed=ephemeral,input_sources=c['input_sources']))

def compare_reference(folder):
    def read_values(path):
        values={}
        for line in Path(path).read_text().splitlines():
            if not line.strip() or line.startswith('*'):continue
            t=line.split();key=(float(t[0]),float(t[1]),t[8])
            check(key not in values,'Duplicate canary key');values[key]=float(t[2])
        return values
    a=read_values(folder/'receptor_horas.out');b=read_values(folder/'reference.out')
    check(a.keys()==b.keys(),'Cross-platform keys differ')
    errors=[abs(a[k]-b[k]) for k in b]
    failures=[k for k in b if abs(a[k]-b[k])>2e-5+1e-5*abs(b[k])]
    check(not failures,'Cross-platform concentration check failed')
    return dict(status='PASSED',values=len(b),absolute_tolerance_ug_m3=2e-5,relative_tolerance=1e-5,max_absolute_error=max(errors))


def main(planpath):
    planpath=Path(planpath).resolve();root=planpath.parent;plan=json.loads(planpath.read_text())
    binary=Path(plan['binary']);check(sha(binary)==plan['binary_sha256'],'Binary hash mismatch')
    for n,h in plan['dependencies'].items():check(sha(safe(root,n))==h,'Dependency changed: '+n)
    check(len({c['id'] for c in plan['cases']})==len(plan['cases']),'Duplicate assigned task')
    check(plan['max_workers']==2,'Unexpected concurrency')
    (root/'receipts').mkdir(exist_ok=True);(root/'exports').mkdir(exist_ok=True)
    with (root/'run.lock').open('x') as f:json.dump({'pid':os.getpid(),'started':now()},f)
    mutex=threading.Lock();active={};completed=[];errors={};stop=threading.Event()
    def snapshot(state):
        with mutex:
            a=[dict(v,postfile_bytes=(safe(root,v['folder'])/'receptor_horas.out').stat().st_size if (safe(root,v['folder'])/'receptor_horas.out').exists() else 0) for v in active.values()]
            d=dict(state=state,updated_utc=now(),supervisor_pid=os.getpid(),platform=plan['platform'],
                   assigned=len(plan['cases']),completed=list(completed),active=a,errors=dict(errors),max_workers=2)
            save(root/'status.json',d)
    def watcher():
        while not stop.wait(20):snapshot('RUNNING')
    def worker(c):
        folder=safe(root,c['folder']);folder.mkdir(parents=True,exist_ok=True)
        check(not (folder/'execution.json').exists() and not (folder/'aermod.out').exists(),'Previous attempt exists; preserve and review')
        for n,h in c['inputs'].items():
            check(Path(n).name==n,'Non-basename input')
            source=source_for(plan,c,n);check(sha(source)==h,'Frozen source changed: '+n)
            if (folder/n).exists():check(sha(folder/n)==h,'Existing stage changed: '+n)
            else:shutil.copyfile(source,folder/n)
        check(shutil.disk_usage(root).free>6*1024**3,'Disk reserve reached')
        check(not (folder/'execution.json').exists() and not (folder/'aermod.out').exists(),'Previous attempt exists; preserve and review')
        started=now();t=time.monotonic()
        with (folder/'console.log').open('xb') as log:
            kw={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            p=subprocess.Popen([str(binary),'aermod.inp','aermod.out'],cwd=folder,stdin=subprocess.DEVNULL,
                               stdout=log,stderr=subprocess.STDOUT,**kw)
            with mutex:active[c['id']]={'id':c['id'],'day':c['day'],'pollutant':c['pollutant'],'pid':p.pid,'folder':c['folder'],'started_utc':started}
            save(folder/'execution.json',dict(state='RUNNING',pid=p.pid,started_utc=started))
            code=p.wait()
        execution=dict(state='FINISHED',pid=p.pid,started_utc=started,finished_utc=now(),seconds=time.monotonic()-t,returncode=code)
        save(folder/'execution.json',execution);check(code==0,'AERMOD exit '+str(code))
        qa=validate(folder,c)
        if c.get('cross_platform_canary'):qa['cross_platform']=compare_reference(folder)
        for n,h in c['inputs'].items():check(sha(folder/n)==h,'Input changed during execution')
        products=['aermod.out','resumen.sum','errores.out','receptor_horas.out','console.log','execution.json']
        if len(c['hour_states'])==24:products.append('receptor_24h.out')
        receipt=dict(id=c['id'],day=c['day'],pollutant=c['pollutant'],execution=execution,qa=qa,
            binary_sha256=plan['binary_sha256'],inputs=c['inputs'],outputs={n:sha(folder/n) for n in products},
            status='NATIVE_CHECK_PASSED_PENDING_SCIENTIFIC_RECEPTION')
        save(folder/'receipt.json',receipt)
        temp=root/'exports'/ (c['id']+'.tar.gz.part')
        with tarfile.open(temp,'w:gz',compresslevel=1) as tar:
            for n in products+['receipt.json']:tar.add(folder/n,arcname=n)
        os.replace(temp,root/'exports'/(c['id']+'.tar.gz'))
        save(root/'receipts'/(c['id']+'.json'),receipt)
        compact(root,folder,c)
        with mutex:active.pop(c['id'],None);completed.append(c['id'])
        print(json.dumps({'completed':c['id'],'seconds':execution['seconds']}),flush=True)
    for c in plan['cases']:
        prior=root/'receipts'/(c['id']+'.json')
        if prior.exists():
            r=json.loads(prior.read_text());folder=safe(root,c['folder'])
            check(r['inputs']==c['inputs'] and r['binary_sha256']==plan['binary_sha256'],'Prior receipt mismatch')
            for n,h in r['inputs'].items():check(sha(source_for(plan,c,n))==h,'Prior source changed')
            for n,h in r['outputs'].items():check(product_hash(root,folder,c['id'],n)==h,'Prior completed product changed')
            completed.append(c['id'])
    snapshot('RUNNING')
    thread=threading.Thread(target=watcher,daemon=True);thread.start()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            queue=iter(c for c in plan['cases'] if c['id'] not in completed);pending={}
            for _ in range(2 if not (root/'STOP_AFTER_CURRENT').exists() else 0):
                c=next(queue,None)
                if c:pending[pool.submit(worker,c)]=c
            while pending:
                done,_=wait(pending,timeout=10,return_when=FIRST_COMPLETED)
                for fut in done:
                    c=pending.pop(fut)
                    try:fut.result()
                    except Exception:
                        with mutex:errors[c['id']]=traceback.format_exc();active.pop(c['id'],None)
                    if not errors and not (root/'STOP_AFTER_CURRENT').exists():
                        nxt=next(queue,None)
                        if nxt:pending[pool.submit(worker,nxt)]=nxt
                snapshot('ERROR_DRAINING' if errors else 'RUNNING')
    finally:
        stop.set();thread.join()
        final='FAILED' if errors else ('COMPLETE' if len(completed)==len(plan['cases']) else 'PAUSED')
        snapshot(final)
        (root/'run.lock').rename(root/('run.'+final.lower()+'.'+str(time.time_ns())+'.lock'))
    if errors:raise SystemExit(1)
if __name__=='__main__':main(sys.argv[1])
