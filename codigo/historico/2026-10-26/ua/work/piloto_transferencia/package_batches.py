from pathlib import Path
import hashlib,json,shutil,re,sys,zipfile
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/Piloto_transferencia_2026-10-27';OLD=Path(r'/archivo/usuario\Documents\Codex\2026-10-08\hem');BASE=OLD/'outputs/BASE_verano_2026-10-21'
REMOTE='C:/Users/Daniel/Documents/Tesis_Calculo_20261027'
sys.path.insert(0,str(OLD/'work'))
import ejecutar_base_verano_20261021 as common
from prepare_transfer import sha,save

def main():
    qc=json.loads((OUT/'Verificacion_meteorologia.json').read_text());assert qc['status']=='PASSED'
    for rel,h in qc['outputs'].items():assert sha(OUT/'Meteorologia'/rel)==h
    assert not (OUT/'Lotes').exists()
    members=pd.read_csv(BASE/'Comunes/membresia_completa.csv')
    four=members[members.grupo.isin(['PCAR','LBCEN','SULF','PALP'])];assert len(four)==4
    coords=set(map(tuple,four[['x_m','y_m']].to_numpy()))
    full_receptors=(BASE/'Comunes/receptores.inc').read_text(encoding='ascii').splitlines()
    small_receptors=[s for s in full_receptors if tuple(map(float,s.split()[2:4])) in coords];assert len(small_receptors)==4
    mask=pd.read_csv(BASE/'Revision_QC_2026-10-21/Cobertura_horaria.csv')
    provenance={};casesets={}
    for size in ['small','full']:
        batch=OUT/'Lotes'/size;batch.mkdir(parents=True)
        shutil.copy2(ROOT/'work/linux_aermod/batch_runner.py',batch/'batch_runner.py')
        plan=dict(platform='Windows',binary=REMOTE+'/bin/aermod.exe',binary_sha256=sha(BASE/'Binarios/aermod.exe'),max_workers=2,
                  scope='Deterministic wind-transfer sensitivity; separate from BASE and uncertainty ensemble',dependencies={'batch_runner.py':sha(batch/'batch_runner.py')},cases=[])
        if size=='small':four.to_csv(batch/'membresia.csv',index=False)
        else:shutil.copy2(BASE/'Comunes/membresia_completa.csv',batch/'membresia.csv')
        plan['dependencies']['membresia.csv']=sha(batch/'membresia.csv')
        for scenario in (['UNIFORM','PBL'] if size=='small' else ['PBL']):
            for day in ['2016-12-21','2016-12-22']:
                stamp=day.replace('-','');m=mask.loc[mask.dia.eq(day)];assert len(m)==24 and m.estado.eq('VALIDA').all()
                for pol in ['MP10','MP25']:
                    reference=BASE/'Lote_estacional/Recibos'/f'{stamp}_{pol}.json'
                    rec=json.loads(reference.read_text(encoding='utf-8'));source=Path(rec['carpeta'])
                    known={Path(x['path']).name:x['sha256'] for x in rec['archivos']}
                    cid=f'{scenario}_{stamp}_{pol}';folder=batch/'Casos'/cid;folder.mkdir(parents=True)
                    names=['aermod.inp','fuentes_aermod.inc','receptores.inc',pol+'.emi']
                    for n in names:
                        assert sha(source/n)==known[n],str(source/n)
                        shutil.copy2(source/n,folder/n)
                    (folder/'receptores.inc').write_text('\n'.join(small_receptors if size=='small' else full_receptors)+'\n',encoding='ascii')
                    text=(folder/'aermod.inp').read_text();text=re.sub(r'CO TITLEONE.*',f'CO TITLEONE {scenario} column wind sensitivity {day} {size}',text)
                    (folder/'aermod.inp').write_text(text,encoding='ascii')
                    for ext in ['SFC','PFL']:
                        raw=(OUT/'Meteorologia'/scenario/('met.'+ext)).read_text().splitlines()
                        selected=[l for l in (raw[1:] if ext=='SFC' else raw) if tuple(map(int,l.split()[:3]))==(2016,12,int(day[-2:]))]
                        assert len(selected)==24*(1 if ext=='SFC' else 29)
                        (folder/('met.'+ext)).write_text('\n'.join((raw[:1] if ext=='SFC' else [])+selected)+'\n',encoding='ascii')
                    common.validar_vinculo_horario(folder/'aermod.inp',folder/'fuentes_aermod.inc',folder/(pol+'.emi'),{(16,12,int(day[-2:]),h) for h in range(1,25)})
                    inputs={n:sha(folder/n) for n in names+['met.SFC','met.PFL']}
                    plan['cases'].append(dict(id=cid,day=day,pollutant=pol,scenario=scenario,folder=str(folder.relative_to(batch)).replace('\\','/'),sources=12263,receptors=4 if size=='small' else 6295,hour_states={f'16{day[5:7]}{day[-2:]}{h:02d}':'VALIDA' for h in range(1,25)},inputs=inputs))
                    provenance[f'{stamp}_{pol}']=dict(receipt=str(reference),receipt_sha256=sha(reference),folder=str(source),reference_postfile_sha256=known['receptor_horas.out'])
        save(batch/'plan.json',plan);casesets[size]=len(plan['cases'])
        # Full native runner and the remote launch wrapper use different lock directories.
        job=dict(kind='aermod_batch',folder=f'jobs/transfer_20261027/launch_{size}',plan=f'jobs/transfer_20261027/{size}/plan.json',plan_sha256=sha(batch/'plan.json'),runner_sha256=sha(batch/'batch_runner.py'))
        save(OUT/('job_'+size+'.json'),job)
        archive=OUT/(size+'.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in batch.rglob('*'):
                if p.is_file():z.write(p,str(p.relative_to(batch)))
    save(OUT/'Referencias_BASE.json',provenance)
    save(OUT/'Paquetes.json',dict(cases=casesets,files={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in [OUT/'small.zip',OUT/'full.zip']},meteorology_qc_sha256=sha(OUT/'Verificacion_meteorologia.json')))
    print(json.dumps(casesets))
if __name__=='__main__':main()