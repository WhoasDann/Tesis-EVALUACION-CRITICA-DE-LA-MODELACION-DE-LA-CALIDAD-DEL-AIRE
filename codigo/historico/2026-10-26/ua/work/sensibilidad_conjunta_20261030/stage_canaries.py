"""Stage only verified local outputs as the new Linux canary references."""
import copy
from campaign import OUT,read,save,sha,rec,now
from package import REMOTE
from deploy import ssh,scp
def main():
    assert not (OUT/'Canarios_preparados.json').exists()
    ids=read(OUT/'Canarios_planificados.json')['reference_local_case_ids']
    allcases=read(OUT/'Casos.json')['cases'];references=[];cases=[]
    target=OUT/'Lotes/canary';target.mkdir()
    root=REMOTE['rocky'];plan=read(OUT/'Lotes/rocky/plan.json')
    for cid in ids:
        rp=OUT/'Recibos'/(cid+'.json');r=read(rp)
        assert r['host']=='local' and r['status']=='SCIENTIFIC_RECEPTION_PASSED'
        from pathlib import Path
        p=Path(r['result_folder'])/'receptor_horas.out';h=sha(p);assert h==r['outputs']['receptor_horas.out']
        c=copy.deepcopy(next(c for c in allcases if c['id']==cid));c['id']='CHECK_'+cid
        c['folder']='Casos/'+c['id'];c['cross_platform_canary']=True;c['inputs']['reference.out']=h
        c['input_sources']={n:root+'/blobs/'+hh for n,hh in c['inputs'].items()}
        scp('rocky',p,root+'/blobs/'+h);cases.append(c)
        references.append(dict(id=cid,receipt=rec(rp),reference=rec(p)))
    plan.update(cases=cases,dependencies={});save(target/'plan.json',plan)
    ssh('rocky',"mkdir -p '"+root+"/canary'")
    scp('rocky',target/'plan.json',root+'/canary/plan.json')
    save(OUT/'Canarios_preparados.json',dict(created_utc=now(),status='STAGED_VERIFIED_LOCAL_REFERENCES',references=references,plan=rec(target/'plan.json')))
    print('Four new-corner canaries staged; Linux can start its gated launcher',flush=True)
if __name__=='__main__':main()
