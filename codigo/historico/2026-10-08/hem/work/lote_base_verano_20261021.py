"""Continúa el verano tras recibir el primer día; dos procesos y cierre por caso."""
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import argparse
import os
import re
import shutil
import subprocess
import time
import traceback
import numpy as np
import pandas as pd
import ejecutar_base_verano_20261021 as common
import salidas_estacionales_20261021 as analysis

ROOT = Path(__file__).resolve().parents[1]
BASE = common.OUT
REV = BASE / 'Revision_QC_2026-10-21'
FIRST = BASE / 'Primer_dia_20161221'
OUT = BASE / 'Lote_estacional'
read, save, verify, files, check = common.read, common.guardar_json, common.verify, common.files, common.check
RESERVE = 5 * 1024**3
LABELS = {'PCAR': 'Piedra Carvajal', 'LBCEN': 'Los Bronces, estación',
          'MINA_envolvente_red': 'Los Bronces, máximo MINA', 'SULF': 'Sulfatos',
          'PALP': 'La Paloma, punto', 'Glaciar Paloma Oeste': 'La Paloma Oeste',
          'Glaciar Paloma Este': 'La Paloma Este', 'Glaciar Paloma Norte': 'La Paloma Norte',
          'Glaciar Olivares Alfa Sur': 'Olivares Alfa Sur', 'GENERAL': 'Máximo general de nodos evaluados'}


def state(**fields):
    fields['actualizado'] = datetime.now().isoformat()
    tmp = OUT / 'Estado.tmp.json'; save(tmp, fields); os.replace(tmp, OUT / 'Estado.json')


def prepare():
    check(not (OUT / 'Entrega.json').exists(), 'Lote ya congelado')
    OUT.mkdir(exist_ok=True)
    verify(read(FIRST / 'Entrega.json')['archivos'])
    verify(read(BASE / 'Preprocesamiento.json')['archivos'])
    tests = analysis.test_masks(); save(OUT / 'Pruebas_lector.json', tests)
    mask = pd.read_csv(REV / 'Cobertura_horaria.csv')
    check(len(mask) == 2153 and mask.dia.nunique() == 90, 'Calendario incorrecto')
    plan = dict(inicio='2016-12-21', ultimo_dia='2017-03-20', horas=2153, horas_aptas=2151,
                dias=sorted(mask.dia.unique()), contaminantes=['MP10', 'MP25'],
                max_procesos=2, reserva_disco_bytes=RESERVE,
                condicion='No ejecutar nuevos días hasta recibir ambos contaminantes del primer día y comprobar espacio.',
                meteorologia='Estacional única, UTC−3 provisional; dos I71 explícitos.',
                parametros_y_receptores_fijos=True, fuentes=12263, receptores=6295)
    save(OUT / 'Plan.json', plan)
    dependencies = [Path(__file__), ROOT / 'work/salidas_estacionales_20261021.py',
                    ROOT / 'work/ejecutar_base_verano_20261021.py', BASE / 'Entrega.json',
                    BASE / 'Preprocesamiento.json', REV / 'Cierre.json', FIRST / 'Entrega.json',
                    BASE / 'Comunes/membresia_completa.csv', REV / 'Cobertura_horaria.csv',
                    OUT / 'Plan.json', OUT / 'Pruebas_lector.json']
    save(OUT / 'Entrega.json', dict(estado='LOTE_ESTACIONAL_PREPARADO', archivos=files(dependencies)))
    state(estado='ESPERA_PRIMER_DIA', casos_recibidos=0, casos_previstos=180)
    print('Lote preparado; la continuación depende de recibir el primer día.', flush=True)


def receive(pol, day, folder, mask, members, inputs, execution):
    verify(inputs)
    qa, data, points, _, zones = analysis.receive(folder, mask, members)
    points['dia'] = day; zones['dia'] = day
    points.to_csv(folder / 'Por_receptor_estacional.csv', index=False, encoding='utf-8-sig')
    zones.to_csv(folder / 'Por_ambito_estacional.csv', index=False, encoding='utf-8-sig')
    mask.to_csv(folder / 'Cobertura_usada.csv', index=False, encoding='utf-8-sig')
    save(folder / 'QA_estacional.json', qa)
    receipt = dict(contaminante=pol, dia=day, carpeta=str(folder), qa=qa, ejecucion=execution,
        bytes_caso=sum(p.stat().st_size for p in folder.iterdir() if p.is_file()),
        entradas=inputs, archivos=files([p for p in folder.iterdir() if p.is_file()]))
    save(OUT / 'Recibos' / (day.replace('-', '') + '_' + pol + '.json'), receipt)
    return receipt


def receive_first(mask, members):
    start = time.monotonic()
    while True:
        if (FIRST / 'Estado.json').exists():
            try:
                current = read(FIRST / 'Estado.json')
            except ValueError:
                current = {}
            check(not current.get('errores'), 'Primer día con errores; no se despachan nuevos casos')
            if current.get('estado') == 'PRIMER_DIA_COMPLETO':
                break
        check(time.monotonic() - start < 24 * 3600, 'Primer día sin cierre en 24 h; revisar ejecución')
        time.sleep(30)
    verify(current['archivos'])
    receipts = []
    for pol in ['MP10', 'MP25']:
        p = OUT / 'Recibos' / ('20161221_' + pol + '.json')
        if p.exists():
            old = read(p); verify(old['archivos']); receipts.append(old); continue
        old = read(FIRST / ('Recibo_' + pol + '.json')); verify(old['archivos'])
        # Copiar sólo productos de la corrida para añadir el nuevo resumen fuera del caso congelado.
        src = Path(old['carpeta']); folder = OUT / 'Casos/20161221' / pol; folder.mkdir(parents=True)
        for name in ['aermod.inp', 'aermod.out', 'resumen.sum', 'errores.out', 'receptor_horas.out',
                     'receptor_24h.out', 'met.SFC', 'met.PFL', 'fuentes_aermod.inc', 'receptores.inc', pol + '.emi']:
            shutil.copy2(src / name, folder / name)
        inputs = files([folder / n for n in ['aermod.inp', 'met.SFC', 'met.PFL', 'fuentes_aermod.inc', 'receptores.inc', pol + '.emi']])
        receipts.append(receive(pol, '2016-12-21', folder, mask.loc[mask.dia.eq('2016-12-21')], members, inputs, old['ejecucion']))
    size = max(r['bytes_caso'] for r in receipts)
    estimate = size * 178 * 1.5
    check(shutil.disk_usage(ROOT).free - estimate > RESERVE, 'Proyección de espacio insuficiente; no se inicia resto del verano')
    seconds = max(r['ejecucion']['segundos'] for r in receipts)
    save(OUT / 'Costo_primer_dia.json', dict(segundos_mayor_corrida=seconds, bytes_mayor_caso=size,
        proyeccion_restante_disco_bytes_con_margen=estimate, reserva_bytes=RESERVE,
        proyeccion_horas_restantes_89_pares=seconds * 89 / 3600,
        nota='Extrapolación del primer día con dos procesos; el costo real varía con meteorología y carga del equipo.'))
    report(receipts, complete=False)
    return receipts


def prepare_case(pol, day, mask):
    dest = OUT / 'Casos' / day.replace('-', '') / pol
    dest.mkdir(parents=True)
    timestamp = pd.Timestamp(day); nh = len(mask)
    for name in ['fuentes_aermod.inc', 'receptores.inc']:
        shutil.copy2(BASE / 'Comunes' / name, dest / name)
    shutil.copy2(BASE / 'Emisiones' / timestamp.strftime('%Y%m%d') / (pol + '.emi'), dest / (pol + '.emi'))
    for kind in ['SFC', 'PFL']:
        raw = (REV / 'Objetivo' / ('met.' + kind)).read_text(encoding='ascii').splitlines()
        selected = [line for line in (raw[1:] if kind == 'SFC' else raw)
                    if tuple(map(int, line.split()[:3])) == (timestamp.year, timestamp.month, timestamp.day)]
        check(len(selected) == nh * (1 if kind == 'SFC' else 29), 'Recorte de meteorología diario incompleto')
        (dest / ('met.' + kind)).write_text('\n'.join((raw[:1] if kind == 'SFC' else []) + selected) + '\n', encoding='ascii')
    template_path = Path(read(REV / f'Recibo_SETUP_{pol}_20161221.json')['carpeta']) / 'aermod.inp'
    control = template_path.read_text(encoding='ascii').replace('CO RUNORNOT NOT', 'CO RUNORNOT RUN')
    control = re.sub(r'CO TITLEONE.*', f'CO TITLEONE BASE estacional {day} UTC-3 provisional', control)
    control = re.sub(r'ME STARTEND.*', f'ME STARTEND {timestamp:%Y %m %d} 1 {timestamp:%Y %m %d} {nh}', control)
    for key in ['SURFDATA', 'UAIRDATA', 'SITEDATA']:
        control = re.sub(r'(ME ' + key + r'\s+\d+)\s+\d+', lambda m: m[1] + ' ' + str(timestamp.year), control)
    if nh == 24:
        control = control.replace('OU FINISHED', 'OU POSTFILE 24 ALL PLOT receptor_24h.out\nOU FINISHED')
    else:
        check(day == '2017-03-20' and nh == 17, 'Día parcial no esperado')
        control = control.replace('CO AVERTIME 1 24 PERIOD', 'CO AVERTIME 1 PERIOD')
    (dest / 'aermod.inp').write_text(control, encoding='ascii')
    binding = common.validar_vinculo_horario(dest / 'aermod.inp', dest / 'fuentes_aermod.inc', dest / (pol + '.emi'),
        {(timestamp.year % 100, timestamp.month, timestamp.day, h) for h in range(1, nh + 1)})
    info = dict(carpeta=str(dest), vinculo=binding,
        entradas=files([dest / n for n in ['aermod.inp', 'met.SFC', 'met.PFL', 'fuentes_aermod.inc', 'receptores.inc', pol + '.emi']]))
    save(dest / 'Preparacion.json', info)
    return info


def worker(pol, day, mask, members):
    receipt = OUT / 'Recibos' / (day.replace('-', '') + '_' + pol + '.json')
    if receipt.exists():
        old = read(receipt); verify(old['archivos']); return old
    folder = OUT / 'Casos' / day.replace('-', '') / pol
    if folder.exists():
        info = read(folder / 'Preparacion.json'); verify(info['entradas'])
        check((folder / 'aermod.out').exists() and 'AERMOD Finishes Successfully' in (folder / 'aermod.out').read_text(encoding='ascii'),
              'Intento previo incompleto; conservarlo y revisar antes de reejecutar: ' + str(folder))
        return receive(pol, day, folder, mask, members, info['entradas'], read(folder / 'Ejecucion.json'))
    check(shutil.disk_usage(ROOT).free > RESERVE + 1024**3, 'Espacio libre por debajo de la reserva')
    info = prepare_case(pol, day, mask)
    start = time.perf_counter(); execution = dict(inicio=datetime.now().isoformat(), estado='EN_CURSO')
    with (folder / 'consola.log').open('xb') as stream:
        proc = subprocess.Popen([str(BASE / 'Binarios/aermod.exe')], cwd=folder, stdout=stream,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        execution['pid'] = proc.pid; save(folder / 'Ejecucion.json', execution)
        print('AERMOD ' + day + ' ' + pol + ', PID ' + str(proc.pid), flush=True)
        code = proc.wait()
    execution.update(fin=datetime.now().isoformat(), segundos=time.perf_counter() - start, codigo=code, estado='FINALIZADO')
    save(folder / 'Ejecucion.json', execution); check(code == 0, 'AERMOD terminó con código ' + str(code))
    return receive(pol, day, folder, mask, members, info['entradas'], execution)


def report(receipts, complete):
    members = pd.read_csv(BASE / 'Comunes/membresia_completa.csv')
    summaries = []
    for pol in ['MP10', 'MP25']:
        entries = [r for r in receipts if r['contaminante'] == pol]
        if not entries:
            continue
        daily = pd.concat([pd.read_csv(Path(r['carpeta']) / 'Por_receptor_estacional.csv') for r in entries], ignore_index=True)
        check(not daily.duplicated(['dia', 'x_m', 'y_m']).any(), 'Día/receptor duplicado al consolidar')
        per_point = daily.groupby(['x_m', 'y_m']).agg(suma=('suma_horaria_ug_m3', 'sum'),
            horas_validas=('horas_validas', 'sum'), maximo_1h=('maximo_1h_ug_m3', 'max'),
            maximo_24h=('media_24h_ug_m3', 'max')).reset_index()
        per_point['media_periodo_ug_m3'] = per_point.suma / per_point.horas_validas
        per_point.to_csv(OUT / ('Acumulado_receptores_' + pol + '.csv'), index=False, encoding='utf-8-sig')
        joined = members.merge(per_point, on=['x_m', 'y_m'], validate='many_to_one')
        for group, label in LABELS.items():
            subset = joined.loc[joined.grupo.eq(group)]
            check(len(subset) > 0, 'Falta ámbito ' + group)
            row = subset.sort_values(['media_periodo_ug_m3', 'x_m', 'y_m'], ascending=[False, True, True]).iloc[0]
            summaries.append(dict(contaminante=pol, grupo=group, nombre=label, dias=len(entries),
                horas_validas=int(row.horas_validas), maximo_media_periodo_ug_m3=float(row.media_periodo_ug_m3),
                maximo_24h_ug_m3=float(subset.maximo_24h.max()), maximo_1h_ug_m3=float(subset.maximo_1h.max()),
                x_maximo_media_m=float(row.x_m), y_maximo_media_m=float(row.y_m)))
    table = pd.DataFrame(summaries); table.to_csv(OUT / 'Resumen_ambitos.csv', index=False, encoding='utf-8-sig')
    lines = ['# Concentraciones BASE del verano: ' + ('completo' if complete else 'avance parcial'), '',
        f'{len(receipts)} de 180 corridas diarias recibidas. Configuración fija: 12.263 fuentes y 6.295 receptores. '
        'Unidades: µg/m³; aportes modelados sin fondo. No son todavía intervalos de incertidumbre.', '',
        'Se promedia por receptor antes de maximizar por zona. GENERAL es el máximo de los nodos evaluados. '
        'El punto La Paloma y sus sectores glaciales se mantienen separados. Los faltantes se excluyen mediante máscara; '
        'el 20 de marzo parcial no aporta una media de 24 h.', '',
        '| Contaminante | Receptor o zona | Días recibidos | Horas aptas | Mayor media del período recibido | Máximo de medias 24 h |',
        '|---|---|---:|---:|---:|---:|']
    for r in table.itertuples():
        lines.append(f'| {r.contaminante} | {r.nombre} | {r.dias} | {r.horas_validas} | {r.maximo_media_periodo_ug_m3:.6f} | {r.maximo_24h_ug_m3:.6f} |')
    lines += ['', 'Las columnas se refieren exclusivamente a los días recibidos de cada contaminante. '
              'No comparar dos períodos distintos si sus conteos todavía difieren. La meteorología procede de la ventana estacional; '
              'los pilotos de otra ventana no son una referencia idéntica.']
    (OUT / 'Resultados.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def run():
    verify(read(OUT / 'Entrega.json')['archivos'])
    verify(read(BASE / 'Entrega.json')['archivos'])
    verify(read(BASE / 'Preprocesamiento.json')['archivos'])
    lock = OUT / 'Ejecucion_activa.lock'
    with lock.open('x', encoding='ascii') as f:
        f.write(str(os.getpid()))
    try:
        (OUT / 'Recibos').mkdir(exist_ok=True)
        state(estado='ESPERA_PRIMER_DIA', casos_recibidos=0, casos_previstos=180, supervisor_pid=os.getpid())
        mask = pd.read_csv(REV / 'Cobertura_horaria.csv'); members = pd.read_csv(BASE / 'Comunes/membresia_completa.csv')
        receipts = receive_first(mask, members)
        for p in sorted((OUT / 'Recibos').glob('*.json')):
            r = read(p)
            if r['dia'] != '2016-12-21':
                verify(r['archivos']); receipts.append(r)
        done = {(r['dia'], r['contaminante']) for r in receipts}
        jobs = iter([(d, p) for d in read(OUT / 'Plan.json')['dias'][1:] for p in ['MP10', 'MP25'] if (d, p) not in done])
        errors = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            active = {}
            def submit():
                job = next(jobs, None)
                if job:
                    day, pol = job
                    active[pool.submit(worker, pol, day, mask.loc[mask.dia.eq(day)], members)] = job
            submit(); submit()
            while active:
                state(estado='DISPERSION_EN_CURSO', casos_recibidos=len(receipts), casos_previstos=180,
                      activos=list(active.values()), errores=errors, supervisor_pid=os.getpid())
                completed, _ = wait(active, return_when=FIRST_COMPLETED)
                for future in completed:
                    key = active.pop(future)
                    try:
                        result = future.result(); receipts.append(result)
                        print('Recibido ' + str(key) + f' ({len(receipts)}/180)', flush=True)
                    except Exception:
                        errors[str(key)] = traceback.format_exc()
                report(receipts, complete=False)
                if not errors:
                    while len(active) < 2:
                        before = len(active); submit()
                        if len(active) == before:
                            break
            check(not errors, 'Lote detenido tras errores; se conservan todos los recibos')
        check(len(receipts) == 180, 'Faltan corridas')
        report(receipts, complete=True)
        state(estado='VERANO_BASE_COMPLETO', casos_recibidos=180, casos_previstos=180,
              archivos=files([OUT / 'Resumen_ambitos.csv', OUT / 'Resultados.md',
                  OUT / 'Acumulado_receptores_MP10.csv', OUT / 'Acumulado_receptores_MP25.csv',
                  *sorted((OUT / 'Recibos').glob('*.json'))]))
    except Exception:
        error = traceback.format_exc()
        state(estado='DETENIDO_REQUIERE_REVISION', error=error, casos_previstos=180)
        raise
    finally:
        lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('etapa', choices=['preparar', 'ejecutar'])
    args = parser.parse_args(); {'preparar': prepare, 'ejecutar': run}[args.etapa]()
