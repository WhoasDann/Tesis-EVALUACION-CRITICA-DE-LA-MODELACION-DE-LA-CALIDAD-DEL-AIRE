"""Scientific figures and discussion report from audited complete seasonal results."""
from pathlib import Path
import sys,json,html,zipfile
sys.path.insert(0,r'/archivo/usuario\Documents\Codex\2026-10-19\es\work\python_deps')
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
from campaign import ROOT,OUT,PILOT,read,save,sha,rec,now,SCENARIOS
NAMES=['Los Bronces','Sulfatos','Piedra Carvajal','La Paloma'];SEASONS=['VERANO','INVIERNO']
LABEL=dict(zip(SCENARIOS,['BASE','T-','T+','u-','u+','v-','v+']))
POL={'MP10':'MP10','MP25':'MP2,5'}
def num(x,n=3):return f'{x:.{n}f}'.replace('.',',')
def sig(x):return f'{x:.4g}'.replace('.',',') if pd.notna(x) else 'No definido'
def pct(x):return f'{x:+.2f}%'.replace('.',',') if pd.notna(x) else 'No definido'

def main():
 audit=read(OUT/'Auditoria_final.json');assert audit['status']=='PASSED'
 a=pd.read_csv(OUT/'Resumen_cuatro_receptores.csv');daily=pd.read_csv(OUT/'Medias_diarias_civiles.csv');daily=daily[daily.receptor.isin(NAMES)].copy();stats=pd.read_csv(OUT/'Tabla_variabilidad_BASE_civil.csv');ranges=pd.read_csv(OUT/'Tabla_rangos_sensibilidad.csv');diff=pd.read_csv(OUT/'Diferencias_pareadas_civiles_cuatro_receptores.csv')
 sources=[rec(OUT/n) for n in ['Auditoria_final.json','Resumen_cuatro_receptores.csv','Medias_diarias_civiles.csv','Tabla_variabilidad_BASE_civil.csv','Tabla_rangos_sensibilidad.csv','Diferencias_pareadas_civiles_cuatro_receptores.csv']]
 figures=OUT/'Figuras';figures.mkdir(exist_ok=True)
 plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white','axes.unicode_minus':False})
 def savefig(fig,name):
  fig.savefig(figures/(name+'.png'),dpi=180);fig.savefig(figures/(name+'.svg'));plt.close(fig)
 # Coverage uses civil dates, and flags the final summer17h fragment explicitly.
 fig,axes=plt.subplots(2,1,figsize=(11.5,4.3))
 for ax,s in zip(axes,SEASONS):
  g=daily[daily.season.eq(s)&daily.scenario.eq('BASE')&daily.pollutant.eq('MP10')&daily.receptor.eq('Los Bronces')].sort_values('day');dates=pd.to_datetime(g.day)
  ax.bar(dates,g.horas_validas,width=.85,color=['#E69F00' if not x else '#137B85' for x in g.complete_civil_day]);ax.axhline(24,color='#777777',lw=.6,ls='--');ax.set_ylim(0,27);ax.set_ylabel('Horas válidas');ax.set_title(s.title()+' | '+str(len(g))+' fechas disponibles',loc='left',fontsize=11)
  ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2));ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m'));ax.grid(axis='y',alpha=.18)
 fig.tight_layout();savefig(fig,'Cobertura_civil')
 for pol in POL:
  fig,axes=plt.subplots(4,2,figsize=(10.2,10.7))
  for row,name in enumerate(NAMES):
   for col,s in enumerate(SEASONS):
    ax=axes[row,col];g=daily[daily.season.eq(s)&daily.pollutant.eq(pol)&daily.receptor.eq(name)];p=g.pivot(index='day',columns='scenario',values='media_horas_validas_ug_m3').sort_index();dates=pd.to_datetime(p.index)
    ax.fill_between(dates,p[SCENARIOS].min(axis=1),p[SCENARIOS].max(axis=1),color='#D2E5E8',label='Rango de los 7 casos')
    ax.plot(dates,p.BASE,color='#124E72',lw=1.1,marker='.',ms=3,label='BASE')
    if s=='VERANO':ax.plot(dates[-1],p.BASE.iloc[-1],marker='^',ms=6,color='#CA7900',ls='None')
    ax.set_title(name+' | '+s.title(),fontsize=11);ax.set_ylabel('Media (µg/m³)');ax.set_ylim(bottom=0);ax.grid(alpha=.2)
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=3));ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m'));ax.tick_params(axis='x',rotation=35,labelsize=8)
  handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='upper center',ncol=2,bbox_to_anchor=(.5,.955),frameon=False)
  fig.suptitle('Variabilidad diaria y rango de sensibilidad | '+POL[pol],fontsize=15,y=.99)
  fig.text(.04,.012,'Cada panel usa su propia escala. Días civiles en invierno. Triángulo: último día de verano, sólo 17 h.\nLa franja muestra escenarios prescritos; no es un intervalo de confianza. Concentraciones: aporte modelado.',fontsize=9)
  fig.tight_layout(rect=[0,.055,1,.925]);savefig(fig,'Series_y_rango_'+pol)
  fig,axes=plt.subplots(1,2,figsize=(11.8,4.3))
  for ax,s in zip(axes,SEASONS):
   matrix=a[a.season.eq(s)&a.pollutant.eq(pol)].pivot(index='receptor',columns='scenario',values='delta_pct').reindex(index=NAMES,columns=SCENARIOS[1:]);vmax=max(abs(matrix.to_numpy()).max(),1)
   im=ax.imshow(matrix,cmap='RdBu_r',vmin=-vmax,vmax=vmax,aspect='auto');ax.set_xticks(range(6),[LABEL[x] for x in SCENARIOS[1:]]);ax.set_yticks(range(4),NAMES);ax.set_title(s.title())
   for yy in range(4):
    for xx in range(6):
     v=matrix.iloc[yy,xx];ax.text(xx,yy,f'{v:+.1f}',ha='center',va='center',fontsize=9,color='white' if abs(v)>.57*vmax else '#17202A')
   fig.colorbar(im,ax=ax,fraction=.045,pad=.03,label='Cambio (%)')
  fig.suptitle('Cambio de la media de temporada respecto de BASE | '+POL[pol],fontsize=14);fig.tight_layout(rect=[0,.015,1,.93]);savefig(fig,'Cambios_porcentuales_'+pol)
  fig,axes=plt.subplots(4,2,figsize=(10.2,10.3))
  for row,name in enumerate(NAMES):
   for col,s in enumerate(SEASONS):
    ax=axes[row,col];g=diff[diff.season.eq(s)&diff.pollutant.eq(pol)&diff.receptor.eq(name)]
    values=[g.loc[g.scenario.eq(k),'delta_ug_m3'].to_numpy() for k in SCENARIOS[1:]]
    ax.boxplot(values,tick_labels=[LABEL[k] for k in SCENARIOS[1:]],whis=(5,95),patch_artist=True,boxprops={'facecolor':'#BCDCE1'},medianprops={'color':'#163D55','linewidth':1.3},flierprops={'marker':'.','markersize':2,'markeredgecolor':'#AB5757'})
    ax.axhline(0,color='#777777',lw=.8);ax.set_title(name+' | '+s.title(),fontsize=11);ax.set_ylabel('Caso - BASE (µg/m³)');ax.grid(axis='y',alpha=.18)
  fig.suptitle('Distribución de las diferencias diarias pareadas | '+POL[pol],fontsize=14,y=.99)
  fig.text(.035,.01,'Verano: 89 días completos; invierno: 92 días civiles. Caja: P25-P75; línea: mediana; bigotes: P5-P95.\nPuntos: diferencias fuera de los bigotes. Son contrastes entre escenarios, no errores observados ni incertidumbre.',fontsize=9)
  fig.tight_layout(rect=[0,.06,1,.955]);savefig(fig,'Diferencias_diarias_'+pol)
 # Compact results used both in PDF and Markdown.
 def get(s,name,case='BASE',pol='MP10'):
  return a[a.season.eq(s)&a.receptor.eq(name)&a.scenario.eq(case)&a.pollutant.eq(pol)].iloc[0]
 summary=[
  'Se completaron y auditaron 2.548 casos diarios: 90 fechas de verano y 92 de invierno, siete configuraciones, MP10 y MP2,5. Los cuatro receptores sensibles están incluidos en un panel fijo de 40 nodos. Se verificaron 2.441.600 valores horarios, de los cuales 2.439.360 son válidos y 2.240 corresponden a horas enmascaradas.',
  'La ejecución nueva y su recepción demoraron '+num(audit['hours_from_first_new_case_to_final_reception'],2)+' horas, desde la primera corrida nueva hasta el último recibo. Se reutilizaron 406 casos equivalentes y se ejecutaron 2.142 nuevos; ocho pruebas Linux-Windows adicionales coincidieron exactamente. La preparación y este informe no están incluidos en ese tiempo.',
  'En Los Bronces, la media BASE de MP10 es '+num(get('VERANO','Los Bronces').mean_ug_m3)+' µg/m³ en verano y '+num(get('INVIERNO','Los Bronces').mean_ug_m3)+' µg/m³ en invierno. Con u+, cambia a '+num(get('VERANO','Los Bronces','U_PLUS').mean_ug_m3)+' ('+pct(get('VERANO','Los Bronces','U_PLUS').delta_pct)+') y '+num(get('INVIERNO','Los Bronces','U_PLUS').mean_ug_m3)+' ('+pct(get('INVIERNO','Los Bronces','U_PLUS').delta_pct)+'), respectivamente.',
  'En verano, v- eleva la media de MP10 en Sulfatos de '+num(get('VERANO','Sulfatos').mean_ug_m3)+' a '+num(get('VERANO','Sulfatos','V_MINUS').mean_ug_m3)+' µg/m³ ('+pct(get('VERANO','Sulfatos','V_MINUS').delta_pct)+') y en La Paloma de '+num(get('VERANO','La Paloma').mean_ug_m3)+' a '+num(get('VERANO','La Paloma','V_MINUS').mean_ug_m3)+' ('+pct(get('VERANO','La Paloma','V_MINUS').delta_pct)+'). Ese mismo cambio reduce Los Bronces: no existe una dirección de cambio desfavorable común a todos los puntos y ambas temporadas.',
  'En el invierno estudiado, u+ produce la mayor media de MP10 entre las siete configuraciones en los cuatro receptores. Es un resultado de este conjunto de ensayos; no demuestra que sea el peor estado meteorológico posible ni el máximo para cada día.',
  'El diseño permite presentar variabilidad temporal BASE y sensibilidad ante cambios meteorológicos prescritos. No estima probabilidades, intervalos de confianza, concentraciones ambientales totales ni cumplimiento normativo.'
 ]
 method=[
  'BASE mantiene la meteorología de la cadena WRF - MMIF - AERMET y la configuración de AERMOD. Para cada variante se modifica el archivo ONSITE serializado a la salida de MMIF, se vuelve a ejecutar AERMET y luego AERMOD. No se vuelve a integrar WRF ni se afirma equivalencia con modificar wrfout y regenerar MMIF.',
  'La escala a_X es la desviación estándar muestral entre discrepancias medias diarias Obs-WRF del período de ajuste. Cada día requiere al menos 18 ternas horarias válidas de T, u y v. Se usaron 31 días de verano (21-dic-2016 a 20-ene-2017) y 29 de invierno (21-jun a 21-jul-2017). Las amplitudes se fijaron antes de estas concentraciones; no se estiman a partir de los resultados AERMOD.',
  'Se aplica un desplazamiento persistente +a_X o -a_X durante la temporada, cambiando sólo T, u o v por caso. No se añade sesgo medio ni residuo sorteado y no se usan las 1.024 trayectorias Ridge. u es la componente hacia el este y v hacia el norte; variar una componente puede cambiar rapidez y dirección simultáneamente.',
  'Perfil vertical: X_caso(z,t) = X_BASE(z,t) + signo × a_X × w(z,t). Con s = limitar[(z-z_ref)/(H_BASE(t)-z_ref),0,1], se usa w = 1-3s²+2s³. Hay amplitud completa hasta z_ref (2 m para T, 10 m para viento) y cero por encima de la PBL BASE. La amplitud superficial es constante; la atenuación cambia con la PBL horaria.',
  'Se recalculan rapidez y dirección desde u/v, y DT01 desde temperaturas redondeadas. Se conservan RH, presión, flujos, UST, MHGT y archivos auxiliares BASE según el diseño congelado. AERMET regenera sus salidas dependientes. La admisibilidad numérica no demuestra equilibrio dinámico o termodinámico.',
  'La transferencia de amplitudes desde la estación Piedra Carvajal a la columna MMIF I43/J44 es una hipótesis espacial. En cada contraste pareado se mantienen las mismas 12.263 fuentes, emisiones horarias de esa fecha y 40 receptores. MP10 y MP2,5 se ejecutan por separado; no se obtienen multiplicando una tabla de concentración por un factor.'
 ]
 limits=[
  'La dispersión entre días BASE combina cambios meteorológicos y cambios en las emisiones. El contraste de configuraciones del mismo día mantiene las emisiones iguales y muestra la respuesta al cambio meteorológico impuesto. Una comparación entre temporadas tampoco separa por sí sola meteorología y emisiones.',
  'La SD diaria, los percentiles de concentración y el rango de escenarios tienen significados distintos. P90 describe la distribución de días simulados; no es un intervalo de confianza. Un desplazamiento de una SD meteorológica no significa que las concentraciones queden dentro de un 68% de probabilidad.',
  'Los ensayos cambian una componente por vez. No cuantifican interacciones simultáneas entre T, u y v, ni una distribución conjunta de errores. Una sensibilidad térmica pequeña bajo auxiliares BASE fijos no demuestra poca importancia de todos los procesos térmicos.',
  'Los resultados cubren las ventanas disponibles de 2016-2017, no otros años. El último día de verano sólo tiene 17 horas. Los cuatro puntos sensibles sí están calculados, pero el panel no representa máximos de la malla completa de 6.295 receptores ni de toda la superficie de un glaciar.',
  'Se trata de aportes del inventario modelado, sin añadir una concentración de fondo ni contrastar estas concentraciones con observaciones de calidad del aire. Los cambios porcentuales se omiten si BASE es cero. Un porcentaje muy alto desde un BASE pequeño debe leerse junto con el cambio absoluto.',
  'El máximo entre las siete configuraciones es el máximo ensayado. Su aceptación como escenario regulatorio exige justificación adicional y revisión específica; aquí no se establece cumplimiento de una norma ni un peor caso legal.'
 ]
 # PDF: fixed page structure with readable figures and tables.
 pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'));pdfmetrics.registerFont(TTFont('ArialB','C:/Windows/Fonts/arialbd.ttf'));pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='ArialB')
 navy=colors.HexColor('#163548');teal=colors.HexColor('#137B85')
 styles={k:ParagraphStyle(k,fontName='ArialB' if k in ['title','h','sub','head'] else 'Arial',fontSize=size,leading=leading,spaceAfter=after,textColor=colors.white if k=='head' else navy) for k,size,leading,after in [('title',23,28,15),('h',16,20,12),('sub',11,15,7),('body',9.5,13,8),('small',8.2,11,6),('cell',8,10.5,0),('head',8,10.5,0)]}
 story=[];W=507
 def p(text,style='body'):story.append(Paragraph(html.escape(str(text)),styles[style]))
 def page(title):
  if story:story.append(PageBreak())
  p(title,'h')
 def table(data,widths=None):
  cells=[[Paragraph(html.escape(str(v)),styles['head' if i==0 else 'cell']) for v in row] for i,row in enumerate(data)];t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),teal),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#EDF3F5')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.extend([t,Spacer(1,9)])
 def img(name,width=W):
  from PIL import Image as PILImage
  file=figures/(name+'.png');im=PILImage.open(file);story.append(Image(str(file),width=width,height=width*im.height/im.width));story.append(Spacer(1,7))
 def cases_table(season,pol):
  matrix=a[a.season.eq(season)&a.pollutant.eq(pol)].pivot(index='receptor',columns='scenario',values='mean_ug_m3').reindex(index=NAMES,columns=SCENARIOS)
  return [['Receptor']+[LABEL[k] for k in SCENARIOS]]+[[n]+[sig(matrix.loc[n,k]) for k in SCENARIOS] for n in NAMES]
 def variability_table(pol):
  result=[['Temporada / receptor','Media diaria','Mediana','SD días','P90','Máximo / fecha']]
  for s in SEASONS:
   for n in NAMES:
    r=stats[stats.season.eq(s)&stats.pollutant.eq(pol)&stats.receptor.eq(n)].iloc[0];result.append([s.title()+' / '+n,sig(r.mean_daily),sig(r['median']),sig(r.sd_days),sig(r.P90),sig(r.maximum)+' / '+r.date_max[8:10]+'-'+r.date_max[5:7]])
  return result
 p('Variabilidad y sensibilidad\nde la dispersión','title');p('Los Bronces Integrado | Temporadas 2016-2017','sub');p('Resultados auditados al 30 de octubre de 2026','small')
 for text in summary:p(text)
 table([['Cobertura','Verano','Invierno'],['Fechas de ejecución','90','92'],['Horas objetivo / válidas','2.153 / 2.151','2.207 / 2.205'],['Días para estadística diaria','89 completos + 1 fragmento separado','92 días civiles'],['Configuraciones × contaminantes','7 × 2','7 × 2']],[205,145,157])
 page('1. Qué se hizo y qué significa')
 for text in method:p(text)
 table([['Amplitud superficial','Verano','Invierno'],['T (°C)','±0,953243','±1,585853'],['u (m/s)','±1,779851','±3,541337'],['v (m/s)','±4,531311','±6,724597']],[205,145,157])
 p('El método responde primero a una pregunta de sensibilidad. Su sencillez permite seguir cada cambio, pero no elimina las hipótesis de escala temporal, transferencia espacial y atenuación vertical.','small')
 page('2. Cobertura y promedios comparables');img('Cobertura_civil')
 for text in [
  'Verano: 21-dic-2016 a 20-mar-2017. Faltan una hora del 3-feb y una del 3-mar; el 20-mar termina tras 17 horas. La media estacional usa las 2.151 horas válidas, incluida esa fracción final. La mediana, SD, percentiles y máximos entre días usan sólo los 89 días completos; las fechas con 23 horas válidas por un faltante conservan ese denominador.',
  'Invierno: 21-jun a 20-sep-2017. AERMOD opera con LST fijo UTC-4. Los resultados horarios se convierten al calendario civil de Chile antes de describir días: el 13-ago tiene 23 horas por el cambio de horario; el 14-ago tiene 22 horas válidas de 24 posiciones; el 20-sep se recompone con horas de dos archivos LST para recuperar sus 24 horas civiles.',
  'Una hora faltante no es una concentración cero. Se conservó el cero interno de AERMOD para comprobar la ejecución, pero se enmascaró antes de calcular estadísticas. El patrón de horas válidas coincide en BASE y en las seis variantes.',
  'Media de temporada = suma de concentraciones horarias válidas / número de horas válidas. Es una media ponderada por horas. Media diaria de la tabla descriptiva = media simple entre promedios diarios completos. No tienen por qué coincidir cuando hay días con diferente cobertura.',
  'Cambio pareado = concentración del caso - concentración BASE del mismo receptor y fecha. El cambio porcentual divide esa diferencia por BASE y sólo se define cuando BASE > 0. Las figuras estacionales comparan las mismas 2.151 o 2.205 horas en todas las configuraciones.'
 ]:p(text)
 for pol in POL:
  page('3. Evolución diaria y sensibilidad - '+POL[pol]);img('Series_y_rango_'+pol)
  p('La línea muestra BASE y la franja el rango diario entre BASE y las seis perturbaciones. La franja no representa probabilidad. Los picos muestran la importancia de conservar fechas y receptores al comparar; no identifican por sí solos el mecanismo físico de un episodio.','small')
 for pol in POL:
  page('4. Medias de temporada y cambios - '+POL[pol])
  for s in SEASONS:p(s.title()+' | Concentración media (µg/m³)','sub');table(cases_table(s,pol),[115]+[56]*7)
  img('Cambios_porcentuales_'+pol)
  p('Los porcentajes usan las medias estacionales ponderadas por horas. Cada mapa utiliza su propia escala de color; los valores anotados permiten comparar. Leer siempre los porcentajes junto con los aportes absolutos de las tablas.','small')
 page('5. Estadísticas de la variabilidad BASE')
 for pol in POL:p(POL[pol]+' | Concentraciones diarias en µg/m³','sub');table(variability_table(pol),[166,61,59,57,57,107])
 p('Verano: 89 días completos; invierno: 92 días civiles. SD muestral entre días; P90 descriptivo de la serie simulada. La media diaria de estas tablas no sustituye la media estacional ponderada. Los cuartiles, mínimos y días con cero están disponibles en la tabla CSV complementaria.','small')
 for pol in POL:
  page('6. Diferencias pareadas entre días - '+POL[pol]);img('Diferencias_diarias_'+pol)
  p('Cada caja contiene diferencias del mismo día y receptor respecto de BASE. El ancho de su distribución describe cómo cambia la respuesta entre días. Los puntos extremos son episodios simulados, no estimaciones de error del modelo.','small')
 page('7. Episodios y cambios respecto del piloto')
 p('Aporte de los días dominantes en BASE de invierno','sub')
 ep=[['Receptor','Día dominante','Día / suma total (%)','5 días / suma total (%)']]
 for n in NAMES:
  r=stats[stats.season.eq('INVIERNO')&stats.pollutant.eq('MP10')&stats.receptor.eq(n)].iloc[0];ep.append([n,r.dominant_sum_day,num(r.top1_share_pct,2),num(r.top5_share_pct,2)])
 table(ep,[150,100,125,132]);p('Las proporciones se calculan sobre la suma horaria BASE de los 92 días civiles de invierno. Ayudan a identificar episodios que merecen inspección meteorológica y de emisiones; no atribuyen causalidad.','small')
 prior=pd.read_csv(PILOT/'Resumen_cuatro_receptores.csv');comparison=[['Temporada / receptor','BASE piloto15d','BASE temporada','Cambio u+ piloto / temporada']]
 for s in SEASONS:
  for n in NAMES:
   old=prior[prior.season.eq(s)&prior.receptor.eq(n)&prior.pollutant.eq('MP10')];b=old[old.scenario.eq('BASE')].iloc[0];u=old[old.scenario.eq('U_PLUS')].iloc[0];comparison.append([s.title()+' / '+n,sig(b.mean_ug_m3),sig(get(s,n).mean_ug_m3),pct(u.delta_pct)+' / '+pct(get(s,n,'U_PLUS').delta_pct)])
 table(comparison,[173,95,99,140]);p('Esta comparación no es un efecto causal de ampliar días: cambia el conjunto temporal. Sirve para mostrar cuánto dependía la conclusión del piloto de sus fechas. El 1-feb se recalculó porque ampliar la perturbación a días precedentes cambió algunas alturas de mezcla SFC de primeras horas en las variantes de viento; los otros 406 casos se reutilizaron sólo después de comprobar equivalencia.','small')
 page('8. Alcance, respaldo y discusión con el profesor')
 for text in limits:p(text)
 p('Por qué este diseño sencillo','sub')
 p('La revisión previa de 28 documentos distingue estadística descriptiva, sensibilidad e incertidumbre. Villalón (2025, D27, PDF40) usa media y SD; Pachón et al. (2024, DOI10.5194/gmd-17-7467-2024) comparan configuraciones con mediana y dispersión; Faulkner et al. (2008, DOI10.3155/1047-3289.58.10.1288, métodos p.1290) estudian sensibilidad de AERMOD cambiando una entrada por vez. Estos antecedentes apoyan la lógica de comparación; no validan nuestras amplitudes ni el operador cordillerano.','small')
 p('Los siete casos y la escala SD diaria son una adaptación para esta tesis, no una receta atribuida a Huneeus ni una aprobación académica obtenida. La revisión previa conserva las páginas consultadas y sus límites; para Faulkner no se atribuye una lectura completa no disponible.','small')
 p('Propuesta para la reunión','sub')
 p('1. Acordar que el objetivo principal sea variabilidad y sensibilidad. 2. Revisar amplitudes SD y transferencia a ONSITE/PBL. 3. Seleccionar episodios por su aporte acumulado y examinar meteorología y emisiones. 4. Decidir si es necesaria la malla completa para conclusiones espaciales. 5. Si se exige incertidumbre probabilística, definir una validación adicional y no reinterpretar estas franjas como intervalos.','small')
 p('Trazabilidad','sub');p('Auditoria_final.json verifica productos nativos comprimidos, CSV horarios, promedios diarios y estacionales, 92 días civiles de invierno y ocho pruebas Linux-Windows. Diseno.json fija las hipótesis; Recibos/ conserva la evidencia por caso. Revisión bibliográfica: ../Revision_Huneeus_2026-10-28/Revision_Huneeus_y_propuesta_metodologica.pdf. Las corridas finalizaron sin iniciar nuevas colas BASE antiguas.','small')
 def footer(canvas,doc):
  canvas.setStrokeColor(teal);canvas.line(44,37,551,37);canvas.setFont('Arial',8);canvas.setFillColor(navy);canvas.drawString(44,24,'Los Bronces | Sensibilidad estacional | 2.548 casos auditados');canvas.drawRightString(551,24,str(doc.page))
 pdf=OUT/'Informe_sensibilidad_estacional_completo.pdf'
 SimpleDocTemplate(str(pdf),pagesize=(595,842),rightMargin=44,leftMargin=44,topMargin=38,bottomMargin=48,title='Variabilidad y sensibilidad estacional - Los Bronces',author='Daniel Castro - resultados de simulaciones').build(story,onFirstPage=footer,onLaterPages=footer)
 def mdtable(data):return '\n'.join(['| '+' | '.join(data[0])+' |','| '+' | '.join(['---']*len(data[0]))+' |']+['| '+' | '.join(map(str,row))+' |' for row in data[1:]])
 md=['# Resultados estacionales completos para discutir','',*sum(([t,''] for t in summary),[]),'## Método','',*sum(([t,''] for t in method),[]),'## Medias de temporada','']
 for pol in POL:
  for s in SEASONS:md += ['### '+s.title()+' / '+POL[pol],'',mdtable(cases_table(s,pol)),'']
 md += ['## Variabilidad diaria BASE','']
 for pol in POL:md += ['### '+POL[pol],'',mdtable(variability_table(pol)),'']
 md += ['## Límites y discusión','',*sum(([t,''] for t in limits),[]),'Estadística diaria: 89 días completos de verano y92días civiles de invierno. El20-mar tiene17horas: se incluye en la media del período y se excluye de la distribución diaria.','',mdtable(ep),'']
 (OUT/'Sintesis_para_discutir.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
 assert all(sha(x['path'])==x['sha256'] for x in sources)
 reader=PdfReader(pdf);save(OUT/'Informe_generado.json',dict(created_utc=now(),pdf=rec(pdf),pages=len(reader.pages),sources=sources,figures=[rec(p) for p in sorted(figures.glob('*.png'))],script=rec(__file__)))
 print('PDF pages',len(reader.pages),flush=True)
 for i,page in enumerate(reader.pages):print(i+1,len(page.extract_text()),page.extract_text().splitlines()[0],flush=True)

if __name__=='__main__':main()
