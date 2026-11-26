from pathlib import Path
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


WORK = Path(__file__).resolve().parent
PACKAGE = WORK.parent/'Reproduccion_doce'
OUT = None
POINTS = ('Los Bronces', 'Piedra Carvajal', 'Sulfatos', 'La Paloma')
PERIODS = {'VERANO': 86, 'INVIERNO': 90}
ROW_NAMES = {'base': 'BASE', 'mean': 'Mayor media', 'peak': 'Mayor máximo diario', 'both': 'Mayor media y máximo'}
REFERENCES = (('Guía OMS · 24 h', '> 45 µg/m³', '#176b87'),
              ('Referencia chilena · 24 h', '> 130 µg/m³N', '#a43c48'))


def prepare():
    daily = pd.read_csv(WORK/'datos/Medias_diarias_civiles_doce.csv.gz')
    daily = daily.loc[daily.pollutant.eq('MP10') & daily.complete_24h & daily.receptor.isin(POINTS)]
    selection = pd.read_csv(PACKAGE/'referencia/Seleccion.csv').query("pollutant == 'MP10'")
    codes = ['BASE', 'T_MINUS', 'T_PLUS', 'WS_MINUS', 'WS_PLUS', 'T_MINUS_WS_MINUS', 'T_MINUS_WS_PLUS',
             'T_PLUS_WS_MINUS', 'T_PLUS_WS_PLUS', 'WS_MINUS_INV', 'T_MINUS_WS_MINUS_INV', 'T_PLUS_WS_MINUS_INV']
    keys = ['season', 'receptor', 'civil']
    ambient = daily.set_index(keys)[codes].sort_index()
    assert ambient.index.is_unique and len(ambient) == 4*(86+90)

    f = pd.read_csv(WORK/'datos/Factores_condicionales_horarios.csv.gz').rename(columns={'point':'receptor'})
    f['utc'] = pd.to_datetime(f.time_UTC, utc=True)
    assert np.isfinite(f[['PSFC_Pa','T2_C','factor_condicional']]).all().all()
    assert f.PSFC_Pa.gt(0).all() and f.T2_C.gt(-273.15).all()
    np.testing.assert_allclose(f.factor_condicional, (101325/f.PSFC_Pa)*((f.T2_C+273.15)/298.15), rtol=1e-13)
    assert not f.duplicated(['season','receptor','utc']).any()
    locations = pd.read_csv(WORK/'datos/Ubicacion_puntos.csv').rename(columns={'point':'receptor'})

    raw_hours, normalized_hours = [], []
    for season, n_days in PERIODS.items():
        cal = pd.read_csv(WORK/'datos'/f'Calendario_{season}.csv.gz')
        day, end = ('dia','fin_local') if season == 'VERANO' else ('dia_LST','fin_LST')
        civil = 'dia' if season == 'VERANO' else 'dia_civil'
        cal['fecha_AERMOD'] = pd.to_datetime(cal[day]).dt.strftime('%y%m%d')+pd.to_datetime(cal[end]).dt.hour.replace(0,24).map('{:02}'.format)
        # The WRF audit labels each diagnostic at the UTC end of the interval.
        cal['utc'] = pd.to_datetime(cal.fin_local, utc=True)+pd.Timedelta(hours=3) if season == 'VERANO' else pd.to_datetime(cal.fin_UTC, utc=True)
        cal = cal.loc[cal.comun_doce, ['fecha_AERMOD',civil,'utc']].rename(columns={civil:'civil_cal'})
        assert cal.utc.is_unique
        h = pd.read_csv(PACKAGE/'datos'/f'Horas_comunes_{season}_MP10.csv.gz', dtype={'fecha_AERMOD':str})
        h = h.loc[h.comun_doce & h.receptor.isin(POINTS)].assign(season=season)
        h = h.merge(cal, on='fecha_AERMOD', validate='many_to_one')
        assert h.civil.eq(h.civil_cal).all()
        complete = ambient.loc[season].reset_index()[['receptor','civil']]
        h = h.merge(complete, on=['receptor','civil'], validate='many_to_one')
        assert len(h) == n_days*24*4
        assert h.groupby(['receptor','civil']).utc.nunique().eq(24).all()
        loc = h.merge(locations[['season','receptor','x_utm','y_utm']], on=['season','receptor'], validate='many_to_one')
        np.testing.assert_allclose(loc[['x_m','y_m']], loc[['x_utm','y_utm']], rtol=0, atol=1e-6)
        h = h.merge(f[['season','receptor','utc','factor_condicional']], on=['season','receptor','utc'], how='left', validate='one_to_one')
        assert h.factor_condicional.notna().all(), h.loc[h.factor_condicional.isna(), ['receptor','civil','utc']].to_string(index=False)
        assert np.isfinite(h[codes]).all().all() and h[codes].ge(0).all().all()
        raw_hours.append(h[keys+codes])
        normalized_hours.append(h[keys].join(h[codes].mul(h.factor_condicional, axis=0)))

    unscaled = pd.concat(raw_hours).groupby(keys)[codes].mean().sort_index()
    pd.testing.assert_frame_equal(unscaled, ambient, check_exact=False, rtol=0, atol=2e-12)
    conditional = pd.concat(normalized_hours).groupby(keys)[codes].mean().sort_index()
    pd.testing.assert_index_equal(conditional.index, ambient.index)
    conditional.to_csv(OUT/'Medias_diarias_MP10_normalizacion_exploratoria.csv')
    return ambient, conditional, selection.set_index(['receptor','season'])


def count(ambient, conditional, selection):
    result = {}
    for receptor in POINTS:
        for season, total in PERIODS.items():
            a, n = ambient.loc[season,receptor], conditional.loc[season,receptor]
            assert len(a) == len(n) == total and a.index.equals(n.index)
            mean, peak = selection.loc[(receptor,season), ['mean_scenario','day_scenario']]
            cases = [('BASE','base')] + ([(mean,'both')] if mean == peak else [(mean,'mean'),(peak,'peak')])
            result[receptor,season] = [dict(scenario=sc, criterio=tag, dias=total,
                                            oms=int(a[sc].gt(45).sum()), chile=int(n[sc].gt(130).sum()),
                                            nuevos_chile=int((n.BASE.le(130)&n[sc].gt(130)).sum()),
                                            reducen_chile=int((n.BASE.gt(130)&n[sc].le(130)).sum())) for sc,tag in cases]
    return result


def plot(points, counts, filename):
    groups = [(point,s,counts[point,s]) for point in points for s in PERIODS]
    fig = plt.figure(figsize=(8.8,6.8))
    gs = fig.add_gridspec(1,3,width_ratios=(2.20,3.2,3.35),left=.038,right=.982,top=.83,bottom=.10,wspace=.19)
    label_ax = fig.add_subplot(gs[0,0])
    axes = [fig.add_subplot(gs[0,i]) for i in (1,2)]
    height = sum(len(rows)+2.0 for _,_,rows in groups)
    for ax in (label_ax,*axes):
        ax.set_ylim(height-.65,0)
    label_ax.set_axis_off()
    for ax, (title, threshold, color) in zip(axes,REFERENCES):
        ax.set_xlim(0,151)
        ax.set_xticks([0,25,50,75,100], ['0','25','50','75','100'])
        ax.set_yticks([])
        ax.tick_params(axis='x', length=0, labelsize=10, colors='#475569', pad=5)
        ax.set_xlabel('Porcentaje de días', fontsize=10.5, labelpad=7, x=.33)
        ax.spines[:].set_visible(False)
        for x in (0,25,50,75,100):
            ax.axvline(x, color='#d9e0e6', lw=.7, zorder=0)
        ax.text(0,1.162,title, transform=ax.transAxes,ha='left',va='bottom',fontsize=12,weight='bold',color='#182938')
        ax.text(0,1.105,threshold,transform=ax.transAxes,ha='left',va='bottom',fontsize=13,weight='bold',color=color)
    axes[0].text(0,1.055,'Concentraciones de salida',transform=axes[0].transAxes,ha='left',fontsize=9.5,color='#475569')
    axes[1].text(0,1.055,'Normalización exploratoria',transform=axes[1].transAxes,ha='left',fontsize=9.5,color='#475569')

    pos = .28
    for receptor, season, records in groups:
        n = records[0]['dias']
        label_ax.text(0,pos,f'{receptor} · {season.lower()}',fontsize=10.4,weight='bold',va='center')
        label_ax.text(0,pos+.52,f'{n} días completos',fontsize=9.3,va='center',color='#475569')
        for ax in axes:
            ax.axhline(pos+.78,lw=.55,color='#d9e0e6',zorder=0,xmax=.98)
        for j, record in enumerate(records):
            y = pos+1.30+j
            label_ax.text(.025,y,ROW_NAMES[record['criterio']],fontsize=9.7,va='center')
            for ax, (_,_,color), key in zip(axes,REFERENCES,('oms','chile')):
                days = record[key]
                percent = 100*days/n
                ax.barh(y,100,height=.47,color='#f0f3f5',zorder=1)
                if days:
                    ax.barh(y,percent,height=.47,color=color,zorder=2)
                displayed = '0' if days == 0 else '100' if days == n else f'{percent:.1f}'.replace('.',',')
                ax.text(106,y-.23,f'{days}/{n} días',fontsize=9.8,va='center',weight='bold',color='#182938')
                ax.text(106,y+.25,f'{displayed} %',fontsize=9.0,va='center',color='#475569')
        pos += len(records)+2

    for ext in ('pdf','png'):
        fig.savefig(OUT/f'{filename}.{ext}',dpi=220,bbox_inches='tight',pad_inches=.14)
    plt.close(fig)


def main():
    global OUT
    import argparse
    from integridad import verificar
    parser=argparse.ArgumentParser(description='Recuentos exploratorios de MP10; no evaluación legal de cumplimiento.')
    parser.add_argument('salida', type=Path)
    args=parser.parse_args()
    verificar(WORK); verificar(PACKAGE)
    OUT=args.salida.resolve(); OUT.mkdir(parents=True,exist_ok=False)
    plt.rcParams.update({'font.family':'DejaVu Sans','pdf.fonttype':42,'text.color':'#182938'})
    values = count(*prepare())
    (OUT/'recuentos.json').write_text(json.dumps({f'{p}/{s}':n for (p,s),n in values.items()},ensure_ascii=False,indent=2),encoding='utf-8')
    assert json.loads((OUT/'recuentos.json').read_text(encoding='utf-8')) == json.loads((WORK/'referencia/recuentos.json').read_text(encoding='utf-8'))
    calculated=pd.read_csv(OUT/'Medias_diarias_MP10_normalizacion_exploratoria.csv')
    expected=pd.read_csv(WORK/'referencia/Medias_diarias_MP10_normalizacion_exploratoria.csv.gz')
    pd.testing.assert_frame_equal(calculated,expected,rtol=0,atol=2e-12)
    (OUT/'Verificacion.json').write_text(json.dumps(dict(status='PASSED',dias_verano=86,dias_invierno=90,filas_diarias=len(calculated),alcance='Normalización exploratoria, no acreditación normativa.'),indent=2),encoding='utf-8')
    plot(POINTS[:2], values, 'Frecuencia_MP10_Los_Bronces_Piedra_Carvajal')
    plot(POINTS[2:], values, 'Frecuencia_MP10_Sulfatos_La_Paloma')
    for (point, season), items in values.items():
        print(point,season,[(r['criterio'],r['oms'],r['chile'],r['nuevos_chile'],r['reducen_chile']) for r in items])


if __name__ == '__main__':
    main()
