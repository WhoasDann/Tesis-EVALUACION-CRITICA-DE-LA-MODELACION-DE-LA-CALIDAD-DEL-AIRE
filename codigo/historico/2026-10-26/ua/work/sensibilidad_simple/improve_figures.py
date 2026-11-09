from pathlib import Path
p=Path('work/sensibilidad_simple/plot_results.py');s=p.read_text(encoding='utf-8')
start=s.index(" fig,axes=plt.subplots(2,2,figsize=(13.5,8))")
end=s.index(" assert all(sha(x['path'])",start)
new=""" for pol in ['MP10','MP25']:
  fig,axes=plt.subplots(4,2,figsize=(12,12))
  for row,name in enumerate(POINTS):
   for col,season in enumerate(['VERANO','INVIERNO']):
    ax=axes[row,col]
    g=daily[daily.season.eq(season)&daily.pollutant.eq(pol)&daily.receptor.eq(name)].sort_values('day')
    dates=pd.date_range(g.day.min(),g.day.max())
    vals=g.set_index(pd.to_datetime(g.day)).BASE.reindex(dates)
    ax.plot(range(len(dates)),vals,marker='o',color='#21618c',markersize=4)
    ax.set_xticks(range(len(dates)),dates.strftime('%d-%b'),rotation=45,ha='right',fontsize=8)
    ax.set_title(f'{name} · {season.title()} · {len(g)} días completos',fontsize=10)
    ax.set_ylabel('Media (µg/m³)');ax.grid(alpha=.22)
    if vals.dropna().eq(0).all():
     ax.text(.5,.75,'Valores nulos a la precisión de salida',transform=ax.transAxes,ha='center',fontsize=8)
  fig.suptitle('Variabilidad diaria BASE · '+('MP2,5' if pol=='MP25' else 'MP10'),fontsize=16,y=.995)
  fig.text(.02,.012,'Escalas verticales propias de cada receptor. Los huecos corresponden a comparaciones todavía incompletas.\\nAporte modelado, medias de horas válidas; período ilustrativo, sin representatividad estacional.',fontsize=10)
  fig.tight_layout(rect=[0,.055,1,.97])
  fig.savefig(figs/('Variabilidad_diaria_BASE.png' if pol=='MP10' else 'Variabilidad_diaria_BASE_MP25.png'),dpi=170);plt.close(fig)
"""
s=s[:start]+new+s[end:];p.write_text(s,encoding='utf-8')

