"""Audited joint-effect supplement: four corners, paired changes, and interaction."""
from pathlib import Path
import sys,html
sys.path.insert(0,'/archivo/usuario/Documents/Codex/2026-10-19/es/work/python_deps')
import numpy as np,pandas as pd,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader
from campaign import OUT,SCENARIOS,read,save,rec,now
NAMES=['Los Bronces','Sulfatos','Piedra Carvajal','La Paloma']
SEASONS=['VERANO','INVIERNO'];POLS={'MP10':'MP10','MP25':'MP2,5'}
def fmt(x,n=3):return f'{x:.{n}f}'.replace('.',',')
def sig(x):return f'{x:.4g}'.replace('.',',')
def pct(x):return f'{x:+.2f}%'.replace('.',',')

def main():
    audit=read(OUT/'Auditoria_final.json');assert audit['status']=='PASSED' and audit['cases']==1456
    design=read(OUT/'Diseno.json')
    a=pd.read_csv(OUT/'Interaccion_periodo_comparable.csv');a=a[a.receptor.isin(NAMES)].copy()
    d=pd.read_csv(OUT/'Interaccion_diaria_civil.csv');d=d[d.receptor.isin(NAMES)].copy()
    assert len(a)==16 and len(d)==1456
    dd=d[d.complete_civil_day].copy()
    assert len(dd)==1448
    stats=[]
    for key,g in dd.groupby(['season','pollutant','receptor']):
        q=g.interaccion_ug_m3;idx=q.abs().idxmax()
        stats.append(dict(zip(['season','pollutant','receptor'],key),days=len(g),mean_daily_interaction=q.mean(),median_daily_interaction=q.median(),sd_daily_interaction=q.std(ddof=1),p10=q.quantile(.1),p90=q.quantile(.9),min_interaction=q.min(),max_interaction=q.max(),max_absolute_interaction_day=g.loc[idx,'day'],max_absolute_interaction_value=g.loc[idx,'interaccion_ug_m3']))
    pd.DataFrame(stats).to_csv(OUT/'Estadisticas_interaccion_diaria.csv',index=False)
    a.to_csv(OUT/'Tabla_conjunto_cuatro_receptores.csv',index=False)
    figdir=OUT/'Figuras';figdir.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.unicode_minus':False,'savefig.facecolor':'white'})
    def figure(fig,name):
        fig.savefig(figdir/(name+'.png'),dpi=180);fig.savefig(figdir/(name+'.svg'));plt.close(fig)
    for pol,label in POLS.items():
        fig,axes=plt.subplots(2,4,figsize=(12,6.2))
        for row,s in enumerate(SEASONS):
            for col,name in enumerate(NAMES):
                ax=axes[row,col];r=a[a.season.eq(s)&a.pollutant.eq(pol)&a.receptor.eq(name)].iloc[0]
                values=[r.efecto_T_ug_m3,r.efecto_T_con_WS_alta_ug_m3]
                ax.bar([0,1],values,color=['#287F8E','#CA7640'],width=.6);ax.axhline(0,color='#777777',lw=.7)
                ax.set_xticks([0,1],['Rapidez\nBASE','Rapidez\n+SD']);ax.set_title(name+' | '+s.title(),fontsize=9)
                ax.set_ylabel('Efecto de T+ (µg/m³)',fontsize=9);ax.grid(axis='y',alpha=.17)
                ax.text(.03,.96,'I = '+sig(r.interaccion_ug_m3),transform=ax.transAxes,va='top',fontsize=9,bbox=dict(facecolor='white',edgecolor='none',alpha=.8))
                ax.margins(y=.3)
        fig.suptitle('¿Cuánto cambia el efecto de T+ cuando aumenta la rapidez? | '+label,fontsize=13)
        fig.text(.025,.012,'I es la segunda barra menos la primera. Una diferencia muestra interacción en el modelo. Cada panel tiene escala propia.',fontsize=9)
        fig.tight_layout(rect=[0,.045,1,.94]);figure(fig,'Interaccion_condicional_'+pol)
        fig,axes=plt.subplots(4,2,figsize=(10.1,10.2))
        for row,name in enumerate(NAMES):
            for col,s in enumerate(SEASONS):
                ax=axes[row,col];g=d[d.season.eq(s)&d.pollutant.eq(pol)&d.receptor.eq(name)].sort_values('day')
                ax.plot(pd.to_datetime(g.day),g.interaccion_ug_m3,lw=1,color='#287F8E',marker='.',ms=3)
                if s=='VERANO':ax.plot(pd.Timestamp(g.iloc[-1].day),g.iloc[-1].interaccion_ug_m3,'^',color='#CA7640',ms=6)
                ax.axhline(0,color='#666666',lw=.7);ax.set_title(name+' | '+s.title(),fontsize=10);ax.set_ylabel('Interacción (µg/m³)')
                ax.grid(alpha=.15);ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3));ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m'));ax.tick_params(axis='x',rotation=30,labelsize=8)
        fig.suptitle('Interacción diaria: efecto conjunto menos suma de efectos | '+label,fontsize=13,y=.99)
        fig.text(.035,.012,'Calendario civil en invierno; triángulo: fragmento de 17 horas del último día de verano. Escalas propias por panel.\nLa interacción puede cambiar de signo entre días y no es un error observado ni un intervalo de incertidumbre.',fontsize=9)
        fig.tight_layout(rect=[0,.06,1,.96]);figure(fig,'Interaccion_diaria_'+pol)
    pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'));pdfmetrics.registerFont(TTFont('ArialB','C:/Windows/Fonts/arialbd.ttf'))
    pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='ArialB')
    navy=colors.HexColor('#17384A');teal=colors.HexColor('#287F8E');W=507
    styles={k:ParagraphStyle(k,fontName='ArialB' if k in ['title','h','sub','head'] else 'Arial',fontSize=size,leading=lead,spaceAfter=after,textColor=colors.white if k=='head' else navy) for k,size,lead,after in [('title',23,28,15),('h',16,20,12),('sub',11,15,8),('body',10,14,9),('small',8.5,11,6),('cell',7.8,10,0),('head',7.8,10,0)]}
    story=[]
    def p(s,style='body'):story.append(Paragraph(html.escape(str(s)),styles[style]))
    def page(s):
        if story:story.append(PageBreak())
        p(s,'h')
    def table(rows,widths):
        t=Table([[Paragraph(html.escape(str(v)),styles['head' if i==0 else 'cell']) for v in row] for i,row in enumerate(rows)],colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),teal),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#EFF4F5')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.extend([t,Spacer(1,8)])
    def image(name,width=W):
        from PIL import Image as PI
        file=figdir/(name+'.png');im=PI.open(file);story.append(Image(str(file),width=width,height=width*im.height/im.width));story.append(Spacer(1,8))
    bullets=[]
    for s in SEASONS:
        r=a[a.season.eq(s)&a.pollutant.eq('MP10')&a.receptor.eq('Los Bronces')].iloc[0]
        bullets.append(f"En Los Bronces, MP10 de {s.lower()}: BASE {fmt(r.BASE)} µg/m³; con temperatura y rapidez aumentadas, {fmt(r.T_WS_PLUS)} µg/m³ ({pct(r.conjunto_pct_BASE)}). La interacción estacional es {sig(r.interaccion_ug_m3)} µg/m³; corresponde a {pct(r.interaccion_pct_BASE)} de BASE.")
    maxr=a.loc[a.interaccion_pct_BASE.abs().idxmax()]
    bullets.append('La mayor interacción estacional relativa a BASE entre los receptores y contaminantes corresponde a '+maxr.receptor+' en '+maxr.season.lower()+' ('+POLS[maxr.pollutant]+'): '+pct(maxr.interaccion_pct_BASE)+'. El tamaño absoluto es '+sig(maxr.interaccion_ug_m3)+' µg/m³; ambos números deben leerse juntos.')
    p('Temperatura y rapidez\ndel viento: efecto conjunto','title');p('Complemento del análisis estacional | Los Bronces Integrado','sub')
    p('Se ejecutaron y recibieron 728 casos nuevos y se reutilizaron 728 casos auditados: 1.456 comparaciones caso-día. Se mantienen 90 fechas de verano y 92 de invierno, MP10 y MP2,5 y el panel fijo de 40 receptores, incluidos los cuatro puntos sensibles.')
    for s in bullets:p(s)
    p('La pregunta nueva es si aumentar simultáneamente temperatura y rapidez produce el mismo cambio que sumar sus efectos separados. Para responder se necesita el caso conjunto y un control de rapidez aislada; cambiar u o v por separado también modifica la dirección y no sirve como ese control.')
    p('Todos los resultados de este documento son sensibilidad determinista a la perturbación prescrita. No representan probabilidades, intervalos de confianza ni un peor escenario regulatorio.','small')
    page('1. Diseño, amplitudes y cálculo')
    table([['Configuración','Temperatura','Rapidez','Origen'],['BASE','Original','Original','Reutilizado'],['T+','+1 SD','Original','Reutilizado'],['WS+','Original','+1 SD','Nuevo'],['T+WS+','+1 SD','+1 SD','Nuevo']],[110,110,110,177])
    table([['Temporada','SD T (°C)','SD rapidez (m/s)','Días de ajuste']]+[[s.title(),fmt(design['scales'][s]['T_C'],6),fmt(design['scales'][s]['WS_m_s'],6),design['scales'][s]['training_days']] for s in SEASONS],[150,110,140,107])
    for text in [
        'La discrepancia de rapidez es magnitud del viento observado menos magnitud del viento WRF. Se promedian sus valores firmados por día, con al menos 18 horas conjuntas válidas, y se calcula la SD muestral entre días (ddof=1). Es diferente de calcular la magnitud del error vectorial. Las ventanas de ajuste y amplitudes térmicas son las del estudio anterior.',
        'Se eligió una esquina positiva (+T, +rapidez) antes de examinar las nuevas concentraciones. La rapidez se aumenta sin cambiar la dirección serializada. En calma exacta se conserva velocidad cero porque no hay dirección definida. No se corrige el sesgo medio: la discrepancia media de rapidez de ajuste es negativa en ambas temporadas.',
        'La amplitud se atenúa con la misma función cúbica hasta la PBL BASE: w = 1 - 3s² + 2s³; s = limitar[(z-zref)/(HBASE-zref),0,1]. zref es 2 m para temperatura y 10 m para rapidez. La dirección y los campos auxiliares se conservan; AERMET se ejecuta de nuevo. T+ es idéntico al ensayo estacional anterior.',
        'Efecto conjunto = C(T+,WS+) - C(BASE). Interacción I = C(T+,WS+) - C(T+) - C(WS+) + C(BASE). También: I = efecto de T con rapidez alta - efecto de T con rapidez BASE. Si I = 0, los dos cambios se suman exactamente en ese contraste.',
        'I es una diferencia de diferencias en µg/m³. No es una prueba estadística: no se calculan p-valores con días meteorológicos dependientes. En codificación factorial 0/1 es el coeficiente de interacción; con codificación -1/+1 el coeficiente sería I/4 y el efecto factorial I/2.'
    ]:p(text,'small')
    for pol,label in POLS.items():
        page('2. Cuatro configuraciones y contraste - '+label)
        for s in SEASONS:
            p(s.title()+' | Medias sobre las mismas horas válidas','sub')
            rows=[['Receptor','BASE','T+','WS+','T+WS+','Cambio conjunto','Interacción I']]
            for name in NAMES:
                r=a[a.season.eq(s)&a.pollutant.eq(pol)&a.receptor.eq(name)].iloc[0]
                rows.append([name]+[sig(r[k]) for k in SCENARIOS]+[pct(r.conjunto_pct_BASE),sig(r.interaccion_ug_m3)])
            table(rows,[105,63,63,63,63,77,73])
        p('Concentraciones e interacción en µg/m³; el cambio conjunto es porcentaje de BASE. Una interacción positiva significa un resultado mayor que la suma aditiva esperada; no implica necesariamente una concentración conjunta mayor que BASE.','small')
        image('Interaccion_condicional_'+pol)
        p('Las barras muestran únicamente el cambio debido a T+ bajo cada rapidez. Su diferencia es I. La escala varía entre receptores para que también se vean respuestas pequeñas.','small')
    for pol,label in POLS.items():
        page('3. Cuándo aparece la interacción - '+label);image('Interaccion_diaria_'+pol)
        p('Cada punto compara cuatro resultados del mismo día, receptor y contaminante. La curva distingue episodios que una media de temporada puede compensar. Un valor cercano a cero en la media no demuestra ausencia de interacción en todos los días.','small')
    page('4. Lectura científica y límites')
    for text in [
        'Cobertura: verano 2.153 horas objetivo y 2.151 válidas; invierno 2.207 y 2.205. Las cuatro configuraciones conservan las mismas máscaras. La media estacional incluye las 17 horas del 20 de marzo. Las estadísticas de días completos consideran 89 fechas de verano y 92 días civiles de invierno.',
        'En invierno se convirtió el reloj LST fijo UTC-4 al calendario civil: el 13 de agosto tiene 23 horas por cambio de horario; el 14 de agosto tiene 22 horas válidas; el último día civil se reconstruyó con dos archivos LST. Las horas faltantes se enmascaran, no se interpretan como concentración cero.',
        'El ensayo ocurre en los perfiles ONSITE a la salida de MMIF, seguido de AERMET y AERMOD. Se conservan humedad relativa, presión, flujos, UST, MHGT y entradas auxiliares. La respuesta térmica depende de esas restricciones: no evalúa todos los procesos de calentamiento o cambio de estabilidad en una reintegración WRF.',
        'Las amplitudes de estación se transfieren a la columna MMIF I43/J44. Es una hipótesis espacial. Las correlaciones diarias T-rapidez del ajuste son '+fmt(design['scales']['VERANO']['daily_T_WS_correlation'])+' en verano y '+fmt(design['scales']['INVIERNO']['daily_T_WS_correlation'])+' en invierno; escoger ambos signos positivos no reproduce esa dependencia ni asigna una probabilidad conjunta.',
        'Las emisiones y 12.263 fuentes se mantienen iguales entre las cuatro configuraciones de cada fecha. MP10 y MP2,5 son ejecuciones separadas. El panel de 40 puntos no da máximos de toda la malla de 6.295 receptores, ni de toda la superficie de un glaciar. Los resultados son aportes modelados, sin concentración de fondo.',
        'Se verificaron 1.395.200 registros horarios: 1.393.920 válidos y 1.280 enmascarados. Cuatro canarios de los casos nuevos compararon Linux y Windows. Los resultados previos y los planes originales se conservaron al redistribuir únicamente casos aún no iniciados.',
        'Para discutir con el profesor: ¿el interés es el cambio conjunto o su desviación respecto de la suma? ¿Qué receptores y episodios explican la respuesta? ¿Se justifica añadir otra esquina de signos o ampliar la malla? Una sola esquina positiva permite responder este contraste concreto, sin caracterizar todas las combinaciones posibles.'
    ]:p(text,'small')
    p('Fundamento del diseño experimental','sub')
    p('NIST/SEMATECH e-Handbook: Two-level full factorial designs; Interaction effects matrix plot. El esquema factorial respalda separar factores e interacción, pero no valida las amplitudes locales ni el operador meteorológico.','small')
    for url in ['https://www.itl.nist.gov/div898/handbook/pri/section3/pri3331.htm','https://itl.nist.gov/div898/handbook/pri/section5/pri594.htm']:p(url,'small')
    def footer(canvas,doc):
        canvas.setFont('Arial',8);canvas.setFillColor(colors.HexColor('#647580'));canvas.drawString(44,23,'Sensibilidad conjunta T + rapidez | Resultados auditados | 30 octubre 2026');canvas.drawRightString(551,23,str(doc.page))
    pdf=OUT/'Informe_efecto_conjunto_T_WS.pdf'
    SimpleDocTemplate(str(pdf),pagesize=(595.28,841.89),leftMargin=44,rightMargin=44,topMargin=36,bottomMargin=42,title='Efecto conjunto de temperatura y rapidez del viento',author='Daniel - análisis de sensibilidad').build(story,onFirstPage=footer,onLaterPages=footer)
    pages=len(PdfReader(pdf).pages)
    summary=['# Efecto conjunto de temperatura y rapidez del viento','','728 casos nuevos completos y 728 referencias reutilizadas; cuatro esquinas comparables.','']+bullets+['','El efecto conjunto incluye las contribuciones individuales y su interacción. I = C(T+,WS+) - C(T+) - C(WS+) + C(BASE). Sensibilidad prescrita ONSITE; no incertidumbre calibrada.','', '## Resultados MP10','', '| Temporada / receptor | BASE | T+ | WS+ | T+WS+ | Cambio conjunto | Interacción (µg/m³) |','|---|---:|---:|---:|---:|---:|---:|']
    for s in SEASONS:
        for n in NAMES:
            r=a[a.season.eq(s)&a.pollutant.eq('MP10')&a.receptor.eq(n)].iloc[0]
            summary.append('| '+s.title()+' / '+n+' | '+' | '.join([sig(r[k]) for k in SCENARIOS]+[pct(r.conjunto_pct_BASE),sig(r.interaccion_ug_m3)])+' |')
    summary += ['','El PDF incluye también MP2,5 y las series de interacción diaria. Ver LEEME.md para método y referencias; Interaccion_diaria_civil.csv es la tabla correcta para días civiles.']
    (OUT/'Sintesis_efecto_conjunto.md').write_text('\n'.join(summary)+'\n',encoding='utf-8')
    save(OUT/'Informe_generado.json',dict(created_utc=now(),pdf=rec(pdf),pages=pages,figures=[rec(p) for p in sorted(figdir.iterdir())],sources=[rec(OUT/n) for n in ['Auditoria_final.json','Diseno.json','Interaccion_periodo_comparable.csv','Interaccion_diaria_civil.csv']]))
    print('PDF created:',pages,'pages',flush=True);print(a.to_string(index=False),flush=True)
if __name__=='__main__':main()
