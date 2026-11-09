"""Paired physical diagnostics of retained and daily-adverse empirical scenarios."""
from piloto import *
def main():
    hn=pd.read_csv(PILOT/'Horas_cuatro_receptores.csv');rows=[];hours=[];cache={};audit={}
    specs=[('VERANO','2017-01-16','OBS_U','Los Bronces'),('VERANO','2017-01-26','OBS_V','La Paloma'),('INVIERNO','2017-07-09','OBS_U','Los Bronces')]
    points={'Los Bronces':(380148.,6331485.),'La Paloma':(381759.,6327947.)}
    geo=pd.read_csv(OUT/'Diagnostico_geometrico_transporte.csv')
    for season,day,scenario,rec in specs:
        g=hn[(hn.season==season)&(hn.day==day)&(hn.scenario==scenario)&(hn.receptor==rec)&(hn.pollutant=='MP10')].copy()
        b=get_hourly(season,day,'BASE','MP10',cache,audit);x,y=points[rec];b=b[(b.x_m==x)&(b.y_m==y)].copy()
        met,_=sfc(season,'BASE');b=b.merge(met,on='fin_LST',validate='one_to_one')
        peak=g.loc[g.C_ug_m3.idxmax()];peak_time=pd.Timestamp(peak.fin_LST)
        for sc,data in [('BASE',b),(scenario,g)]:
            assert len(data)==24
            same=data[pd.to_datetime(data.fin_LST)==peak_time].iloc[0]
            weights=data.C_ug_m3/data.C_ug_m3.sum()
            row=dict(season=season,day=day,scenario=sc,receptor=rec,mean_ug_m3=float(data.C_ug_m3.mean()),peak_reference_end_LST=str(peak_time),C_at_reference_hour=float(same.C_ug_m3),WS_at_reference_hour=float(same.WS),WD_at_reference_hour=float(same.WD),L_at_reference_hour=float(same.L),zim_at_reference_hour=float(same.zim),share_reference_hour_pct=float(same.C_ug_m3/data.C_ug_m3.sum()*100),C_share_stable_pct=float(weights[data.L>0].sum()*100),C_weighted_WS_ms=float((weights*data.WS).sum()))
            match=geo[(geo.season==season)&(geo.day==day)&(geo.scenario==sc)&(geo.receptor==rec)].iloc[0]
            row['emission_fraction_sector30_pct']=100*match.fraction_emission_within_30deg
            rows.append(row)
            tmp=data[['fin_LST','C_ug_m3','WS','WD','L','zim','T_K']].copy()
            tmp['season']=season;tmp['day']=day;tmp['scenario']=sc;tmp['receptor']=rec;hours.append(tmp)
    pd.DataFrame(rows).to_csv(OUT/'Diagnostico_candidatos_finales.csv',index=False,encoding='utf-8-sig')
    pd.concat(hours).to_csv(OUT/'Horas_candidatos_finales.csv',index=False,encoding='utf-8-sig')
    putjson(OUT/'Trazabilidad_diagnostico_final.json',audit)
    print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':main()
