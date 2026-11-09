"""Reconstrucción separada y presentación de evaluación temporal adicional."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from evaluacion_febrero_20261021 import ROOT,O,OUT,FIT,OBS_PATH,BASE,OBS,RES,read,rec,verify,guardar_json

def main():
    dest=OUT/'Recepcion';assert not (dest/'Verificacion.json').exists()
    verify(read(OUT/'Congelacion.json')['archivos']);verify(read(OUT/'Predicciones_congeladas.json')['archivos'])
    verify(read(OUT/'Evaluacion/Verificacion.json')['archivos'])
    fit=pd.read_csv(FIT,parse_dates=['fecha_local']);base=pd.read_csv(OUT/'Predictores.csv',parse_dates=['fecha_local'])
    a=np.load(OUT/'Predicciones.npz');r=fit[RES].to_numpy();idx=a['indices']
    assert idx.shape==(1024,168) and idx.max()<744
    assert np.isfinite(r[idx]).all() and (np.diff(idx.reshape(1024,7,24),axis=2)==1).all()
    assert (idx%24==np.arange(168)[None]%24).all()
    def x(frame):
        hour=frame.fecha_local.dt.hour+frame.fecha_local.dt.minute/60
        return np.column_stack([frame[BASE],np.sin(2*np.pi*hour/24),np.cos(2*np.pi*hour/24)])
    xf,xt=x(fit),x(base);ok=np.isfinite(np.c_[xf,r]).all(axis=1)
    mu=xf[ok].mean(axis=0);scale=xf[ok].std(axis=0);b=r[ok].mean(axis=0)
    z=(xf[ok]-mu)/scale
    coef=np.linalg.solve(z.T@z/ok.sum()+.1*np.eye(5),z.T@(r[ok]-b)/ok.sum())
    m=b+(xf-mu)/scale@coef;mt=b+(xt-mu)/scale@coef
    pool=(r-m)[a['starts'][:,None]+np.arange(24)];center=pool.mean(axis=(0,1))
    np.testing.assert_allclose(mt,a['mean_target'],atol=1e-12,rtol=0)
    np.testing.assert_allclose(base[BASE].to_numpy()[None]+r[idx],a['G1_24'],atol=1e-12,rtol=0)
    np.testing.assert_allclose(base[BASE].to_numpy()[None]+mt[None]+(r-m)[idx]-center,a['RIDGE_24'],atol=1e-12,rtol=0)
    # Interpolación temporal explícita entre h y h+1; conserva49/60.
    hourly=pd.read_csv(OUT/'WRF_estacion_horario.csv')
    explicit=hourly[BASE].to_numpy()[:-1]*(11/60)+hourly[BASE].to_numpy()[1:]*(49/60)
    np.testing.assert_allclose(explicit,base[BASE],atol=1e-12,rtol=0)
    d=pd.read_csv(OUT/'Evaluacion/Pares.csv',parse_dates=['fecha_local'])
    assert len(d)==168 and d.valido_conjunto.all()
    raw=pd.read_csv(OBS_PATH,parse_dates=['Fecha_original']).set_index('Fecha_original').loc[d.fecha_local]
    direction=np.deg2rad(raw.Direccion_viento_grados.to_numpy());speed=raw.Velocidad_viento_m_s.to_numpy()
    observed=np.column_stack([raw.Temperatura_aire_C,-speed*np.sin(direction),-speed*np.cos(direction)])
    np.testing.assert_allclose(observed,d[OBS],atol=1e-12,rtol=0)
    metrics=pd.read_csv(OUT/'Evaluacion/Metricas.csv').set_index(['modelo','variable'])
    errors=[]
    for name in ['BASE','RIDGE','G1_24','RIDGE_24']:
        p=a[name] if a[name].ndim==3 else a[name][None]
        # Fórmula alternativa desde valores ordenados frente a integralCDF previa.
        s=np.sort(p,axis=0);n=len(p);weights=(2*np.arange(1,n+1)-n-1).reshape(n,1,1)
        score=np.abs(p-observed).mean(axis=0)-(s*weights).sum(axis=0)/(n*n)
        for j,var in enumerate(['T','u','v']):
            row=metrics.loc[(name,var)];delta=float(abs(score[:,j].mean()-row.CRPS));errors.append(delta)
            assert delta<2e-12
            for level in [50,80,90]:
                lo,hi=np.quantile(p[:,:,j],[(1-level/100)/2,(1+level/100)/2],axis=0)
                np.testing.assert_allclose(((observed[:,j]>=lo)&(observed[:,j]<=hi)).mean(),row[f'cobertura{level}'],atol=1e-14,rtol=0)
    dest.mkdir(exist_ok=True)
    fig,axes=plt.subplots(3,1,figsize=(11,8.8),sharex=True,layout='constrained')
    p=a['RIDGE_24'];lo,hi=np.quantile(p,[.05,.95],axis=0)
    for j,ax in enumerate(axes):
        ax.fill_between(d.fecha_local,lo[:,j],hi[:,j],color='#b6ded2',label='Intervalo central nominal90 %')
        ax.plot(d.fecha_local,p.mean(axis=0)[:,j],color='#126a57',lw=1.5,label='Media condicional')
        ax.plot(d.fecha_local,observed[:,j],color='#923250',lw=1.2,label='Observación')
        ax.set_ylabel(['Temperatura (°C)','Viento este u (m/s)','Viento norte v (m/s)'][j])
        ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
    axes[0].legend(fontsize=9,loc='upper left',ncol=3)
    axes[-1].xaxis.set_major_locator(mdates.DayLocator());axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d feb'))
    axes[-1].set_xlabel('2017 · hora local bajo H-CIVIL · registros a :49')
    fig.suptitle('Evaluación temporal adicional con modelo fijo\nT:93,5 % · u:72,6 % · v:77,4 % de cobertura observada del intervalo90 %',fontsize=14)
    for ext in ['png','pdf']:fig.savefig(dest/f'Evaluacion_adicional.{ext}',dpi=170,facecolor='white')
    plt.close(fig)
    changes={v:100*(metrics.loc[('RIDGE_24',v),'CRPS']/metrics.loc[('G1_24',v),'CRPS']-1) for v in ['T','u','v']}
    text=f'''# Evaluación adicional del1–7 de febrero

El modelo condicional fijo mejora el CRPS de las tres variables frente a WRF y a los bloques crudos de24h. **La cobertura del viento sigue siendo insuficiente para atribuir a sus intervalos la probabilidad nominal.** Se cierra esta comprobación sin modificar parámetros, bandas ni reloj. El BASE estacional puede avanzar; esta limitación afecta la interpretación probabilística de las perturbaciones, no la posibilidad de calcular la referencia.

Se usaron168 ternas válidas, ajuste21dic–20ene y11 días de separación. La semana se fijó por calendario, después de auditar el historial local, antes de leer sus observaciones para puntuar. Diseño, ajuste y predicciones se congelaron por etapas. Los valores observacionales habían tenido auditorías generales previas; se denomina evaluación temporal adicional con exposición descriptiva, no validación externa plenamente ciega. Los datos24–30ene no vuelven a usarse como reserva.

| Variable | CRPS WRF | CRPS bloques24h | CRPS condicional24h | Cambio vs bloques | Cobertura90 condicional |
|---|---:|---:|---:|---:|---:|
'''
    for v in ['T','u','v']:
        unit='°C' if v=='T' else 'm/s';row=metrics.loc[('RIDGE_24',v)]
        text+=f'| {v} ({unit}) | {metrics.loc[("BASE",v),"CRPS"]:.4f} | {metrics.loc[("G1_24",v),"CRPS"]:.4f} | {row.CRPS:.4f} | {changes[v]:.1f}% | {100*row.cobertura90:.1f}% |\n'
    text+='''
CRPS menor es mejor; no se suman unidades distintas. Los sesgos predicho−observado del conjunto condicional son−0,331°C,+0,102m/s y−0,661m/s. Las anchuras medias del intervalo90 son4,284°C,3,937m/s y5,532m/s. La cobertura de u baja respecto de los bloques crudos (75,6%→72,6%), y la de v también (82,1%→77,4%), aunque mejora el CRPS. No se omiten esos deterioros.

Sólo1/168horas tiene un predictor fuera del rango marginal de ajuste; se conserva. Esto no demuestra soporte multivariado. La persistencia de las discrepancias sigue desajustada: a24h T observada0,623 frente mediana simulada0,269; u0,518 frente0,754; v0,127 frente0,325. Los percentiles entre miembros no son intervalos de confianza de correlación. Los1024 miembros tampoco son1024 observaciones independientes.

La recepción separada reconstruye el ajuste, los índices de bloques conjuntos, las trayectorias, las observaciones de viento y la interpolación a49/60 de hora. Contrasta CRPS por dos fórmulas y coberturas. No hay cambios en fuentes, emisividad, cotas, red de receptores ni concentraciones calculadas en esta evaluación.

## Decisión operativa

No abrir otra ronda de ajuste automático para acercarse al90% en esta semana. Conservar el candidato como modelo fijo para un primer lote de **propagación exploratoria**, con la cobertura y dependencia deficientes declaradas. Cualquier dispersión entre concentraciones de ese lote describe los escenarios generados; no constituye por sí sola un intervalo calibrado ni incertidumbre total. Ocho realizaciones pueden verificar la transferencia y costo, pero no sostienen un P95.

Preparar el BASE del verano en paralelo es coherente con la pregunta de tesis: mantener fuentes y receptores fijos, y comparar posteriormente cómo las discrepancias meteorológicas cambian la concentración. La incertidumbre del huso, la altura de sensores y la transferencia estación→dominio/perfil permanece estructural. El muestreo de validación meteorológica conserva la ubicación de estación previa, distinta del receptor de concentración Piedra Carvajal.

**Texto para tesis:** “La evaluación temporal adicional del1 al7 de febrero, con168 ternas válidas y sin reajuste del candidato, mantuvo la mejora de CRPS respecto al remuestreo crudo. No obstante, las coberturas de los intervalos centrales nominales del90% fueron93,5%,72,6% y77,4% para T,u yv, respectivamente. Junto con los desajustes de persistencia, esto limita la interpretación probabilística de los escenarios propagados y obliga a distinguir sensibilidad exploratoria de incertidumbre calibrada.”
'''
    (dest/'Decision.md').write_text(text,encoding='utf-8')
    guardar_json(dest/'Verificacion.json',dict(estado='EVALUACION_ADICIONAL_RECIBIDA',ternas=168,
        error_max_CRPS=max(errors),reconstruccion_trayectorias=True,observaciones_e_interpolacion_verificadas=True,
        modelo_reajustado=False,calibracion_acreditada=False,decision='CANDIDATO_FIJO_PARA_PROPAGACION_EXPLORATORIA',
        archivos=[rec(p) for p in [Path(__file__),OUT/'Evaluacion/Verificacion.json',OUT/'Predicciones_congeladas.json',*dest.iterdir()]]))
    print('Evaluación adicional recibida; candidato fijo, cobertura de viento limitada.',flush=True)

if __name__=='__main__':main()
