"""Comparación cruzada: mismas coordenadas para fuentes50/25 y malla125/62,5."""
from pathlib import Path
from datetime import datetime
import json
import sys
import importlib.util
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1] if Path(__file__).parent.name=='work' else Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'outputs/Biblioteca_Tesis'))
from tesis.comun import guardar_json,sha256
from tesis.convergencia import clasificar_cambio
OUT=ROOT/'outputs/Convergencia_conjunta_2026-10-16'
FAIL={'REQUIERE_REFINAMIENTO','DIFERENCIA_ABSOLUTA_RELEVANTE'}
LABELS={'PCAR':'Piedra Carvajal','LBCEN':'Los Bronces, estación','MINA_envolvente_red':'Los Bronces, máximo MINA',
    'SULF':'Sulfatos','PALP':'La Paloma, punto','Glaciar Olivares Alfa Sur':'Olivares Alfa Sur',
    'Glaciar Paloma Oeste':'Paloma Oeste','Glaciar Paloma Este':'Paloma Este','Glaciar Paloma Norte':'Paloma Norte','GENERAL':'Máximo general de puntos evaluados'}
KEYS=['grupo','x_m','y_m','dia']
DAYS=set(pd.date_range('2016-12-21',periods=7).strftime('%Y-%m-%d'))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def verify(entries):
    for e in entries:
        if sha256(e['path'])!=e['sha256']:raise ValueError('Archivo cambió: '+e['path'])
def validate(data):
    if data.empty or data.duplicated(KEYS).any():raise ValueError('Medias vacías o duplicadas')
    if not data.horas.eq(24).all() or set(data.dia)!=DAYS:raise ValueError('Horas o días incompletos')
    if not data.groupby(KEYS[:-1]).size().eq(7).all():raise ValueError('Cobertura desigual por punto')
    if not np.isfinite(data.media_24h_ug_m3).all() or data.media_24h_ug_m3.lt(0).any():raise ValueError('Concentración inválida')
def compare(a,b,pol,criteria,kind):
    validate(a);validate(b)
    groups=set(a.grupo)&set(LABELS)
    if groups!=set(b.grupo)&set(LABELS):raise ValueError('Ámbitos distintos')
    if kind=='fuentes' and set(map(tuple,a[KEYS].to_numpy()))!=set(map(tuple,b[KEYS].to_numpy())):
        raise ValueError('La comparación de fuentes exige los mismos puntos/días')
    if kind=='malla' and not set(map(tuple,a[KEYS].to_numpy()))<=set(map(tuple,b[KEYS].to_numpy())):
        raise ValueError('Malla no anidada')
    rows=[];weekly=[]
    for group in sorted(groups):
        aa=a.loc[a.grupo.eq(group)];bb=b.loc[b.grupo.eq(group)]
        for day in sorted(DAYS):
            ad=aa.loc[aa.dia.eq(day)];bd=bb.loc[bb.dia.eq(day)]
            ar=ad.loc[ad.media_24h_ug_m3.idxmax()];br=bd.loc[bd.media_24h_ug_m3.idxmax()]
            if kind=='malla' and br.media_24h_ug_m3<ar.media_24h_ug_m3:raise ValueError('Disminuyó máximo en unión anidada')
            change=clasificar_cambio(float(ar.media_24h_ug_m3),float(br.media_24h_ug_m3),criteria['relativo'],criteria['absoluto_ug_m3'])
            rows.append(dict(contaminante=pol,grupo=group,dia=day,base_ug_m3=ar.media_24h_ug_m3,refinado_ug_m3=br.media_24h_ug_m3,
                x_base_m=ar.x_m,y_base_m=ar.y_m,x_refinado_m=br.x_m,y_refinado_m=br.y_m,**change))
        ar=aa.loc[aa.media_24h_ug_m3.idxmax()];br=bb.loc[bb.media_24h_ug_m3.idxmax()]
        weekly.append(dict(contaminante=pol,grupo=group,base_max24h=ar.media_24h_ug_m3,refinado_max24h=br.media_24h_ug_m3,
            base_max_media168h=aa.groupby(['x_m','y_m']).media_24h_ug_m3.mean().max(),
            refinado_max_media168h=bb.groupby(['x_m','y_m']).media_24h_ug_m3.mean().max(),
            dia_base=ar.dia,dia_refinado=br.dia,x_refinado_m=br.x_m,y_refinado_m=br.y_m))
    return pd.DataFrame(rows),pd.DataFrame(weekly)
def pointwise(a,b,pol,criteria):
    aa=a.loc[a.grupo.eq('GENERAL')];bb=b.loc[b.grupo.eq('GENERAL')]
    joined=aa.merge(bb,on=KEYS,validate='one_to_one',suffixes=('_50','_25'))
    if len(joined)!=len(aa) or len(joined)!=len(bb):raise ValueError('Puntos no coinciden')
    rows=[]
    for r in joined.itertuples():
        change=clasificar_cambio(r.media_24h_ug_m3_50,r.media_24h_ug_m3_25,criteria['relativo'],criteria['absoluto_ug_m3'])
        rows.append(dict(contaminante=pol,x_m=r.x_m,y_m=r.y_m,dia=r.dia,fuentes50_ug_m3=r.media_24h_ug_m3_50,
            fuentes25_ug_m3=r.media_24h_ug_m3_25,**change))
    return pd.DataFrame(rows)
def main():
    verify(read(OUT/'Entrega.json')['archivos']);plan=read(OUT/'Plan.json')
    members125=pd.read_csv(OUT/'Comunes/membresia125.csv')
    frames={};evidence=[]
    for tag in ('F50','F25'):
        folder=OUT/tag;status=read(folder/'Estado.json')
        if status['estado']!='UNION_COMPLETA':raise ValueError('Falta cerrar '+tag)
        verify(status['archivos']);verify(read(folder/'Entrega.json')['archivos'])
        spec=importlib.util.spec_from_file_location('run_'+tag,folder/'ejecutar.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        blocks=read(folder/'Corridas_diarias.json')
        if set(blocks)!={f'{p}_{d}' for p in ('MP10','MP25') for d in range(21,28)}:raise ValueError('Bloques incompletos')
        for e in blocks.values():
            verify(e['archivos']);m.verify_inputs(e);m.native_ok(Path(e['carpeta']),'AERMOD')
            if (e['qa']['fuentes'],e['qa']['receptores'],e['qa']['horas'],e['qa']['valores'])!=(plan['fuentes'][tag],4691,24,112584):
                raise ValueError('Dimensiones QA distintas')
        for pol in ('MP10','MP25'):
            data=pd.read_csv(folder/('Medias_diarias_union_'+pol+'.csv'));validate(data)
            expected=pd.concat([pd.read_csv(folder/'Referencias'/pol/'Medias_diarias.csv')]+[
                pd.read_csv(Path(blocks[f'{pol}_{d}']['carpeta'])/'Medias_diarias.csv') for d in range(21,28)],ignore_index=True)
            merged=data.merge(expected,on=KEYS,validate='one_to_one',suffixes=('_saved','_rebuilt'))
            if len(merged)!=len(data) or len(data)!=len(expected) or not np.allclose(merged.media_24h_ug_m3_saved,merged.media_24h_ug_m3_rebuilt,rtol=0,atol=1e-12):
                raise ValueError('Unión no coincide con bloques')
            if len(data[['x_m','y_m']].drop_duplicates())!=6295:raise ValueError('Unión incorrecta')
            frames[tag,pol]=data
        evidence.extend(status['archivos'])
    source_daily=[];source_week=[];grid_daily=[];point=[]
    for pol in ('MP10','MP25'):
        a=frames['F50',pol];b=frames['F25',pol]
        d,w=compare(a,b,pol,plan['criterios'],'fuentes');source_daily.append(d);source_week.append(w)
        point.append(pointwise(a,b,pol,plan['criterios']))
        for tag in ('F50','F25'):
            fine=frames[tag,pol]
            coarse=members125.merge(fine,on=['grupo','x_m','y_m'],validate='one_to_many')
            if len(coarse[['x_m','y_m']].drop_duplicates())!=2727:raise ValueError('Submalla125 incompleta')
            d,_=compare(coarse,fine,pol,plan['criterios'],'malla');d['fuentes']=tag;grid_daily.append(d)
    sd=pd.concat(source_daily,ignore_index=True);sw=pd.concat(source_week,ignore_index=True)
    gd=pd.concat(grid_daily,ignore_index=True);pw=pd.concat(point,ignore_index=True)
    if (len(sd),len(sw),len(gd),len(pw))!=(140,20,280,88130):raise ValueError('Contrastes incompletos')
    saved=[]
    for name,data in [('Fuentes50_vs25_diario.csv',sd),('Fuentes50_vs25_semanal.csv',sw),('Malla125_vs625_diario.csv',gd),('Diagnostico_puntual.csv',pw)]:
        p=OUT/name;data.to_csv(p,index=False,encoding='utf-8-sig');saved.append(p)
    local=sd.loc[sd.grupo.ne('GENERAL')];sf=local.estado.isin(FAIL)
    counts={tag:int(gd.loc[gd.fuentes.eq(tag)&gd.grupo.isin(plan['zonas']),'estado'].isin(FAIL).sum()) for tag in ('F50','F25')}
    bad=pw.loc[pw.estado.isin(FAIL)];npoints=len(bad[['x_m','y_m']].drop_duplicates())
    lines=['# Convergencia conjunta de fuentes y receptores','',
        '28 bloques nuevos verificados: 3.152.352 concentraciones horarias, 21–27 de diciembre de 2016. '
        'Cada rama reúne 6.295 puntos; reutiliza 1.604 y calcula 4.691. Meteorología BASE/WRF, emisiones, parámetros físicos y cotas conservados. UTC−3 fijo provisional.','',
        f'Fuentes50→25: **{int(sf.sum())}/126** contrastes locales diarios fuera del criterio. '
        f'Malla125→62,5: **{counts["F50"]}/70** contrastes zonales con fuentes50 y **{counts["F25"]}/70** con fuentes25.','',
        f'Diagnóstico punto a punto: **{len(bad)}/88.130** pares fuera del umbral, en **{npoints}** ubicaciones. '
        'Este diagnóstico complementa el criterio de máximos; no equivale a cambiarlo.','',
        'Umbral previamente fijado: 5 % y piso absoluto 0,00002 µg/m³. Si ambos valores son ≤0,0004 µg/m³, '
        'se informa diferencia absoluta sin afirmar convergencia física.']
    for pol in ('MP10','MP25'):
        lines+=['',f'## {pol}: máximo de las medias de 24 h en la semana (µg/m³)','',
            '| Receptor o zona | Fuentes50 | Fuentes25 |','|---|---:|---:|']
        for group,label in LABELS.items():
            r=sw.loc[sw.contaminante.eq(pol)&sw.grupo.eq(group)].iloc[0]
            lines.append(f'| {label} | {r.base_max24h:.6f} | {r.refinado_max24h:.6f} |')
    lines+=['','## Próximo paso','',
        'Revisar los días y lugares fuera del criterio antes de fijar una resolución. '
        'Si persiste sensibilidad a la malla, preparar un refinamiento local adicional conservando los nodos existentes. '
        'Si persiste sensibilidad a la segmentación, examinar esas ubicaciones con fuentes más cortas. '
        'No escoger la discretización por la concentración deseada.','',
        'Estos son aportes modelados sin concentración de fondo. GENERAL es el máximo de los puntos evaluados; '
        'no certifica un máximo espacial continuo. La prueba semanal no acredita toda la temporada ni otras meteorologías. '
        'CG5 histórica sigue en los datos de procedencia, pero no sustituye la envolvente MINA autorizada.']
    p=OUT/'Resultados.md';p.write_text('\n'.join(lines)+'\n',encoding='utf-8');saved.append(p)
    guardar_json(OUT/'Estado.json',dict(estado='COMPARACION_COMPLETA',fecha=datetime.now().isoformat(),bloques_verificados=28,
        fuentes_fuera_criterio=int(sf.sum()),malla_fuera_criterio=counts,pares_puntuales_fuera=len(bad),ubicaciones_puntuales=npoints,
        archivos=[dict(path=str(p),sha256=sha256(p)) for p in saved],uniones_verificadas=evidence))
    print('Comparación conjunta completa; ver Resultados.md.',flush=True)

if __name__=='__main__':main()
