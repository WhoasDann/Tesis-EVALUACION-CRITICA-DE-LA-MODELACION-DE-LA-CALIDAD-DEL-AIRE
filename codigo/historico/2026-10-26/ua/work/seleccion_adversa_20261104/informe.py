"""Scientific figures and discussion report; requires complete verified reception."""
from piloto import *
sys.path.insert(0,r'/archivo/usuario\Documents\Codex\2026-10-19\es\work\python_deps')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from xml.sax.saxutils import escape

FIG=OUT/'Figuras';FIG.mkdir(exist_ok=True)
LABEL={'BASE':'BASE','U_PLUS':'u+','V_MINUS':'v-','T_MINUS':'T-','OBS_U':'Terna U','OBS_V':'Terna V'}
COL={'BASE':'#263e50','U_PLUS':'#d87722','V_MINUS':'#d87722','OBS_U':'#168479','OBS_V':'#168479'}
def fmt(v,n=2):return f'{v:,.{n}f}'.replace(',','_').replace('.',',').replace('_','.')
def figs():
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':180})
    daily=pd.read_csv(OUT/'Discrepancias_diarias_conjuntas.csv');design=read(PILOT/'Diseno.json');scales=read(A/'Diseno.json')['scales']
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for ax,season in zip(axes,['VERANO','INVIERNO']):
        g=daily[daily.season==season]
        ax.scatter(g.residuo_u_m_s,g.residuo_v_m_s,color='#667f92',s=25,label='Días observados completos')
        for target in (['U_PLUS','V_MINUS'] if season=='VERANO' else ['U_PLUS']):
            u=scales[season]['u'] if target=='U_PLUS' else 0;v=-scales[season]['v'] if target=='V_MINUS' else 0
            ax.scatter([u],[v],color='#d87722',marker='x',s=90,lw=2)
            ax.annotate(LABEL[target],(u,v),xytext=(5,9) if target=='V_MINUS' else (5,-13),textcoords='offset points',color='#a95513')
        for r in design['prototypes']:
            if r['season']!=season:continue
            t,u,v=r['delta'];ax.scatter([u],[v],s=85,facecolors='none',edgecolors='#168479',linewidths=2)
            ax.annotate(pd.Timestamp(r['source_day']).strftime('%d/%m'),(u,v),xytext=(7,7),textcoords='offset points',fontsize=8,color='#12685f')
        ax.axhline(0,color='.8',lw=.8);ax.axvline(0,color='.8',lw=.8)
        ax.set(title=f'{season.title()} ({len(g)} días)',xlabel='Discrepancia diaria u (m/s)',ylabel='Discrepancia diaria v (m/s)')
    fig.savefig(FIG/'Ternas_observadas.png');fig.savefig(FIG/'Ternas_observadas.svg');plt.close(fig)
    old=pd.read_csv(OUT/'Episodios_horarios.csv');new=pd.read_csv(PILOT/'Horas_cuatro_receptores.csv')
    new=new[['season','day','scenario','pollutant','receptor','fin_LST','C_ug_m3','WS','WD','L','zim','ustar','H','T_K']]
    allh=pd.concat([old,new],ignore_index=True).drop_duplicates(['season','day','scenario','pollutant','receptor','fin_LST'])
    fig,axes=plt.subplots(2,2,figsize=(10,6.1),sharex='col',layout='constrained')
    for j,(season,day,rec,cand,obs) in enumerate([('INVIERNO','2017-06-28','Los Bronces','U_PLUS','OBS_U'),('VERANO','2017-01-12','Sulfatos','V_MINUS','OBS_V')]):
        for sc in ['BASE',cand,obs]:
            g=allh[(allh.season==season)&(allh.day==day)&(allh.receptor==rec)&(allh.pollutant=='MP10')&(allh.scenario==sc)].sort_values('fin_LST')
            assert len(g)==24
            hours=np.arange(24)
            axes[0,j].plot(hours,g.C_ug_m3,label=LABEL[sc],color=COL[sc],lw=1.8)
            axes[1,j].plot(hours,g.WS,label=LABEL[sc],color=COL[sc],lw=1.8)
        axes[0,j].set_title(f'{rec} | {day}');axes[0,j].set_ylabel('MP10 horario (µg/m³)');axes[0,j].legend(fontsize=8)
        axes[1,j].set(xlabel='Inicio de hora local',ylabel='Rapidez de referencia (m/s)',xticks=[0,6,12,18,23])
        for ax in axes[:,j]:ax.grid(alpha=.18)
    fig.savefig(FIG/'Dos_episodios_mecanismo.png');fig.savefig(FIG/'Dos_episodios_mecanismo.svg');plt.close(fig)
    pick=pd.read_csv(PILOT/'Seleccion_episodios_con_respaldo_conjunto.csv');pair=pd.read_csv(PILOT/'Comparacion_cuatro_receptores.csv')
    recs=['Los Bronces','Piedra Carvajal','Sulfatos','La Paloma']
    fig,axes=plt.subplots(1,2,figsize=(10,3.8),layout='constrained')
    for ax,season in zip(axes,['VERANO','INVIERNO']):
        g=pick[(pick.season==season)&(pick.pollutant=='MP10')].set_index('receptor').loc[recs]
        y=np.arange(4);ax.barh(y,g.increase_pct,color='#168479',height=.58)
        for i,v in enumerate(g.increase_pct):ax.text(v+.5,i,f'{v:.1f}%',va='center',fontsize=9)
        ax.set(yticks=y,yticklabels=recs,title=season.title(),xlabel='Aumento del máximo frente al máximo BASE (%)')
        ax.set_xlim(0,max(8,g.increase_pct.max()*1.25));ax.invert_yaxis();ax.grid(axis='x',alpha=.18)
    fig.savefig(FIG/'Maximos_con_soporte_empirico.png');fig.savefig(FIG/'Maximos_con_soporte_empirico.svg');plt.close(fig)
    # Vertical profiles at common diagnostic hours, not at differently timed peaks.
    from analizar import pfl
    fig,axes=plt.subplots(1,4,figsize=(10,3.8),sharey=True,layout='constrained')
    for j,(season,day,hr,cand,obs) in enumerate([('INVIERNO','2017-06-28',17,'U_PLUS','OBS_U'),('VERANO','2017-01-12',20,'V_MINUS','OBS_V')]):
        for sc in ['BASE',cand,obs]:
            folder=(PILOT if sc.startswith('OBS') else A)/'Meteorologia'/season/sc
            p=pfl(folder);p=p[(p.fin_LST==pd.Timestamp(day)+pd.Timedelta(hours=hr))&(p.z>=10)&(p.z<=500)]
            axes[2*j].plot(p.WS,p.z,label=LABEL[sc],color=COL[sc]);axes[2*j+1].plot(np.rad2deg(np.unwrap(np.deg2rad(p.WD))),p.z,color=COL[sc])
        axes[2*j].set_title(f'{day}\nRapidez');axes[2*j+1].set_title(f'Hora final {hr} LST\nDirección de origen')
        axes[2*j].set_xlabel('m/s');axes[2*j+1].set_xlabel('grados');axes[2*j+1].xaxis.set_major_formatter(FuncFormatter(lambda value,pos:f'{value%360:.0f}'));axes[2*j].legend(fontsize=7)
    axes[0].set_ylabel('Altura sobre superficie (m)')
    fig.savefig(FIG/'Perfiles_horas_comparables.png');fig.savefig(FIG/'Perfiles_horas_comparables.svg');plt.close(fig)
    final=pd.read_csv(OUT/'Horas_candidatos_finales.csv')
    fig,axes=plt.subplots(1,2,figsize=(10,3.3),layout='constrained')
    for ax,day,rec,newcase in zip(axes,['2017-01-16','2017-01-26'],['Los Bronces','La Paloma'],['OBS_U','OBS_V']):
        for sc in ['BASE',newcase]:
            g=final[(final.day==day)&(final.receptor==rec)&(final.scenario==sc)].sort_values('fin_LST');assert len(g)==24
            ax.plot(np.arange(24),g.C_ug_m3,label=LABEL[sc],color=COL[sc],lw=1.7)
        ax.set(title=f'{rec} | {day}',xlabel='Inicio de hora local',ylabel='MP10 horario (µg/m³)',xticks=[0,6,12,18,23]);ax.legend(fontsize=8);ax.grid(alpha=.18)
    fig.savefig(FIG/'Candidatos_retenidos.png');fig.savefig(FIG/'Candidatos_retenidos.svg');plt.close(fig)
    return pick,pair

def report():
    audit=read(PILOT/'Recepcion.json');assert audit['status']=='COMPLETE_SCIENTIFIC_RECEPTION' and audit['received']==38
    pick,pair=figs();old=pd.read_csv(OUT/'Seleccion_numerica_32_indicadores.csv');design=read(PILOT/'Diseno.json');geo=pd.read_csv(OUT/'Diagnostico_geometrico_transporte.csv')
    pdfmetrics.registerFont(TTFont('Arial',r'C:\Windows\Fonts\arial.ttf'));pdfmetrics.registerFont(TTFont('Arial-Bold',r'C:\Windows\Fonts\arialbd.ttf'))
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BodyES',fontName='Arial',fontSize=10,leading=14,spaceAfter=8,textColor=colors.HexColor('#20323e')))
    styles.add(ParagraphStyle(name='TitleES',fontName='Arial-Bold',fontSize=23,leading=28,spaceAfter=15,textColor=colors.HexColor('#173f50')))
    styles.add(ParagraphStyle(name='HeadES',fontName='Arial-Bold',fontSize=15,leading=19,spaceAfter=12,textColor=colors.HexColor('#173f50')))
    styles.add(ParagraphStyle(name='SmallES',fontName='Arial',fontSize=8.3,leading=11,spaceAfter=6))
    styles.add(ParagraphStyle(name='CellES',fontName='Arial',fontSize=8,leading=10))
    story=[]; md=[]
    def p(text,kind='BodyES',record=True):
        story.append(Paragraph(text,styles[kind]));
        if record:md.append(re.sub('<[^>]+>','',text))
    def head(text):p(text,'HeadES');md.append('')
    def page():story.append(PageBreak());md.append('\n---\n')
    def table(headers,rows,widths):
        grid=[[Paragraph(escape(str(v)),styles['CellES']) for v in row] for row in [headers]+rows]
        t=Table(grid,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e3eef1')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#8da5af')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8f9')])]))
        story.append(t);story.append(Spacer(1,10));md.append('| '+' | '.join(headers)+' |');md.append('| '+' | '.join(['---']*len(headers))+' |');md.extend('| '+' | '.join(map(str,r))+' |' for r in rows)
    def fig(name,width=500):
        from PIL import Image as PI
        path=FIG/name;im=PI.open(path);story.append(Image(str(path),width=width,height=width*im.height/im.width));story.append(Spacer(1,8));md.append(f'![{name}]({path.as_posix()})')
    p('Selección de escenarios adversos','TitleES');p('Contraste con discrepancias conjuntas observadas. Los Bronces Integrado. 4 de noviembre de 2026.','SmallES')
    p('Se conservó el estudio estacional y se completó un contraste de <b>38 casos nuevos</b> sobre episodios críticos. La selección distingue un máximo numérico de una alternativa con respaldo empírico. Se revisaron las nueve configuraciones anteriores, las ternas diarias T/u/v y la meteorología de sus máximos.')
    p('<b>Resultado principal:</b> en Los Bronces, la terna U de verano produce 860,817 µg/m³ de MP10 el 16 de enero: +65,73% frente a BASE de ese mismo día (519,401) y +14,44% frente al mayor valor diario BASE del conjunto comparable (752,191, el 26 de enero). Es un candidato adverso con respaldo empírico de sus amplitudes, condicionado a su transferencia meteorológica.')
    p('Combinar los cambios también puede eliminar un extremo: el 28 de junio, el MP10 diario de Los Bronces pasa de 297 en BASE a 936 con u+ aislado, pero a 275 µg/m³ con la terna observada completa. Ese episodio deja de ser adverso respecto de BASE con esta combinación. No se generaliza esa disminución a otras ternas.','SmallES')
    head('Qué seleccionaba el estudio anterior')
    g=old[(old.pollutant=='MP10')&(old.metric=='media_periodo')]
    table(['Temporada','Receptor','Caso','BASE','Mayor media','Cambio'],[[r.season.title(),r.receptor,LABEL.get(r.scenario,r.scenario),fmt(r.base,3),fmt(r.value,3),fmt(r.delta_pct,1)+'%'] for r in g.itertuples()],[61,94,43,76,81,68])
    p('Unidades: µg/m³. Son medias ponderadas por las mismas horas válidas: 2151 en verano y 2205 en invierno. Las tres ternas nuevas solo se ensayaron en episodios; sus medias estacionales todavía no están calculadas.','SmallES')
    p('Los máximos diarios antiguos se compararon en 87 días de verano y 90 de invierno con 24 horas válidas comunes. Los 13 pares fecha/configuración seleccionados para diagnóstico generan 20 pares únicos al añadir BASE en las mismas fechas. Se reprodujeron 160 medias de los cuatro receptores desde archivos horarios con huellas verificadas.','SmallES')
    page();head('Regla simple para conservar la combinación observada')
    p('Para cada candidato principal se tomó la terna real más cercana a su desplazamiento, midiendo la distancia en unidades de las SD originales. Se conservaron juntos ΔT, Δu y Δv de un mismo día, sin escoger por separado tres extremos. La regla se congeló antes de calcular las nuevas concentraciones. La elección de los candidatos iniciales sí es retrospectiva.')
    table(['Temporada / código','Día observado','ΔT (°C)','Δu (m/s)','Δv (m/s)'],[[r['season'].title()+' / '+r['scenario'],r['source_day'],fmt(r['delta'][0],3),fmt(r['delta'][1],3),fmt(r['delta'][2],3)] for r in design['prototypes']],[128,105,63,63,64])
    fig('Ternas_observadas.png')
    p('Puntos: 31 días de verano y 29 de invierno con al menos 18 ternas horarias válidas. Cruces: desplazamientos aislados anteriores. Círculos verdes: días escogidos. La figura muestra u/v; la selección utiliza también T. No representa probabilidades.','SmallES')
    p('v- de verano (-4,531 m/s) queda fuera del rango diario observado de v (-1,255 a +14,235 m/s). Esto debilita su justificación como discrepancia diaria empírica, sin demostrar imposibilidad física. La comprobación conjunta adicional también muestra que la terna cero de BASE está fuera de la envolvente de la muestra: esa prueba no debe usarse para declarar que BASE es una atmósfera imposible.','SmallES')
    page();head('Mecanismos que explican los candidatos anteriores')
    fig('Dos_episodios_mecanismo.png')
    p('<b>Los Bronces, 28 de junio.</b> A la hora final 17 LST, u+ cambia 3,61 m/s y 94,8° de BASE a 0,31 m/s y 170,2°. La terna completa da 5,73 m/s y 194,2°. El gran aumento aislado coincide con cancelación de componentes, viento muy débil y transporte más favorable hacia el receptor. La comparación no separa causalmente cada cambio de AERMET.')
    p('<b>Sulfatos, 12 de enero.</b> A la hora final 20 local, v- gira el viento desde 250,7° a 332,4° y aumenta su rapidez de 2,12 a 4,32 m/s. La fracción de emisión situada en un sector de transporte de ±30° hacia Sulfatos pasa de 0,3% a 95,9%. Es evidencia geométrica compatible con el aumento; no es una descomposición de fuentes de AERMOD. La terna OBS_V da 1,55 m/s y 260,0° en esa hora.')
    p('Las emisiones se ponderaron como tasa LINE por área serializada. Se verificaron 12263 fuentes; los dos episodios tienen 6783 y 7321 fuentes con emisión positiva. La orientación no incluye relieve, recirculación, altura de pluma ni dilución con la distancia.','SmallES')
    page();head('Perfiles y condiciones de admisión')
    fig('Perfiles_horas_comparables.png')
    p('Los perfiles se comparan en las mismas horas. Se leen rapidez, dirección y temperatura de PFL, y L, u*, flujo de calor y altura de mezcla de SFC. L se usa como indicador de estabilidad calculada por AERMET, no como medición independiente. Los perfiles originales y los nuevos conservan el calendario y la máscara de datos faltantes.')
    p('La dirección se representa de forma continua al cruzar 0/360°, conservando etiquetas entre 0 y 360°. Ese ajuste es solo gráfico; evita dibujar un giro artificial en el cruce del norte.','SmallES')
    table(['Comprobación','Resultado y alcance'],[['Mismos datos de comparación','Emisiones, geometría, binario y receptores iguales. Horas y fechas civiles reconstruidas.'],['Amplitudes conjuntas','Tres ternas completas tomadas de días observados. No son extremos marginales mezclados.'],['Mecanismo de transporte','Rapidez, giros, perfiles y orientación respecto de las fuentes documentados en los episodios.'],['Representatividad espacial','Pendiente: trasladar discrepancias de la estación a la columna MMIF sigue siendo una hipótesis.'],['Coherencia dinámica','Pendiente: se prescribe ONSITE, sin reintegrar WRF ni cerrar balances de energía y momento.']],[135,388])
    p('Por ello se admite el contraste como <b>sensibilidad prescrita con respaldo empírico de las ternas</b>. No se le asigna la categoría de atmósfera físicamente validada. La conservación de una terna diaria tampoco conserva su secuencia horaria ni garantiza que el día de aplicación tenga el mismo régimen meteorológico.','SmallES')
    page();head('Qué ocurre en los casos retenidos')
    fig('Candidatos_retenidos.png')
    p('<b>Los Bronces, 16 de enero.</b> La terna U genera un máximo horario de 4144,086 µg/m³ entre las 00 y 01 locales, que aporta 20,06% de la suma diaria. En esa hora, el viento cambia de 3,21 m/s y 70,7° a 0,46 m/s y 179,5°, con L positivo en ambos casos. La fracción de emisión en un sector de transporte de ±30° hacia el receptor pasa de 2,0% a 36,5%. El 88,85% de la concentración integrada del caso nuevo ocurre en horas de L positivo. Esto es compatible con viento débil y transporte favorable, pero requiere contrastar la ocurrencia real de ese régimen; la terna por sí sola no lo valida.')
    p('<b>La Paloma, 26 de enero.</b> El máximo diario sube solo 0,087 µg/m³ (+1,24%). Entre 08 y 09 locales, el pico horario baja de 165,747 a 157,858 µg/m³; el incremento diario proviene del balance de las demás horas. Esa hora concentra 92,86% de la suma nueva. Es un aumento pequeño del indicador diario, no evidencia de un aumento general del impacto.')
    p('<b>Un máximo igual a BASE no implica ausencia de aumentos diarios.</b> El 9 de julio, la terna U de invierno aumenta Los Bronces de 128,227 a 311,070 µg/m³ (+142,59%). Aun así, ambos valores quedan por debajo del máximo BASE de 665,320 µg/m³ del 13 de septiembre.','BodyES')
    table(['Contraste MP10','BASE mismo día','Terna nueva','Cambio'],[['Los Bronces, 16/01',fmt(519.4008466666666,3),fmt(860.817035,3),'+65,73%'],['La Paloma, 26/01',fmt(6.9968375,3),fmt(7.083434166666667,3),'+1,24%'],['Los Bronces, 09/07',fmt(128.2268970833333,3),fmt(311.0704766666667,3),'+142,59%']],[175,116,116,116])
    page();head('Selección en los episodios comparables')
    p('Máximo de medias de 24 horas entre BASE y las ternas nuevas, usando solo las mismas cinco fechas civiles de verano o seis de invierno. Todas tienen 24 horas válidas. BASE permanece si ninguna terna supera su máximo. La fecha del máximo BASE puede diferir de la fecha seleccionada. Este conjunto de episodios contiene los máximos BASE conocidos; no contiene todos los posibles máximos de las ternas nuevas.')
    for pol in ['MP10','MP25']:
        p('MP10' if pol=='MP10' else 'MP2,5','HeadES')
        g=pick[pick.pollutant==pol]
        table(['Temporada','Receptor','Caso','Fecha','BASE máx.','Máximo','Δ %'],[[r.season.title(),r.receptor,LABEL.get(r.scenario,r.scenario),pd.Timestamp(r.day).strftime('%d/%m'),fmt(r.BASE_max,3),fmt(r.maximum,3),fmt(r.increase_pct,2)] for r in g.itertuples()],[59,87,54,48,76,76,63])
    p('Concentraciones en µg/m³. Las comparaciones pareadas de cada fecha, incluidos descensos y cambios muy pequeños, se conservan en Comparacion_cuatro_receptores.csv. Ningún máximo de esta tabla es una concentración ambiental total ni un estadístico anual.','SmallES')
    page();head('Qué puede defenderse y qué sigue pendiente')
    fig('Maximos_con_soporte_empirico.png')
    p('Figura: MP10. Un 0% significa que ninguna terna nueva supera el máximo BASE entre las fechas comparadas. No significa que todas sus diferencias diarias sean cero o negativas.','SmallES')
    p('<b>Selección terminada para este contraste.</b> Se entrega el máximo condicionado entre BASE y las ternas empíricas ensayadas por receptor y contaminante, con fechas y diferencias. También queda la selección numérica de las nueve configuraciones anteriores, que no se sustituye ni se borra. Un candidato puede ser útil como ensayo de estrés y tener respaldo insuficiente para llamarlo condición física adversa.')
    p('<b>Para la tesis:</b> “Se evaluó el conservadurismo de una referencia de dispersión mediante sensibilidad meteorológica y un contraste de episodios con perturbaciones conjuntas sustentadas en discrepancias observadas. La selección adversa se limita a las configuraciones y fechas ensayadas y está condicionada a la representatividad espacial y al operador ONSITE”.')
    p('<b>Siguiente decisión científica.</b> Antes de ampliar una terna a toda la temporada, comprobar su representatividad en los regímenes que generan los mayores aumentos. Para un máximo espacial, simular BASE y el candidato retenido en los 6295 receptores sobre idénticas fechas. Esa extensión no se ha ejecutado. Tampoco se ha cerrado la aplicabilidad de AERMOD en relieve complejo ni la equivalencia con el expediente CALPUFF.')
    p('Debe comprobarse el horario real de operación: el inventario actual reparte la masa diaria en 24 horas. Mantenerlo fijo es correcto para aislar la sensibilidad meteorológica, pero no demuestra que represente la condición operacional adversa. No se fabricó un calendario de emisiones.','SmallES')
    page();head('Verificación, fuentes y archivos para discutir')
    table(['Control','Resultado'],[['Nuevos casos LST','38 recibidos y verificados; 36480 valores horarios válidos.'],['Comparaciones civiles','32 casos-día, 1280 filas de receptor; 30720 valores horarios objetivo.'],['Calendario','5 fechas de verano y 6 de invierno; tres fechas LST auxiliares reconstruyen el cambio horario.'],['Productos nativos','266 productos originales rehasheados en archivos comprimidos y comparados con copias existentes.'],['Datos recuperados','18 archivos de emisiones de invierno recuperados de paquetes existentes con SHA-256 idéntico; disco D no disponible en esta sesión.'],['Integridad','Sin cambios en los estudios originales. Sin nuevas colas históricas ni duplicación de corridas.']],[150,373])
    p('Los resultados científicos se guardan en Seleccion_adversa_2026-11-04. El paquete incluye protocolo, selección de 32 indicadores anteriores, ranking completo, diagnóstico de soporte y perfiles, contraste nuevo, figuras y scripts. Las entradas voluminosas originales se identifican mediante rutas y huellas; el paquete de discusión no es una copia íntegra de todo el proyecto.','SmallES')
    p('<b>Fuentes técnicas.</b> EPA (2026), <i>AERMET User’s Guide</i>, versión 26135, §3.13, §5.6.2 y tablas C-4/C-5: interpretación de variables y tratamiento del viento débil. <link href="https://gaftp.epa.gov/Air/aqmg/SCRAM/models/met/aermet/aermet_userguide.pdf" color="#176e84">Documento oficial EPA</link>.','SmallES')
    p('SEA (2023), <i>Guía para el uso de modelos de calidad del aire en el SEIA</i>, segunda edición, §§3.2, 4.1, 4.3.2 y 5.9: representatividad, emisiones, período y receptores. <link href="https://www.sea.gob.cl/sites/default/files/imce/archivos/2023/02.FEB/28/Guia-Calidad-del-aire_V.4-final.pdf" color="#176e84">Documento oficial SEA</link>. Estos antecedentes no validan automáticamente la terna más cercana ni certifican cumplimiento del proyecto.','SmallES')
    p('Fuentes del proyecto: entregas auditadas Sensibilidad_estacional_2026-10-29 y Sensibilidad_conjunta_T_WS_2026-10-30; observaciones y discrepancias originales; dictamen del chat «Validar metodología de incertidumbre», 4 de noviembre. La nueva regla de cercanía y la selección de episodios son decisiones explícitas de este análisis.','SmallES')
    def footer(canvas,doc):
        canvas.setFont('Arial',8);canvas.setFillColor(colors.HexColor('#627681'));canvas.drawString(37,25,'Los Bronces | Sensibilidad y selección adversa condicionada');canvas.drawRightString(A4[0]-37,25,str(doc.page))
    dest=OUT/'Informe_seleccion_adversa.pdf'
    SimpleDocTemplate(str(dest),pagesize=A4,rightMargin=36,leftMargin=36,topMargin=35,bottomMargin=42,title='Seleccion adversa y contraste empirico',author='Daniel Castro').build(story,onFirstPage=footer,onLaterPages=footer)
    (OUT/'Sintesis_para_discutir.md').write_text('\n\n'.join(md),encoding='utf-8')
    putjson(OUT/'Informe_generado.json',dict(status='GENERATED_PENDING_VISUAL_QA',pdf=str(dest),sha256=sha(dest),figures=[str(p) for p in FIG.glob('*.png')]))
    print('Report generated',dest)
if __name__=='__main__':report()
