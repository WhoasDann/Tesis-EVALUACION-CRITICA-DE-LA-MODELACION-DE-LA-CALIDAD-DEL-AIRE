"""Recepción separada de la comparación interna; no importa su implementación."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'outputs/Comparacion_cronologica_2026-10-20'
OUT = PKG / 'Recepcion'
FIT = ROOT / 'outputs/Discrepancias_ajuste_2026-10-19/Residuos_ajuste.csv'
OBS = ['Temperatura_aire_C', 'u_obs_m_s', 'v_obs_m_s']
BASE = ['T2_C', 'u_earth_m_s', 'v_earth_m_s']
RES = ['residuo_T_C', 'residuo_u_m_s', 'residuo_v_m_s']
LABELS = ['T', 'u', 'v']
ERRORS = {}


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def record(p):
    return dict(path=str(Path(p).resolve()), sha256=digest(p))


def same(key, actual, expected, tol=2e-10):
    actual, expected = np.asarray(actual), np.asarray(expected)
    np.testing.assert_allclose(actual, expected, atol=tol, rtol=0, equal_nan=True)
    diff = np.abs(actual - expected)
    finite = diff[np.isfinite(diff)]
    ERRORS[key] = max(ERRORS.get(key, 0.), float(finite.max()) if finite.size else 0.)


def cdf_score(samples, observed):
    """Integral exacta de (F(x)-1{x>=y})² para una distribución empírica."""
    s = np.sort(samples)
    knots = np.sort(np.append(s, observed))
    mids = (knots[:-1] + knots[1:]) / 2
    f = np.searchsorted(s, mids, side='right') / len(s)
    return np.sum(np.diff(knots) * (f - (mids >= observed))**2)


def correlation(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3 or np.std(x[ok]) == 0 or np.std(y[ok]) == 0:
        return np.nan
    return np.corrcoef(x[ok], y[ok])[0, 1]


def main():
    if OUT.exists():
        raise FileExistsError('No sobrescribir una recepción previa')
    checked = {}
    for name in ['Congelacion.json', 'Predicciones_congeladas.json', 'Estado.json']:
        for entry in read(PKG / name)['archivos']:
            assert digest(entry['path']) == entry['sha256'], entry['path']
            checked[entry['path']] = entry
    plan = read(PKG / 'Diseno.json')
    assert read(PKG / 'Predicciones_congeladas.json')['diseno_sha256'] == digest(PKG / 'Congelacion.json')
    data = pd.read_csv(FIT, parse_dates=['fecha_local'])
    assert len(data) == 744 and data.valido_conjunto.sum() == 737
    assert data.fecha_local.equals(pd.Series(pd.date_range('2016-12-21 00:49', periods=744, freq='h'), name='fecha_local'))
    published = pd.read_csv(PKG / 'Evaluacion/Horario.csv', parse_dates=['fecha_local'])
    lookup = published.set_index(['fold', 'modelo', 'fecha_local', 'variable'], verify_integrity=True)
    dep = pd.read_csv(PKG / 'Evaluacion/Dependencia.csv')
    rows, support_rows = [], []
    ensemble_scores, n_valid = 0, 0
    for fold in plan['folds']:
        fid = fold['id']
        a = np.load(PKG / f'Predicciones/fold{fid}.npz')
        train = data[data.fecha_local < fold['fin_ajuste']]
        test = data[(data.fecha_local >= fold['inicio_validacion']) & (data.fecha_local < fold['fin_validacion'])]
        same('indices_ajuste', train.index, a['train_rows'], 0)
        same('indices_validacion', test.index, a['target_rows'], 0)
        assert test.index.min() - train.index.max() - 1 == 72
        r = train[OBS].to_numpy() - train[BASE].to_numpy()
        same('residuos', r, train[RES].to_numpy())
        same('residuos_guardados', r, a['residual_fit'])
        def features(frame):
            angle = 2 * np.pi * (frame.fecha_local.dt.hour + frame.fecha_local.dt.minute / 60).to_numpy() / 24
            return np.column_stack([frame[BASE], np.sin(angle), np.cos(angle)])
        x, xt = features(train), features(test)
        valid = np.isfinite(np.column_stack([x, r])).all(axis=1)
        mu, scale = x[valid].mean(axis=0), x[valid].std(axis=0)
        scale[scale < 1e-12] = 1
        z = (x[valid] - mu) / scale
        # Solución de mínimos cuadrados aumentados con intercepto explícito no penalizado.
        design = np.column_stack([np.ones(len(z)), z])
        penalty = np.column_stack([np.zeros(5), np.eye(5)]) * np.sqrt(len(z) * .1)
        coef = np.linalg.lstsq(np.vstack([design, penalty]), np.vstack([r[valid], np.zeros((5, 3))]), rcond=None)[0]
        same('escala', scale, a['scale']); same('media_predictores', mu, a['mu'])
        same('coeficientes', coef[1:], a['coef']); same('intercepto', coef[0], a['intercept'])
        meantrain = np.column_stack([np.ones(len(x)), (x-mu)/scale]) @ coef
        meantest = np.column_stack([np.ones(len(xt)), (xt-mu)/scale]) @ coef
        same('media_condicional_ajuste', meantrain, a['mean_train'])
        same('media_condicional_test', meantest, a['mean_target'])
        innovation = r - meantrain
        starts = np.array([i for i in range(0, len(train)-23, 24) if np.isfinite(r[i:i+24]).all()])
        assert len(starts) >= 10
        same('bloques_elegibles', starts, a['starts'], 0)
        index = a['indices']
        assert index.shape == (1024, len(test)) and index.max() < len(train)
        assert np.isin(a['chosen'], starts).all()
        same('indice_bloques', index, (a['chosen'][:, :, None]+np.arange(24)).reshape(index.shape), 0)
        assert (index % 24 == np.arange(len(test))[None, :] % 24).all()
        assert (np.diff(index.reshape(1024, -1, 24), axis=2) == 1).all()
        center = innovation[(starts[:, None] + np.arange(24)).ravel()].mean(axis=0)
        same('centro_pool', center, a['pool_center'])
        same('innovaciones', innovation, a['innovations_fit'])
        base = test[BASE].to_numpy()
        obs = test[OBS].to_numpy()
        cycle = np.array([np.nanmean(r[train.fecha_local.dt.hour.to_numpy() == hour], axis=0)
                          for hour in test.fecha_local.dt.hour])
        predictions = dict(BASE=base, SES_GLOBAL=base+np.nanmean(r, axis=0), CICLO=base+cycle,
            RIDGE=base+meantest, G1_24=base[None]+r[index],
            RIDGE_24=base[None]+meantest[None]+innovation[index]-center)
        ok = np.isfinite(np.column_stack([base, obs])).all(axis=1)
        n_valid += int(ok.sum())
        lo, hi = x[valid, :3].min(axis=0), x[valid, :3].max(axis=0)
        outside = ((xt[:, :3] < lo) | (xt[:, :3] > hi)).any(axis=1) & ok
        support_rows.append(dict(fold=fid,ternas=int(ok.sum()),fuera_rango=int(outside.sum()),bloques24=len(starts)))
        assert int(outside.sum()) == read(PKG / f'Predicciones/fold{fid}.json')['horas_predictor_fuera_rango']
        for name, pred in predictions.items():
            same('trayectorias_'+name, pred, a[name])
            # Métricas sobre valores entregados para separar error de cálculo y redondeo del ajuste.
            p = a[name] if a[name].ndim == 3 else a[name][None]
            mean = p.mean(axis=0)
            bounds = {q: np.quantile(p, [(1-q/100)/2, (1+q/100)/2], axis=0) for q in (50, 80, 90)}
            for t in np.flatnonzero(ok):
                date = test.fecha_local.iloc[t]
                for j, variable in enumerate(LABELS):
                    score = cdf_score(p[:, t, j], obs[t, j])
                    ensemble_scores += int(len(p) == 1024)
                    row = dict(fold=fid, modelo=name, fecha_local=date, variable=variable,
                        franja='06_17' if 6 <= date.hour < 18 else '18_05', observado=obs[t,j],
                        BASE=base[t,j], media=mean[t,j], error=mean[t,j]-obs[t,j], CRPS=score)
                    for q, b in bounds.items():
                        low, high = b[:, t, j]
                        row.update({f'inferior{q}': low, f'superior{q}': high,
                            f'cobertura{q}': int(low <= obs[t,j] <= high), f'anchura{q}': high-low})
                    old = lookup.loc[(fid, name, date, variable)]
                    assert row['franja'] == old.franja
                    for field in published.columns[5:]:
                        same('horario_'+field, row[field], old[field])
                    rows.append(row)
            if len(p) == 1024:
                syn = p - base[None]
                actual = obs-base
                syn[:, ~ok] = np.nan; actual[~ok] = np.nan
                for row in dep[(dep.fold == fid) & (dep.modelo == name)].itertuples():
                    if row.tipo == 'conjunta':
                        j,k = [LABELS.index(v) for v in row.variable.split('/')]
                        obs_corr = correlation(actual[:,j], actual[:,k])
                        ensemble_corr = [correlation(member[:,j], member[:,k]) for member in syn]
                        pairs = ok.sum()
                    else:
                        j,lag = LABELS.index(row.variable), row.lag
                        obs_corr = correlation(actual[:-lag,j], actual[lag:,j])
                        ensemble_corr = [correlation(member[:-lag,j], member[lag:,j]) for member in syn]
                        pairs = (ok[:-lag] & ok[lag:]).sum()
                    same('correlaciones', [obs_corr, *np.nanquantile(ensemble_corr,[.5,.05,.95]), pairs],
                         [row.observada,row.mediana,row.p05,row.p95,row.pares])
    rebuilt = pd.DataFrame(rows)
    assert n_valid == 334 and len(rebuilt) == len(published) == 334*3*6
    assert ensemble_scores == 2004
    for filename, keys in [('Metricas_globales',['modelo','variable']),
                           ('Metricas_por_fold',['fold','modelo','variable']),
                           ('Metricas_por_franja',['modelo','variable','franja'])]:
        metrics = pd.read_csv(PKG / f'Evaluacion/{filename}.csv').set_index(keys,verify_integrity=True)
        for key, block in rebuilt.groupby(keys):
            calc = dict(n=len(block),CRPS=block.CRPS.mean(),sesgo=block.error.mean(),RMSE_media=np.sqrt(np.mean(block.error**2)))
            for q in (50,80,90):
                calc[f'cobertura{q}'] = block[f'cobertura{q}'].mean()
                calc[f'anchura{q}'] = block[f'anchura{q}'].mean()
            for col,val in calc.items():
                same('agregados_'+col, val, metrics.loc[key,col])
    OUT.mkdir()
    pd.DataFrame(support_rows).to_csv(OUT / 'Soporte_verificado.csv', index=False, encoding='utf-8-sig')
    plot_results()
    report()
    # Guardar la recepción después de todas las comprobaciones y los productos.
    receipt = dict(estado='COMPARACION_CRONOLOGICA_RECIBIDA',metodo='Reconstrucción desde prefijos, ridge por mínimos cuadrados aumentados y CRPS integral CDF',
        hashes_verificados=len(checked),ternas=334,filas_metricas=6012,CRPS_ensemble_integrados=ensemble_scores,
        errores_maximos=ERRORS,desarrollo_retrospectivo=True,validacion_externa=False,
        modelo_final_adoptado=False,AERMOD_ejecutado=False,accion_usuario_requerida=False,
        entradas=list(checked.values())+[record(PKG/'Estado.json')],
        archivos=[record(__file__),*[record(p) for p in sorted(OUT.iterdir())]])
    (OUT / 'Verificacion.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:receipt[k] for k in ['estado','ternas','filas_metricas','CRPS_ensemble_integrados','hashes_verificados']},ensure_ascii=False))
    print('Mayor error CRPS:',ERRORS['horario_CRPS'])


def plot_results():
    glob = pd.read_csv(PKG/'Evaluacion/Metricas_globales.csv').set_index(['modelo','variable'])
    folds = pd.read_csv(PKG/'Evaluacion/Metricas_por_fold.csv')
    fig, axes = plt.subplots(2,3,figsize=(12,7.6))
    names = ['BASE','G1_24','RIDGE_24']
    captions = ['WRF','Bloques crudos','Condicional']
    colors = ['#7e8795','#c47b20','#1b806f']
    units = ['°C','m/s','m/s']
    for j,var in enumerate(LABELS):
        ax = axes[0,j]
        values = [glob.loc[(name,var),'CRPS'] for name in names]
        ax.bar(captions,values,color=colors,width=.65)
        for i,value in enumerate(values):
            ax.text(i,value+.025*max(values),f'{value:.3f}',ha='center',fontsize=10)
        ax.set_ylim(0,max(values)*1.19)
        ax.set_title(['Temperatura T','Componente este u','Componente norte v'][j],fontsize=12)
        ax.set_ylabel(f'CRPS ({units[j]}) · menor es mejor')
        ax = axes[1,j]
        for name,caption,color in zip(names[1:],captions[1:],colors[1:]):
            part = folds[(folds.modelo==name)&(folds.variable==var)].sort_values('fold')
            ax.plot(part.fold,100*part.cobertura90,'o-',label=caption,color=color,lw=2)
        ax.axhline(90,color='#555555',ls='--',lw=1,label='Nominal 90 %')
        ax.set_xticks([1,2,3,4],['7–10 ene','11–14 ene','15–18 ene','19–20 ene'],rotation=18)
        ymin = max(0,np.floor(folds[(folds.modelo.isin(names[1:]))&(folds.variable==var)].cobertura90.min()*20)*5-10)
        ax.set_ylim(ymin,101)
        ax.set_ylabel('Cobertura central 90 % observada (%)')
        ax.set_xlabel('Período de validación interna, 2017')
        for axis in axes[:,j]:
            axis.spines[['top','right']].set_visible(False)
            axis.grid(axis='y',alpha=.18);axis.set_axisbelow(True)
    axes[1,1].legend(loc='lower center',fontsize=9)
    fig.suptitle('Mejor puntuación marginal; cobertura todavía desigual',fontsize=16,y=.98)
    fig.text(.5,.93,'Comparación retrospectiva: 334 ternas · cuatro períodos · 72 h de separación · bloques conjuntos de 24 h',ha='center',fontsize=10)
    fig.text(.5,.02,'Entrenamiento sólo anterior a cada período. No es validación externa ni acredita incertidumbre de concentración.',ha='center',fontsize=10)
    fig.subplots_adjust(left=.07,right=.985,bottom=.16,top=.86,hspace=.36,wspace=.33)
    for ext in ['png','pdf']:
        fig.savefig(OUT/f'Comparacion_interna.{ext}',dpi=180,facecolor='white')
    plt.close(fig)


def report():
    text = '''# Comparación cronológica interna recibida

La media condicional de discrepancias mejora el desempeño interno de T, u y v frente a WRF y al remuestreo de residuos crudos. Se conserva como candidato fijo para la siguiente evaluación. **Todavía no se adopta como generador calibrado de incertidumbre ni se ejecutan concentraciones con sus miembros.**

La recepción independiente reconstruyó el ajuste por mínimos cuadrados aumentados, las trayectorias conjuntas por índices, 6.012 registros de métricas, coberturas y correlaciones. Para los conjuntos se recalcularon 2.004 CRPS mediante la integral de la distribución acumulada, sin usar el algoritmo original. Ver `Verificacion.json`.

## Qué se comparó

Cuatro períodos sucesivos entre el 7 y el 20 de enero de 2017: 336 posiciones horarias y 334 ternas válidas. Cada ajuste usa únicamente datos anteriores, con 72 h de separación. Se mantienen los huecos y la misma máscara para todos los modelos. Diseño y predicciones se congelaron antes de calcular las métricas; contaminar las observaciones futuras no cambia las predicciones.

Es desarrollo retrospectivo dentro de los 31 días de ajuste ya inspeccionados. La separación cronológica impide fuga computacional, pero no elimina esa exposición previa. Los períodos no son réplicas independientes: datos evaluados antes pueden entrar en ajustes posteriores. No se volvió a abrir la semana del 24–30 de enero, que tampoco puede recuperarse como reserva nueva.

La corrección depende de T, u, v WRF y un armónico de la hora local, con regresión ridge y penalización 0,1 fijada de antemano. Sus innovaciones se remuestrean conjuntamente en bloques de 24 h; no se suma el sesgo dos veces. Se conserva :49 y la hipótesis horaria H-CIVIL. La dependencia vertical y espacial sigue siendo un supuesto separado.

La referencia `G1_24` reajusta el algoritmo de residuos crudos a cada prefijo. **No es la evaluación externa del generador 1.0 de 48 h:** éste permanece intacto, con su deterioro en v documentado. Aquí se usa la alternativa de 24 h porque ofrece 11, 15, 17 y 21 bloques completos; 48 h no cumple el mínimo previo de diez bloques no solapados en los primeros tres ajustes. La longitud no se eligió según las métricas.

## Resultado principal

CRPS menor es mejor; cada variable mantiene sus unidades. Para WRF determinista, CRPS coincide con el error absoluto medio.

| Variable | WRF | Bloques crudos 24 h | Condicional 24 h | Cambio frente a bloques crudos |
|---|---:|---:|---:|---:|
| T (°C) | 1,6527 | 0,9852 | 0,8665 | −12,0 % |
| u (m/s, este) | 2,4569 | 1,9016 | 0,7563 | −60,2 % |
| v (m/s, norte) | 3,4343 | 3,2843 | 1,0433 | −68,2 % |

La mejora frente a ambas referencias aparece en las tres variables en cada uno de los cuatro períodos. Los controles de sesgo global y ciclo horario no resuelven el problema del viento: sus CRPS globales de v son 5,2634 y 5,2346 m/s. La regresión condicional determinista alcanza 1,4429 m/s; añadir innovaciones produce el conjunto de 1,0433 m/s. Esto favorece seguir examinando el candidato condicional, sin atribuir causalidad a los predictores: la discrepancia observado−WRF ya contiene WRF.

## Lo que aún limita su uso

| Variable | Cobertura del intervalo central nominal 90 % | Anchura media | Sesgo predicho−observado |
|---|---:|---:|---:|
| T | 87,4 % | 4,783 °C | −0,003 °C |
| u | 90,7 % | 5,184 m/s | −0,323 m/s |
| v | 83,5 % | 5,934 m/s | +0,338 m/s |

Los promedios esconden diferencias: en el primer período la cobertura de v cae a 70,2 % y la de u a 75,5 %; en el último, T alcanza 77,1 %. Para v, la franja local 06–17 tiene 77,1 % frente a 89,9 % en 18–05; son franjas de reloj, no clasificación solar. No se ampliaron bandas ni se reajustó la penalización después de ver estos resultados. La cercanía de una cobertura agregada al 90 % no prueba calibración.

La persistencia tampoco queda resuelta. Para T, las correlaciones observadas a 24 h son 0,470; 0,589; 0,636 y 0,770, frente a medianas simuladas de 0,204; 0,194; 0,227 y 0,385. Para u en el primer período ocurre lo contrario: 0,474 observada frente a 0,741 mediana. No hay una única dirección de error temporal. Estos diagnósticos tienen muestras cortas; el último dispone de sólo 24 pares a ese retardo. Los percentiles entre miembros describen el conjunto, no son intervalos de confianza para la correlación observada.

En 45 de 334 horas (13,5 %) algún predictor T/u/v queda fuera de su rango marginal de entrenamiento. Esas horas se conservaron. Estar dentro de cada rango tampoco demuestra soporte multivariado. Los bloques de 24 h no reproducen toda la dependencia entre días; las innovaciones ajustadas pueden subestimar dispersión y no incluyen incertidumbre de parámetros ni una varianza condicional explícita.

## Decisión y conexión con la tesis

Se cierra esta comparación sin modificar el candidato según sus puntuaciones. El siguiente paso es fijar una evaluación temporal adicional con datos no usados en la selección, comprobando primero su historial de uso. Si no puede sostenerse esa condición, debe declararse evaluación adicional exploratoria. La semana ya abierta no vuelve a ser independiente. No es necesario repetir MMIF, AERMET, AERMOD o AERMAP para cerrar esta etapa.

Tras esa comprobación se decide el paso a un lote acotado de propagación con fuentes, emisiones, terreno y receptores fijos. La salida será sensibilidad exploratoria mientras no exista evidencia suficiente de calibración; ocho miembros no sustentan un P95. No se elige la corrección por aumentar la concentración y no se requiere otra ronda de refinamiento geométrico. Los supuestos de huso, altura del sensor y transferencia de una estación al dominio siguen limitando cualquier interpretación probabilística.

**Texto utilizable en la tesis:** “En una comparación cronológica interna de cuatro períodos, con 72 h de separación respecto de cada ajuste y 334 ternas observacionales válidas, una media condicional regularizada con remuestreo conjunto de innovaciones de 24 h redujo el CRPS frente al remuestreo de discrepancias crudas en 12,0 %, 60,2 % y 68,2 % para T, u y v, respectivamente. Sin embargo, las diferencias de cobertura entre períodos y los desajustes de persistencia impidieron considerarlo un generador calibrado. Estos resultados corresponden a desarrollo retrospectivo y no acreditan por sí mismos incertidumbre de concentración.”

La motivación bibliográfica y el diseño anterior a las métricas están en [Metodo.md](../Metodo.md) y [Diseno.json](../Diseno.json). La figura `Comparacion_interna.png`/`.pdf` muestra las puntuaciones y la cobertura por período. Se conservan todos los modelos y resultados, incluidos los desfavorables.
'''
    (OUT/'Lectura_resultados.md').write_text(text,encoding='utf-8')


if __name__ == '__main__':
    main()
