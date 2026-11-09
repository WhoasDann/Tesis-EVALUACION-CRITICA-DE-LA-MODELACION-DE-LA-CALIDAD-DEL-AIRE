"""Small observed-vector challenge to the adverse one-at-a-time candidates."""
from analizar import *
import shutil, subprocess, copy, re, os, zipfile
from datetime import datetime,timezone
WORK=Path(__file__).parent
PILOT=OUT/'Contraste_ternas_observadas'
def now():return datetime.now(timezone.utc).isoformat()
def putjson(path,x): Path(path).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def weight(z,h,ref):
    f=np.clip((z-ref)/(h-ref),0,1);return float(1-3*f*f+2*f*f*f)

def prepare():
    assert not (PILOT/'Diseno.json').exists(),'Preserve frozen design and prior attempts'
    PILOT.mkdir(parents=True,exist_ok=True)
    support=pd.read_csv(OUT/'Soporte_conjunto_perturbaciones.csv')
    prototype=[]
    for season,target in [('VERANO','U_PLUS'),('VERANO','V_MINUS'),('INVIERNO','U_PLUS')]:
        r=support[(support.season==season)&(support.scenario==target)].iloc[0]
        prototype.append(dict(season=season,scenario='OBS_'+target[0],target=target,source_day=r.nearest_observed_day,delta=[float(r.nearest_T),float(r.nearest_u),float(r.nearest_v)],distance_SD=float(r.nearest_standardized_distance)))
    ep=pd.read_csv(OUT/'Episodios_auditar.csv');civil={s:sorted(ep[ep.season==s].day.unique()) for s in ['VERANO','INVIERNO']}
    dates={}
    for season,days in civil.items():
        x=set(days)
        if season=='INVIERNO':
            x.update((pd.Timestamp(d)-pd.Timedelta(days=1)).strftime('%Y-%m-%d') for d in days if d>='2017-08-14')
        dates[season]=sorted(x)
    design=dict(created_utc=now(),status='FROZEN_BEFORE_NEW_CONCENTRATIONS',purpose='Challenge numerical adverse candidates with complete empirical daily discrepancy vectors, not independently combined marginal extremes.',prototypes=prototype,civil_days=civil,LST_days=dates,new_cases=sum(len(dates[r['season']])*2 for r in prototype),receptors=40,
      selection='Retrospective choice of target U_PLUS or V_MINUS from completed sensitivity. Before new concentrations, choose one ACTUAL complete daily (dT,du,dv) tuple minimizing Euclidean distance to target after division by the original season-specific marginal SD. All three components come from the SAME observed day; no averaging of selected extremes, random draws, fitting, or probabilities.',
      scope='Apply each constant empirical daily vector to full seasonal ONSITE context so AERMET has the same context as prior campaign. Only selected episode dates are dispersed, with previous LST dates required to reconstruct civil days. These outputs cannot estimate seasonal averages or find the maximum over unrun days.',
      physical_basis='Retains empirical co-occurrence of the three station-scale daily discrepancies and the existing continuous vertical taper. This supports the chosen amplitude combination, NOT its persistent seasonal occurrence, its transfer between columns, or atmospheric dynamic/energy consistency. It is a prescribed sensitivity challenge, not corrected truth.',
      admission='Keep BASE reference. Separate empirical support, numerical acceptance, and dynamic validation. Reject numerical corruption. Flag weather-state departures and unsupported transfer; do not claim a physical/regulatory worst merely because a run passes AERMOD. Retain adverse outcomes only for the evaluated episodes and explicitly conditional on transfer and model applicability.',
      stopping='Complete this finite episode batch; do not automatically extend full seasons or restart prior queues. New full-grid or seasonal expansion depends on the resulting scientific diagnosis.',
      inputs=[dict(path=str(OUT/n),sha256=sha(OUT/n)) for n in ['Soporte_conjunto_perturbaciones.csv','Discrepancias_diarias_conjuntas.csv','Episodios_auditar.csv']])
    putjson(PILOT/'Diseno.json',design)
    for r in prototype:
        season=r['season'];sc=r['scenario'];src=A/'Meteorologia'/season/'BASE'
        folder=PILOT/'Meteorologia'/season/sc;folder.mkdir(parents=True)
        for n in ['met.IN1','upper.dat','surface.dat']:shutil.copy2(src/n,folder/n)
        lines=(src/'onsite.dat').read_text(encoding='ascii').splitlines(keepends=True);rows=list(lines)
        cal=pd.read_csv(A/'Calendarios'/f'{season}.csv');dc,ec=('dia','fin_local') if season=='VERANO' else ('dia_LST','fin_LST')
        keys=set(pd.to_datetime(cal[dc]).dt.strftime('%Y%m%d')+pd.to_datetime(cal[ec]).dt.hour.replace(0,24).map('{:02}'.format))
        dt,du,dv=r['delta'];changes=0
        for k in range(0,len(lines),30):
            if lines[k][:10] not in keys:continue
            H=float(lines[k][40:50]);assert H>10
            for lev in range(1,30):
                a=lines[k+lev];z=float(a[10:20]);line=a
                if lev>=2:
                    ws,wd=float(a[20:30]),float(a[30:40]);assert 0<=ws<99 and 0<=wd<=360
                    u=-ws*np.sin(np.deg2rad(wd))+weight(z,H,10)*du;v=-ws*np.cos(np.deg2rad(wd))+weight(z,H,10)*dv
                    speed=np.hypot(u,v);direction=np.rad2deg(np.arctan2(-u,-v))%360
                    assert 0<=speed<99
                    line=line[:20]+f'{speed:10.3f}{direction:10.3f}'+line[40:]
                if lev!=2:
                    t=float(a[40:50])+weight(z,H,2)*dt;assert -80<t<65
                    line=line[:40]+f'{t:10.3f}'+line[50:]
                rows[k+lev]=line
                if z>=H:assert rows[k+lev]==a,'Above-PBL change'
            rows[k+1]=rows[k+1][:60]+f'{float(rows[k+3][40:50])-float(rows[k+1][40:50]):10.3f}'+rows[k+1][70:]
            assert rows[k]==lines[k]
            changes+=1
        (folder/'onsite.dat').write_text(''.join(rows),encoding='ascii',newline='')
        putjson(folder/'Inputs.json',{n:sha(folder/n) for n in ['onsite.dat','upper.dat','surface.dat','met.IN1']})
        with (folder/'console.log').open('xb') as log:
            p=subprocess.run([str(A/'Binarios/aermet.exe'),'met.IN1'],cwd=folder,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,timeout=300)
        putjson(folder/'execution.json',dict(returncode=p.returncode,finished_utc=now(),target_profiles=changes))
        assert p.returncode==0
        assert not re.search(r'(?m)^\s*(?:\w+\s+)?E\d{2}\s',(folder/'met.ER1').read_text())
        s=np.loadtxt(folder/'met.SFC',skiprows=1,usecols=range(25));b=np.loadtxt(src/'met.SFC',skiprows=1,usecols=range(25))
        bad=lambda x:(x[:,15]>=99)|(x[:,18]>=999)|(x[:,6]<0)|(x[:,10]<=0)
        assert np.array_equal(s[:,:5],b[:,:5]) and np.array_equal(bad(s),bad(b))
        pf=np.loadtxt(folder/'met.PFL');bf=np.loadtxt(src/'met.PFL');assert np.array_equal(pf[:,:6],bf[:,:6])
        assert np.isfinite(s).all() and np.isfinite(pf).all()
        putjson(folder/'QC.json',dict(status='NUMERICAL_CHECK_PASSED_NOT_PHYSICAL_VALIDATION',same_calendar=True,same_missing_mask=True,inputs=read(folder/'Inputs.json'),outputs={n:sha(folder/n) for n in ['met.SFC','met.PFL','met.ER1']}))
        print('AERMET ready',season,sc,flush=True)
    package(design)

def package(design):
    original=read(A/'Casos.json')['cases'];catalog=read(A/'Catalogo_inputs.json');newcat={};cases=[]
    assert not (PILOT/'Lote_local/plan.json').exists()
    (PILOT/'Inputs').mkdir(exist_ok=True);root=PILOT/'Lote_local';root.mkdir(exist_ok=True)
    archives=[p for src in [A,B] for p in src.glob('*.zip') if not p.name.startswith('Paquete')]
    archive_index={}
    for ap in archives:
        with zipfile.ZipFile(ap) as z:
            for name in z.namelist():
                if name.startswith('blobs/') and len(name)==70:archive_index.setdefault(name[6:],(ap,name))
    recovered=[]
    def existing(h):
        if h not in newcat:
            meta=dict(catalog[h])
            if not Path(meta['path']).exists():
                ap,name=archive_index[h]
                with zipfile.ZipFile(ap) as z:data=z.read(name)
                assert hashlib.sha256(data).hexdigest()==h
                recovered_path=PILOT/'Inputs'/h
                if recovered_path.exists():assert sha(recovered_path)==h
                else:recovered_path.write_bytes(data)
                recovered.append(dict(original=meta['path'],archive=str(ap),member=name,recovered=str(recovered_path),sha256=h))
                meta['path']=str(recovered_path)
            assert sha(meta['path'])==h;newcat[h]=meta
        return h
    def put(t):
        data=t.encode('ascii');h=hashlib.sha256(data).hexdigest();p=PILOT/'Inputs'/h
        if not p.exists():p.write_bytes(data)
        assert sha(p)==h;newcat[h]=dict(path=str(p),bytes=len(data));return h
    for r in design['prototypes']:
        season,sc=r['season'],r['scenario'];folder=PILOT/'Meteorologia'/season/sc
        full={k:(folder/f'met.{k}').read_text().splitlines() for k in ['SFC','PFL']}
        for old in original:
            if old['season']!=season or old['scenario']!='BASE' or old['day'] not in design['LST_days'][season]:continue
            c=copy.deepcopy(old);c.pop('result_folder',None);c.update(scenario=sc,host='local',id=f"{season}_{old['day'].replace('-','')}_{sc}_{old['pollutant']}")
            c['folder']='Casos/'+c['id'];dt=pd.Timestamp(c['day']);hours=[int(k[-2:]) for k in c['hour_states']]
            inputs={n:existing(h) for n,h in old['inputs'].items() if n not in ['met.SFC','met.PFL','aermod.inp']}
            for kind in ['SFC','PFL']:
                raw=full[kind];lines=[l for l in (raw[1:] if kind=='SFC' else raw) if tuple(map(int,l.split()[:3]))==(dt.year,dt.month,dt.day) and int(l.split()[4 if kind=='SFC' else 3]) in hours]
                assert len(lines)==len(hours)*(1 if kind=='SFC' else 29)
                inputs['met.'+kind]=put('\n'.join((raw[:1] if kind=='SFC' else [])+lines)+'\n')
            text=Path(catalog[old['inputs']['aermod.inp']]['path']).read_text();inp=re.sub(r'CO TITLEONE.*',f'CO TITLEONE Empirical joint-vector challenge {c["id"]}',text)
            assert re.sub(r'CO TITLEONE.*','',inp)==re.sub(r'CO TITLEONE.*','',text)
            inputs['aermod.inp']=put(inp);c['inputs']=inputs;c['input_sources']={n:newcat[h]['path'] for n,h in inputs.items()};cases.append(c)
    assert len(cases)==design['new_cases'] and len({c['id'] for c in cases})==len(cases)
    cases.sort(key=lambda c:(c['day'] not in ['2017-01-12','2017-06-28'],c['season'],c['day'],c['scenario'],c['pollutant']))
    shutil.copy2(ROOT/'work/sensibilidad_conjunta_20261030/batch_runner.py',root/'batch_runner.py')
    shutil.copy2(A/'Comunes/membresia.csv',root/'membresia.csv')
    plan=read(A/'Lotes/local/plan.json');plan.update(cases=cases,allowed_input_roots=[str(OLD/'outputs'),str(A),str(PILOT),'D:/Tesis_Dan/BASE_invierno_2026-10-24/Emisiones'],dependencies={n:sha(root/n) for n in ['batch_runner.py','membresia.csv']})
    putjson(root/'plan.json',plan);putjson(PILOT/'Catalogo_inputs.json',newcat);putjson(PILOT/'Casos.json',dict(cases=cases));putjson(PILOT/'Recuperacion_entradas.json',dict(status='EXACT_HASH_RECOVERY',files=recovered))
    print('Frozen',len(cases),'new exclusive cases',flush=True)

if __name__=='__main__':prepare()
