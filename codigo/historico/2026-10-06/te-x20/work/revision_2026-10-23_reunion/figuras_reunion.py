from pathlib import Path
import ast,hashlib,json,shutil
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
W=Path(__file__).resolve().parent; S=W/'fuentes'; F=W/'figuras'; E=Path(r'/archivo/usuario\Documents\Codex\2026-10-08\hem\outputs')
inputs={}
def freeze(path,name):
    path=Path(path); dst=W/'evidencia'/name; shutil.copy2(path,dst)
    inputs[str(path)]={'copia':name,'sha256':hashlib.sha256(dst.read_bytes()).hexdigest()}
    return dst
fitpath=freeze(E/'Discrepancias_ajuste_2026-10-19/Residuos_ajuste.csv','Residuos_ajuste.csv')
assert hashlib.sha256(fitpath.read_bytes()).hexdigest()=='69ae8317a8b58f3f79e88331e99f8ce9b9bc1d5087aebed2ae607983aa36cde3'
d=pd.read_csv(fitpath); d.index=pd.to_datetime(d.fecha_local)
d=d.loc[d.valido_conjunto.eq(True)].copy()
assert len(d)==737 and d.index.is_unique
d['WS_obs']=np.hypot(d.u_obs_m_s,d.v_obs_m_s);d['WS_WRF']=np.hypot(d.u_earth_m_s,d.v_earth_m_s)
d['r_WS']=d.WS_obs-d.WS_WRF
assert np.allclose(d.residuo_T_C,d.Temperatura_aire_C-d.T2_C)
stats=[]
for name,col in [('T','residuo_T_C'),('WS','r_WS')]:
    r=d[col]
    stats.append(dict(variable=name,n=len(r),media=r.mean(),DE=r.std(ddof=1),mediana=r.median(),P05=r.quantile(.05),P95=r.quantile(.95),P90_abs=r.abs().quantile(.9),P99_abs=r.abs().quantile(.99),IQR=r.quantile(.75)-r.quantile(.25),asimetria=r.skew(),minimo=r.min(),maximo=r.max()))
pd.DataFrame(stats).to_csv(F/'Dispersion_discrepancias.csv',index=False)
d[['residuo_T_C','r_WS']].resample('D').agg(['count','mean','std','min','max']).to_csv(F/'Discrepancias_diarias_T_WS.csv')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
def save(fig,name):
    fig.savefig(S/'img'/f'{name}.pdf',bbox_inches='tight');fig.savefig(F/f'{name}.png',dpi=160,bbox_inches='tight');plt.close(fig)
fig,axs=plt.subplots(2,1,figsize=(9.5,5.4),sharex=True,layout='constrained')
for ax,c,lab in zip(axs,['residuo_T_C','r_WS'],['Temperatura (°C)','Rapidez (m/s)']):
    g=d[c].resample('D'); mu=g.mean();sd=g.std()
    ax.fill_between(mu.index,mu-sd,mu+sd,color='#c8dcec',label='Media diaria ± DE intradiaria')
    ax.plot(mu.index,mu,color='#1f5a80',marker='o',ms=3,label='Media diaria de la discrepancia')
    ax.axhline(0,color='#555555',ls='--',lw=.8);ax.set_ylabel(lab);ax.grid(alpha=.2)
axs[0].legend(loc='upper right',fontsize=8);axs[-1].xaxis.set_major_locator(mdates.DayLocator(interval=5));axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
axs[-1].set_xlabel('Fecha local (2016–2017); discrepancia = observado − WRF')
save(fig,'discrepancias_ajuste')
code=freeze(Path(r'/archivo/usuario\Codigos_VSC\Codigos_oficiales\CiclodiariodirecciónBUENO.py'),'CiclodiariodirecciónBUENO.py')
tree=ast.parse(code.read_text(encoding='utf-8-sig'))
fn=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='matriz_frecuencia_direccion']
assert len(fn)==1
ns={'np':np,'pd':pd,'bins_dir':np.arange(0,361,10)}
exec(compile(ast.Module(body=fn,type_ignores=[]),str(code),'exec'),ns)
v=d.loc[(d.WS_obs>=1)&(d.WS_WRF>=1)].copy()
v['dir_obs']=(270-np.degrees(np.arctan2(v.v_obs_m_s,v.u_obs_m_s)))%360
v['dir_WRF']=(270-np.degrees(np.arctan2(v.v_earth_m_s,v.u_earth_m_s)))%360
mats=[ns['matriz_frecuencia_direccion'](v,c) for c in ['dir_obs','dir_WRF']]
counts=v.groupby(v.index.hour).size().reindex(range(24),fill_value=0)
assert (counts>0).all()
for m in mats: assert np.allclose(m.sum(axis=0),100)
v[['WS_obs','WS_WRF','dir_obs','dir_WRF']].to_csv(F/'Pares_ciclo_direccion.csv',index_label='fecha_local')
counts.to_csv(F/'Soporte_ciclo_direccion.csv',header=['pares'])
for m,n in zip(mats,['observada','WRF']):
    pd.DataFrame(m,index=np.arange(0,360,10),columns=range(24)).to_csv(F/f'Frecuencias_direccion_{n}.csv',index_label='limite_inferior_grados')
fig,axs=plt.subplots(2,1,figsize=(10,8),sharex=True,layout='constrained')
vmax=max(m.max() for m in mats)
for ax,m,title in zip(axs,mats,['Ciclo diario de la dirección del viento: observado','Ciclo diario de la dirección del viento: WRF bilineal']):
    im=ax.imshow(m,origin='lower',aspect='auto',cmap='jet',vmin=0,vmax=vmax,extent=[-.5,23.5,0,360],interpolation='nearest')
    ax.set_title(title);ax.set_ylabel('Dirección del viento (°)');ax.set_yticks(np.arange(0,361,60))
    fig.colorbar(im,ax=ax,label='Frecuencia (%)',pad=.02)
axs[-1].set_xticks(np.arange(24));axs[-1].set_xlabel('Hora local (registros a HH:49)')
save(fig,'ciclo_direccion_BUENO')
pp=freeze(E/'Evaluacion_febrero_2026-10-21/Predicciones.npz','Predicciones_febrero.npz')
assert hashlib.sha256(pp.read_bytes()).hexdigest()=='d81ba9274780950a12c059b8f17dea105a67e25922f23f3ce2a79b3fd2938fd7'
pairs=pd.read_csv(freeze(E/'Evaluacion_febrero_2026-10-21/Evaluacion/Pares.csv','Pares_febrero.csv'))
p=np.load(pp);base=p['BASE']
assert len(pairs)==168 and np.allclose(base,pairs[['T2_C','u_earth_m_s','v_earth_m_s']])
obs=np.column_stack([pairs.Temperatura_aire_C,pairs.Velocidad_viento_m_s])
def transform(x):return np.stack([x[...,0],np.hypot(x[...,1],x[...,2])],axis=-1)
models={k:transform(p[k]) for k in ['BASE','G1_24','RIDGE_24']}
def crps(x,y):
    if x.ndim==1:return np.abs(x-y)
    m=len(x);z=np.sort(x,axis=0)
    return np.mean(np.abs(x-y),axis=0)-np.sum((2*np.arange(1,m+1)-m-1)[:,None]*z,axis=0)/(m*m)
# Independent pairwise check of scoring formula on small subsets.
x=models['RIDGE_24'][:10,:3,1];y=obs[:3,1]
assert np.allclose(crps(x,y),np.abs(x-y).mean(0)-.5*np.abs(x[:,None,:]-x[None,:,:]).mean((0,1)))
rows=[]
for k,x in models.items():
    for j,n in enumerate(['T','WS']):
        a=x[...,j];mean=a if a.ndim==1 else a.mean(0)
        row=dict(modelo=k,variable=n,n=168,CRPS=crps(a,obs[:,j]).mean(),sesgo_pred_menos_obs=(mean-obs[:,j]).mean(),MAE_media=np.abs(mean-obs[:,j]).mean())
        if a.ndim==2:
            lo,hi=np.quantile(a,[.05,.95],axis=0)
            row['cobertura_P05_P95_pct']=100*np.mean((obs[:,j]>=lo)&(obs[:,j]<=hi))
        rows.append(row)
assert abs(rows[0]['CRPS']-2.2319654077)<1e-8
pd.DataFrame(rows).to_csv(F/'Metricas_febrero_T_WS.csv',index=False)
t=pd.to_datetime(pairs.fecha_local)
fig,axs=plt.subplots(2,1,figsize=(10,6.2),sharex=True,layout='constrained')
curves=pd.DataFrame({'fecha_local':t})
for j,(ax,lab,n) in enumerate(zip(axs,['Temperatura (°C)','Rapidez (m/s)'],['T','WS'])):
    a=models['RIDGE_24'][...,j];lo,hi=np.quantile(a,[.05,.95],axis=0)
    ax.fill_between(t,lo,hi,color='#b7d4e8',alpha=.8,label='P5–P95 entre realizaciones')
    ax.plot(t,models['BASE'][:,j],color='#8d8d8d',lw=.9,ls='--',label='WRF')
    ax.plot(t,a.mean(0),color='#176b9b',lw=1.2,label='Media del conjunto')
    ax.plot(t,obs[:,j],color='#202020',lw=1.0,label='Observado')
    ax.set_ylabel(lab);ax.grid(alpha=.2)
    for k,val in [('observado',obs[:,j]),('WRF',models['BASE'][:,j]),('media',a.mean(0)),('P05',lo),('P95',hi)]:curves[f'{n}_{k}']=val
axs[0].legend(ncol=2,fontsize=8,loc='upper left')
axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'));axs[-1].xaxis.set_major_locator(mdates.DayLocator());axs[-1].set_xlabel('Fecha local (febrero de 2017); comparación al instante HH:49')
axs[-1].set_ylim(bottom=0)
save(fig,'evaluacion_febrero');curves.to_csv(F/'Series_febrero_T_WS.csv',index=False)
report={'entradas':inputs,'dispersion':stats,'direccion':{'n':len(v),'excluidos_de737':len(d)-len(v),'por_hora':counts.to_dict(),'vmax':vmax,'ventana':['2016-12-21','2017-01-20'],'funcion_original_reutilizada':fn[0].name,'cambios':'Entradas auditadas; tiempos :49 civiles; filtro >=1 m/s en ambas series; extent centrado en enteros; etiquetas.'},'metricas_febrero':rows}
(W/'evidencia/Verificacion_figuras.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ['dispersion','direccion','metricas_febrero']},ensure_ascii=False,indent=2))

