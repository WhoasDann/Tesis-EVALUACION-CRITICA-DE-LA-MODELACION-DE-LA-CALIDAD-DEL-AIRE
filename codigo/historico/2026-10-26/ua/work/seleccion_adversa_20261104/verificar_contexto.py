"""Check physical diagnostics against frozen meteorological slices and old independent review."""
from piloto import *
def main():
    receipts=read(OUT/'Trazabilidad_horas_revisadas.json');slices=0;cache={}
    for cid,rr in receipts.items():
        rp=Path(rr['receipt']);r=read(rp);season=r['season'];sc=r['scenario'];day=pd.Timestamp(r['day']);folder=(B if 'WS' in sc else A)/'Meteorologia'/season/sc
        for kind in ['SFC','PFL']:
            key=(season,sc,kind)
            if key not in cache:cache[key]=(folder/f'met.{kind}').read_text().splitlines()
            raw=cache[key];lines=[l for l in (raw[1:] if kind=='SFC' else raw) if tuple(map(int,l.split()[:3]))==(day.year,day.month,day.day)]
            text='\n'.join((raw[:1] if kind=='SFC' else [])+lines)+'\n'
            assert hashlib.sha256(text.encode('ascii')).hexdigest()==r['inputs'][f'met.{kind}'],(cid,kind)
            slices+=1
    independent=read(Path(r'/archivo/usuario\Documents\Codex\2026-10-08\auditor-a-t-cnica-y-reorganizaci\outputs\Revision_metodologia_2026-11-04\Comprobacion_estadisticos_y_maximos.json'))
    sel=pd.read_csv(OUT/'Seleccion_numerica_32_indicadores.csv')
    for r in independent['comparisons']:
        g=sel[(sel.season==r['season'])&(sel.pollutant==r['pollutant'])&(sel.receptor==r['receptor'])]
        m=g[g.metric=='media_periodo'].iloc[0];q=g[g.metric=='maximo_diario_24h'].iloc[0]
        assert m.scenario==r['largest_period_mean_scenario'] and np.isclose(m.value,r['largest_period_mean'],atol=1e-10,rtol=0)
        assert q.scenario==r['largest_daily_scenario'] and np.isclose(q.value,r['largest_daily_concentration'],atol=1e-10,rtol=0)
    cube=np.array(list(__import__('itertools').product([0.,1.],repeat=3)));hp=hull_planes(cube)
    assert (hp[:,:3]@np.array([.5,.5,.5])+hp[:,3]).max()<0 and (hp[:,:3]@np.array([1.1,.5,.5])+hp[:,3]).max()>0
    ep=pd.read_csv(OUT/'Episodios_meteorologia_concentracion.csv');d=pd.concat([pd.read_csv(p/'Medias_diarias_civiles.csv') for p in [A,B]]).drop_duplicates(['season','day','scenario','pollutant','x_m','y_m']);d=d[d.receptor.ne('Panel')]
    joined=ep.merge(d,on=['season','day','scenario','pollutant','receptor'],validate='one_to_one');err=(joined.mean_C-joined.media_horas_validas_ug_m3).abs().max();assert err<1e-10
    putjson(OUT/'Verificacion_cruzada.json',dict(status='PASSED',frozen_met_slices=slices,independent_selected_indicators=32,reproduced_episode_means=len(joined),maximum_absolute_error=float(err),joint_hull_sanity=True,meaning='Integrity and calculation verification, not physical validation.'))
    print('Verified',slices,'frozen met slices,32indicators,',len(joined),'episode means')
if __name__=='__main__':main()
