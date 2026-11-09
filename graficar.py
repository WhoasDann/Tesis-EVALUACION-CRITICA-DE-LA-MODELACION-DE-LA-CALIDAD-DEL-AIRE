"""Curvas empíricas de aportes diarios al comparar las nueve configuraciones."""
from collections import defaultdict
from pathlib import Path
import argparse
import csv
import gzip
import statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parent
def render(dest):
    data=defaultdict(list)
    with gzip.open(root/'resultados/Diarios_24h_utilizados.csv.gz','rt',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            data[r['receptor'],r['pollutant'],r['season'],r['scenario']].append(float(r['mean']))
    with (root/'resultados/Referencias_ADC160.csv').open(encoding='utf-8-sig') as f:
        refs={(r['receptor'],r['pollutant']):r['EIA_annual_mean'] for r in csv.DictReader(f)}
    dest.mkdir(exist_ok=True,parents=True)
    for (name,pm),ref in refs.items():
        fig,axes=plt.subplots(1,2,figsize=(11,4.8),sharey=True)
        for season,ax in zip(('VERANO','INVIERNO'),axes):
            choices={sc:v for (n,p,s,sc),v in data.items() if (n,p,s)==(name,pm,season)}
            adverse=max(choices,key=lambda sc:statistics.mean(choices[sc]))
            for sc in dict.fromkeys(('BASE',adverse,'T_WS_PLUS')):
                vals=sorted(choices[sc]);ax.step([vals[0],*vals],[0,*[(i+1)/len(vals) for i in range(len(vals))]],where='post',label=sc)
            base=statistics.mean(choices['BASE'])
            ax.axvline(base,color='#26495e',ls=':',label=f'Media BASE {base:.2f}')
            if ref:ax.axvline(float(ref),color='#775b8d',ls='--',label=f'Media anual ADC {float(ref):.2f}')
            ax.set_title(f'{season.title()} · {len(vals)} días');ax.set_xlabel('Aporte diario (µg/m³)')
            ax.grid(alpha=.15);ax.legend(fontsize=8)
        axes[0].set_ylabel('Fracción acumulada de días')
        fig.suptitle(name+' · '+('MP2,5' if pm=='MP25' else pm))
        fig.tight_layout();fig.savefig(dest/(name.replace(' ','_')+'_'+pm+'.svg'));plt.close(fig)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('destino',type=Path)
    render(parser.parse_args().destino)
