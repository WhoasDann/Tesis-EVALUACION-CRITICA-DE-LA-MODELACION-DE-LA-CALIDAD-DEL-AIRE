"""Reproduce la galeria desde tablas auditadas. No ejecuta modelos ni colas."""
from pathlib import Path
import sys, json, hashlib, shutil, math
from datetime import datetime, timezone
sys.path.insert(0, '/archivo/usuario/Documents/Codex/2026-10-19/es/work/python_deps')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, PercentFormatter, MaxNLocator
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs/Graficos_BASE_EIA_2026-11-05'
N = ROOT/'outputs/Normativa_reproduccion_2026-11-04'
A = ROOT/'outputs/Sensibilidad_estacional_2026-10-29'
B = ROOT/'outputs/Sensibilidad_conjunta_T_WS_2026-10-30'
P = ROOT/'outputs/Seleccion_adversa_2026-11-04/Contraste_ternas_observadas'
PRE = ROOT/'outputs/Informe_presentacion_2026-11-05'
SOURCE = Path('/archivo/usuario/OneDrive/Escritorio/Docs Tesis/LosBronces/Anexo AD-473.pdf')
for sub in ['Figuras', 'Datos', 'Scripts', 'Revision_visual', 'Fuentes']:
    (OUT/sub).mkdir(parents=True, exist_ok=True)
BLUE, ORANGE, TEAL, PURPLE, GRAY = '#234b68', '#cb632c', '#00877d', '#8853a3', '#526373'
INK, LIGHT = '#183647', '#f1f5f7'
RECS = ['Los Bronces', 'Piedra Carvajal', 'Sulfatos', 'La Paloma']
SEASONS = ['VERANO', 'INVIERNO']
POLS = ['MP10', 'MP25']
SCENARIOS = ['BASE', 'T_MINUS', 'T_PLUS', 'U_MINUS', 'U_PLUS', 'V_MINUS', 'V_PLUS', 'WS_PLUS', 'T_WS_PLUS']
LABEL = dict(zip(SCENARIOS, ['BASE', 'T−', 'T+', 'u−', 'u+', 'v−', 'v+', 'WS+', 'T+WS+']))
POL_LABEL = {'MP10': 'MP10', 'MP25': 'MP2,5'}
SLUG = dict(zip(RECS, ['Los_Bronces', 'Piedra_Carvajal', 'Sulfatos', 'La_Paloma']))
PERIOD = {'VERANO': '21 dic 2016 – 20 mar 2017', 'INVIERNO': '21 jun – 20 sep 2017'}
N_DAYS = {'VERANO': 87, 'INVIERNO': 90}
COORD = {'Los Bronces': (380148, 6331485), 'Piedra Carvajal': (381128, 6323667),
         'Sulfatos': (384254, 6324494), 'La Paloma': (381759, 6327947)}

def num(x, digits=None):
    if x is None or pd.isna(x): return 'no disponible'
    if digits is None: digits = 2 if abs(x) >= 10 else 3
    return f'{x:,.{digits}f}'.replace(',', '_').replace('.', ',').replace('_', '.')

def eia_num(x):
    return num(x, 0 if x == 147 else 1)

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def dump(name, obj):
    (OUT/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

daily = pd.read_csv(N/'Diarios_reproducidos_cuatro_receptores.csv')
strict = daily.loc[daily['count'].eq(24) & daily['size'].eq(24) & daily.complete_civil_day.eq(True)].copy()
assert len(daily) == 13104 and len(strict) == (87+90)*9*2*4
assert not strict.duplicated(['season', 'day', 'scenario', 'pollutant', 'receptor']).any()
for season in SEASONS:
    g = strict[strict.season.eq(season)]
    dates = set(g.day)
    assert len(dates) == N_DAYS[season]
    assert all(set(v.day) == dates for _, v in g.groupby(['scenario', 'pollutant', 'receptor']))
stats = strict.groupby(['season','scenario','pollutant','receptor'])['mean'].agg(
    mean_strict='mean', n_days='size', max_daily='max', sd_days='std').reset_index()
expected = pd.read_csv(N/'Indicadores_descriptivos_submuestra.csv')
cmp = stats.merge(expected, on=['season','scenario','pollutant','receptor'], suffixes=('_new','_old'), validate='one_to_one')
assert len(cmp) == 144
assert np.allclose(cmp.mean_strict_new, cmp.mean_strict_old, rtol=1e-12, atol=1e-12)
assert np.array_equal(cmp.n_days_new, cmp.n_days_old)
stats['delta_vs_BASE_pct'] = np.nan
for keys, g in stats.groupby(['season','pollutant','receptor']):
    base = g.loc[g.scenario.eq('BASE'), 'mean_strict'].iloc[0]
    stats.loc[g.index, 'delta_vs_BASE_pct'] = 100*(g.mean_strict/base-1)
stats.to_csv(OUT/'Datos/Medias_9_configuraciones_dias_comparables.csv', index=False)
strict.to_csv(OUT/'Datos/Diarios_24h_utilizados.csv', index=False)
daily.loc[~daily.index.isin(strict.index), ['season','day','count','size','complete_civil_day']].drop_duplicates().to_csv(
    OUT/'Datos/Fechas_excluidas_de_graficos_24h.csv', index=False)

refs = []
for rec in RECS:
    for pol in POLS:
        v = p98 = ex = ey = table = None
        note = 'No se identifica una concentracion de PM equivalente para este punto en las tablas VI.1-VI.3.'
        if rec == 'Piedra Carvajal':
            v, p98, ex, ey, table = (1.0 if pol == 'MP10' else .2), (2.4 if pol == 'MP10' else .5), 381128, 6323666, 'VI.2'
            note = 'Punto nominal homologo; separacion horizontal 1 m. Cotas/modelo/inventario no acreditados como identicos.'
        elif rec == 'Sulfatos':
            v, p98, ex, ey, table = (.6 if pol == 'MP10' else .1), (2.4 if pol == 'MP10' else .5), 384261, 6324500, 'VI.2'
            note = 'Punto nominal homologo; separacion horizontal 9.22 m. Cotas/modelo/inventario no acreditados como identicos.'
        elif rec == 'Los Bronces' and pol == 'MP10':
            v, ex, ey, table = 147., 380148, 6331485, 'VI.3'
            note = 'Maximo de media anual de MP10 del dominio EIA, en las mismas coordenadas horizontales de nuestro punto Los Bronces.'
        elif rec == 'Los Bronces':
            note = 'La media anual MP2.5 de 27 y P98 de 117 de VI.3 son de otro punto (380285,6331890); no se asignan a Los Bronces.'
        x, y = COORD[rec]
        refs.append(dict(receptor=rec, pollutant=pol, EIA_annual_mean=v, EIA_annual_P98=p98,
                         our_x=x, our_y=y, eia_x=ex, eia_y=ey,
                         offset_m=math.hypot(x-ex,y-ey) if ex else None,
                         table=table, PDF_page=82 if table else None, printed_page=81 if table else None,
                         year=2017 if table else None, model='CALPUFF', unit_as_printed='ug/m3',
                         kind='modeled contribution', use='context only; not equivalent periods', note=note))
refdf = pd.DataFrame(refs)
refdf.to_csv(OUT/'Datos/Referencias_EIA_transcripcion.csv', index=False)
def ref(rec, pol):
    row = refdf[refdf.receptor.eq(rec) & refdf.pollutant.eq(pol)].iloc[0]
    return None if pd.isna(row.EIA_annual_mean) else float(row.EIA_annual_mean)
def series(season, rec, pol, scenario):
    return strict.loc[strict.season.eq(season) & strict.receptor.eq(rec) & strict.pollutant.eq(pol) & strict.scenario.eq(scenario), 'mean'].to_numpy()
def get_stats(season, rec, pol):
    return stats.loc[stats.season.eq(season) & stats.receptor.eq(rec) & stats.pollutant.eq(pol)].set_index('scenario').loc[SCENARIOS]

plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':11, 'axes.titlesize':13, 'axes.labelsize':11,
                     'axes.spines.top':False, 'axes.spines.right':False, 'axes.edgecolor':'#8996a0',
                     'axes.labelcolor':INK, 'text.color':INK, 'xtick.color':GRAY, 'ytick.color':GRAY,
                     'savefig.facecolor':'white', 'svg.fonttype':'none'})
figures = []
def finish(fig, name, title, caption, kind):
    for ext in ['png','svg']:
        fig.savefig(OUT/f'Figuras/{name}.{ext}', dpi=200, facecolor='white')
    plt.close(fig)
    figures.append(dict(name=name,title=title,caption=caption,kind=kind))

for rec in RECS:
    for pol in POLS:
        fig, axes = plt.subplots(1, 2, figsize=(15, 7.4))
        fig.subplots_adjust(left=.066, right=.98, bottom=.23, top=.77, wspace=.22)
        fig.suptitle(f'{rec} | {POL_LABEL[pol]}\nDistribución de los aportes diarios', x=.05, ha='left', y=.975, fontsize=20, fontweight='bold')
        rv = ref(rec,pol)
        et = f'Media anual EIA 2017: {eia_num(rv)} µg/m³ (contexto)' if rv is not None else 'EIA: media anual no disponible para este punto'
        fig.text(.05,.858,et, fontsize=12, color=PURPLE)
        for ax, season in zip(axes,SEASONS):
            g = get_stats(season,rec,pol)
            adverse = g.mean_strict.idxmax()
            base = g.loc['BASE','mean_strict']
            curve_specs = [('BASE',BLUE,'BASE'), (adverse,ORANGE,f'{LABEL[adverse]}: mayor media de las 9'), ('T_WS_PLUS',TEAL,'T+WS+: cambio conjunto')]
            for sc,col,lab in curve_specs:
                vals = np.sort(series(season,rec,pol,sc))
                x = np.r_[0, vals]
                y = np.r_[0, np.arange(1,len(vals)+1)/len(vals)]
                ax.step(x,y,where='post',label=lab,color=col,lw=1.8)
            ax.axvline(base,color=BLUE,lw=1.8,ls=':',label=f'Media BASE: {num(base)}')
            if rv is not None: ax.axvline(rv,color=PURPLE,lw=1.6,ls='--',label=f'Media anual EIA: {eia_num(rv)}')
            ax.set_title(f'{season.title()} · {N_DAYS[season]} días de 24 h\nMedia BASE = {num(base)} µg/m³', loc='left', pad=12, fontweight='bold')
            ax.set_xlim(left=0); ax.set_ylim(0,1.025)
            ax.yaxis.set_major_formatter(PercentFormatter(1))
            ax.xaxis.set_major_locator(MaxNLocator(6))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x,pos: f'{x:g}'.replace('.',',')))
            ax.grid(alpha=.18); ax.set_axisbelow(True)
            ax.set_xlabel(f'Aporte diario {POL_LABEL[pol]} (µg/m³)')
            ax.legend(loc='upper center',bbox_to_anchor=(.5,-.18),frameon=False,fontsize=9.2,ncol=2)
        axes[0].set_ylabel('Fracción de días con aporte igual o menor')
        fig.text(.05,.025,'Mismas fechas y horas por escenario. Línea EIA: media de otro período; no es un límite normativo.',fontsize=10,color=GRAY)
        caption = ('Leer a una misma altura: una curva más a la derecha indica concentraciones mayores para esa fracción de días. '
                   'La curva naranja se selecciona por la media de los días mostrados, entre nueve configuraciones; '
                   'no es una envolvente de máximos horarios. Los saltos en cero corresponden a días de aporte nulo. '
                   'La referencia EIA es un aporte modelado anual de 2017, no una medición ni una validación de nuestra BASE.')
        finish(fig,f'ECDF_{SLUG[rec]}_{pol}',f'{rec}: distribución diaria de {POL_LABEL[pol]}',caption,'ecdf')

design = json.loads((A/'Diseno.json').read_text(encoding='utf-8'))
joint = json.loads((B/'Diseno.json').read_text(encoding='utf-8'))
for rec in RECS:
    fig, axes = plt.subplots(2,2,figsize=(15,8))
    fig.subplots_adjust(left=.075,right=.97,bottom=.13,top=.83,hspace=.52,wspace=.3)
    fig.suptitle(f'{rec} | Respuesta a las variaciones meteorológicas',x=.04,ha='left',y=.97,fontsize=20,fontweight='bold')
    fig.text(.04,.916,'Cada punto es la media del escenario en los mismos días completos; se anotan concentración y cambio frente a BASE.',fontsize=11)
    for row,pol in enumerate(POLS):
        for col,season in enumerate(SEASONS):
            ax=axes[row,col]; g=get_stats(season,rec,pol); best=g.mean_strict.idxmax(); rv=ref(rec,pol)
            y=np.arange(9)
            vals=g.mean_strict.to_numpy(); xmax=max(vals.max(),rv or 0)*1.47
            ax.hlines(y,0,vals,color='#dbe3e8',lw=2)
            for j,sc in enumerate(SCENARIOS):
                color=BLUE if sc=='BASE' else ORANGE if sc==best else TEAL if sc=='T_WS_PLUS' else '#7e909e'
                ax.scatter(vals[j],j,color=color,s=44 if sc in ['BASE',best] else 27,zorder=4)
                txt=num(vals[j]) + ('' if sc=='BASE' else f' ({num(g.loc[sc,"delta_vs_BASE_pct"],1)}%)')
                ax.text(vals[j]+xmax*.016,j,txt,va='center',fontsize=10.5,color=color,zorder=6,
                        bbox=dict(facecolor='white',edgecolor='none',alpha=.85,pad=.3))
            ax.axvline(g.loc['BASE','mean_strict'],color=BLUE,ls=':',lw=1.3)
            if rv is not None: ax.axvline(rv,color=PURPLE,ls='--',lw=1.3)
            reftxt=f'EIA anual: {eia_num(rv)}' if rv is not None else 'EIA anual: no disponible'
            ax.set_title(f'{season.title()} · {POL_LABEL[pol]} · {N_DAYS[season]} días\n{reftxt}',loc='left',fontsize=12)
            ax.set_yticks(y,[LABEL[s] for s in SCENARIOS]);ax.invert_yaxis();ax.set_xlim(0,xmax)
            ax.grid(axis='x',alpha=.15); ax.set_axisbelow(True)
            ax.set_xlabel('Media del aporte (µg/m³)')
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{x:g}'.replace('.',',')))
    handles=[Line2D([0],[0],marker='o',color=BLUE,linestyle=':',label='BASE'),
             Line2D([0],[0],marker='o',color=ORANGE,linestyle='',label='Mayor media entre las 9'),
             Line2D([0],[0],color=PURPLE,ls='--',label='Media anual EIA: contexto')]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.018),ncol=3,frameon=False,fontsize=11)
    caption=('Las variaciones T±, u± y v± usan una desviación estándar (SD) de la discrepancia diaria Obs−WRF. '
             'WS+ aumenta la rapidez con dirección fija y T+WS+ suma ambos cambios; las calmas exactas permanecen calmas. '
             'Los porcentajes comparan cada escenario con nuestra BASE en las mismas fechas. '
             'No se calcula un porcentaje de error frente al EIA, porque los períodos, modelos y condiciones no están equiparados.')
    finish(fig,f'Medias_escenarios_{SLUG[rec]}',f'{rec}: media de cada configuración',caption,'means')

# Episodios pareados de verano: los valores se verifican con las tablas científicas.
ep = pd.read_csv(PRE/'Tablas/09_ejemplos_pareados_cuatro_receptores.csv')
obs = pd.read_csv(P/'Comparacion_cuatro_receptores.csv')
protos = json.loads((P/'Diseno.json').read_text(encoding='utf-8'))['prototypes']
proto = {x['scenario']:x for x in protos if x['season']=='VERANO'}
for _,r in ep.iterrows():
    hit=obs.loc[obs.receptor.eq(r.receptor)&obs.day.eq(r.day)&obs.scenario.eq(r.scenario)&obs.pollutant.eq(r.pollutant)]
    assert len(hit)==1
    assert np.isclose(hit.iloc[0]['mean'],r.candidate,rtol=1e-12)
    assert np.isclose(hit.iloc[0]['BASE'],r.BASE,rtol=1e-12)
ep.to_csv(OUT/'Datos/Episodios_pareados_de_verano.csv',index=False)
for pol in POLS:
    fig,axes=plt.subplots(2,2,figsize=(15,9))
    fig.subplots_adjust(left=.07,right=.97,bottom=.15,top=.83,hspace=.75,wspace=.28)
    fig.suptitle(f'Ternas empíricas | Cambio del mismo día en los 4 receptores\n{POL_LABEL[pol]} · Ejemplos de verano',x=.04,ha='left',y=.975,fontsize=19,fontweight='bold')
    for ax,rec in zip(axes.flat,RECS):
        r=ep[ep.receptor.eq(rec)&ep.pollutant.eq(pol)].iloc[0]
        dt,du,dv=proto[r.scenario]['delta']
        ax.bar([0,1],[r.BASE,r.candidate],color=[BLUE,ORANGE],width=.52)
        for x,v in enumerate([r.BASE,r.candidate]):ax.text(x,v+max(r.BASE,r.candidate)*.035,num(v),ha='center',fontweight='bold',fontsize=12)
        ax.set_ylim(0,max(r.BASE,r.candidate)*1.25); ax.set_xticks([0,1],['BASE',r.scenario]);ax.grid(axis='y',alpha=.16);ax.set_axisbelow(True)
        ax.set_title(f'{rec} · {r.day}\nCambio: +{num(r.delta_pct,1)}%  |  ΔC = +{num(r.delta)} µg/m³',loc='left',fontsize=12,fontweight='bold')
        ax.set_ylabel('Aporte diario (µg/m³)')
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{x:g}'.replace('.',',')))
        ax.text(.5,-.23,f'ΔT = {num(dt,2)} °C; Δu = {num(du,2)}; Δv = {num(dv,2)} m/s',transform=ax.transAxes,ha='center',fontsize=10)
    fig.text(.04,.025,'Ternas = tres discrepancias diarias (Obs−WRF) del mismo día fuente, aplicadas juntas. No son nuevas medias estacionales.',fontsize=11,color=GRAY)
    caption=('Cada par compara el mismo receptor, contaminante y día, conservando emisiones. OBS_U y OBS_V son ternas empíricas '
             'de discrepancias T/u/v, no una atmósfera observada ni una validación física. Los ejemplos son retrospectivos: '
             'no tienen por qué ser el máximo de cada candidato. En total se estudiaron cinco días civiles de verano y seis de invierno; '
             'no hay distribuciones estacionales completas de estas ternas.')
    finish(fig,f'Episodios_ternas_{pol}',f'Ternas: cambios diarios de {POL_LABEL[pol]}',caption,'episodes')

# Preserva cifras de la media del período completo para explicar la diferencia de muestra.
period = pd.read_csv(N/'Medias_periodo_reproducidas.csv')
base_cmp = stats[stats.scenario.eq('BASE')].merge(period[period.scenario.eq('BASE')],
    on=['season','scenario','pollutant','receptor'],validate='one_to_one').merge(refdf,on=['receptor','pollutant'],validate='many_to_one')
base_cmp.to_csv(OUT/'Datos/BASE_muestra24h_y_periodo_completo_con_EIA.csv',index=False)
pd.DataFrame([dict(season=s,**design['scales'][s], WS=joint['scales'][s]['WS_m_s']) for s in SEASONS]).to_csv(
    OUT/'Datos/Amplitudes_SD.csv',index=False)

fontdir=Path('C:/Windows/Fonts')
pdfmetrics.registerFont(TTFont('Arial',str(fontdir/'arial.ttf')))
pdfmetrics.registerFont(TTFont('Arial-Bold',str(fontdir/'arialbd.ttf')))
pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='Arial-Bold',italic='Arial',boldItalic='Arial-Bold')
W,H=960,660
pdfpath=OUT/'Informe_grafico_BASE_EIA_y_escenarios.pdf'
c=canvas.Canvas(str(pdfpath),pagesize=(W,H))
c.setTitle('Los Bronces Integrado: aportes BASE, referencia EIA y sensibilidad meteorologica')
c.setAuthor('Daniel Castro - análisis reproducible de resultados existentes')
page=0
def para(text,x,y,width,size=12,color=INK):
    sty=ParagraphStyle('p',fontName='Arial',fontSize=size,leading=size*1.35,textColor=HexColor(color),spaceAfter=0)
    p=Paragraph(text,sty);pw,ph=p.wrap(width,1000);p.drawOn(c,x,y-ph);return y-ph
def page_start(title,sub=''):
    global page
    page+=1
    c.setFillColor(HexColor(INK));c.rect(0,H-9,W,9,fill=1,stroke=0)
    c.setFont('Arial-Bold',20);c.drawString(38,H-44,title)
    if sub:para(sub,38,H-56,W-76,10,GRAY)
def page_end():
    c.setStrokeColor(HexColor('#d4dee5'));c.line(38,32,W-38,32)
    c.setFont('Arial',8);c.setFillColor(HexColor(GRAY));c.drawString(38,18,'5 noviembre 2026 | Aportes modelados | Panel de 40 receptores; aquí se muestran los 4 sensibles')
    c.drawRightString(W-38,18,f'{page}');c.showPage()

page_start('Cómo leer estos gráficos','Nuestra BASE AERMOD y la referencia CALPUFF del Anexo AD-473')
y=H-104
blocks=[
 ('01  Promedios visibles', 'Azul: nuestra media BASE de los días completos que aparecen en el gráfico. Morado: media anual del EIA de 2017, cuando se identifica para el punto. Son <b>aportes modelados</b>; la línea del EIA es una referencia contextual y no un límite normativo.'),
 ('02  Variabilidad y sensibilidad', 'Las curvas muestran la fracción de días con aporte menor o igual a cada valor. Los gráficos de puntos comparan las <b>nueve configuraciones</b> con las mismas fechas. La media se calcula para cada escenario; “mayor media” identifica cuál de esas nueve es la más alta.'),
 ('03  Una muestra comparable', '<b>87 días de verano y 90 de invierno, todos de 24 horas válidas.</b> Se excluyen tres fechas de verano y dos de invierno, incluida la jornada de 17 horas del 20 de marzo. Esto evita comparar promedios con distinta cobertura. Las medias difieren levemente de las del período completo del informe previo; ambas se conservan en el CSV.'),
 ('04  Referencias con ubicación comprobada', 'Piedra Carvajal: MP10 <b>1,0</b> y MP2,5 <b>0,2</b> µg/m³. Sulfatos: <b>0,6</b> y <b>0,1</b>. Sus posiciones difieren de las nuestras en 1 m y 9,22 m, respectivamente. Los Bronces: MP10 <b>147</b>, máximo de media anual del EIA en las mismas coordenadas horizontales de nuestro punto. El valor MP2,5 de 27 pertenece a otro punto y no se asigna a Los Bronces. La Paloma queda sin referencia PM.'),
 ('05  Qué significa un candidato adverso', 'La selección naranja es numérica y depende del receptor, temporada e indicador. Las ternas añaden soporte empírico a combinaciones T/u/v en episodios. <b>La transferencia estación-columna, coherencia dinámica y aplicabilidad siguen pendientes</b>; no se presenta un peor caso legal ni incertidumbre calibrada.'),
 ('06  Cuánto se modifica la meteorología', '<b>SD de verano:</b> T = 0,95 °C; u = 1,78; v = 4,53; rapidez WS = 2,54 m/s. <b>SD de invierno:</b> T = 1,59 °C; u = 3,54; v = 6,72; WS = 2,98 m/s. Se suma o resta la amplitud indicada en perfiles ONSITE después de MMIF, atenuada verticalmente hasta la altura de mezcla BASE, y se recalculan AERMET y AERMOD. No se reintegra WRF. u/v son componentes este/norte del viento; sus cambios pueden modificar también la dirección.')]
for title,text in blocks:
    c.setFillColor(HexColor(BLUE));c.setFont('Arial-Bold',13);c.drawString(38,y,title)
    y=para(text,38,y-12,W-76,11.6)-19
para('Fuentes: AD-473, tablas VI.1-VI.3, páginas PDF 81-82 (impresas 80-81); tablas científicas reproducidas de la campaña. No se ejecutaron modelos nuevos.',38,57,W-76,9,GRAY)
page_end()

for f in figures:
    page_start(f['title'])
    # Se reserva una caja fija, manteniendo la relación de aspecto.
    from PIL import Image
    path=OUT/f'Figuras/{f["name"]}.png'; iw,ih=Image.open(path).size
    mw,mh=W-60,470
    scale=min(mw/iw,mh/ih);dw,dh=iw*scale,ih*scale
    c.drawImage(str(path),(W-dw)/2,116+(mh-dh)/2,width=dw,height=dh)
    para(f['caption'],38,102,W-76,10.2)
    page_end()

page_start('Normativa: qué aportan estos gráficos y qué falta','Referencia actual de calidad del aire; no evaluación retroactiva del expediente ni dictamen de cumplimiento')
c.setFillColor(HexColor(LIGHT));c.roundRect(38,414,428,143,9,fill=1,stroke=0);c.roundRect(486,414,436,143,9,fill=1,stroke=0)
para('<b>MP10 · D.S. 12/2021</b><br/><br/>Diario: <b>130 µg/m³N</b>. Superación por P98 anual ≥ 130 o más de siete días con mediciones sobre ese valor en un año calendario.<br/>Anual: <b>50 µg/m³N</b>, según promedio de tres años calendario consecutivos ≥ 50.',54,542,395,12)
para('<b>MP2,5 · D.S. 12/2011</b><br/><br/>Diario: <b>50 µg/m³</b>. Superación cuando el P98 de las concentraciones diarias de un año es > 50.<br/>Anual: <b>20 µg/m³</b>, según promedio trianual de concentraciones anuales > 20.',502,542,402,12)
y=393
for title,text in [
 ('Separar indicadores', 'Media estacional, máximo diario y P98 anual son indicadores diferentes. Una media del EIA tampoco es un umbral. Por eso se retiró la línea “50” de las distribuciones y se conservaron las normas en esta página.'),
 ('Preparar una comparación normativa', 'Se requiere la serie y cobertura del indicador regulado, la base volumétrica correspondiente y la concentración ambiental pertinente, incluido el fondo cuando corresponda. Estos gráficos muestran aportes del inventario modelado, no acreditan por sí solos la concentración ambiental total.'),
 ('Resolver MP10 y el alcance espacial', 'La equivalencia de nuestra salida con µg/m³N a 25 °C y 1 atm no está acreditada. El panel tiene 40 puntos y no identifica el máximo de toda la malla. Las temporadas disponibles no constituyen un año completo ni tres años de evaluación.'),
 ('Sostener la selección adversa', 'Usar un escenario íntegro y físicamente defendible para el receptor y el indicador de interés. No formar una serie tomando el máximo horario de distintas configuraciones. El mayor promedio y el mayor día pueden corresponder a escenarios distintos.')]:
    c.setFont('Arial-Bold',12);c.setFillColor(HexColor(BLUE));c.drawString(38,y,title)
    y=para(text,38,y-10,W-76,11)-18
para('Fuentes oficiales consultadas: BCN, D.S. 12/2021 (idNorma 1176988) y D.S. 12/2011 (idNorma 1025202); fichas vigentes del MMA. Ver enlaces completos y auditoría de unidades en Fuentes/Fuentes_normativas.json y el informe normativo previo. La norma MP10 actual entró en vigor después del período del expediente.',38,93,W-76,9,GRAY)
c.linkURL('https://www.bcn.cl/leychile/navegar?idNorma=1176988',(38,52,455,91),relative=0)
c.linkURL('https://www.bcn.cl/leychile/navegar?idNorma=1025202',(465,52,922,91),relative=0)
page_end();c.save()
assert len(PdfReader(pdfpath).pages)==16

inputs=[N/'Diarios_reproducidos_cuatro_receptores.csv',N/'Indicadores_descriptivos_submuestra.csv',N/'Medias_periodo_reproducidas.csv',
        PRE/'Tablas/09_ejemplos_pareados_cuatro_receptores.csv',P/'Comparacion_cuatro_receptores.csv',P/'Diseno.json',A/'Diseno.json',B/'Diseno.json',SOURCE]
dump('Fuentes/Procedencia.json',{'created_utc':datetime.now(timezone.utc).isoformat(),'source_pdf':str(SOURCE),
     'source_title':'Actualizacion Anexo C4-2: Modelacion calidad del aire. Proyecto Los Bronces Integrado. GEOAIRE, 20 marzo 2020, Rev B.',
     'tables':'VI.1 positions; VI.2 receptor modeled annual 2017 contributions; VI.3 full-domain maxima',
     'pages_pdf':[81,82],'pages_printed':[80,81],'source_pages_visually_reviewed':True,
     'sources':[{'path':str(p),'sha256':sha(p)} for p in inputs]})
shutil.copy2(N/'Fuentes_normativas.json',OUT/'Fuentes/Fuentes_normativas.json')
shutil.copy2(N/'Auditoria_unidades.json',OUT/'Fuentes/Auditoria_unidades_previa.json')
shutil.copy2(__file__,OUT/'Scripts/construir.py')
dump('Indice_figuras.json',figures)
dump('Verificacion_numerica.json',{'status':'PASSED','native_model_runs':0,'daily_source_rows':len(daily),
    'strict_rows':len(strict),'strict_days':N_DAYS,'metrics_checked':len(cmp),'max_mean_difference':float(abs(cmp.mean_strict_new-cmp.mean_strict_old).max()),
    'paired_episode_values_checked':len(ep),'same_dates_all_9_scenarios':True,'ECDF_monotone_by_sorted_daily_values':True,
    'EIA_available_receptor_pollutant_pairs':int(refdf.EIA_annual_mean.notna().sum()),'EIA_missing_not_zero_filled':True,
    'EIA_different_point_MP25_27_not_used':True,'comparisons_with_norm_thresholds_in_plots':False,
    'PDF_pages':16,'PNG_count':14,'SVG_count':14,'visual_QA':'PENDING'})
dump('Artifact_operation.json',{'kind':'create','expected_output_count':1,'output_format':'pdf',
    'marker_invoked_once_before_authoring':True,'marker_managed_by_assistant':True})
print(json.dumps({'pdf':str(pdfpath),'pages':16,'figures':len(figures),'status':'NUMERICAL_QA_PASSED_VISUAL_PENDING'},ensure_ascii=False))
