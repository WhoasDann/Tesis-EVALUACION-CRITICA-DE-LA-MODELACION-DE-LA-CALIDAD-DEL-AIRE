"""Fetch and independently receive the bounded alternative batches, never BASE receipts."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys,tarfile,shutil,time,traceback,os
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/Piloto_transferencia_2026-10-27';OLD=Path(r'/archivo/usuario\Documents\Codex\2026-10-08\hem');BASE=OLD/'outputs/BASE_verano_2026-10-21'
sys.path.insert(0,str(OLD/'work'))
import salidas_estacionales_20261021 as scientific
from prepare_transfer import sha,save
REMOTE='C:/Users/Daniel/Documents/Tesis_Calculo_20261027/jobs/transfer_20261027'
SSH=['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=8','windows3-tesis']

def now():return datetime.now(timezone.utc).isoformat()
def status(size):
    r=subprocess.run(SSH+['type '+REMOTE.replace('/','\\')+'\\'+size+'\\status.json'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=35)
    if r.returncode:raise ConnectionError(r.stderr[-2000:])
    d=json.loads(r.stdout);save(OUT/(size+'_remote_status.json'),d);return d

def receive(size):
    s=status(size);batch=OUT/'Lotes'/size;plan=json.loads((batch/'plan.json').read_text());receipts=OUT/'Recepcion'/size;receipts.mkdir(parents=True,exist_ok=True)
    masks=pd.read_csv(BASE/'Revision_QC_2026-10-21/Cobertura_horaria.csv');members=pd.read_csv(batch/'membresia.csv')
    allrefs=json.loads((OUT/'Referencias_BASE.json').read_text());tables=[]
    for c in plan['cases']:
        rp=receipts/(c['id']+'.json');folder=batch/c['folder']
        if c['id'] not in s['completed']:continue
        if rp.exists():
            old=json.loads(rp.read_text());assert all(sha(folder/n)==h for n,h in old['outputs'].items());continue
        remote=REMOTE+'/'+size+'/exports/'+c['id']+'.tar.gz';archive=receipts/(c['id']+'.tar.gz')
        r=subprocess.run(['scp','-o','BatchMode=yes','-o','ConnectTimeout=8','windows3-tesis:'+remote,str(archive)],capture_output=True,text=True,timeout=120)
        if r.returncode:raise ConnectionError(r.stderr)
        allowed={'aermod.out','resumen.sum','errores.out','receptor_horas.out','receptor_24h.out','console.log','execution.json','receipt.json'}
        with tarfile.open(archive,'r:gz') as tar:
            items=tar.getmembers();assert {m.name for m in items}==allowed and len(items)==len(allowed)
            for m in items:
                assert m.isfile() and m.name==Path(m.name).name and m.size<300*1024**2
                dst=folder/m.name
                if dst.exists():raise ValueError('Unreceived file exists: '+str(dst))
                with tar.extractfile(m) as src,dst.open('xb') as dest:shutil.copyfileobj(src,dest)
        native=json.loads((folder/'receipt.json').read_text());assert native['id']==c['id'] and native['inputs']==c['inputs'] and native['binary_sha256']==plan['binary_sha256']
        assert all(sha(folder/n)==h for n,h in {**c['inputs'],**native['outputs']}.items())
        mask=masks.loc[masks.dia.eq(c['day'])]
        qa,data,points,joined,zones=scientific.receive(folder,mask,members,receptors=c['receptors'])
        if size=='full':
            small=OUT/'Lotes/small'/c['folder']/'receptor_horas.out'
            proof=json.loads((OUT/'Recepcion/small'/(c['id']+'.json')).read_text())
            assert sha(small)==proof['outputs']['receptor_horas.out']
            control=scientific.postfile(small)
            compare=data.merge(control[['x_m','y_m','fecha_AERMOD','C_bruta_ug_m3']],on=['x_m','y_m','fecha_AERMOD'],suffixes=('','_small'),validate='one_to_one')
            assert len(compare)==96
            maximum=float(abs(compare.C_bruta_ug_m3-compare.C_bruta_ug_m3_small).max())
            assert maximum<=1.1e-5,'Four-point/full-grid discrepancy'
            qa['max_difference_small_grid']=maximum
        points.to_csv(folder/'Por_receptor.csv',index=False);joined.to_csv(folder/'Por_membresia.csv',index=False);zones.to_csv(folder/'Por_ambito.csv',index=False)
        ref=allrefs[c['day'].replace('-','')+'_'+c['pollutant']]
        src=Path(ref['folder']);assert sha(src/'receptor_horas.out')==ref['reference_postfile_sha256']
        b=scientific.postfile(src/'receptor_horas.out');b=b.merge(points[['x_m','y_m']],on=['x_m','y_m'],validate='many_to_one')
        pair=data.merge(b[['x_m','y_m','fecha_AERMOD','C_bruta_ug_m3']],on=['x_m','y_m','fecha_AERMOD'],suffixes=('','_BASE'),validate='one_to_one')
        assert len(pair)==len(data) and pair.estado.eq('VALIDA').all()
        pair['delta_ug_m3']=pair.C_ug_m3-pair.C_bruta_ug_m3_BASE
        summary=pair.groupby(['x_m','y_m']).agg(BASE_media24=('C_bruta_ug_m3_BASE','mean'),alternativa_media24=('C_ug_m3','mean'),delta_media24=('delta_ug_m3','mean'),BASE_max1h=('C_bruta_ug_m3_BASE','max'),alternativa_max1h=('C_ug_m3','max')).reset_index()
        summary['delta_porcentaje']=np.where(summary.BASE_media24>0,100*summary.delta_media24/summary.BASE_media24,np.nan)
        summary.to_csv(folder/'Comparacion_BASE.csv',index=False)
        outputs={n:sha(folder/n) for n in list(native['outputs'])+['Por_receptor.csv','Por_membresia.csv','Por_ambito.csv','Comparacion_BASE.csv']}
        save(rp,dict(status='SCIENTIFIC_RECEPTION_PASSED',id=c['id'],day=c['day'],scenario=c['scenario'],pollutant=c['pollutant'],received_utc=now(),qa=qa,seconds=native['execution']['seconds'],inputs=c['inputs'],outputs=outputs,base=ref))
        print('Received '+c['id'],flush=True)
    rs=[json.loads((receipts/(c['id']+'.json')).read_text()) for c in plan['cases'] if (receipts/(c['id']+'.json')).exists()]
    for c in plan['cases']:
        if not (receipts/(c['id']+'.json')).exists():continue
        df=pd.read_csv(batch/c['folder']/'Comparacion_BASE.csv');df['scenario']=c['scenario'];df['day']=c['day'];df['pollutant']=c['pollutant'];tables.append(df)
    if tables:pd.concat(tables).to_csv(OUT/('Comparaciones_'+size+'.csv'),index=False)
    result=dict(state='RECEIVED_COMPLETE' if len(rs)==len(plan['cases']) else s['state'],updated_utc=now(),received=len(rs),assigned=len(plan['cases']),receptors=plan['cases'][0]['receptors'],hourly_values_received=sum(r['qa']['valores_horarios'] for r in rs),native=s,seconds_total=sum(r['seconds'] for r in rs),scope='Deterministic sensitivity; not calibrated uncertainty or additional BASE days')
    save(OUT/('Estado_'+size+'.json'),result)
    if s['errors']:raise RuntimeError(str(s['errors']))
    return result

def main():
    contract=json.loads((OUT/'Contrato_recepcion.json').read_text())
    assert all(sha(x['path'])==x['sha256'] for x in contract['inputs']),'Receiver dependency changed'
    size=sys.argv[1];watch='--watch' in sys.argv
    if watch:
        lock=OUT/(size+'_collector.lock')
        with lock.open('x') as f:json.dump({'pid':os.getpid(),'started_utc':now()},f)
    while True:
        try:
            result=receive(size);print(json.dumps({k:result[k] for k in ['state','received','assigned']}),flush=True)
            if result['state']=='RECEIVED_COMPLETE' or not watch:break
        except ConnectionError as e:
            save(OUT/(size+'_connection.json'),dict(state='UNREACHABLE_RETRY_60S',updated_utc=now(),error=str(e)))
            if not watch:raise
        if (OUT/(size+'_STOP_COLLECTOR')).exists():break
        time.sleep(60)
    if watch:lock.rename(OUT/(size+'_collector.finished.'+str(time.time_ns())+'.lock'))
if __name__=='__main__':
    try:main()
    except Exception:
        save(OUT/('Fallo_recepcion_'+sys.argv[1]+'.json'),dict(updated_utc=now(),error=traceback.format_exc()))
        raise