"""Frozen structural wind sensitivity at the single MMIF column; no calibrated errors."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,subprocess,sys,re
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/Piloto_transferencia_2026-10-27'
OLD=Path(r'/archivo/usuario\Documents\Codex\2026-10-08\hem')
BASE=OLD/'outputs/BASE_verano_2026-10-21'
MET=BASE/'Meteorologia/aermet_20261021_145804_172910'
sys.path.insert(0,str(OLD/'work'))
from transferencia_vertical_20261020 import pesos_pbl,tests

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def uv(ws,wd):a=np.deg2rad(wd);return -ws*np.sin(a),-ws*np.cos(a)
def wdws(u,v):return np.hypot(u,v),np.mod(np.rad2deg(np.arctan2(-u,-v)),360)
def prepare():
    assert not (OUT/'Diseno.json').exists(),'Preserve the frozen design'
    files=['met.IN1','onsite.dat','upper.dat','surface.dat']
    manifest=json.loads((BASE/'MMIF_validado.json').read_text(encoding='utf-8'))['archivos'] + json.loads((BASE/'Entrega.json').read_text(encoding='utf-8'))['archivos']
    known={str(Path(x['path']).resolve()):x['sha256'] for x in manifest}
    # The scientific receipt pins the upstream AERMET files.
    checked=[]
    for n in files:
        p=MET/n
        if n=='met.IN1':
            from tesis.cadena_corta import ajustar_aermet
            original=next(Path(x) for x in known if Path(x).name=='met.IN1.original')
            assert sha(original)==known[str(original)]
            assert p.read_text()==ajustar_aermet(original.read_text(),'WRF')
        else:
            original=next(Path(x) for x in known if Path(x).name.lower()==n.lower())
            assert sha(p)==sha(original)==known[str(original)],n
        checked.append({'path':str(p),'sha256':sha(p)})
    design=dict(created_utc=datetime.now(timezone.utc).isoformat(),status='FROZEN_BEFORE_NEW_CONCENTRATIONS',
      purpose='Complete the pending structural comparison of uniform versus PBL-limited wind transfer.',
      days=['2016-12-21','2016-12-22'],selection='Same dates as the documented technical wind contrast; deterministic comparison, no selection by new concentrations.',
      scenarios=['UNIFORM','PBL'],delta_earth_m_s=[1.,-.5],
      adapter='Apply vector increments to wind records of the single MMIF ONSITE column, BEFORE AERMET. This is a new column adapter, not an edit or rerun of WRF.',
      vertical='UNIFORM: weight 1 at all valid wind heights. PBL: w=1-3s^2+2s^3, s=clip((z-10)/(H-10),0,1). H is the hourly BASE MHGT serialized by MMIF, not an inferred observed height.',
      horizontal='Single MMIF column I43/J44. No covariance or observed-error transfer across the domain is inferred.',
      perturbation_window='2016-12-20 through 2016-12-23 inclusive (96 hourly records; one auxiliary day on either side).',
      preprocessing='Use the entire existing seasonal AERMET input calendar and identical seasonal surface file; change only ONSITE WS/WD in the declared window. Upper-air sounding remains BASE; no dynamics reintegration.',
      controls_fixed=['All thermal, humidity, pressure, flux, PBL height fields','AERMET version/configuration','Emissions','12263 physical sources','Terrain'],
      staging='8 daily runs at the four exact sensitive receptors (2 days x 2 pollutants x 2 scenarios), then 4 PBL runs on the full 6295-receptor grid only after the native/profile checks pass. Reuse existing matching BASE results.',
      scientific_scope='Deterministic structural sensitivity. Not 8 random realizations, not a calibrated uncertainty distribution, not a seasonal P95. Full-grid PBL comparison remains conditional on this assumed transfer.',
      references=['https://gaftp.epa.gov/aqmg/SCRAM/models/related/mmif/MMIF_Guidance.pdf','https://gaftp.epa.gov/Air/aqmg/SCRAM/models/met/aermet/aermet_userguide.pdf'],
      prior_operator=str(OLD/'outputs/Transferencia_vertical_2026-10-20/Operador.json'),inputs=checked,
      numerical_tests=tests())
    save(OUT/'Diseno.json',design)
    exe=BASE/'Binarios/aermet.exe'
    assert str(exe.resolve()) in known and sha(exe)==known[str(exe.resolve())]
    (OUT/'Binarios').mkdir();shutil.copy2(exe,OUT/'Binarios/aermet.exe')
    lines=(MET/'onsite.dat').read_text(encoding='ascii').splitlines(keepends=True)
    assert len(lines)%30==0
    expected=[]
    for scenario in ['BASE_CHECK','UNIFORM','PBL']:
        folder=OUT/'Meteorologia'/scenario;folder.mkdir(parents=True)
        for n in files:shutil.copy2(MET/n,folder/n)
        changed=0;rows=list(lines)
        for k in range(0,len(lines),30):
            head=lines[k];stamp=head[:10];h=float(head[40:50])
            if not ('2016122001'<=stamp<='2016122324'):continue
            assert h>10 and np.isfinite(h)
            for lev in range(2,30):
                line=lines[k+lev];z,ws,wd=map(float,[line[10:20],line[20:30],line[30:40]])
                assert ws>=0 and ws<50 and 0<=wd<=360
                w=0 if scenario=='BASE_CHECK' else (1. if scenario=='UNIFORM' else float(pesos_pbl(z,h)))
                if w:
                    u,v=uv(ws,wd);ns,nd=wdws(u+w,v-.5*w)
                    rows[k+lev]=line[:20]+f'{ns:10.3f}{nd:10.3f}'+line[40:]
                    nu,nv=uv(float(rows[k+lev][20:30]),float(rows[k+lev][30:40]))
                    tol=.0015+(ws+ns)*np.deg2rad(.00051)
                    assert max(abs(nu-u-w),abs(nv-v+.5*w))<tol
                    changed+=1
                assert rows[k+lev][:20]==line[:20] and rows[k+lev][40:]==line[40:]
                if scenario!='BASE_CHECK':expected.append(dict(scenario=scenario,stamp=stamp,z=z,H=h,weight=w,ws=ws,wd=wd))
        (folder/'onsite.dat').write_text(''.join(rows),encoding='ascii',newline='')
        save(folder/'Entradas.json',dict(scenario=scenario,changed_records=changed,inputs={n:sha(folder/n) for n in files}))
    save(OUT/'Expected_profile.json',expected)
    save(OUT/'Preparacion.json',dict(binary_sha256=sha(OUT/'Binarios/aermet.exe'),script_sha256=sha(__file__),design_sha256=sha(OUT/'Diseno.json')))
    print('Frozen column sensitivity inputs prepared',flush=True)

def run():
    for scenario in ['BASE_CHECK','UNIFORM','PBL']:
        p=OUT/'Meteorologia'/scenario
        assert not (p/'execution.json').exists(),'Existing attempt must be inspected'
        before=json.loads((p/'Entradas.json').read_text())['inputs']
        assert all(sha(p/n)==v for n,v in before.items())
        print('AERMET '+scenario,flush=True)
        with (p/'console.log').open('xb') as log:
            r=subprocess.run([str(OUT/'Binarios/aermet.exe'),'met.IN1'],cwd=p,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,timeout=180)
        save(p/'execution.json',dict(returncode=r.returncode,finished_utc=datetime.now(timezone.utc).isoformat()))
        assert r.returncode==0,r.returncode
        msg=(p/'met.ER1').read_text()
        assert not re.search(r'(?m)^\s*(?:\w+\s+)?E\d{2}\s',msg)
    print('AERMET three scenarios complete',flush=True)

def verify():
    origin_s=np.loadtxt(MET/'met.SFC',skiprows=1,usecols=range(25));origin_p=np.loadtxt(MET/'met.PFL')
    base_s=np.loadtxt(OUT/'Meteorologia/BASE_CHECK/met.SFC',skiprows=1,usecols=range(25));base_p=np.loadtxt(OUT/'Meteorologia/BASE_CHECK/met.PFL')
    np.testing.assert_array_equal(base_s,origin_s);np.testing.assert_array_equal(base_p,origin_p)
    expected=json.loads((OUT/'Expected_profile.json').read_text())
    results={}
    for scen in ['UNIFORM','PBL']:
        folder=OUT/'Meteorologia'/scen
        s=np.loadtxt(folder/'met.SFC',skiprows=1,usecols=range(25));p=np.loadtxt(folder/'met.PFL')
        np.testing.assert_array_equal(s[:,:5],base_s[:,:5]);np.testing.assert_array_equal(p[:,:6],base_p[:,:6]);np.testing.assert_array_equal(s[:,18],base_s[:,18]);np.testing.assert_array_equal(p[:,8:],base_p[:,8:])
        target=(p[:,0]==2016)&(p[:,1]==12)&(p[:,2]>=20)&(p[:,2]<=23)
        np.testing.assert_array_equal(p[~target],base_p[~target])
        outside=(s[:,0]!=2016)|(s[:,1]!=12)|(s[:,2]<20)|(s[:,2]>23)
        np.testing.assert_array_equal(s[outside],base_s[outside])
        exp=[e for e in expected if e['scenario']==scen]
        pp=p[target & (p[:,4]>=10)];bb=base_p[target & (base_p[:,4]>=10)]
        assert len(pp)==len(exp)==96*28
        u,v=uv(bb[:,7],bb[:,6]);nu,nv=uv(pp[:,7],pp[:,6]);w=np.array([e['weight'] for e in exp])
        tol=.013+(pp[:,7]+bb[:,7])*np.deg2rad(.051)
        err=np.maximum(abs(nu-u-w),abs(nv-v+.5*w))
        assert np.all(err<=tol),float(np.max(err/tol))
        np.testing.assert_array_equal(pp[w==0],bb[w==0])
        ss=s[~outside];bs=base_s[~outside];u,v=uv(bs[:,15],bs[:,16]);nu,nv=uv(ss[:,15],ss[:,16]);e=np.maximum(abs(nu-u-1),abs(nv-v+.5));t=.013+(ss[:,15]+bs[:,15])*np.deg2rad(.051)
        assert np.all(e<=t)
        assert np.all(ss[:,15]>0) and np.all(ss[:,10]>0) and np.all(ss[:,6]>=0)
        results[scen]=dict(profile_valid_records=len(pp),max_profile_error_ms=float(err.max()),max_error_over_serialization_tolerance=float((err/tol).max()),exact_unchanged_upper_records=int((w==0).sum()),max_surface_error_ms=float(e.max()),warnings=sorted(set(re.findall(r'\bW\d{2}\b',(folder/'met.ER1').read_text()))))
    save(OUT/'Verificacion_meteorologia.json',dict(status='PASSED',base_reproduction='Exact equality of all numeric SFC/PFL entries across the seasonal calendar',temperature_unchanged=True,outside_window_unchanged=True,scenarios=results,outputs={f'{sc}/{n}':sha(OUT/'Meteorologia'/sc/n) for sc in ['BASE_CHECK','UNIFORM','PBL'] for n in ['met.SFC','met.PFL','met.ER1']}))
    print(json.dumps(results),flush=True)
if __name__=='__main__':globals()[sys.argv[1]]()