"""Geometric transport diagnostics; not an AERMOD source-contribution decomposition."""
from piloto import *
def main():
    plan=read(PILOT/'Lote_local/plan.json')
    f=OLD/'outputs/BASE_verano_2026-10-21/Comunes/fuentes_aermod.inc'
    locations={};widths={}
    for line in f.read_text().splitlines():
        a=line.split()
        if a[1]=='LOCATION':
            assert a[3]=='LINE';x1,y1,x2,y2=map(float,a[4:8]);locations[a[2]]=(.5*(x1+x2),.5*(y1+y2),np.hypot(x2-x1,y2-y1))
        elif a[1]=='SRCPARAM':widths[a[2]]=float(a[5])
    assert len(locations)==len(widths)==12263
    source=pd.DataFrame([(sid,*v,widths[sid]) for sid,v in locations.items()],columns=['source','x','y','length','width'])
    source.to_csv(OUT/'Geometria_fuentes.csv',index=False)
    points={'Los Bronces':(380148.,6331485.),'Piedra Carvajal':(381128.,6323667.),'Sulfatos':(384254.,6324494.),'La Paloma':(381759.,6327947.)}
    out=[];active=[]
    for season,day,hour,candidate,new in [('INVIERNO','2017-06-28',17,'U_PLUS','OBS_U'),('VERANO','2017-01-12',20,'V_MINUS','OBS_V'),('VERANO','2017-01-16',1,'U_PLUS','OBS_U'),('VERANO','2017-01-26',9,'V_MINUS','OBS_V'),('INVIERNO','2017-07-09',3,'U_PLUS','OBS_U')]:
        c=next(c for c in plan['cases'] if c['season']==season and c['day']==day and c['pollutant']=='MP10')
        path=c['input_sources']['MP10.emi'];assert sha(path)==c['inputs']['MP10.emi']
        emi={}
        for line in Path(path).open():
            a=line.split()
            if int(a[5])==hour:emi[a[6]]=float(a[7])
        assert set(emi)==set(locations)
        src=source.copy();src['rate_g_s']=src.source.map(emi)*src.length*src.width
        src=src[src.rate_g_s>0];src['season']=season;src['day']=day;src['hour_LST_end']=hour;active.append(src)
        weights=src.rate_g_s.to_numpy()/src.rate_g_s.sum()
        for scenario in ['BASE',candidate,new]:
            folder=PILOT/'Meteorologia'/season/scenario if scenario.startswith('OBS') else None
            met,_=sfc(season,scenario,folder);row=met[(met.fin_LST==pd.Timestamp(day)+pd.Timedelta(hours=hour))].iloc[0]
            for rec,(rx,ry) in points.items():
                bearing=np.rad2deg(np.arctan2(rx-src.x,ry-src.y))%360
                departure=((row.WD+180-bearing+180)%360-180).to_numpy()
                cosine=float(np.sum(weights*np.cos(np.deg2rad(departure))))
                out.append(dict(season=season,day=day,hour_LST_end=hour,scenario=scenario,receptor=rec,WS=row.WS,WD_from=row.WD,L=row.L,zim=row.zim,active_source_count=len(src),total_emission_g_s=float(src.rate_g_s.sum()),emission_weighted_direction_cosine=cosine,fraction_emission_within_15deg=float(weights[np.abs(departure)<=15].sum()),fraction_emission_within_30deg=float(weights[np.abs(departure)<=30].sum()),interpretation='Geometric overlap only; no terrain, vertical plume, distance dilution, or source-attribution calculation.'))
    pd.DataFrame(out).to_csv(OUT/'Diagnostico_geometrico_transporte.csv',index=False,encoding='utf-8-sig')
    pd.concat(active).to_csv(OUT/'Fuentes_activas_episodios.csv',index=False,encoding='utf-8-sig')
    print(pd.DataFrame(out)[lambda d:d.receptor.isin(['Los Bronces','Sulfatos'])].drop(columns='interpretation').to_string(index=False))
if __name__=='__main__':main()
