"""Figuras del manuscrito: lectura independiente de ocho casos cerrados.
No importa ejecutores ni modifica la biblioteca o las simulaciones.
"""
from pathlib import Path
import sys,hashlib,json,csv,shutil,math
from datetime import datetime,timedelta
from collections import Counter
W=Path(__file__).resolve().parent
sys.path.append(str(W.parent/'python_deps'))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator,FuncFormatter

E=Path(r'/archivo/usuario\Documents\Codex\2026-10-08\hem\outputs')
L=E/'BASE_verano_2026-10-21/Lote_estacional'
OUT=W/'figuras';OUT.mkdir(exist_ok=True)
IMG=W/'fuentes/img'
IMG.mkdir(parents=True,exist_ok=True)
points={'PCAR':(381128.,6323667.),'LBCEN':(380148.,6331485.),'SULF':(384254.,6324494.),'PALP':(381759.,6327947.)}
labels={'PCAR':'Piedra Carvajal','LBCEN':'Los Bronces, estación','SULF':'Sulfatos','PALP':'La Paloma, punto'}
xy_to_id={v:k for k,v in points.items()}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
series=[];met=[];daily=[];zone=[];manifest=[]
for day in range(21,25):
    tag=f'201612{day}'; fecha=f'2016-12-{day}'
    for pol in ['MP10','MP25']:
        rp=L/'Recibos'/f'{tag}_{pol}.json';rec=json.loads(rp.read_text(encoding='utf-8-sig'))
        assert rec['dia']==fecha and rec['contaminante']==pol
        q=rec['qa'];assert q['horas_validas']==q['horas_calendario']==24
        assert q['fuentes']==12263 and q['receptores']==6295 and q['valores_enmascarados']==0
        folder=Path(rec['carpeta'])
        contracts={Path(x['path']).name:x['sha256'] for x in rec['archivos']}
        critical=['receptor_horas.out','Por_receptor_estacional.csv','Por_ambito_estacional.csv','Cobertura_usada.csv','fuentes_aermod.inc','receptores.inc','aermod.out']
        for n in critical:
            assert sha(folder/n)==contracts[n],(folder,n,'hash distinto del recibo')
        dest=W/'evidencia/BASE_21_24dic'/f'{tag}_{pol}';dest.mkdir(parents=True,exist_ok=True)
        for n in ['Por_receptor_estacional.csv','Por_ambito_estacional.csv','Cobertura_usada.csv']:
            shutil.copy2(folder/n,dest/n)
        shutil.copy2(rp,dest/'Recibo.json')
        cobertura=pd.read_csv(folder/'Cobertura_usada.csv')
        assert len(cobertura)==24 and cobertura.apta_dispersion.all() and set(cobertura.estado)=={'VALIDA'}
        if pol=='MP10':met.extend(cobertura.to_dict('records'))
        else:
            prev=pd.read_csv(W/'evidencia/BASE_21_24dic'/f'{tag}_MP10/Cobertura_usada.csv')
            pd.testing.assert_frame_equal(cobertura,prev)
        means=pd.read_csv(folder/'Por_receptor_estacional.csv')
        zones=pd.read_csv(folder/'Por_ambito_estacional.csv')
        assert len(means)==6295 and (means.horas_validas==24).all()
        all_xy=set(); times=Counter(); selected=[]
        with (folder/'receptor_horas.out').open(encoding='ascii') as f:
            for line in f:
                if not line.strip() or line.startswith('*'):continue
                v=line.split();assert v[6]=='1-HR' and v[7]=='ALL'
                x,y,conc=map(float,v[:3]);assert math.isfinite(conc) and conc>=0
                stamp=v[8];assert stamp[:6]==tag[2:]
                h=int(stamp[6:]);assert 1<=h<=24
                times[h]+=1;all_xy.add((x,y))
                if (x,y) in xy_to_id:
                    start=datetime(2016,12,day)+timedelta(hours=h-1)
                    selected.append({'contaminante':pol,'receptor':xy_to_id[(x,y)],'inicio_local':start.isoformat(),'fin_local':(start+timedelta(hours=1)).isoformat(),'dia':fecha,'hora_inicio':h-1,'concentracion_ug_m3':conc})
        assert len(all_xy)==6295 and times==Counter({h:6295 for h in range(1,25)})
        assert len(selected)==96 and len({(x['receptor'],x['hora_inicio']) for x in selected})==96
        assert sha(folder/'receptor_horas.out')==contracts['receptor_horas.out']
        df=pd.DataFrame(selected)
        for receptor,(x,y) in points.items():
            m=means[(means.x_m==x)&(means.y_m==y)]
            assert len(m)==1
            calc=df[df.receptor==receptor].concentracion_ug_m3.mean()
            assert abs(calc-float(m.iloc[0].media_24h_ug_m3))<1e-10
            daily.append({'contaminante':pol,'receptor':receptor,'dia':fecha,'media_24h_ug_m3':calc})
        for row in zones.to_dict('records'):zone.append({'contaminante':pol,**row})
        series.extend(selected)
        manifest.append({'recibo':str(rp),'sha256_recibo':sha(rp),'fuentes':q['fuentes'],'receptores':q['receptores'],'horas':24,'archivos_verificados':{str(folder/n):contracts[n] for n in critical}})

df=pd.DataFrame(series).sort_values(['contaminante','receptor','inicio_local'])
assert len(df)==768 and df.groupby(['contaminante','receptor']).size().eq(96).all()
df['inicio_local']=pd.to_datetime(df.inicio_local)
df.to_csv(OUT/'Series_concentracion_21_24dic.csv',index=False)
dd=pd.DataFrame(daily);dd.to_csv(OUT/'Medias_diarias_21_24dic.csv',index=False)
md=pd.DataFrame(met).sort_values('inicio_local');md['inicio_local']=pd.to_datetime(md.inicio_local)
assert len(md)==96 and md.inicio_local.is_unique
assert md.inicio_local.diff().dropna().eq(pd.Timedelta(hours=1)).all()
md.to_csv(OUT/'Meteorologia_SFC_21_24dic.csv',index=False)
pd.DataFrame(zone).to_csv(OUT/'Maximos_zonales_diarios_21_24dic.csv',index=False)
fmt=FuncFormatter(lambda x,pos:f'{x:g}'.replace('.',','))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':11,'axes.labelsize':10,'figure.dpi':160,'savefig.dpi':200,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'axes.formatter.useoffset':False})
def style(ax):
    ax.grid(alpha=.20,linewidth=.5);ax.yaxis.set_major_formatter(fmt);ax.yaxis.set_major_locator(MaxNLocator(4));ax.set_axisbelow(True)
def dates(ax):
    ax.xaxis.set_major_locator(mdates.DayLocator());ax.xaxis.set_major_formatter(mdates.DateFormatter('%d dic'))
    ax.set_xlim(datetime(2016,12,21),datetime(2016,12,25))
def save(fig,name):
    fig.savefig(OUT/f'{name}.pdf',bbox_inches='tight');fig.savefig(OUT/f'{name}.png',bbox_inches='tight');plt.close(fig)
    shutil.copy2(OUT/f'{name}.pdf',IMG/f'{name}.pdf')

fig,axs=plt.subplots(4,2,figsize=(10,9.5),sharex=True,layout='constrained')
for i,r in enumerate(points):
    for j,pol in enumerate(['MP10','MP25']):
        a=axs[i,j];z=df[(df.receptor==r)&(df.contaminante==pol)]
        a.plot(z.inicio_local,z.concentracion_ug_m3,color=['#236287','#a74d2c'][j],lw=1)
        for day,zday in z.groupby('dia'):
            start=pd.Timestamp(day);mean=zday.concentracion_ug_m3.mean()
            a.hlines(mean,start,start+pd.Timedelta(days=1),colors='#535353',ls='--',lw=.85,label='Media de 24 h' if day=='2016-12-21' else None)
        a.set_title(labels[r]+(' · MP$_{10}$' if j==0 else ' · MP$_{2,5}$'))
        a.set_ylabel('µg/m³');a.set_ylim(bottom=0);style(a);dates(a)
axs[0,0].legend(frameon=False,fontsize=8,loc='upper left')
fig.supxlabel('Diciembre de 2016 · inicio del intervalo horario · UTC−3 fijo provisional',fontsize=10)
save(fig,'base_series_21_24dic')

fig,axs=plt.subplots(2,2,figsize=(10,6.5),sharex=True,layout='constrained')
cycles=[]
for a,r in zip(axs.flat,points):
    z=df[(df.receptor==r)&(df.contaminante=='MP10')].groupby('hora_inicio').concentracion_ug_m3.agg(['mean','min','max','count'])
    assert z['count'].eq(4).all()
    a.fill_between(z.index,z['min'],z['max'],color='#b9cedb',alpha=.65,label='Mínimo–máximo entre días')
    a.plot(z.index,z['mean'],color='#236287',lw=1.6,label='Media de cuatro días')
    a.set_title(labels[r]);a.set_ylabel('MP$_{10}$ [µg/m³]');a.set_ylim(bottom=0);a.set_xlim(0,23);a.set_xticks([0,6,12,18,23]);style(a)
    for hr,row in z.iterrows():cycles.append({'receptor':r,'hora_inicio':int(hr),**row.to_dict()})
axs[0,0].legend(fontsize=8,frameon=False)
fig.supxlabel('Hora de inicio del intervalo · UTC−3 fijo provisional · n = 4 días por hora',fontsize=10)
save(fig,'base_perfil_horario_21_24dic')
pd.DataFrame(cycles).to_csv(OUT/'Perfil_horario_MP10_21_24dic.csv',index=False)

fig,axs=plt.subplots(4,1,figsize=(10,7.5),sharex=True,layout='constrained')
for a,(col,label,colr) in zip(axs,[('T_K','Temperatura [°C]','#a74d2c'),('WS_ms','Rapidez [m/s]','#236287'),('WD_grados','Dirección [°]','#6b5895'),('ZiM_m','ZiM [m]','#32756a')]):
    y=md[col]-(273.15 if col=='T_K' else 0)
    if col=='WD_grados':
        a.scatter(md.inicio_local,y,s=8,color=colr);a.set_ylim(0,360);a.set_yticks([0,90,180,270,360])
    else:a.plot(md.inicio_local,y,color=colr,lw=1.2)
    a.set_ylabel(label);style(a);dates(a)
    if col=='WD_grados':a.set_yticks([0,90,180,270,360])
    if col in ['WS_ms','ZiM_m']:a.set_ylim(bottom=0)
fig.supxlabel('Diciembre de 2016 · inicio del intervalo horario · UTC−3 fijo provisional',fontsize=10)
save(fig,'base_meteorologia_21_24dic')

vertical=E/'Contraste_vertical_2026-10-20/Recepcion/Efecto_vertical_por_receptor.pdf'
shutil.copy2(vertical,IMG/'sensibilidad_vertical.pdf')
stats={}
for r in points:
    z=df[(df.receptor==r)&(df.contaminante=='MP10')]
    row=z.loc[z.concentracion_ug_m3.idxmax()]
    cyc=pd.DataFrame(cycles).query('receptor == @r');hi=cyc.loc[cyc['mean'].idxmax()]
    stats[r]={'media_96h':float(z.concentracion_ug_m3.mean()),'maximo_1h':float(row.concentracion_ug_m3),'inicio_maximo':str(row.inicio_local),'hora_maxima_media_4dias':int(hi.hora_inicio),'maxima_media_horaria':float(hi['mean'])}
out={'fecha':'2026-10-23','ventana_inicio_local':'2016-12-21 00:00','ventana_fin_exclusivo_local':'2016-12-25 00:00','reloj':'UTC-3 fijo provisional','casos_recibidos_utilizados':8,'horas_por_contaminante':96,'concentraciones_nativas_controladas':8*24*6295,'valores_en_series_puntos':768,'fuentes':12263,'receptores':6295,'validacion_medias':'Recalculadas desde POSTFILE horario y coinciden con los CSV recibidos a tolerancia absoluta 1e-10 µg/m³.','faltantes_y_calmas':0,'resumen_MP10':stats,'casos':manifest,'figura_vertical':{'origen':str(vertical),'sha256':sha(vertical)},'productos':[{ 'archivo':p.name,'sha256':sha(p)} for p in sorted(OUT.glob('*')) if p.is_file()]}
(OUT/'Verificacion_figuras.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k not in ['casos','productos']},ensure_ascii=False,indent=2))
