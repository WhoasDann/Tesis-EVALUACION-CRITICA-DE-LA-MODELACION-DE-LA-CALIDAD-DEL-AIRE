"""Figures from verified complete comparisons; regenerate after receipt completion."""
from pathlib import Path
import sys,json
sys.path.insert(0,r'/archivo/usuario\Documents\Codex\2026-10-19\es\work\python_deps')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np,pandas as pd
from prepare_sensitivity import ROOT,OUT,read,save,rec,now,sha
POINTS=['Los Bronces','Sulfatos','Piedra Carvajal','La Paloma']
SCENARIOS=['T_MINUS','T_PLUS','U_MINUS','U_PLUS','V_MINUS','V_PLUS']
LABELS=['T−','T+','u−','u+','v−','v+']
def main():
 src=OUT/'Resumen_cuatro_receptores.csv';raw=OUT/'Comparaciones_completas.csv'
 before=[rec(src),rec(raw)]
 a=pd.read_csv(src);daily=pd.read_csv(raw);daily=daily[daily.receptor.isin(POINTS)]
 # Keep only dates complete for both pollutants.
 cov=daily.groupby(['season','day']).pollutant.nunique();valid=cov[cov==2].reset_index()[['season','day']]
 daily=daily.merge(valid,on=['season','day'],validate='many_to_one')
 assert len(daily)>0
 figs=OUT/'Figuras';figs.mkdir(exist_ok=True)
 plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})
 fig,axes=plt.subplots(2,2,figsize=(13.5,8.5))
 for i,s in enumerate(['VERANO','INVIERNO']):
  for j,p in enumerate(['MP10','MP25']):
   ax=axes[i,j];part=a[a.season.eq(s)&a.pollutant.eq(p)&a.scenario.isin(SCENARIOS)]
   matrix=part.pivot(index='receptor',columns='scenario',values='delta_ug_m3').reindex(index=POINTS,columns=SCENARIOS)
   assert not matrix.isna().any().any()
   vmax=max(.00001,float(np.abs(matrix.to_numpy()).max()))
   im=ax.imshow(matrix.to_numpy(),cmap='RdBu_r',vmin=-vmax,vmax=vmax,aspect='auto')
   ax.set_xticks(range(6),LABELS);ax.set_yticks(range(4),POINTS)
   for yy in range(4):
    for xx in range(6):
     v=matrix.iloc[yy,xx];ax.text(xx,yy,f'{v:+.3g}',ha='center',va='center',color='white' if abs(v)>.6*vmax else '#17202A',fontsize=9)
   n=int(part.days.min());ax.set_title(f'{s.title()} · {"MP2,5" if p=="MP25" else "MP10"} · {n} días completos')
   fig.colorbar(im,ax=ax,fraction=.035,pad=.03,label='Cambio respecto de BASE (µg/m³)')
 fig.suptitle('Sensibilidad de la concentración media en los cuatro receptores',fontsize=16,y=.99)
 fig.text(.02,.015,'Medias sobre las mismas horas válidas. Una variable por caso; escalas de color propias de cada panel.\nPeríodos ilustrativos, operador ONSITE atenuado. No son intervalos de incertidumbre ni máximos de toda la malla.',fontsize=10)
 fig.tight_layout(rect=[0,.07,1,.955]);fig.savefig(figs/'Cambios_por_receptor.png',dpi=170);plt.close(fig)
 for pol in ['MP10','MP25']:
  fig,axes=plt.subplots(4,2,figsize=(10,11.7))
  for row,name in enumerate(POINTS):
   for col,season in enumerate(['VERANO','INVIERNO']):
    ax=axes[row,col]
    g=daily[daily.season.eq(season)&daily.pollutant.eq(pol)&daily.receptor.eq(name)].sort_values('day')
    dates=pd.date_range(g.day.min(),g.day.max())
    vals=g.set_index(pd.to_datetime(g.day)).BASE.reindex(dates)
    ax.plot(range(len(dates)),vals,marker='o',color='#21618c',markersize=4)
    ticks=list(range(0,len(dates),3))+[len(dates)-1]; ax.set_xticks(ticks,dates[ticks].strftime('%d-%b'),rotation=45,ha='right',fontsize=10)
    ax.set_title(f'{name} · {season.title()} · {len(g)} días completos',fontsize=12)
    ax.set_ylabel('Media (µg/m³)');ax.grid(alpha=.22)
    if vals.dropna().eq(0).all():
     ax.text(.5,.75,'Valores nulos a la precisión de salida',transform=ax.transAxes,ha='center',fontsize=8)
  fig.suptitle('Variabilidad diaria BASE · '+('MP2,5' if pol=='MP25' else 'MP10'),fontsize=16,y=.995)
  fig.text(.02,.012,'Escalas verticales propias de cada receptor. Quince días consecutivos por temporada.\nAporte modelado, medias de horas válidas; período ilustrativo, sin representatividad estacional.',fontsize=10)
  fig.tight_layout(rect=[0,.055,1,.97])
  fig.savefig(figs/('Variabilidad_diaria_BASE.png' if pol=='MP10' else 'Variabilidad_diaria_BASE_MP25.png'),dpi=170);plt.close(fig)
 assert all(sha(x['path'])==x['sha256'] for x in before),'Tables changed during rendering; rerun'
 save(OUT/'Figuras_verificables.json',dict(created_utc=now(),inputs=before,days_by_season={s:int(len(valid[valid.season.eq(s)])) for s in ['VERANO','INVIERNO']},figures=[rec(p) for p in sorted(figs.glob('*.png'))],scope='Only complete same-date comparisons; numerical annotations from paired valid-hour means.'))
 print('Figures generated',flush=True)
if __name__=='__main__':main()


