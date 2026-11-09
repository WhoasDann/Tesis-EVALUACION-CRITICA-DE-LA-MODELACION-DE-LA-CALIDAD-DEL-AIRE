"""Append a shared regulatory/reproduction supplement to both existing reports."""
from pathlib import Path
import sys,json,shutil,hashlib,datetime,re,math
import pandas as pd
import numpy as np
sys.path.insert(0,'/archivo/usuario/Documents/Codex/2026-10-19/es/work/python_deps')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader,PdfWriter
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/Normativa_reproduccion_2026-11-04';FIG=OUT/'Figuras';FIG.mkdir(exist_ok=True)
I=ROOT/'outputs/Informe_integrado_2026-11-04';C=ROOT/'outputs/Seleccion_adversa_2026-11-04'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fmt(x,n=2):return f'{x:,.{n}f}'.replace(',','_').replace('.',',').replace('_','.')
audit=read(OUT/'Verificacion_reproduccion.json');assert audit['status']=='PASSED'
m=pd.read_csv(OUT/'Indicadores_descriptivos_submuestra.csv');d=pd.read_csv(OUT/'Diarios_reproducidos_cuatro_receptores.csv')
reg=pd.read_csv(OUT/'Contraste_regimen_horario.csv');regsum=pd.read_csv(OUT/'Contraste_regimen_resumen.csv')
LAB={'BASE':'BASE','T_MINUS':'T-','T_PLUS':'T+','U_MINUS':'u-','U_PLUS':'u+','V_MINUS':'v-','V_PLUS':'v+','WS_PLUS':'WS+','T_WS_PLUS':'T+WS+'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':180})
fig,axes=plt.subplots(1,2,figsize=(10,3.8),layout='constrained')
for ax,s in zip(axes,['VERANO','INVIERNO']):
    for sc,col in [('BASE','#263e50'),('U_PLUS','#c46a2c'),('T_WS_PLUS','#168479')]:
        x=np.sort(d[(d.season==s)&(d.scenario==sc)&(d.receptor=='Los Bronces')&(d.pollutant=='MP25')&(d['count']==24)&(d['size']==24)&d.complete_civil_day]['mean'].to_numpy())
        assert len(x) in [87,90];ax.step(x,np.arange(1,len(x)+1)/len(x),where='post',label=LAB[sc],color=col)
    ax.axvline(50,color='#963c58',ls='--',lw=1,label='Referencia numérica 50')
    ax.set(title=s.title(),xlabel='Aporte diario MP2,5 (µg/m³)',ylabel='Fracción acumulada de días disponibles',ylim=(0,1.03));ax.grid(alpha=.18);ax.legend(fontsize=8)
fig.savefig(FIG/'Distribucion_MP25.png');fig.savefig(FIG/'Distribucion_MP25.svg');plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(10,3.6),layout='constrained')
for ax,day in zip(axes,['2017-01-16','2017-07-09']):
    g=reg[(reg.day==day)&(reg.scenario=='BASE')].sort_values('hour_start')
    hours=pd.to_datetime(g.hour_start).dt.hour.to_numpy();ax.plot(hours,g.WS_obs,'o-',ms=3,color='#9d3372',label='Estación, lectura :49')
    for sc,col in [('BASE','#263e50'),('OBS_U','#168479')]:
        x=reg[(reg.day==day)&(reg.scenario==sc)].sort_values('hour_start');ax.plot(pd.to_datetime(x.hour_start).dt.hour,x.WS,label='SFC '+('BASE' if sc=='BASE' else 'terna U'),color=col)
    ax.axhline(1,color='.6',ls=':',lw=1);ax.set(title=day,xlabel='Inicio del intervalo civil',ylabel='Rapidez del viento (m/s)',xticks=[0,6,12,18,23]);ax.legend(fontsize=8);ax.grid(alpha=.18)
fig.savefig(FIG/'Contraste_regimen.png');fig.savefig(FIG/'Contraste_regimen.svg');plt.close(fig)

pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'));pdfmetrics.registerFont(TTFont('Arial-Bold','C:/Windows/Fonts/arialbd.ttf'))
pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='Arial-Bold',italic='Arial',boldItalic='Arial-Bold')
styles=getSampleStyleSheet()
for n,font,size,lead in [('BodyES','Arial',10,14),('HeadES','Arial-Bold',16,20),('SmallES','Arial',8.7,11.5),('CellES','Arial',8.3,11)]:styles.add(ParagraphStyle(name=n,fontName=font,fontSize=size,leading=lead,spaceAfter=9,textColor=colors.HexColor('#203846')))
story=[];md=[]
def p(t,k='BodyES'):story.append(Paragraph(t,styles[k]));md.append(re.sub('<[^>]+>','',t))
def head(t):p(t,'HeadES')
def page():story.append(PageBreak());md.append('\n---\n')
def table(headers,rows,widths):
    t=Table([[Paragraph(escape(str(v)),styles['CellES']) for v in r] for r in [headers]+rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e0edf1')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f3f6f7')])]))
    story.extend([t,Spacer(1,10)]);md.extend(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])
def image(name):
    from PIL import Image as PI
    path=FIG/name
    with PI.open(path) as im:h=510*im.height/im.width
    story.extend([Image(str(path),width=510,height=h),Spacer(1,9)]);md.append(f'![{name}](Figuras/{name})')
def link(url,text):return f'<link href="{url}" color="#176e84">{text}</link>'
mp10='https://www.bcn.cl/leychile/navegar?idNorma=1176988';mp25='https://www.bcn.cl/leychile/navegar?idNorma=1025202'

head('Complemento A. Normativa chilena verificada')
p('Actualización del 5 de noviembre de 2026. Este complemento se añade a los dos informes y conserva sus resultados previos. Incorpora los criterios legales y una nueva reproducción independiente desde las salidas horarias; no convierte el análisis de sensibilidad en una certificación de cumplimiento.')
table(['Materia','MP10','MP2,5'],[
['Norma de referencia','DS12/2021 MMA. Vigente desde 04/06/2022.','DS12/2011 MMA. Vigente desde 01/01/2012.'],
['Valor diario','130 µg/m³N','50 µg/m³'],
['Superación diaria','P98 anual ≥130; o más de siete días con mediciones >130 antes de terminar el año calendario.','P98 de los promedios diarios del año >50. El decreto no incorpora aquí la regla alternativa de siete días de MP10.'],
['Valor anual','50 µg/m³N; superación si promedio de tres años calendario consecutivos ≥50.','20 µg/m³; superación si promedio trianual de las concentraciones anuales >20.'],
['Base de volumen','Normal: 25 °C y 1 atm (298,15 K; 101325 Pa).','El límite se expresa en µg/m³. No trasladar automáticamente la N de MP10.'],
['Ámbito de constatación','Mediciones de concentración ambiental en estaciones calificadas EMRP.','Mediciones de concentración ambiental en estaciones calificadas EMRP.']],[111,206,206])
p('Fuentes: '+link(mp10,'DS12/2021, artículos 2-6 y 17')+'; '+link(mp25,'DS12/2011, artículos 2-4, 6 y 14')+'. Los signos son parte del criterio: ≥ para MP10 y > para MP2,5. Un máximo diario aislado no sustituye al P98 anual.','SmallES')
p('Las fichas vigentes del '+link('https://normasaire.mma.gob.cl/nambientales/normas-de-calidad-del-aire/norma-primaria-de-calidad-del-aire-para-material-particulado-respirable-mp10/','MMA para MP10')+' y '+link('https://normasaire.mma.gob.cl/nambientales/normas-de-calidad-del-aire/norma-primaria-de-calidad-del-aire-para-material-particulado-fino-mp25/','MP2,5')+' confirman esos límites. La revisión de MP10 comenzó mediante resolución 4115/2026. El expediente de MP2,5 registra un proyecto y actuaciones posteriores: no se usan propuestas como límites obligatorios.','SmallES')
p('<b>Fecha del estudio y fecha de la norma.</b> La meteorología simulada es de 2016-2017, anterior al DS12/2021. El valor actual de 130 se documenta como referencia contemporánea. Una evaluación jurídica del expediente histórico requiere identificar sus normas, fechas y obligaciones aplicables; no se afirma retroactividad ni incumplimiento del EIA.')

page();head('Complemento B. Condiciones para una comparación válida')
table(['Condición','Situación de este estudio'],[
['Aporte frente a concentración ambiental','AERMOD representa las fuentes incluidas. No se añadió fondo ambiental ni se acreditó el total de otras fuentes. Estar bajo un límite como aporte no prueba cumplimiento del total.'],
['Receptor frente a EMRP','Los cuatro receptores son puntos de cálculo; no se presume su calificación por la SMA. Una estación meteorológica tampoco equivale a estación de material particulado EMRP.'],
['Protección de personas y glaciares','Las normas primarias protegen salud humana. Estos límites no son umbrales específicos de daño glaciar, deposición de partículas, albedo o efecto ecológico.'],
['Año y promedio trianual','Se dispone de dos temporadas, no de años completos ni tres años consecutivos. El verano cruza 2016 y 2017. No se calcula una media anual juntando temporadas ni un P98 anual con esta selección.'],
['Regla de siete días','En MP10 cuenta mediciones válidas >130 en un mismo año. No es una regla general de tolerancia ni se aplica a MP2,5. No se deduce incumplimiento desde conteos de este panel simulado.']],[132,391])
head('La unidad µg/m³ no acredita por sí sola µg/m³N')
p('Se inspeccionaron los archivos principales de los 3276 casos estacionales y la reconstrucción de sus salidas: no aparece una conversión acreditada al volumen normal chileno. El manual AERMOD v26135 (§3.3.13) describe la conversión de masa a µg/m³ mediante el factor 10⁶; eso no demuestra la normalización requerida por MP10. Por ello no se publican conteos de superación de 130 ni porcentajes de norma para MP10.')
p('Si se acredita que C es una concentración a condiciones ambientales, la conversión de volumen sería C_N(t) = C(t) · [P_N/P(t)] · [T(t)/T_N], con T en kelvin. Debe resolverse a la misma escala temporal y con presión/temperatura representativas del receptor. No se aplicó una presión única de la estación a los cuatro receptores ni se normalizó una media usando promedios de P y T.','SmallES')
p('Para MP2,5 se muestra únicamente una comparación numérica descriptiva del aporte con 50 µg/m³. Quedan las limitaciones de cobertura, fondo, representatividad y modelo. No se asignan alertas, preemergencias o emergencias a estas corridas.','SmallES')
p('Fuente técnica: '+link('https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/aermod_userguide.pdf','EPA, AERMOD User’s Guide, julio de 2026')+'. Detalle verificable en Auditoria_unidades.json y Fuentes_normativas.json.','SmallES')

page();head('Complemento C. Reproducción de resultados e indicadores')
p('Se leyeron los POSTFILE horarios originales, se verificaron sus SHA-256 contra los recibos, se aplicó únicamente la máscara ya auditada y se reconstruyó el calendario civil desde las marcas AERMOD. Las medias se recalcularon desde esas horas. No se relanzaron simulaciones para repetir un posprocesamiento.')
table(['Control independiente','Resultado'],[
['Casos estacionales únicos','3276; los 728 controles reutilizados no se cuentan dos veces.'],
['Valores horarios / válidos',str(audit['native_hourly_values'])+' / '+str(audit['valid_hourly_values'])],
['Medias diarias sensibles','13104 filas reproducidas; error máximo '+f"{audit['maximum_daily_error']:.2e}"+' µg/m³.'],
['Selección e interacción','32 indicadores de selección y 16 interacciones T/WS reproducidos.'],
['Muestra estricta común','87 días de verano y 90 de invierno, todos con 24 horas válidas y nueve configuraciones.'],
['Ternas nuevas','38 casos y sus 128 medias diarias de los cuatro receptores verificados aparte; cinco fechas civiles de verano y seis de invierno.']],[155,368])
p('<b>Cómo se calcula el percentil.</b> Los decretos usan un estadístico de orden: se ordenan n valores y se toma la posición k = 0,98n redondeada al entero más cercano (numeración desde 1). No se sustituye por el percentil interpolado predeterminado de una librería. MP2,5 requiere además redondear las concentraciones al µg/m³ más próximo antes de ordenar.')
p('En esta muestra estricta k vale 85 para 87 días y 88 para 90 días. Los valores que siguen se rotulan <b>P98 de submuestra</b>: no son P98 anuales normativos. También se conservan los datos sin redondear. Se usa el entero más próximo, con empates exactos a 0,5 hacia arriba como convención computacional documentada; no se alteran las simulaciones.')
p('La regla de 24 horas completas es un control analítico deliberadamente estricto. MP10 admite promedios diarios con al menos 18 horas; MP2,5 remite sus promedios al DS61/2008. Por tanto, los denominadores 87 y 90 no se presentan como el calendario legal de una estación.','SmallES')
p('<b>Promedios anuales.</b> Ambos decretos construyen el valor anual a partir de concentraciones mensuales. El DS12/2011 establece además requisitos de disponibilidad mensual/anual. No se imputaron meses sin respaldo ni se aplicó una equivalencia entre una media estacional y el límite anual.')
p('Los archivos Indicadores_descriptivos_submuestra.csv y Cobertura_por_ano_calendario.csv conservan las 144 combinaciones receptor/temporada/contaminante/configuración y separan los años. Verificacion_reproduccion.json documenta las tolerancias y los hashes.','SmallES')

page();head('Complemento D. Lectura descriptiva de MP2,5')
g=m[(m.receptor=='Los Bronces')&(m.pollutant=='MP25')]
rows=[]
for sc in LAB:
    a=g[(g.season=='VERANO')&(g.scenario==sc)].iloc[0];b=g[(g.season=='INVIERNO')&(g.scenario==sc)].iloc[0]
    rows.append([LAB[sc],f'{int(a.days_above50_raw)}/{int(a.n_days)}',f'{int(b.days_above50_raw)}/{int(b.n_days)}',str(int(a.P98_subset_rounded)),str(int(b.P98_subset_rounded)),fmt(a.max_daily),fmt(b.max_daily)])
table(['Caso','Días >50 V','Días >50 I','P98 sub. V','P98 sub. I','Máximo V','Máximo I'],rows,[65,80,80,75,75,74,74])
p('Los Bronces; concentraciones en µg/m³. Días >50 se cuenta sobre las medias sin redondear. P98 sub. usa las medias redondeadas según la regla MP2,5; V/I indican verano/invierno. El CSV también conserva conteos tras redondeo. Son recuentos de aportes simulados en la muestra, no días de superación normativa de una EMRP.','SmallES')
image('Distribucion_MP25.png')
p('La distribución distingue el día extremo del conjunto de días. La línea vertical de 50 es una referencia numérica; los datos no cumplen el alcance temporal ni observacional necesario para un dictamen legal.','SmallES')
other=m[(m.pollutant=='MP25')&(m.receptor!='Los Bronces')]
p('En Piedra Carvajal, Sulfatos y La Paloma, todos los máximos diarios de las nueve configuraciones quedan por debajo de 50 en esta muestra: el mayor es '+fmt(other.max_daily.max(),3)+' µg/m³. Esto describe el aporte modelado y no permite concluir cumplimiento de la concentración ambiental total.','SmallES')

page();head('Complemento E. Avance en el contraste meteorológico')
image('Contraste_regimen.png')
p('Se comparó el viento de referencia SFC con las lecturas de Piedra Carvajal dentro del mismo intervalo civil, para el 16 de enero y el 9 de julio. Las observaciones son instantáneas al minuto :49; SFC representa la meteorología horaria de otra columna y puede tener distinta representatividad vertical. Es un diagnóstico de compatibilidad, no una validación directa.')
table(['Fecha / caso','Horas','WS media estación','WS media SFC','Diferencia abs. media','Horas SFC <1'],[[pd.Timestamp(r.day).strftime('%d/%m')+' / '+('BASE' if r.scenario=='BASE' else 'Terna U'),r.paired_hours,fmt(r.observed_WS_mean),fmt(r.SFC_WS_mean),fmt(r.WS_MAE_rough),r.SFC_hours_WS_lt1] for r in regsum.itertuples()],[110,47,85,85,114,82])
p('Rapideces y diferencias en m/s. El umbral de 1 m/s es solo diagnóstico; no redefine la condición técnica de calma de AERMOD. La diferencia absoluta mezcla desajustes de tiempo, altura y lugar, por lo que no se utiliza para declarar un escenario mejor validado.','SmallES')
for day,hour in [('2017-01-16',0),('2017-07-09',2)]:
    q=reg[(reg.day==day)&(reg.scenario=='OBS_U')&(pd.to_datetime(reg.hour_start).dt.hour==hour)].iloc[0]
    p(f'En {pd.Timestamp(day).strftime("%d/%m")}, intervalo {hour:02d}-{hour+1:02d} h: la lectura de estación es {fmt(q.WS_obs)} m/s y {fmt(q.WD_obs,1)}°; la terna U produce {fmt(q.WS)} m/s y {fmt(q.WD,1)}° en SFC. La combinación diaria observada no garantiza reproducir ese viento horario.', 'SmallES')
p('La diferencia absoluta de rapidez aumenta con la terna U en ambos episodios. Esto refuerza la necesidad de validar su transferencia; por los desajustes de lugar y soporte temporal, no basta para declarar un error físico de AERMOD. Ambos días pertenecen a las ventanas de ajuste, por lo que no son evaluación fuera de muestra. La observación del 26 de enero no está en los archivos examinados: no se fabricó un contraste para La Paloma.','SmallES')

page();head('Complemento F. Conclusiones actualizadas y continuidad')
p('<b>El estudio conserva su alcance:</b> sensibilidad prescrita y variabilidad del aporte de las fuentes incluidas. La reproducción desde salidas originales respalda la consistencia numérica. Las normas aportan referencias y reglas de evaluación, pero no solucionan la falta de fondo, años completos, calificación EMRP o equivalencia física de las perturbaciones.')
table(['Prioridad','Trabajo necesario y criterio de cierre'],[
['1. Unidades de MP10','Acreditar la base volumétrica de entrada/salida y el procedimiento aceptado para normalizar. Obtener presión y temperatura representativas de cada receptor y hora si corresponde. Hasta entonces, sin porcentajes ni conteos contra 130.'],
['2. Representatividad meteorológica','Contrastar estación, columna MMIF y receptores; alturas y relojes; regímenes de viento débil y giro. Ampliar observaciones fuera de ajuste antes de admitir candidatos como físicamente sustentados.'],
['3. Comparabilidad ambiental','Precisar fondo y otras fuentes, evitando doble conteo; justificar horarios reales de operación y población expuesta; obtener resolución EMRP cuando se invoque cumplimiento en una estación.'],
['4. Alcance normativo o del EIA','Identificar régimen jurídico aplicable y estadísticas exigidas; ampliar cobertura temporal/espacial solo una vez fijado ese objetivo. No confundir todas las fechas estacionales con un año completo.']],[132,391])
p('<b>Cómo presentar el resultado:</b> “Se reprodujeron los aportes diarios simulados y se examinaron con referencia a los valores de las normas primarias chilenas. Las comparaciones disponibles son descriptivas y condicionadas a cobertura y unidades; no constituyen constatación de superación normativa”.')
p('Para MP10 no se evaluó el umbral hasta acreditar µg/m³N. Para MP2,5, los conteos y percentiles se mantienen etiquetados como submuestra. No se generalizan resultados de una terna sobre episodios elegidos a medias estacionales o a probabilidades de excedencia.')
p('<b>Material añadido.</b> Fuentes_normativas.json registra vínculos, artículos y fecha de consulta. Auditoria_unidades.json, Verificacion_reproduccion.json, Verificacion_ternas.json y Trazabilidad_reproduccion.json documentan los controles. Los CSV permiten reproducir estadísticas y el contraste horario. Los scripts de esta actualización solo analizan y generan informes; no despachan modelos.','SmallES')
p('Versiones: los PDFs anteriores están preservados en Version_anterior_sin_normativa. Este complemento aparece como N1-N6 en ambos informes. Las páginas originales se mantienen; el nuevo texto amplía las consideraciones normativas y el control de reproducibilidad.','SmallES')
p('Fuentes de vigencia adicionales: '+link('https://www.bcn.cl/leychile/navegar?idNorma=1227023','Resolución 4115/2026 (MP10)')+' y '+link('https://planesynormas.mma.gob.cl/normas/expediente/index.php?id_expediente=939510&tipo=busqueda','expediente MMA de revisión MP2,5')+'. El inicio de revisión no equivale a reemplazo automático de los límites.','SmallES')

def footer(canvas,doc):
    canvas.setFont('Arial',8);canvas.setFillColor(colors.HexColor('#476777'));canvas.drawString(36,23,'Complemento normativo y reproducción | 05-11-2026');canvas.drawRightString(559,23,'N'+str(doc.page))
annex=OUT/'Complemento_normativa_reproduccion.pdf'
SimpleDocTemplate(str(annex),pagesize=A4,leftMargin=36,rightMargin=36,topMargin=34,bottomMargin=48,title='Normativa chilena y reproducción de resultados').build(story,onFirstPage=footer,onLaterPages=footer)
assert len(PdfReader(annex).pages)==6
(OUT/'Complemento_normativa_reproduccion.md').write_text('\n\n'.join(md),encoding='utf-8')
changed=[]
for folder,name,expected in [(I,'Informe_integrado_resultados.pdf',12),(C,'Informe_seleccion_adversa.pdf',8)]:
    backup=folder/'Version_anterior_sin_normativa';backup.mkdir(exist_ok=True)
    path=folder/name
    if not (backup/name).exists():
        for q in folder.iterdir():
            if q.is_file() and q.suffix.lower() in ['.pdf','.md','.json','.zip']:shutil.copy2(q,backup/q.name)
    base=backup/name;assert len(PdfReader(base).pages)==expected
    writer=PdfWriter();writer.append(str(base));writer.append(str(annex))
    writer.add_metadata({'/Title':'Resultados con normativa chilena y reproducción - Los Bronces','/Author':'Proyecto de tesis de Daniel Castro'})
    with path.open('wb') as f:writer.write(f)
    updated=PdfReader(path);original=PdfReader(base)
    assert len(updated.pages)==expected+6
    for i in range(expected):assert updated.pages[i].get_contents().get_data()==original.pages[i].get_contents().get_data()
    changed.append({'pdf':str(path),'original_pages_preserved':expected,'total_pages':expected+6,'sha256':sha(path)})
save(OUT/'Informes_actualizados.json',{'status':'GENERATED_PENDING_VISUAL_QA','reports':changed,'annex_pages':6,'annex_sha256':sha(annex)})
print(json.dumps(changed))
