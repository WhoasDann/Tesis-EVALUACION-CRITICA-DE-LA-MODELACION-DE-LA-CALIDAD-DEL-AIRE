"""Read supplied sources, preserving originals and per-page evidence."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/Contraste_ADC160_normativa_2026-11-05'
(OUT/'Fuentes_texto').mkdir(parents=True,exist_ok=True)
sources={
 'ADC160':Path('/archivo/usuario/OneDrive/Escritorio/Docs Tesis/LosBronces/ANEXO ADC-160vi/ANEXO ADC-160vi.pdf'),
 'DS12_2021':Path('/archivo/usuario/Downloads/Decreto-12_04-JUN-2022.pdf'),
 'DS12_2011':Path('/archivo/usuario/Downloads/Decreto-12_09-MAY-2011.pdf')}
items=[]
for name,path in sources.items():
    r=PdfReader(path);folder=OUT/'Fuentes_texto'/name;folder.mkdir(exist_ok=True)
    texts=[]
    for i,page in enumerate(r.pages,1):
        text=page.extract_text(extraction_mode='layout')
        (folder/f'pagina_{i:03d}.txt').write_text(text,encoding='utf-8')
        texts.append(f'\n\n===== PAGINA PDF {i} =====\n\n{text}')
    (OUT/'Fuentes_texto'/f'{name}_completo.txt').write_text(''.join(texts),encoding='utf-8')
    item={'id':name,'path':str(path),'pages':len(r.pages),'bytes':path.stat().st_size,
          'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pdf_metadata':dict(r.metadata or {}),
          'extracted_characters':sum(map(len,texts))}
    items.append(item);print(json.dumps(item,ensure_ascii=False,default=str),flush=True)
(OUT/'Fuentes_recibidas.json').write_text(json.dumps({'time_utc':datetime.now(timezone.utc).isoformat(),'sources':items},indent=2,ensure_ascii=False,default=str),encoding='utf-8')
