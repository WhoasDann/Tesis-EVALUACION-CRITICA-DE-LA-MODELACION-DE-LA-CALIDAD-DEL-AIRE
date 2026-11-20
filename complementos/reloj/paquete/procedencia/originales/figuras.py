from pathlib import Path
import sys,json,hashlib
import pandas as pd
import numpy as np
sys.path.insert(0,'C:/Users/dcitu/Documents/Codex/2026-10-19/es/work/python_deps')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/Sensibilidad_reloj_ternas_2026-11-15'
D=OUT/'Figuras';D.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False})
a=pd.read_csv(OUT/'Amplitudes_SD.csv');s=pd.read_csv(OUT/'Seleccion_ternas.csv');f=pd.read_csv(OUT/'Ternas_fechas_originales.csv')
clocks=['civil_santiago','fijo_menos3','fijo_menos4','utc'];ops=['interpolacion_instantanea','vecino_15min']
keys=[(c,o) for c in clocks for o in ops]
clock_labels={'civil_santiago':'Civil','fijo_menos3':'UTC−3','fijo_menos4':'UTC−4','utc':'UTC'}
labels=[clock_labels[c]+(' · I' if o==ops[0] else ' · V') for c,o in keys]
fig,axes=plt.subplots(1,2,figsize=(10.5,4.2),layout='constrained')
limit=np.ceil(a.delta_pct_same_sample.abs().max())
for ax,season in zip(axes,['VERANO','INVIERNO']):
    values=np.array([[a[(a.season==season)&(a.clock==c)&(a.operator==o)&(a.variable==v)].delta_pct_same_sample.iloc[0] for v in ['T','u','v','WS']] for c,o in keys])
    im=ax.imshow(values,cmap='RdBu_r',vmin=-limit,vmax=limit,aspect='auto')
    ax.set_xticks(range(4),['Temperatura','u','v','Rapidez'])
    ax.set_yticks(range(8),labels)
    ax.set_title(season.title(),fontsize=12)
    for (i,j),v in np.ndenumerate(values):ax.text(j,i,f'{v:+.1f}%',ha='center',va='center',fontsize=9,color='white' if abs(v)>limit*.65 else '#183641')
fig.colorbar(im,ax=axes,shrink=.84,pad=.03,label='Cambio de SD respecto de civil + interpolación (%)')
fig.savefig(D/'Amplitudes_reloj.png',dpi=200);fig.savefig(D/'Amplitudes_reloj.svg');plt.close(fig)

groups=[('VERANO','OBS_U'),('VERANO','OBS_V'),('INVIERNO','OBS_U')]
colnames=['Verano OBS_U\nOrigen: 27 dic.','Verano OBS_V\nOrigen: 18 ene.','Invierno OBS_U\nOrigen: 2 jul.']
fig,axes=plt.subplots(1,2,figsize=(11.8,4.9),layout='constrained')
for ax,rule,title in zip(axes,['objetivo_y_escala_fijos','regla_recalculada'],['Objetivo y escala originales fijos','Objetivo y escala recalculados']):
    matrix=np.zeros((8,3));dates={}
    for i,(clock,op) in enumerate(keys):
        for j,(season,proto) in enumerate(groups):
            r=s[(s.season==season)&(s.prototype==proto)&(s.clock==clock)&(s.operator==op)&(s.rule==rule)].iloc[0]
            matrix[i,j]=int(r.changed_day);dates[i,j]=pd.Timestamp(r.selected_day).strftime('%d/%m')
    ax.imshow(matrix,cmap=ListedColormap(['#e3edf2','#f4cdad']),vmin=0,vmax=1,aspect='auto')
    ax.set_xticks(range(3),colnames);ax.tick_params(axis='x',length=0,labelsize=8)
    ax.set_yticks(range(8),labels);ax.tick_params(axis='y',length=0)
    ax.set_title(title,fontsize=11)
    for (i,j),date in dates.items():ax.text(j,i,date,ha='center',va='center',fontsize=10,color='#173c4a',weight='bold' if matrix[i,j] else 'normal')
    ax.set_xticks(np.arange(-.5,3,1),minor=True);ax.set_yticks(np.arange(-.5,8,1),minor=True)
    ax.grid(which='minor',color='white',linewidth=2);ax.tick_params(which='minor',length=0)
fig.legend(handles=[Patch(color='#e3edf2',label='Misma fecha de origen'),Patch(color='#f4cdad',label='Fecha distinta')],loc='outside lower center',ncol=2,frameon=False)
fig.savefig(D/'Fechas_ternas_reloj.png',dpi=200);fig.savefig(D/'Fechas_ternas_reloj.svg');plt.close(fig)

fig,axes=plt.subplots(1,3,figsize=(10.6,3.0),layout='constrained')
rowlabels=['Verano OBS_U\n27 dic. 2016','Verano OBS_V\n18 ene. 2017','Invierno OBS_U\n2 jul. 2017']
for ax,var,title in zip(axes,['dT','du','dv'],['ΔT (°C)','Δu (m/s)','Δv (m/s)']):
    for i,(season,proto) in enumerate(groups):
        g=f[(f.season==season)&(f.prototype==proto)]
        ax.plot([g[var].min(),g[var].max()],[i,i],color='#24738c',linewidth=3)
        ax.scatter([g['original_'+var].iloc[0]],[i],color='#222222',s=36,zorder=3)
    ax.set_yticks(range(3),rowlabels if ax is axes[0] else ['']*3);ax.invert_yaxis();ax.set_xlabel(title)
    ax.set_ylim(2.45,-.45);ax.grid(axis='x',alpha=.22);ax.axvline(0,color='#777777',lw=.6,ls=':')
fig.savefig(D/'Vectores_dias_originales.png',dpi=200);fig.savefig(D/'Vectores_dias_originales.svg');plt.close(fig)
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in D.iterdir() if p.suffix in ['.png','.svg']}
(OUT/'Figuras.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print('Tres gráficos PNG/SVG preparados.')
