"""Additional independent checks; no model executions or changes to model inputs."""
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import json, hashlib, datetime
import pandas as pd
import numpy as np
from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs/Normativa_reproduccion_2026-11-04'
A = ROOT/'outputs/Sensibilidad_estacional_2026-10-29'
B = ROOT/'outputs/Sensibilidad_conjunta_T_WS_2026-10-30'
I = ROOT/'outputs/Informe_integrado_2026-11-04'
C = ROOT/'outputs/Seleccion_adversa_2026-11-04'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
keys = ['season','scenario','pollutant','receptor']
means = pd.read_csv(OUT/'Medias_periodo_reproducidas.csv')
old = pd.concat([pd.read_csv(p/'Resumen_periodo_comparable.csv') for p in [A,B]])
old = old[old.receptor!='Panel'].drop_duplicates(keys)
check = means.merge(old,on=keys,validate='one_to_one')
assert len(check)==len(means)==len(old)==144
err = float((check['mean']-check.mean_ug_m3).abs().max())
assert err<1e-9 and (check['count']==check.valid_hours).all()

d = pd.read_csv(OUT/'Diarios_reproducidos_cuatro_receptores.csv')
m = pd.read_csv(OUT/'Indicadores_descriptivos_submuestra.csv')
good = d[(d['count']==24)&(d['size']==24)&d.complete_civil_day]
coverage = good.groupby(['season','day']).size()
days = set(coverage[coverage==72].index)
ties = 0
for row in m.itertuples():
    group = d.copy()
    for k in keys: group=group[group[k]==getattr(row,k)]
    values = [float(r.mean) for r in group.itertuples() if (r.season,r.day) in days]
    n = len(values)
    k = int((Decimal('0.98')*n).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    assert n==row.n_days and k==row.k_ordinal
    assert abs(sorted(values)[k-1]-row.P98_subset_raw)<1e-9
    if row.pollutant=='MP25':
        decimals=[Decimal(str(v)) for v in values]
        ties+=sum((v%1)==Decimal('.5') for v in decimals)
        rounded=[int(v.quantize(Decimal('1'),rounding=ROUND_HALF_UP)) for v in decimals]
        assert sorted(rounded)[k-1]==row.P98_subset_rounded
        assert sum(v>50 for v in values)==row.days_above50_raw
        assert sum(v>50 for v in rounded)==row.days_above50_rounded
    else:
        assert pd.isna(row.P98_subset_rounded) and pd.isna(row.days_above50_raw)
assert len(m)==144

annex = PdfReader(OUT/'Complemento_normativa_reproduccion.pdf')
reports=[]
for folder,pdfname,original_count in [(I,'Informe_integrado_resultados.pdf',12),(C,'Informe_seleccion_adversa.pdf',8)]:
    current=PdfReader(folder/pdfname)
    original=PdfReader(folder/'Version_anterior_sin_normativa'/pdfname)
    assert len(original.pages)==original_count and len(current.pages)==original_count+6
    pages=[]
    for i in range(original_count):
        before=folder/'Revision_visual'/f'pagina-{i+1:02}.png' if folder==I else folder/'Revision_visual'/f'pagina-{i+1}.png'
        after=folder/'Revision_visual_normativa'/f'pagina-{i+1:02}.png'
        with Image.open(before) as a, Image.open(after) as b:
            a=a.convert('RGB');b=b.convert('RGB')
            assert a.size==b.size and a.tobytes()==b.tobytes(),(pdfname,i+1,a.size,b.size)
        assert original.pages[i].get_contents().get_data()==current.pages[i].get_contents().get_data()
        pages.append({'page':i+1,'png':str(after.relative_to(folder)),'sha256':sha(after),'review':'Identical pixels and content stream to previously visually approved page'})
    for i in range(6):
        n=original_count+i+1
        assert annex.pages[i].get_contents().get_data()==current.pages[n-1].get_contents().get_data()
        png=folder/'Revision_visual_normativa'/f'pagina-{n:02}.png'
        assert png.exists()
        pages.append({'page':n,'png':str(png.relative_to(folder)),'sha256':sha(png),'review':'Shared appendix manually reviewed; N5 and N6 reviewed again after final wording correction'})
    reports.append({'pdf':str(folder/pdfname),'pdf_sha256':sha(folder/pdfname),'pages':pages,'total_pages':len(pages),'original_pages_pixel_identical':original_count})
save(OUT/'Verificacion_cierre.json',{'status':'PASSED','checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'period_means_reproduced':144,'maximum_period_mean_difference':err,'order_statistic_groups_checked':144,'MP25_rounding_exact_half_ties':ties,'common_dates':{s:sum(x[0]==s for x in days) for s in ['VERANO','INVIERNO']},'reports':reports})
print(json.dumps({'status':'PASSED','period_means':144,'maximum_mean_error':err,'percentile_groups':144,'rounding_half_ties':ties,'unchanged_original_pages':20,'final_pages':32}))
