"""Prespecified 2x2 temperature / scalar wind-speed extension, no direction change."""
from pathlib import Path
import sys, json, shutil, subprocess, re
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'work/piloto_conjunto'))
from prepare_joint import sha, read, save, rec, now, weight
OLD = Path('/archivo/usuario/Documents/Codex/2026-10-08/hem')
PILOT = ROOT/'outputs/Sensibilidad_estacional_2026-10-29'
OUT = ROOT/'outputs/Sensibilidad_conjunta_T_WS_2026-10-30'
WORK = Path(__file__).parent
SCENARIOS = ['BASE', 'T_PLUS', 'WS_PLUS', 'T_WS_PLUS']
NEW = SCENARIOS[2:]
CONFIG = read(PILOT/'Diseno.json')['seasons']

def prepare():
    assert not (OUT/'Diseno.json').exists(), 'Preserve previous attempt'
    assert read(PILOT/'Auditoria_final.json')['status'] == 'PASSED'
    OUT.mkdir(exist_ok=True)
    for name in ['Comunes', 'Calendarios', 'Binarios']:
        shutil.copytree(PILOT/name, OUT/name)
    statpath = ROOT/'outputs/Revision_Huneeus_2026-10-28/Estadisticas_discrepancias_locales.json'
    stats = read(statpath)
    amplitudes = {}; daily_all = []; sources = []
    for season in CONFIG:
        src = stats['sources'][season.title()]
        assert sha(src['source']) == src['sha256']
        df = pd.read_csv(src['source']); sources.append(rec(src['source']))
        valid = df.valido_conjunto.eq(True)
        cols = ['residuo_T_C', 'u_obs_m_s', 'v_obs_m_s', 'u_earth_m_s', 'v_earth_m_s']
        assert np.isfinite(df.loc[valid, cols].to_numpy()).all()
        good = df.loc[valid].copy()
        good['residuo_WS'] = np.hypot(good.u_obs_m_s, good.v_obs_m_s) - np.hypot(good.u_earth_m_s, good.v_earth_m_s)
        good['day'] = pd.to_datetime(good.fecha_local).dt.strftime('%Y-%m-%d')
        daily = good.groupby('day').agg(T=('residuo_T_C','mean'), WS=('residuo_WS','mean'), n=('residuo_T_C','size'))
        daily = daily[daily.n >= 18]
        expected = next(x for x in stats['daily_statistics'] if x['temporada']==season.title() and x['variable']=='T')
        assert len(daily)==expected['n_dias']
        assert abs(daily.T.loc['T'].std(ddof=1)-expected['sd_diaria_ddof1']) < 1e-10
        tsd = expected['sd_diaria_ddof1']; wsd = float(daily.WS.std(ddof=1))
        assert tsd>0 and wsd>0
        amplitudes[season] = dict(T_C=tsd, WS_m_s=wsd, training_days=len(daily),
                                  mean_WS_discrepancy=float(daily.WS.mean()),
                                  daily_T_WS_correlation=float(daily[['T','WS']].corr().iloc[0,1]))
        daily['season']=season; daily_all.append(daily.reset_index())
    pd.concat(daily_all).to_csv(OUT/'Discrepancias_diarias_T_WS.csv', index=False)
    design = dict(created_utc=now(), status='FROZEN_BEFORE_NEW_CONCENTRATIONS',
        seasons=CONFIG, scenarios=SCENARIOS, new_scenarios=NEW, new_cases=728, reused_cases=728, total_comparison_cases=1456,
        scales=amplitudes, inputs=sources+[rec(statpath), rec(PILOT/'Auditoria_final.json')],
        amplitude='Sample SD (ddof=1) of daily mean signed Obs-WRF discrepancies, >=18 joint valid hours/day. WS discrepancy is norm(observed vector) minus norm(WRF vector), NOT norm of u/v discrepancies.',
        choice='One joint positive corner (T+SD, WS+SD) and necessary WS-only control. Signs chosen before new concentrations; not optimized for high pollution. Does not sample both signs or a joint probability distribution.',
        operator='T_plus profile is reused byte-for-byte from audited seasonal campaign. Add SD_WS times original cubic BASE-PBL weight to scalar speed at valid non-calm profile levels; retain serialized direction exactly. At exactly zero speed preserve zero (direction undefined), and report exception count. Above BASE PBL profiles unchanged.',
        interface='Prescribed MMIF ONSITE sensitivity -> rerun AERMET -> AERMOD. Retain auxiliary RH, pressure, heat flux, UST, MHGT, sounding and surface inputs. No WRF reintegration or physical/probabilistic calibration.',
        interaction='I = C(T+,WS+) - C(T+,BASE_WS) - C(BASE_T,WS+) + C(BASE). Difference-in-differences on identical hours, dates, emissions and receptors. This is the 0/1 factorial interaction coefficient; do not confuse with +/-1 coefficient I/4 or factorial effect I/2.',
        statistics='Deterministic contrasts; dates are meteorological blocks, not independent experimental replicates. No ANOVA p-values or calibrated confidence intervals from this design.',
        coverage='Same 90 summer /92 winter execution dates,40 fixed nodes,2pollutants. 17h final summer day; reconstruct winter civil calendar and missing masks exactly as completed campaign.',
        references=[dict(title='NIST Two-level full factorial designs',url='https://www.itl.nist.gov/div898/handbook/pri/section3/pri3331.htm'),dict(title='NIST Interaction effects matrix plot',url='https://itl.nist.gov/div898/handbook/pri/section5/pri594.htm')])
    save(OUT/'Diseno.json', design)
    qc=[]
    for season in CONFIG:
        cal=pd.read_csv(OUT/'Calendarios'/(season+'.csv'))
        dc='dia' if season=='VERANO' else 'dia_LST'; ec='fin_local' if season=='VERANO' else 'fin_LST'
        keys=set(pd.to_datetime(cal[dc]).dt.strftime('%Y%m%d')+pd.to_datetime(cal[ec]).dt.hour.replace(0,24).map('{:02}'.format))
        base_lines=(PILOT/'Meteorologia'/season/'BASE/onsite.dat').read_text(encoding='ascii').splitlines(keepends=True)
        for scenario in NEW:
            parent='T_PLUS' if scenario=='T_WS_PLUS' else 'BASE'
            src=PILOT/'Meteorologia'/season/parent
            folder=OUT/'Meteorologia'/season/scenario; folder.mkdir(parents=True)
            for name in ['met.IN1','upper.dat','surface.dat']: shutil.copy2(src/name,folder/name)
            lines=(src/'onsite.dat').read_text(encoding='ascii').splitlines(keepends=True)
            assert len(lines)==len(base_lines) and len(lines)%30==0
            rows=list(lines); calm=changed=target_hours=0; maxws=0.; expected=[]
            for k in range(0,len(lines),30):
                stamp=lines[k][:10]
                if stamp not in keys: continue
                target_hours+=1
                assert lines[k]==base_lines[k]
                h=float(base_lines[k][40:50]); assert h>10
                for lev in range(2,30):
                    line=lines[k+lev]; z=float(line[10:20]); w=weight(z,h,10)
                    speed=float(line[20:30]); assert 0<=speed<99
                    direction=float(line[30:40]); assert 0<=direction<=360
                    delta=amplitudes[season]['WS_m_s']*w if speed>0 else 0.
                    if speed==0 and w>0: calm+=1
                    ns=speed+delta; assert 0<=ns<99 and (w==0 or ns<50)
                    if delta: rows[k+lev]=line[:20]+f'{ns:10.3f}'+line[30:]; changed+=1
                    assert rows[k+lev][:20]==line[:20] and rows[k+lev][30:]==line[30:]
                    expected.append(dict(stamp=stamp,level=lev,delta_WS=delta,weight=w,original_WS=speed))
                    maxws=max(maxws,ns)
            assert target_hours==sum(base_lines[k][:10] in keys for k in range(0,len(base_lines),30))
            (folder/'onsite.dat').write_text(''.join(rows),encoding='ascii',newline='')
            save(folder/'Expected.json', expected)
            save(folder/'Inputs.json',{n:sha(folder/n) for n in ['met.IN1','upper.dat','surface.dat','onsite.dat']})
            qc.append(dict(season=season,scenario=scenario,parent=parent,target_profiles=target_hours,changed_wind_levels=changed,calm_levels_preserved=calm,max_profile_WS=maxws))
        a=(OUT/'Meteorologia'/season/'WS_PLUS/onsite.dat').read_text().splitlines()
        b=(OUT/'Meteorologia'/season/'T_WS_PLUS/onsite.dat').read_text().splitlines()
        assert all(x[20:40]==y[20:40] for i,(x,y) in enumerate(zip(a,b)) if i%30>=2)
    save(OUT/'Verificacion_operador.json',dict(status='PASSED',cases=qc,script=rec(__file__)))
    print(json.dumps(amplitudes),flush=True)

def run():
    for season in CONFIG:
        for scenario in NEW:
            folder=OUT/'Meteorologia'/season/scenario
            assert not (folder/'execution.json').exists()
            assert all(sha(folder/n)==h for n,h in read(folder/'Inputs.json').items())
            print('AERMET '+season+' '+scenario,flush=True)
            with (folder/'console.log').open('xb') as log:
                p=subprocess.run([str(OUT/'Binarios/aermet.exe'),'met.IN1'],cwd=folder,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,timeout=240)
            save(folder/'execution.json',dict(returncode=p.returncode,finished_utc=now()))
            assert p.returncode==0
            assert not re.search(r'(?m)^\s*(?:\w+\s+)?E\d{2}\s',(folder/'met.ER1').read_text())

def verify():
    results=[]
    for season in CONFIG:
        base=PILOT/'Meteorologia'/season/'BASE'
        bs=np.loadtxt(base/'met.SFC',skiprows=1,usecols=range(25));bp=np.loadtxt(base/'met.PFL')
        pkeys=[f'{int(r[0]):04}{int(r[1]):02}{int(r[2]):02}{int(r[3]):02}' for r in bp]
        pidx={}
        for i,k in enumerate(pkeys):pidx.setdefault(k,[]).append(i)
        bad=lambda s:(s[:,15]>=99)|(s[:,18]>=999)|(s[:,6]<0)|(s[:,10]<=0)
        for scenario in NEW:
            folder=OUT/'Meteorologia'/season/scenario
            assert read(folder/'execution.json')['returncode']==0
            parent='T_PLUS' if scenario=='T_WS_PLUS' else 'BASE'
            reference=np.loadtxt(PILOT/'Meteorologia'/season/parent/'met.PFL')
            s=np.loadtxt(folder/'met.SFC',skiprows=1,usecols=range(25));p=np.loadtxt(folder/'met.PFL')
            assert np.isfinite(s).all() and np.isfinite(p).all()
            np.testing.assert_array_equal(s[:,:5],bs[:,:5]);np.testing.assert_array_equal(p[:,:6],bp[:,:6])
            np.testing.assert_array_equal(bad(s),bad(bs))
            np.testing.assert_array_equal(p[:,6],reference[:,6])
            np.testing.assert_array_equal(p[:,8:],reference[:,8:])
            ex=read(folder/'Expected.json');ix=np.array([pidx[x['stamp']][x['level']-1] for x in ex])
            delta=np.array([x['delta_WS'] for x in ex]);valid=(bp[ix,7]<99)&(p[ix,7]<99)
            errors=np.abs(p[ix,7]-bp[ix,7]-delta)[valid]
            assert errors.max()<=.0111,(season,scenario,errors.max())
            zero=np.array([x['weight']==0 for x in ex]);np.testing.assert_array_equal(p[ix[zero]],reference[ix[zero]])
            results.append(dict(season=season,scenario=scenario,max_speed_serialization_error=float(errors.max()),same_direction=True,same_temperature_as_parent=True,same_missing_mask=True,files={n:sha(folder/n) for n in ['met.SFC','met.PFL','met.ER1']}))
    save(OUT/'Verificacion_meteorologia.json',dict(status='PASSED',cases=results))
    print('AERMET verification PASSED: four new configurations',flush=True)

if __name__=='__main__': globals()[sys.argv[1]]()
