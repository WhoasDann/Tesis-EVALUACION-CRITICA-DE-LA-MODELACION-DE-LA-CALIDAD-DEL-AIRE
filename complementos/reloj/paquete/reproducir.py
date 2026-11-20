"""Reproducción local del diagnóstico de reloj, sin llamadas de red ni modelos."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,importlib.metadata,json,os,platform,runpy,shutil,sys

ROOT=Path(__file__).resolve().parent

def verificar_archivos():
    manifest=json.loads((ROOT/'MANIFEST_SHA256.json').read_text(encoding='utf8'))
    for name,digest in manifest.items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError(f'Archivo ausente o fuera del paquete: {name}')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError(f'Hash distinto: {name}')
    return len(manifest)

def main():
    if not __debug__:
        raise SystemExit('Se requiere Python sin -O: los controles científicos usan assert.')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--salida',type=Path,help='Directorio nuevo para tablas, gráficos y controles.')
    parser.add_argument('--solo-verificar',action='store_true',help='Comprueba integridad sin recalcular.')
    parser.add_argument('--sin-figuras',action='store_true',help='Reproduce las tablas sin cargar Matplotlib.')
    args=parser.parse_args()
    if not args.solo_verificar and args.salida is None:
        parser.error('Debe indicarse --salida o --solo-verificar.')
    count=verificar_archivos()
    print(f'Integridad comprobada: {count} archivos.')
    if args.solo_verificar:
        return
    out=args.salida.resolve()
    protected=[ROOT/'entradas',ROOT/'biblioteca',ROOT/'scripts',ROOT/'referencia',ROOT/'procedencia']
    if out==ROOT or any(out.is_relative_to(p) for p in protected):
        raise ValueError('La salida no puede ocupar los directorios de insumos o referencia.')
    out.mkdir(parents=True,exist_ok=False)
    os.environ['TESIS_RELOJ_SALIDA']=str(out)
    os.environ['MPLCONFIGDIR']=str(out/'config_matplotlib')
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(ROOT/'scripts'))
    sys.path.insert(0,str(ROOT/'biblioteca'))
    shutil.copyfile(ROOT/'Protocolo_original.json',out/'Protocolo.json')
    stages=['analizar.py','verificar.py']+([] if args.sin_figuras else ['figuras.py'])
    for name in stages:
        print(f'Ejecutando {name}...')
        runpy.run_path(str(ROOT/'scripts'/name),run_name='__main__')
    from comparar import comparar
    comparison=comparar(ROOT,out)
    versions={}
    for name in ['numpy','pandas','matplotlib','tzdata','python-dateutil','Pillow']:
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    receipt=dict(status='REPRODUCED',completed_utc=datetime.now(timezone.utc).isoformat(),
        python=sys.version,platform=platform.platform(),dependencies=versions,
        input_and_code_files_verified=count,tables_reproduced=len(comparison['tables']),
        numeric_cells_compared=sum(r['numeric_cells'] for r in comparison['tables']),
        text_cells_compared=sum(r['text_cells'] for r in comparison['tables']),
        max_table_abs_error=max(r['max_abs_error'] for r in comparison['tables']),
        byte_identical_tables=sum(r['byte_identical'] for r in comparison['tables']),
        figures_generated=not args.sin_figuras,new_dispersion_runs=0,
        physical_validation=False)
    (out/'Reproduccion.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
