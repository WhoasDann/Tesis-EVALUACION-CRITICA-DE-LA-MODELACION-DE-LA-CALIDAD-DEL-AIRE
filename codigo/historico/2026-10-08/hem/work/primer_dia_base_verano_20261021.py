"""Primer día BASE con meteorología estacional, dos corridas recuperables."""
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import numpy as np
import pandas as pd
import ejecutar_base_verano_20261021 as previous

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'outputs/BASE_verano_2026-10-21'
REV = BASE / 'Revision_QC_2026-10-21'
OUT = BASE / 'Primer_dia_20161221'
read, verify, save, files, check = previous.read, previous.verify, previous.guardar_json, previous.files, previous.check
from tesis.validacion_dispersion import verificar_dispersion


def prepare():
    check(not (OUT / 'Entrega.json').exists(), 'Primer día ya preparado')
    pre = read(BASE / 'Preprocesamiento.json'); verify(pre['archivos'])
    closure = read(REV / 'Cierre.json'); verify(closure['archivos'])
    mask = pd.read_csv(REV / 'Cobertura_horaria.csv')
    day = mask.loc[mask.dia.eq('2016-12-21')]
    check(len(day) == 24 and day.estado.eq('VALIDA').all(), 'Primer día no tiene 24 horas aptas')
    check(shutil.disk_usage(ROOT).free > 5 * 1024**3, 'Espacio insuficiente para primer día')
    OUT.mkdir(exist_ok=True)
    cases = {}
    for pol in ['MP10', 'MP25']:
        entry = read(REV / f'Recibo_SETUP_{pol}_20161221.json'); verify(entry['archivos'])
        src = Path(entry['carpeta']); dest = OUT / pol; dest.mkdir()
        names = ['met.SFC', 'met.PFL', pol + '.emi', 'fuentes_aermod.inc', 'receptores.inc']
        for name in names:
            shutil.copy2(src / name, dest / name)
            check(previous.sha256(src / name) == previous.sha256(dest / name), 'Copia distinta: ' + name)
        control = (src / 'aermod.inp').read_text(encoding='ascii')
        check(control.count('CO RUNORNOT NOT') == 1, 'RUNORNOT inesperado')
        control = control.replace('CO RUNORNOT NOT', 'CO RUNORNOT RUN')
        control = control.replace('OU FINISHED', 'OU POSTFILE 24 ALL PLOT receptor_24h.out\nOU FINISHED')
        (dest / 'aermod.inp').write_text(control, encoding='ascii')
        binding = previous.validar_vinculo_horario(dest / 'aermod.inp', dest / 'fuentes_aermod.inc', dest / (pol + '.emi'),
                                                  {(16, 12, 21, h) for h in range(1, 25)})
        cases[pol] = dict(carpeta=str(dest), vinculo=binding, entradas=files([dest / n for n in ['aermod.inp', *names]]))
    save(OUT / 'Plan.json', dict(dia='2016-12-21', horas=24, fuentes=12263, receptores=6295,
        contaminantes=['MP10', 'MP25'], procesos_simultaneos=2, casos=cases,
        meteo='Único procesamiento estacional recibido; Bowen diciembre 0,60. No comparar directamente con pilotos de otra ventana.',
        alcance='Primer día, sin inferir máximos ni costo exacto de todo el verano.',
        espacio_libre_inicial_bytes=shutil.disk_usage(ROOT).free,
        mascara_obligatoria=str(REV / 'Cobertura_horaria.csv')))
    save(OUT / 'Entrega.json', dict(estado='PRIMER_DIA_PREPARADO', archivos=files([
        Path(__file__), OUT / 'Plan.json', BASE / 'Preprocesamiento.json', REV / 'Cierre.json',
        REV / 'Cobertura_horaria.csv', BASE / 'Comunes/membresia_completa.csv',
        BASE / 'Binarios/aermod.exe', ROOT / 'work/ejecutar_base_verano_20261021.py',
        *sorted((BASE.parent / 'Biblioteca_Tesis/tesis').glob('*.py'))]) +
        [e for c in cases.values() for e in c['entradas']]))
    save(OUT / 'Estado.json', dict(estado='PREPARADO', corridas_completas=0, corridas_previstas=2))
    print('Preparadas MP10 y MP25: 24 h, 12263 fuentes y 6295 receptores por corrida.', flush=True)


def receive(pol, info):
    verify(info['entradas']); folder = Path(info['carpeta'])
    members = pd.read_csv(BASE / 'Comunes/membresia_completa.csv')
    qa, daily, zones = verificar_dispersion(folder, 12263, 6295, members, '2016-12-21', '2016-12-22')
    cols = ['x_m', 'y_m', 'C_ug_m3', 'elev_m', 'hill_m', 'flag', 'average', 'group', 'fecha_AERMOD']
    native = pd.read_csv(folder / 'receptor_24h.out', sep=r'\s+', comment='*', names=cols, usecols=range(9), dtype={'fecha_AERMOD': str})
    check(len(native) == 6295 and native.average.eq('24-HR').all() and native.group.eq('ALL').all(), 'POSTFILE24 incompleto')
    check(native.fecha_AERMOD.eq('16122124').all() and not native.duplicated(['x_m', 'y_m']).any(), 'POSTFILE24 fechas o duplicados')
    general = daily.loc[daily.grupo.eq('GENERAL')]
    check(len(general) == 6295, 'GENERAL no representa toda la unión')
    joined = general.merge(native, on=['x_m', 'y_m'], validate='one_to_one')
    check(len(joined) == 6295 and np.allclose(joined.media_24h_ug_m3, joined.C_ug_m3, rtol=0, atol=1.1e-5),
          'Media horaria reconstruida no coincide con POSTFILE24')
    qa['error_max_media_vs_POSTFILE24'] = float(abs(joined.media_24h_ug_m3 - joined.C_ug_m3).max())
    daily.to_csv(folder / 'Medias_diarias.csv', index=False, encoding='utf-8-sig')
    zones.to_csv(folder / 'Maximos_diarios.csv', index=False, encoding='utf-8-sig')
    save(folder / 'QA.json', qa)
    bytes_total = sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
    result = dict(contaminante=pol, dia='2016-12-21', carpeta=str(folder), qa=qa, bytes_caso=bytes_total,
        ejecucion=read(folder / 'Ejecucion.json'), archivos=files([p for p in folder.iterdir() if p.is_file()]))
    save(OUT / ('Recibo_' + pol + '.json'), result)
    return result


def worker(pol, info):
    receipt = OUT / ('Recibo_' + pol + '.json')
    if receipt.exists():
        result = read(receipt); verify(result['archivos']); return result
    folder = Path(info['carpeta']); verify(info['entradas'])
    report = folder / 'aermod.out'
    if report.exists():
        check('AERMOD Finishes Successfully' in report.read_text(encoding='ascii', errors='replace'),
              'Existe intento incompleto; conservarlo y preparar nueva revisión antes de repetir: ' + str(folder))
        return receive(pol, info)
    started = time.perf_counter()
    record = dict(inicio=datetime.now().isoformat(), estado='EN_CURSO')
    with (folder / 'consola.log').open('xb') as stream:
        proc = subprocess.Popen([str(BASE / 'Binarios/aermod.exe')], cwd=folder, stdout=stream, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        record['pid'] = proc.pid; save(folder / 'Ejecucion.json', record)
        print('AERMOD iniciado: ' + pol + ', PID ' + str(proc.pid), flush=True)
        code = proc.wait()
    record.update(fin=datetime.now().isoformat(), segundos=time.perf_counter() - started, codigo=code, estado='FINALIZADO')
    save(folder / 'Ejecucion.json', record)
    check(code == 0, 'Código AERMOD ' + str(code))
    return receive(pol, info)


def run():
    verify(read(OUT / 'Entrega.json')['archivos'])
    plan = read(OUT / 'Plan.json'); lock = OUT / 'Ejecucion_activa.lock'
    with lock.open('x', encoding='ascii') as f:
        f.write(str(os.getpid()))
    results, errors = {}, {}
    start = time.perf_counter()
    try:
        save(OUT / 'Estado.json', dict(estado='CONCENTRACIONES_EN_CURSO', corridas_completas=0, corridas_previstas=2,
                                      inicio=datetime.now().isoformat(), supervisor_pid=os.getpid()))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(worker, pol, info): pol for pol, info in plan['casos'].items()}
            for future in as_completed(futures):
                pol = futures[future]
                try:
                    results[pol] = future.result()
                    print('Recibido: ' + pol, flush=True)
                except Exception:
                    errors[pol] = traceback.format_exc()
                save(OUT / 'Estado.json', dict(estado='CONCENTRACIONES_EN_CURSO', corridas_completas=len(results),
                    corridas_previstas=2, recibidas=sorted(results), errores=errors))
        check(not errors, 'Revisar errores en Estado.json')
        save(OUT / 'Estado.json', dict(estado='PRIMER_DIA_COMPLETO', corridas_completas=2, corridas_previstas=2,
            valores_horarios=302160, segundos_lote=time.perf_counter() - start,
            bytes_casos=sum(r['bytes_caso'] for r in results.values()),
            espacio_libre_final_bytes=shutil.disk_usage(ROOT).free,
            archivos=files([OUT / ('Recibo_' + pol + '.json') for pol in ['MP10', 'MP25']])))
        print('Primer día estacional completo y verificado.', flush=True)
    finally:
        lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('etapa', choices=['preparar', 'ejecutar'])
    args = parser.parse_args(); {'preparar': prepare, 'ejecutar': run}[args.etapa]()
