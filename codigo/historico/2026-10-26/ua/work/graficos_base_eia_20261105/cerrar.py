from pathlib import Path
import json, hashlib, zipfile, shutil
from datetime import datetime, timezone
from pypdf import PdfReader

root=Path(__file__).resolve().parents[2]
out=root/'outputs/Graficos_BASE_EIA_2026-11-05'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
pdf=out/'Informe_grafico_BASE_EIA_y_escenarios.pdf'
assert len(PdfReader(pdf).pages)==16
pages=sorted((out/'Revision_visual').glob('pagina-*.png'))
assert len(pages)==16
assert len(list((out/'Figuras').glob('*.png')))==14
assert len(list((out/'Figuras').glob('*.svg')))==14
qa={'status':'PASSED','reviewed_utc':datetime.now(timezone.utc).isoformat(),
    'method':'All 16 final page renders inspected directly with view_image, at 100 dpi; figures also verified numerically.',
    'pdf_sha256':sha(pdf),'pages':[{'page':i+1,'render':p.name,'sha256':sha(p),'status':'PASSED'} for i,p in enumerate(pages)],
    'corrections':['Enlarged scenario labels and changed aspect ratio for readability.',
                   'Separated empirical-tuple labels from figure footer.',
                   'Preserved original EIA reference precision.',
                   'Added amplitude and source-location details.'],
    'checks':['No cropped legends, headings or numeric labels.','No overlapping footer or caption.',
              'Units and sample sizes visible.','Unavailable references explicitly labelled.',
              'Full-season curves exclude empirical tuples available only for episodes.']}
dump(out/'Revision_visual.json',qa)
v=json.loads((out/'Verificacion_numerica.json').read_text(encoding='utf-8'))
v['visual_QA']='PASSED';dump(out/'Verificacion_numerica.json',v)
dump(out/'Estado.json',{'status':'DELIVERY_READY','created_utc':datetime.now(timezone.utc).isoformat(),
     'PDF_pages':16,'figures':14,'formats':['PDF','PNG','SVG','CSV'],
     'new_model_runs':0,'execution':'ON_HOLD_BY_EXPLICIT_USER_REQUEST',
     'previous_reports_preserved':True,'legal_compliance':'NOT_EVALUATED',
     'pdf_sha256':sha(pdf),'scientific_scope':'Prescribed sensitivity; contextual EIA annual references; conditional episode candidates.'})
shutil.copy2(__file__,out/'Scripts/cerrar.py')
files=[p for p in out.rglob('*') if p.is_file() and p.suffix!='.zip' and 'Revision_visual' not in p.relative_to(out).parts and p.name not in ['Manifest.json','Paquete_verificado.json']]
manifest={'files':[{'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files)]}
dump(out/'Manifest.json',manifest)
files.append(out/'Manifest.json')
zip_path=out/'Graficos_y_datos_para_presentacion.zip'
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(files):z.write(p,p.relative_to(out).as_posix())
with zipfile.ZipFile(zip_path) as z:
    assert z.testzip() is None
    for row in manifest['files']:assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
dump(out/'Paquete_verificado.json',{'status':'PASSED','zip_sha256':sha(zip_path),'entries':len(files),'bytes':zip_path.stat().st_size,'manifest_hashes_checked':len(manifest['files'])})
prev=root/'outputs/Informe_presentacion_2026-11-05/Continuacion.md'
note='\n\n## Complemento gráfico del 5 de noviembre\n\nSe entregó `outputs/Graficos_BASE_EIA_2026-11-05/Informe_grafico_BASE_EIA_y_escenarios.pdf`: 16 páginas y 14 gráficos PNG/SVG con medias BASE y referencias EIA espacialmente cotejadas. Usar esa galería para las distribuciones sin la antigua referencia numérica 50. Conserva 87/90 días completos comunes, distingue media anual EIA y mantiene explícita la falta de referencias de Los Bronces MP2,5 y La Paloma. El informe anterior permanece sin cambios. Nuevas simulaciones y validación física ampliada continúan en espera.\n'
text=prev.read_text(encoding='utf-8')
if '## Complemento gráfico del 5 de noviembre' not in text:prev.write_text(text+note,encoding='utf-8')
print(json.dumps({'status':'DELIVERY_READY','pdf':str(pdf),'zip':str(zip_path),'zip_MB':round(zip_path.stat().st_size/1e6,2),'verified_entries':len(files)},ensure_ascii=False))
