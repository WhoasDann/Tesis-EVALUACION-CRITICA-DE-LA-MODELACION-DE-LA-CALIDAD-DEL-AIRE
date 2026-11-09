"""Recibe AERMET ya ejecutado, identifica I71 y continúa sin rellenar meteorología.

Revisión separada: no modifica el runner, manifiesto ni salidas originales.
"""
from pathlib import Path
from datetime import datetime
from collections import Counter
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import numpy as np
import pandas as pd
import ejecutar_base_verano_20261021 as original

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'outputs/BASE_verano_2026-10-21'
REV = BASE / 'Revision_QC_2026-10-21'
MET = BASE / 'Meteorologia/aermet_20261021_145804_172910'
EXPECTED = {pd.Timestamp('2017-02-03 20:00'), pd.Timestamp('2017-03-03 20:00')}
read, check, files = original.read, original.check, original.files
save, verify = original.guardar_json, original.verify


def receive_met(folder, plan):
    """Sólo reconoce los dos faltantes identificados; cualquier otro fallo detiene."""
    start = pd.Timestamp(plan['inicio_auxiliar']) + pd.Timedelta(hours=1)
    end = pd.Timestamp(plan['fin_exclusivo'])
    auxiliary = pd.date_range(start, end, freq='h')
    target = pd.date_range(pd.Timestamp(plan['inicio']) + pd.Timedelta(hours=1), end, freq='h')
    tail = set(pd.date_range(end + pd.Timedelta(hours=1), end.normalize() + pd.Timedelta(days=1), freq='h'))
    errors = (folder / 'met.ER1').read_text(encoding='ascii')
    check(not re.search(r'(?m)^\s*\w+\s+E\d{2}\s', errors), 'AERMET contiene errores E##')
    i71 = {pd.Timestamp(datetime.strptime(d, '%Y%m%d')) + pd.Timedelta(hours=int(h))
           for d, h in re.findall(r'I71\s+NETRAD\s+DATE:\s+(\d{8})\s+HR\s+(\d+)\s+MISSING INSOLATION AND CLOUD COVER', errors)}
    check(i71 == EXPECTED, 'Cambió el conjunto I71: requiere revisión explícita')
    sfc = (folder / 'met.SFC').read_text(encoding='ascii').splitlines()
    sr, pr = {}, {}
    for line in sfc[1:]:
        if not line.strip():
            continue
        a = line.split()
        check(len(a) >= 25 and '*' not in line, 'SFC incompleto')
        v = np.asarray(a[:25], float)
        check(np.isfinite(v).all(), 'SFC NaN/Inf')
        k = pd.Timestamp(original.hora_fin(*map(int, [a[0], a[1], a[2], a[4]])))
        check(k not in sr, 'SFC duplicado')
        sr[k] = (v, line)
    for line in (folder / 'met.PFL').read_text(encoding='ascii').splitlines():
        if not line.strip():
            continue
        a = np.asarray(line.split(), float)
        check(len(a) == 11 and np.isfinite(a).all(), 'PFL inválido')
        k = pd.Timestamp(original.hora_fin(*map(int, a[:4])))
        pr.setdefault(k, []).append((a, line))
    for rows in [sr, pr]:
        check(list(rows) == sorted(rows), 'Meteorología desordenada')
        check(set(auxiliary) <= set(rows) and set(rows) - set(auxiliary) <= tail,
              'Cobertura auxiliar incompleta o inesperada')
    check(set(sr) == set(pr), 'SFC/PFL con calendarios distintos')
    diagnostics, missing = [], set()
    # Revisar también las 24 h auxiliares, además del objetivo.
    for k in auxiliary:
        v = sr[k][0]
        p = np.array([a for a, _ in pr[k]])
        check(len(p) == 29 and np.all(np.diff(p[:, 4]) > 0)
              and list(p[:, 5]) == [0] * 28 + [1], f'PFL con niveles incompletos: {k}')
        check(np.any((p[:, 6] >= 0) & (p[:, 6] <= 360) & (p[:, 7] >= 0) & (p[:, 7] < 99))
              and np.any((p[:, 8] > -123) & (p[:, 8] < 77)), f'PFL sin viento/temperatura: {k}')
        common = (v[12] > 0 and v[15] >= 0 and 0 <= v[16] <= 360 and v[17] > 0
                  and 150 < v[18] < 350 and v[19] > 0)
        check(common, f'SFC: viento, temperatura o alturas inválidos: {k}')
        usable = (v[6] >= 0 and v[10] > 0 and abs(v[11]) < 99998 and (v[11] >= 0 or v[9] > 0))
        state = 'VALIDA' if v[15] > 0 else 'CALMA'
        if not usable:
            sentinel = np.array_equal(v[5:12], [-999, -9, -9, -9, -999, -999, -99999])
            check(k in i71 and sentinel and v[24] == 99, f'Fallo SFC no explicado por I71: {k}')
            missing.add(k)
            state = 'FALTANTE_AERMET_I71'
        else:
            check(k not in i71, f'I71 sin patrón de faltante: {k}')
        if k in target:
            # AERMET usa hora final 1..24; día de emisión = inicio del intervalo.
            diagnostics.append(dict(fin_local=str(k), inicio_local=str(k - pd.Timedelta(hours=1)),
                                    dia=str((k - pd.Timedelta(hours=1)).date()), estado=state,
                                    apta_dispersion=(state == 'VALIDA'), WS_ms=v[15], WD_grados=v[16],
                                    T_K=v[18], ZiM_m=v[10], Bowen=v[13]))
    check(missing == EXPECTED, 'Los faltantes no coinciden con los dos casos documentados')
    # ONSITE contiene radiación cero (valor físico), no el sentinel 9999.
    onsite = {}
    for line in (folder / 'onsite.dat').read_text(encoding='ascii').splitlines():
        if len(line) >= 10 and line[:10].isdigit():
            k = pd.Timestamp(datetime.strptime(line[:10], '%Y%m%d%H')) if line[8:10] != '24' else (
                pd.Timestamp(datetime.strptime(line[:8], '%Y%m%d')) + pd.Timedelta(days=1))
            if k in EXPECTED:
                a = line[10:].split()
                check(float(a[0]) == 0 and float(a[4]) == 10, 'I71: cambiaron entradas INSO/TSKC')
                onsite[str(k)] = dict(INSO_W_m2=float(a[0]), TSKC_decimos=float(a[4]), linea=line)
    check(len(onsite) == 2, 'No se encontraron las dos entradas ONSITE')
    ids = {}
    for key, following in [('UA_ID', 'SF_ID'), ('SF_ID', 'OS_ID'), ('OS_ID', 'VERSION')]:
        match = re.search(key + r':\s*(.*?)\s*' + following + r':', sfc[0])
        check(match is not None, 'IDs ausentes')
        ids[key] = int(match[1].strip() or '0')
    frame = pd.DataFrame(diagnostics)
    daily = frame.groupby('dia', sort=True).agg(horas_calendario=('estado', 'size'),
                                               horas_validas=('apta_dispersion', 'sum')).reset_index()
    daily['horas_no_validas'] = daily.horas_calendario - daily.horas_validas
    daily['cobertura_porcentaje'] = 100 * daily.horas_validas / daily.horas_calendario
    daily['dia_completo'] = daily.horas_calendario == 24
    daily['denominador_24h_AERMOD'] = np.where(daily.dia_completo, np.maximum(daily.horas_validas, 18), np.nan)
    qc = dict(horas_objetivo=len(target), horas_auxiliares=len(auxiliary), filas_SFC=len(sr),
              horas_PFL=len(pr), niveles_PFL=[29], ids=ids, calmas=int((frame.estado == 'CALMA').sum()),
              faltantes_AERMET=len(missing), horas_aptas=int(frame.apta_dispersion.sum()),
              cobertura_porcentaje=float(100 * frame.apta_dispersion.mean()),
              faltantes=[str(k) for k in sorted(missing)], entradas_I71=onsite,
              advertencias_AERMET=dict(Counter(re.findall(r'\bW\d{2}\b', errors))),
              horas_cola_excluidas=len(set(sr) - set(auxiliary)),
              nota='Faltantes conservados literalmente; máscara obligatoria para concentración. No usar ceros internos AERMOD como concentraciones físicas.')
    return qc, frame, daily, sfc[0], sr, pr, target


def tests(plan):
    qc, *_ = receive_met(MET, plan)
    check(qc['horas_aptas'] == 2151 and qc['faltantes_AERMET'] == 2 and qc['calmas'] == 0, 'Conteo inesperado')
    results = {}
    with tempfile.TemporaryDirectory(prefix='qc_i71_', dir=ROOT / 'work') as temp:
        dest = Path(temp)
        for name in ['met.SFC', 'met.PFL', 'met.ER1', 'onsite.dat']:
            shutil.copy2(MET / name, dest / name)
        sfc = (dest / 'met.SFC').read_text(encoding='ascii')
        pfl = (dest / 'met.PFL').read_text(encoding='ascii')
        errors = (dest / 'met.ER1').read_text(encoding='ascii')
        def rejected(name):
            try:
                receive_met(dest, plan)
            except ValueError:
                results[name] = True
            else:
                raise AssertionError('No se rechazó: ' + name)
        lines = sfc.splitlines()
        (dest / 'met.SFC').write_text('\n'.join(lines[:26] + lines[27:]) + '\n', encoding='ascii')
        rejected('hora_ausente'); (dest / 'met.SFC').write_text(sfc, encoding='ascii')
        lines = pfl.splitlines()
        (dest / 'met.PFL').write_text('\n'.join(lines[1:]) + '\n', encoding='ascii')
        rejected('nivel_ausente'); (dest / 'met.PFL').write_text(pfl, encoding='ascii')
        (dest / 'met.ER1').write_text(errors.replace('I71', 'I00'), encoding='ascii')
        rejected('faltantes_sin_traza_I71'); (dest / 'met.ER1').write_text(errors, encoding='ascii')
        lines = sfc.splitlines(); a = lines[26].split(); a[6] = '-9.000'; lines[26] = ' '.join(a)
        (dest / 'met.SFC').write_text('\n'.join(lines) + '\n', encoding='ascii')
        rejected('tercer_fallo_no_autorizado')
    return results


def prepare():
    check(not (REV / 'Entrega_revision.json').exists(), 'Revisión ya congelada')
    REV.mkdir(exist_ok=True)
    verify(read(BASE / 'Entrega.json')['archivos'])
    verify(read(BASE / 'MMIF_validado.json')['archivos'])
    plan = read(BASE / 'Plan.json')
    qmmif = original.mmif_qc(Path(read(BASE / 'MMIF_validado.json')['carpeta']), plan)
    check('AERMET FINISHED SUCCESSFULLY' in (MET / 'aermet.exe.consola.log').read_text(encoding='ascii'), 'AERMET no terminó')
    test_results = tests(plan)
    qc, frame, daily, header, sr, pr, target = receive_met(MET, plan)
    frame.to_csv(REV / 'Cobertura_horaria.csv', index=False, encoding='utf-8-sig')
    daily.to_csv(REV / 'Cobertura_diaria.csv', index=False, encoding='utf-8-sig')
    monthly = frame.assign(mes=frame.dia.str[:7]).groupby('mes').agg(
        horas_calendario=('estado', 'size'), horas_aptas=('apta_dispersion', 'sum'),
        Bowen_min=('Bowen', 'min'), Bowen_max=('Bowen', 'max')).reset_index()
    monthly.to_csv(REV / 'Cobertura_mensual.csv', index=False, encoding='utf-8-sig')
    dest = REV / 'Objetivo'; dest.mkdir(exist_ok=True)
    (dest / 'met.SFC').write_text('\n'.join([header, *[sr[k][1] for k in target]]) + '\n', encoding='ascii')
    (dest / 'met.PFL').write_text('\n'.join(line for k in target for a, line in pr[k]) + '\n', encoding='ascii')
    save(REV / 'Recepcion_meteorologia.json', dict(estado='METEOROLOGIA_RECIBIDA_CON_DOS_FALTANTES', qa=qc,
        MMIF=qmmif, pruebas=test_results, datos_modificados=False, concentraciones_estacionales_calculadas=False,
        archivos=files([MET / n for n in ['met.IN1', 'met.IN1.original', 'met.SFC', 'met.PFL', 'met.ER1', 'met.OU1',
                                        'aermet.exe.consola.log', 'onsite.dat', 'upper.dat', 'surface.dat', 'Problemas_met.json']]) +
                  files([dest / 'met.SFC', dest / 'met.PFL'])))
    save(REV / 'Entrega_revision.json', dict(estado='REVISION_QC_CONGELADA', archivos=files([
        Path(__file__), ROOT / 'work/ejecutar_base_verano_20261021.py', BASE / 'Entrega.json',
        BASE / 'MMIF_validado.json', BASE / 'Plan.json', REV / 'Recepcion_meteorologia.json',
        REV / 'Cobertura_horaria.csv', REV / 'Cobertura_diaria.csv', REV / 'Cobertura_mensual.csv'])))
    save(BASE / 'Estado.json', dict(estado='MET_ESTACIONAL_RECIBIDA_PENDIENTE_SETUP', horas=2153,
        horas_aptas=2151, faltantes_AERMET=2, accion='CONTINUAR_PREPROCESAMIENTO_VERANO.cmd',
        detalle='Reutiliza MMIF y AERMET, conserva faltantes I71, ejecuta sólo SETUP AERMOD.',
        archivos=files([REV / 'Entrega_revision.json'])))
    print(json.dumps(qc, ensure_ascii=False, indent=2), flush=True)


def run():
    lock = BASE / 'preprocesamiento.lock'
    with lock.open('x', encoding='ascii') as f:
        f.write(str(os.getpid()))
    try:
        verify(read(REV / 'Entrega_revision.json')['archivos'])
        verify(read(BASE / 'Entrega.json')['archivos'])
        verify(read(BASE / 'MMIF_validado.json')['archivos'])
        received = read(REV / 'Recepcion_meteorologia.json'); verify(received['archivos'])
        qc = received['qa']
        done = BASE / 'Preprocesamiento.json'
        if done.exists():
            verify(read(done)['archivos']); print('Preprocesamiento estacional ya recibido.'); return
        print('Reutilizando MMIF y AERMET. 2151 horas aptas y 2 faltantes I71 documentados.', flush=True)
        setups = []
        for day, nh in [(pd.Timestamp('2016-12-21'), 24), (pd.Timestamp('2017-03-20'), 17)]:
            for pol in ['MP10', 'MP25']:
                receipt = REV / f'Recibo_SETUP_{pol}_{day:%Y%m%d}.json'
                if receipt.exists():
                    result = read(receipt); verify(result['archivos'])
                else:
                    # Carpeta por intento; una interrupción no pisa entradas/salidas previas.
                    attempt = REV / ('intento_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
                    attempt.mkdir(); shutil.copytree(REV / 'Objetivo', attempt / 'Objetivo')
                    result = original.setup(attempt, pol, day, nh, qc['ids'])
                    save(receipt, result)
                setups.append(result)
        save(done, dict(estado='METEOROLOGIA_ESTACIONAL_Y_SETUP_VERIFICADOS_CON_FALTANTES', carpeta=str(REV),
            qa=qc, setups=setups, archivos=files([REV / 'Entrega_revision.json', REV / 'Recepcion_meteorologia.json',
                REV / 'Cobertura_horaria.csv', REV / 'Cobertura_diaria.csv', REV / 'Cobertura_mensual.csv',
                REV / 'Objetivo/met.SFC', REV / 'Objetivo/met.PFL']) +
                [entry for result in setups for entry in result['archivos']]))
        save(BASE / 'Estado.json', dict(estado='BASE_ESTACIONAL_PREPROCESADO_CON_DOS_FALTANTES', horas=2153,
            horas_aptas=2151, faltantes_AERMET=2, fuentes=12263, receptores=6295,
            concentraciones_calculadas=False, calmas=0, archivos=files([done])))
        print('Cuatro SETUP verificados. Meteorología recibida con 2 faltantes explícitos; aún sin concentraciones estacionales.', flush=True)
    except Exception:
        import traceback
        save(REV / ('Fallo_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json'), dict(error=traceback.format_exc()))
        raise
    finally:
        lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('etapa', choices=['preparar', 'ejecutar'])
    args = parser.parse_args()
    {'preparar': prepare, 'ejecutar': run}[args.etapa]()
