"""Finite local finalizer: waits for this batch only; never dispatches model cases."""
from piloto import *
import time,traceback
def state(status,**kwargs):
    temp=OUT/'Finalizador.json.tmp';putjson(temp,dict(status=status,pid=os.getpid(),updated_utc=now(),**kwargs));os.replace(temp,OUT/'Finalizador.json')
def main():
    lock=OUT/'finalizador.lock'
    with lock.open('x') as f:json.dump(dict(pid=os.getpid(),started_utc=now()),f)
    started=time.monotonic()
    try:
        while True:
            s=read(PILOT/'Lote_local/status.json')
            state('WAITING_BATCH',received_native=len(s['completed']),expected=s['assigned'],worker_state=s['state'])
            if s['state']=='COMPLETE':break
            if s.get('errors') or s['state'] in ['FAILED','PAUSED']:raise RuntimeError('Batch requires review: '+json.dumps(s))
            if time.monotonic()-started>6*3600:raise TimeoutError('Six-hour finite monitoring limit reached; do not restart cases')
            time.sleep(20)
        state('SCIENTIFIC_RECEPTION')
        from recibir import receive
        receive();assert read(PILOT/'Recepcion.json')['status']=='COMPLETE_SCIENTIFIC_RECEPTION'
        state('BUILDING_REPORT')
        marker=OUT/'Artifact_operation.json'
        if not marker.exists():
            node=Path(r'/archivo/usuario\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
            helper=Path(r'/archivo/usuario\.codex\plugins\cache\openai-primary-runtime\pdf\26.1030.10813\skills\pdf\container_tools\mark_artifact_operation_started.mjs')
            subprocess.run([str(node),str(helper),'--operation-kind','create','--expected-output-count','1','--output-format','pdf'],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
            putjson(marker,dict(status='MARKED',at=now()))
        from informe import report
        report()
        state('RENDERING_REPORT')
        preview=OUT/'Revision_visual';preview.mkdir(exist_ok=True)
        poppler=Path(r'/archivo/usuario\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe')
        subprocess.run([str(poppler),'-r','110','-png',str(OUT/'Informe_seleccion_adversa.pdf'),str(preview/'pagina')],check=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=180)
        from pypdf import PdfReader
        pdf=PdfReader(OUT/'Informe_seleccion_adversa.pdf');assert len(list(preview.glob('pagina-*.png')))==len(pdf.pages)
        state('WAITING_VISUAL_QA',pages=len(pdf.pages),pdf=str(OUT/'Informe_seleccion_adversa.pdf'),received_scientific=38,delivery_ready=False)
    except Exception:
        state('FAILED_REQUIRES_REVIEW',traceback=traceback.format_exc());raise
    finally:
        if lock.exists():lock.rename(OUT/f'finalizador.finished.{time.time_ns()}.lock')
if __name__=='__main__':main()
