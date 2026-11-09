from pathlib import Path
import sys
sys.path.insert(0,r'/archivo/usuario\Documents\Codex\2026-10-19\es\work\python_deps')
import numpy as np,pandas as pd,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from prepare_sensitivity import OUT
a=pd.read_csv(OUT/'Resumen_cuatro_receptores.csv')
pts=['Los Bronces','Sulfatos','Piedra Carvajal','La Paloma']
ss=['T_MINUS','T_PLUS','U_MINUS','U_PLUS','V_MINUS','V_PLUS']
labs=['T-','T+','u-','u+','v-','v+']
for pol in ['MP10','MP25']:
 fig,axes=plt.subplots(2,1,figsize=(9,7.4))
 for ax,season in zip(axes,['VERANO','INVIERNO']):
  p=a[a.season.eq(season)&a.pollutant.eq(pol)&a.scenario.isin(ss)]
  m=p.pivot(index='receptor',columns='scenario',values='delta_pct').reindex(index=pts,columns=ss)
  assert m.notna().all().all()
  v=max(1,np.abs(m.values).max())
  im=ax.imshow(m.values,cmap='RdBu_r',vmin=-v,vmax=v,aspect='auto')
  ax.set_xticks(range(6),labs,fontsize=12);ax.set_yticks(range(4),pts,fontsize=12)
  ax.set_title(season.title()+' - 15 días completos',fontsize=14,pad=10)
  for y in range(4):
   for x in range(6):ax.text(x,y,f'{m.iloc[y,x]:+.1f}%',ha='center',va='center',fontsize=12,color='white' if abs(m.iloc[y,x])>.65*v else '#17202A')
  fig.colorbar(im,ax=ax,fraction=.035,pad=.04,label='Cambio (%)')
 fig.suptitle('Sensibilidad de la media del período - '+('MP2,5' if pol=='MP25' else 'MP10'),fontsize=16)
 fig.text(.02,.012,'Mismas horas válidas. Escalas de color por temporada. Un porcentaje grande puede partir de un aporte pequeño.',fontsize=10)
 fig.tight_layout(rect=[0,.05,1,.96]);fig.savefig(OUT/'Figuras'/('Sensibilidad_porcentual_'+pol+'.png'),dpi=180);plt.close(fig)
b=pd.read_csv(OUT/'Medias_por_caso.csv')
b=b[b.scenario.eq('BASE')]
mapping={(380148.,6331485.):'Los Bronces',(384254.,6324494.):'Sulfatos',(381128.,6323667.):'Piedra Carvajal',(381759.,6327947.):'La Paloma'}
b['receptor']=[mapping.get((x,y),'Panel') for x,y in zip(b.x_m,b.y_m)];b=b[b.receptor.ne('Panel')]
rows=[]
for keys,g in b.groupby(['season','pollutant','receptor']):
 mx=g.loc[g.suma_horaria_ug_m3.idxmax()]
 rows.append(dict(zip(['season','pollutant','receptor'],keys),day=mx.day,fraction_hourly_sum=float(mx.suma_horaria_ug_m3/g.suma_horaria_ug_m3.sum())))
pd.DataFrame(rows).to_csv(OUT/'Tabla_dia_dominante.csv',index=False)
print(pd.DataFrame(rows).query("pollutant=='MP10'").to_string(index=False))

