"""Documentary comparison and revised scientific figures. Does not run models."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,hashlib,math
sys.path.insert(0,'/archivo/usuario/Documents/Codex/2026-10-19/es/work/python_deps')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph,Table,TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor,white
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[2]
O=ROOT/'outputs/Contraste_ADC160_normativa_2026-11-05'
G=ROOT/'outputs/Graficos_BASE_EIA_2026-11-05'
for name in ['Figuras','Datos','Revision_visual','Scripts']:(O/name).mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(n,v):(O/n).write_text(json.dumps(v,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
def num(x,n=2):return f'{x:.{n}f}'.replace('.',',')
audit=read(O/'Auditoria_comparabilidad.json')
old=pd.read_csv(G/'Datos/Referencias_EIA_transcripcion.csv')
ref=old.copy();ref['document']='ADC-160vi';ref['document_date']='2021-04-01'
ref.loc[ref.receptor.eq('Piedra Carvajal')&ref.pollutant.eq('MP10'),['EIA_annual_mean','EIA_annual_P98']]=[1.1,2.5]
ref.loc[ref.receptor.eq('Sulfatos')&ref.pollutant.eq('MP10'),'EIA_annual_P98']=2.5
ref.loc[ref.receptor.eq('Sulfatos')&ref.pollutant.eq('MP25'),'EIA_annual_mean']=.2
ref.loc[ref.receptor.isin(['Piedra Carvajal','Sulfatos']),['table','PDF_page','printed_page']]=['VI.2',88,87]
ref.loc[ref.receptor.eq('Los Bronces')&ref.pollutant.eq('MP10'),['table','PDF_page','printed_page']]=['VI.4',89,88]
ref.loc[ref.receptor.eq('Los Bronces')&ref.pollutant.eq('MP25'),'note']='Media anual 27 y P98 118 en (380285,6331890), otro punto; no se asignan a este receptor.'
ref.loc[ref.receptor.eq('La Paloma'),'note']='VI.3 presenta MPS en Paloma Norte/Oeste, no concentraciones PM equivalentes a nuestro punto.'
ref['use']='Referencia documental anual; no comparacion causal ni replica equivalente.'
ref.to_csv(O/'Datos/Referencias_ADC160.csv',index=False)
comparison=old.merge(ref,on=['receptor','pollutant'],suffixes=('_AD473','_ADC160'),validate='one_to_one')
comparison[['receptor','pollutant','EIA_annual_mean_AD473','EIA_annual_mean_ADC160','EIA_annual_P98_AD473','EIA_annual_P98_ADC160']].to_csv(O/'Datos/Cambios_AD473_ADC160.csv',index=False)

d=pd.read_csv(G/'Datos/Diarios_24h_utilizados.csv')
assert len(d)==177*9*2*4
stats=d.groupby(['season','scenario','pollutant','receptor'])['mean'].agg(mean_strict='mean',n_days='size').reset_index()
previous=pd.read_csv(G/'Datos/Medias_9_configuraciones_dias_comparables.csv')
m=stats.merge(previous,on=['season','scenario','pollutant','receptor'],suffixes=('_new','_old'),validate='one_to_one')
assert len(m)==144 and np.allclose(m.mean_strict_new,m.mean_strict_old,atol=1e-12,rtol=1e-12)
for season,n in [('VERANO',87),('INVIERNO',90)]:
    q=d[d.season.eq(season)];sets=q.groupby(['scenario','pollutant','receptor']).day.apply(set)
    assert all(len(x)==n and x==sets.iloc[0] for x in sets)
stats.to_csv(O/'Datos/Medias_propias_dias_comparables.csv',index=False)
refs={(r.receptor,r.pollutant):r.EIA_annual_mean for r in ref.itertuples()}
RECS=['Los Bronces','Piedra Carvajal','Sulfatos','La Paloma']
SLUG=['Los_Bronces','Piedra_Carvajal','Sulfatos','La_Paloma']
LABEL={'BASE':'BASE','T_MINUS':'T−','T_PLUS':'T+','U_MINUS':'u−','U_PLUS':'u+','V_MINUS':'v−','V_PLUS':'v+','WS_PLUS':'WS+','T_WS_PLUS':'T+WS+'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
figs=[]
for rec,slug in zip(RECS,SLUG):
    for pol,pol_label in [('MP10','MP10'),('MP25','MP2,5')]:
        fig,axes=plt.subplots(1,2,figsize=(15,8));fig.subplots_adjust(left=.07,right=.98,top=.74,bottom=.25,wspace=.22)
        annual=refs[rec,pol]
        fig.suptitle(f'{rec} | {pol_label}\nDistribución de los aportes diarios',x=.055,y=.97,ha='left',fontsize=20,fontweight='bold')
        subtitle=f'Media anual ADC-160vi (2017): {num(annual)} µg/m³, referencia documental' if pd.notna(annual) else 'ADC-160vi: sin media anual PM identificada para este punto exacto'
        fig.text(.055,.84,subtitle,color='#805099',fontsize=12)
        for ax,season in zip(axes,['VERANO','INVIERNO']):
            group=stats[(stats.receptor==rec)&(stats.pollutant==pol)&(stats.season==season)].set_index('scenario')
            best=group.mean_strict.idxmax();base=float(group.loc['BASE','mean_strict']);bmean=float(group.loc[best,'mean_strict'])
            specs=[('BASE','#234b68','BASE')]
            if best!='BASE':specs.append((best,'#cb632c',f'{LABEL[best]}: mayor media entre 9'))
            if 'T_WS_PLUS' not in [x[0] for x in specs]:specs.append(('T_WS_PLUS','#00877d','T+WS+'))
            for sc,col,lab in specs:
                vals=np.sort(d.loc[(d.receptor==rec)&(d.pollutant==pol)&(d.season==season)&(d.scenario==sc),'mean'].to_numpy())
                ax.step(np.r_[0,vals],np.r_[0,np.arange(1,len(vals)+1)/len(vals)],where='post',c=col,lw=1.8,label=lab)
            ax.axvline(base,c='#234b68',ls=':',lw=1.7,label=f'Media BASE: {num(base)}')
            if pd.notna(annual):ax.axvline(annual,c='#805099',ls='--',lw=1.6,label=f'Media anual ADC: {num(annual)}')
            ax.set_title(f'{season.title()} | {int(group.loc["BASE","n_days"])} días completos',loc='left',fontweight='bold')
            ax.set_ylim(0,1.03);ax.set_xlim(left=0);ax.set_xlabel(f'Aporte diario {pol_label} (µg/m³)');ax.set_ylabel('Fracción acumulada de días disponibles');ax.grid(alpha=.18)
            ax.legend(loc='lower right',fontsize=9,framealpha=.93)
            ax.text(0,-.19,f'Media {LABEL[best]}: {num(bmean)} µg/m³\nCambio frente a media BASE: {num(100*(bmean/base-1),1)}%',transform=ax.transAxes,fontsize=11)
        fig.text(.055,.085,'Referencia anual CALPUFF/MESOPUFF frente a ventanas propias AERMOD: períodos, fuentes y procesos distintos.',fontsize=11)
        fig.text(.055,.057,'La línea ADC no es un límite legal ni una observación. Las diferencias entre ambos estudios no se atribuyen solo a meteorología.',fontsize=10)
        fig.text(.055,.027,'Comparación interna: mismas fechas y emisiones por día. Mayor media seleccionada después de evaluar nueve configuraciones.',fontsize=10)
        name=f'CDF_{slug}_{pol}_ADC160'
        for ext in ['png','svg']:fig.savefig(O/f'Figuras/{name}.{ext}',dpi=180)
        plt.close(fig);figs.append({'name':name,'receptor':rec,'pollutant':pol})

coord=[]
equiv={'Los Bronces':(380148,6331485,3712,'VI.4, máximo anual MP10'),
       'Piedra Carvajal':(381128,6323666,3817.6,'VI.1'),
       'Sulfatos':(384261,6324500,4374.6,'VI.1')}
for r in audit['receptors']:
    e=equiv.get(r['receptor'])
    coord.append({**r,'ADC_x':e[0] if e else None,'ADC_y':e[1] if e else None,'ADC_elevation_m':e[2] if e else None,
       'horizontal_difference_m':math.hypot(r['x']-e[0],r['y']-e[1]) if e else None,
       'elevation_difference_ours_minus_ADC_m':r['elevation_m']-e[2] if e else None,'source_table':e[3] if e else 'No punto PM equivalente'})
pd.DataFrame(coord).to_csv(O/'Datos/Cotejo_coordenadas_cotas.csv',index=False)

# Report in landscape format, with explicit page breaks and checked text boxes.
pdfmetrics.registerFont(TTFont('ArialLocal','C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialLocalBold','C:/Windows/Fonts/arialbd.ttf'))
pdfmetrics.registerFontFamily('ArialLocal',normal='ArialLocal',bold='ArialLocalBold')
styles={'p':ParagraphStyle('p',fontName='ArialLocal',fontSize=11,leading=15,textColor=HexColor('#233f4f')),
        'small':ParagraphStyle('small',fontName='ArialLocal',fontSize=9,leading=12,textColor=HexColor('#53636e')),
        'table':ParagraphStyle('table',fontName='ArialLocal',fontSize=10,leading=13,textColor=HexColor('#233f4f'))}
pdf=O/'Informe_actualizado_ADC160_y_normativa.pdf'
c=canvas.Canvas(str(pdf),pagesize=(842,595));c.setTitle('Los Bronces: contraste ADC-160vi y normativa');c.setAuthor('Daniel - análisis de tesis')
page=0;y=0;notes=[]
def start(title,sub=''):
    global page,y
    if page:c.showPage()
    page+=1;c.setFillColor(HexColor('#183647'));c.rect(0,575,842,20,fill=1,stroke=0)
    c.setFont('ArialLocalBold',21);c.drawString(42,539,title)
    if sub:c.setFont('ArialLocal',10);c.setFillColor(HexColor('#526373'));c.drawString(42,517,sub)
    c.setFont('ArialLocal',8);c.setFillColor(HexColor('#526373'));c.drawString(42,22,'Tesis Los Bronces | Revisión de fuentes e inventario, 6 de noviembre de 2026')
    c.drawRightString(800,22,str(page));y=489
def p(text,kind='p',gap=10):
    global y
    para=Paragraph(text,styles[kind]);_,h=para.wrap(758,1000)
    assert y-h>44,(page,y,h,text[:80])
    para.drawOn(c,42,y-h);y-=h+gap;notes.append(text)
def table(rows,widths):
    global y
    data=[[Paragraph(str(cell),styles['table']) for cell in row] for row in rows]
    t=Table(data,colWidths=widths,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#e4edf2')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[white,HexColor('#f5f8fa')]),('LEFTPADDING',(0,0),(-1,-1),8),
        ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
        ('LINEBELOW',(0,0),(-1,0),.6,HexColor('#a3b4be'))]))
    _,h=t.wrap(758,1000);assert y-h>44,(page,h,y);t.drawOn(c,42,y-h);y-=h+15

start('Qué cambia con los documentos recibidos','ADC-160vi, informe de 01-04-2021; decretos MP10 y MP2,5 descargados de BCN el 05-11-2026')
p('<b>El análisis numérico se conserva; cambia la precisión de sus conclusiones.</b> Se actualizaron las referencias del titular y se cotejaron inventario, receptores, método y criterios normativos. No se ejecutaron nuevas simulaciones.')
table([['Hallazgo comprobado','Consecuencia para la tesis'],
 ['El ADC-160vi ya tiene un análisis de incertidumbre meteorológica (§5.3, PDF p.78).','El GAP no debe ser que la incertidumbre se ignora: evaluar su propagación explícita y el supuesto de conservadurismo.'],
 ['CALPUFF/MESOPUFF suma particulado secundario al primario (§6, p.86).','Nuestra sensibilidad AERMOD de fuentes de caminos no equivale al aporte total del expediente.'],
 ['Cambian referencias respecto del AD-473 (VI.2, p.88).','Usar la versión ADC-160vi en los gráficos nuevos; conservar el AD-473 como referencia histórica.'],
 ['La norma primaria protege salud; el anexo trata glaciares con MPS (§7, p.139).','Conservar los cuatro receptores, pero distinguir concentración respirable, deposición y finalidad de protección.']], [340,418])
p('<b>GAP propuesto:</b> El diagnóstico meteorológico no demuestra por sí solo cuánto cambian las concentraciones ni que BASE sea conservadora en todos los receptores. Esta tesis cuantifica esa sensibilidad y examina candidatos adversos condicionados.','p')
p('El soporte empírico de las ternas no acredita todavía su transferencia física entre estación, columna y dominio. No se declara incertidumbre probabilística calibrada ni peor caso legal.','small')

start('Comparabilidad: qué representa nuestra BASE','Auditoría de entradas actuales frente a ADC-160vi; diferencias documentadas, sin ajustar concentraciones')
table([['Aspecto','ADC-160vi','Estudio actual'],
 ['Inventario','Varias actividades; 3308 t/año MP10 y 573 t/año MP2,5 (IV.22-23, pp.49/52).','873 arcos viales, divididos en 12263 fuentes LINE. No inventario total del proyecto.'],
 ['Masa anual de tránsito','2357,2 t MP10 y 237,1 t MP2,5 (IV.23 y hoja «Caso Base 2017» de ADC-131a).','Los 873 tramos suman '+num(audit['inventory_annual'][0]['mass_tonnes'])+' t MP10 y '+num(audit['inventory_annual'][1]['mass_tonnes'])+' t MP2,5 en los CSV propios.'],
 ['Procesos / período','CALPUFF + MESOPUFF; año 2017 completo.','AERMOD; PM de emisión directa; ventanas de verano e invierno.'],
 ['Validación meteorológica','Estación Los Bronces (§5.1, p.63).','Discrepancias de Piedra Carvajal; ubicación y soporte distintos.'],
 ['Reparto horario','El PDF no permite reconstruir el horario por fuente.','Masa diaria repartida uniformemente en 24 h; verificado en generador y dos archivos de episodios.']], [125,305,328])
p('<b>Conciliación del inventario vial.</b> En las dos copias del libro de transporte, los 873 tramos utilizados coinciden con los CSV en los 365 días, a la precisión de escritura (318.645 pares por contaminante). De los otros 674 identificadores, 467 tienen emisiones. Estos explican las 84,11 t de MP10 y 9,45 t de MP2,5 restantes.','p')
p('Los tramos incluidos representan el 96,43% de la masa vial anual de MP10 y el 96,01% de MP2,5. Su fracción del aporte en un receptor depende además de la ubicación y del viento. Diciembre de 2016 usa el inventario transferido de 2017.','small')

start('Normativa chilena: valores y uso correcto','Textos proporcionados, cotejados con las fichas oficiales MMA consultadas el 05-11-2026')
table([['Contaminante','24 horas','Anual','Condición y fuente'],
 ['MP10','130 µg/m³N','50 µg/m³N','P98 anual ≥130, o más de 7 días con mediciones >130; media de tres años ≥50. DS12/2021, arts.3-6, p.6.'],
 ['MP2,5','50 µg/m³','20 µg/m³','P98 de promedios diarios del año >50; promedio trianual >20. DS12/2011, arts.3-4, p.5.']], [100,120,120,418])
p('<b>MP10:</b> N corresponde a 25 °C y 1 atm (art.2 b-c). El día se cuenta desde las cero horas; admite al menos 18 valores horarios. Nuestro contraste mantiene 24 horas comunes para evitar comparar soportes distintos. El último día de verano, con 17 horas, sigue fuera del análisis de 24 horas.')
p('<b>Indicadores:</b> el P98 usa la posición k=0,98n, redondeada al entero próximo. MP2,5 redondea además las concentraciones al µg/m³ más próximo (art.2 m). La media anual se construye con medias mensuales; no es la media de dos temporadas. MP2,5 exige cobertura mensual y anual definida en art.6.')
p('<b>Alcance:</b> estos criterios de superación se refieren a mediciones en estaciones EMRP. Una modelación aporta evidencia en el SEIA, pero una salida aislada o un aporte sin fondo no constituye por sí solo el dictamen de cumplimiento de estos decretos.')
p('El ADC-160vi de abril de 2021 usa 150 µg/m³N para MP10 diario (p.139), anterior a la vigencia del DS12/2021 el 04-06-2022 (art.17). La referencia actual es 130; no atribuir retrospectivamente incumplimiento al informe. La ficha MMA mantiene DS12/2011 vigente/en revisión.','small')
p('No está acreditada la normalización de la salida MP10. No se publican cocientes o conteos contra 130 ni se convierte usando una presión única de estación. Las normas primarias tampoco evalúan directamente el efecto sobre el glaciar.','small')

start('Referencias del titular y ubicación de receptores','Tablas VI.1-VI.4: PDF pp.86-89; impreso pp.85-88. Concentraciones en µg/m³ según el anexo')
rows=[['Receptor / PM','Media AD-473','Media ADC-160vi','P98 AD-473 → ADC-160vi']]
for r in comparison.itertuples():
    if pd.notna(r.EIA_annual_mean_ADC160):
        rows.append([r.receptor+' / '+('MP2,5' if r.pollutant=='MP25' else 'MP10'),num(r.EIA_annual_mean_AD473),num(r.EIA_annual_mean_ADC160),
         (num(r.EIA_annual_P98_AD473)+' → '+num(r.EIA_annual_P98_ADC160)) if pd.notna(r.EIA_annual_P98_ADC160) else 'No asignable a este punto'])
table(rows,[230,130,150,248])
p('<b>Los Bronces:</b> 147 es el máximo de media anual MP10 en sus mismas coordenadas horizontales. Los 27 µg/m³ de MP2,5 y los P98 máximos pertenecen a otro punto, unos 428 m más lejos; no se asignan a nuestro receptor.')
p('<b>La Paloma:</b> el anexo entrega MPS en Paloma Norte/Oeste (mg/m²-día), en ubicaciones distintas. No hay en esas tablas una media anual MP10/MP2,5 para nuestro punto exacto. No se convierte MPS a concentración respirable.')
p('<b>Cotas:</b> receptor AERMOD / cota de tabla ADC: Los Bronces 3440,26 / 3712 m; Piedra Carvajal 3265,84 / 3817,6 m; Sulfatos 4198,22 / 4374,6 m. Son discrepancias por resolver: no corregir coordenadas o cotas automáticamente. Tabla II.1 da otras altitudes para las estaciones meteorológicas.','small')

start('Lectura metodológica y pasos para cerrar','Qué queda respaldado y qué evidencia adicional cambia la decisión')
p('<b>El argumento del anexo:</b> compara viento medio observado 7,2 y modelado 6,2 m/s en Los Bronces; calcula −13,9% y razona que subestimar viento/temperatura aumentaría las concentraciones (§5.3). Esto no garantiza conservadurismo en cada receptor cuando también cambian dirección, estabilidad y mezcla. Nuestra sensibilidad examina esa inferencia dentro del modelo actual; aún no refuta cuantitativamente el CALPUFF completo.')
p('<b>Precaución estadística:</b> la tabla V.1 informa sesgos −0,9 y −4,74, junto a “error cuadrático medio” 0,04 y 0,06, sin aclarar unidades/normalización en esa página. Si fueran ECM brutos, deberían ser ≥sesgo²; si fueran RMSE, ≥|sesgo|. Antes de comparar esos números, recuperar la definición y las series originales.')
table([['Próximo cierre','Evidencia concreta necesaria'],
 ['Inventario y modelo del titular','El resumen ADC-131a y las planillas viales permitieron conciliar tránsito (p.2). El ZIP local de ADC-161 contiene dos avisos de descarga fallida. Para verificar cotas y aportes por receptor se necesita la copia íntegra del caso base del titular.'],
 ['Admisión de escenarios','Régimen de aplicación, transferencia horizontal/vertical, reloj/altura de sensores y aplicabilidad al relieve. Contraste WRF ya calculado; heterogeneidad no valida ni invalida por sí sola.'],
 ['Comparación normativa','Trazabilidad de volumen MP10, indicador/período adecuados, aporte y fondo sin doble conteo. Identificar receptores de salud y receptores ambientales.']], [180,578])
p('Corrección documental: el PDF DS12/2011 enviado dice “veinte” y “20” en art.3. La nota anterior sobre una supuesta discordancia verbal no se reproduce en esta fuente y se retira de esta actualización. No afecta el valor 20 usado en los cálculos.','small')
p('Fuentes oficiales de vigencia: <link href="https://normasaire.mma.gob.cl/nambientales/normas-de-calidad-del-aire/norma-primaria-de-calidad-del-aire-para-material-particulado-respirable-mp10/" color="#234b68">MMA MP10</link>; <link href="https://normasaire.mma.gob.cl/nambientales/normas-de-calidad-del-aire/norma-primaria-de-calidad-del-aire-para-material-particulado-fino-mp25/" color="#234b68">MMA MP2,5</link>. Fuentes_recibidas.json registra PDFs, páginas y hashes. Las ocho figuras siguientes conservan las concentraciones calculadas y actualizan solo las referencias documentales.','small')

for f in figs:
    start('Resultados: media BASE y referencia ADC-160vi','Verano: 21-dic-2016 a 20-mar-2017; invierno: 21-jun a 20-sep-2017. Solo días completos comunes.')
    c.drawImage(str(O/f'Figuras/{f["name"]}.png'),25,44,width=792,height=422.4,mask='auto')
c.save();assert len(PdfReader(pdf).pages)==13
dump('Verificacion_construccion.json',{'status':'NUMERICALLY_CHECKED_VISUAL_PENDING','time_utc':datetime.now(timezone.utc).isoformat(),
 'PDF':str(pdf),'PDF_pages':13,'figures':figs,'own_daily_values_unchanged':len(d),'own_means_recomputed_and_matched':144,
 'days_summer':87,'days_winter':90,'reference_rows':len(ref),'models_run':0,
 'input_hashes':[{ 'path':str(p),'sha256':sha(p)} for p in [G/'Datos/Diarios_24h_utilizados.csv',G/'Datos/Referencias_EIA_transcripcion.csv',O/'Auditoria_comparabilidad.json']],
 'physical_admission':'NOT_ESTABLISHED','legal_compliance':'NOT_ASSESSED'})
(O/'Lectura_y_cambios.md').write_text('# Actualización ADC-160vi y normativa\n\n'+
 '\n\n'.join(notes)+'\n\nOcho gráficos PNG/SVG en Figuras. Datos y transcripciones versionadas en Datos. No se modificaron los informes históricos ni las corridas.\n',encoding='utf-8')
print(json.dumps({'pdf':str(pdf),'pages':13,'figures':len(figs),'new_model_runs':0},ensure_ascii=False))
