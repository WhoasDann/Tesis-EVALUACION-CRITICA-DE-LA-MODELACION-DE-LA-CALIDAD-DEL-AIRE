"""Lee AERMOD con cobertura explícita y resume primero por receptor."""
from pathlib import Path
import re
import numpy as np
import pandas as pd
import ejecutar_base_verano_20261021 as base
from tesis.receptores import leer_aermap

COLS = ['x_m', 'y_m', 'C_bruta_ug_m3', 'elev_m', 'hill_m', 'flag', 'average', 'group', 'fecha_AERMOD']


def postfile(path):
    return pd.read_csv(path, sep=r'\s+', comment='*', names=COLS, usecols=range(9), dtype={'fecha_AERMOD': str})


def summarize(data, members, calendar_hours):
    check = base.check
    check(not members.duplicated(['grupo', 'x_m', 'y_m']).any(), 'Membresía duplicada')
    points = data.groupby(['x_m', 'y_m'], sort=True).C_ug_m3.agg(['sum', 'mean', 'max', 'count']).reset_index()
    points.columns = ['x_m', 'y_m', 'suma_horaria_ug_m3', 'media_disponible_ug_m3', 'maximo_1h_ug_m3', 'horas_validas']
    check(points.horas_validas.nunique() == 1 and points.horas_validas.iloc[0] > 0, 'Cobertura desigual o sin horas válidas')
    points['horas_calendario'] = calendar_hours
    points['media_24h_ug_m3'] = points.media_disponible_ug_m3.where((calendar_hours == 24) & points.horas_validas.ge(18))
    points['media_24h_nativa_esperada_ug_m3'] = (
        points.suma_horaria_ug_m3 / np.maximum(points.horas_validas, 18) if calendar_hours == 24 else np.nan)
    joined = members.merge(points, on=['x_m', 'y_m'], how='left', validate='many_to_one')
    check(joined.horas_validas.notna().all(), 'Receptor de membresía ausente')
    zones = []
    for name, group in joined.groupby('grupo', sort=True):
        row = group.sort_values(['media_disponible_ug_m3', 'x_m', 'y_m'], ascending=[False, True, True]).iloc[0]
        zones.append(dict(grupo=name, n_receptores=len(group), horas_calendario=calendar_hours,
            horas_validas=int(row.horas_validas), maximo_media_disponible_ug_m3=float(row.media_disponible_ug_m3),
            maximo_media_24h_ug_m3=float(row.media_24h_ug_m3),
            maximo_1h_ug_m3=float(group.maximo_1h_ug_m3.max()),
            x_maximo_media_m=float(row.x_m), y_maximo_media_m=float(row.y_m)))
    return points, joined, pd.DataFrame(zones)


def receive(folder, mask, members, sources=12263, receptors=6295):
    folder = Path(folder); check = base.check
    check(len(mask) > 0 and mask.dia.nunique() == 1 and not mask.fin_local.duplicated().any(), 'Máscara diaria inválida')
    mask = mask.copy()
    end = pd.to_datetime(mask.fin_local)
    mask['fecha_AERMOD'] = pd.to_datetime(mask.dia).dt.strftime('%y%m%d') + end.dt.hour.replace(0, 24).map('{:02d}'.format)
    check(set(mask.estado) <= {'VALIDA', 'CALMA', 'FALTANTE_AERMET_I71'}, 'Estado meteorológico no reconocido')
    text = (folder / 'aermod.out').read_text(encoding='ascii')
    fatal = re.findall(r'A Total of\s+(\d+)\s+Fatal Error', text)
    check('AERMOD Finishes Successfully' in text and fatal and not any(map(int, fatal)), 'AERMOD no terminó correctamente')
    sizes = re.search(r'This Run Includes:\s+(\d+) Source\(s\);\s+\d+ Source Group\(s\); and\s+(\d+) Receptor\(s\)', text)
    check(sizes and tuple(map(int, sizes.groups())) == (sources, receptors), 'Dimensiones incorrectas')
    check(re.search(r'Output Units\s*=\s*MICROGRAMS/M\*\*3', text), 'Unidades incorrectas')
    summary = (folder / 'resumen.sum').read_text(encoding='ascii')
    counts = {}
    for name in ['Hours Were Processed', 'Calm Hours Identified', 'Missing Hours Identified']:
        m = re.search(r'A Total of\s+(\d+)\s+' + name, summary)
        check(m is not None, 'Sin recuento: ' + name); counts[name] = int(m[1])
    expected = [len(mask), int(mask.estado.eq('CALMA').sum()), int(mask.estado.str.startswith('FALTANTE').sum())]
    check(list(counts.values()) == expected, 'Recuentos nativos distintos de máscara meteorológica')
    data = postfile(folder / 'receptor_horas.out')
    check(data.average.eq('1-HR').all() and data.group.eq('ALL').all(), 'Promedio/grupo inesperado')
    check(np.isfinite(data[COLS[:6]]).all().all() and data.C_bruta_ug_m3.ge(0).all() and data.flag.eq(0).all(), 'POSTFILE inválido')
    check(len(data) == receptors * len(mask) and set(data.fecha_AERMOD) == set(mask.fecha_AERMOD), 'POSTFILE incompleto')
    check(not data.duplicated(['x_m', 'y_m', 'fecha_AERMOD']).any(), 'Receptor/hora duplicado')
    pts = pd.DataFrame(leer_aermap(folder / 'receptores.inc'))
    joined = data.merge(pts, on=['x_m', 'y_m'], validate='many_to_one', suffixes=('', '_esperado'), how='left')
    check(len(pts) == receptors and joined.elev_m_esperado.notna().all(), 'Coordenadas inesperadas')
    check(np.allclose(joined[['elev_m', 'hill_m']], joined[['elev_m_esperado', 'hill_m_esperado']], rtol=0, atol=.011), 'Cotas inesperadas')
    check(data.groupby(['x_m', 'y_m']).size().eq(len(mask)).all(), 'Cobertura desigual por receptor')
    data = data.merge(mask[['fecha_AERMOD', 'estado']], on='fecha_AERMOD', validate='many_to_one')
    valid = data.estado.eq('VALIDA')
    check(data.loc[~valid, 'C_bruta_ug_m3'].eq(0).all(), 'Salida de faltante/calmas no coincide con cero interno esperado')
    data['C_ug_m3'] = data.C_bruta_ug_m3.where(valid)
    points, member_points, zones = summarize(data, members, len(mask))
    max1 = float(points.maximo_1h_ug_m3.max())
    m = re.search(r'SUMMARY OF HIGHEST\s+1-HR RESULTS.*?ALL\s+HIGH\s+1ST HIGH VALUE IS\s+([\d.]+)', summary, re.S)
    check(m and np.isclose(float(m[1]), max1, rtol=0, atol=1.1e-5), 'Máximo horario nativo distinto')
    error24 = None
    if len(mask) == 24:
        native = postfile(folder / 'receptor_24h.out')
        check(len(native) == receptors and native.average.eq('24-HR').all() and native.group.eq('ALL').all(), 'POSTFILE24 incompleto')
        check(native.fecha_AERMOD.eq(str(mask.fecha_AERMOD.iloc[0])[:6] + '24').all(), 'Fecha POSTFILE24 distinta')
        comparison = points.merge(native, on=['x_m', 'y_m'], validate='one_to_one')
        check(len(comparison) == receptors, 'Receptores POSTFILE24 distintos')
        error24 = float(abs(comparison.C_bruta_ug_m3 - comparison.media_24h_nativa_esperada_ug_m3).max())
        check(error24 <= 1.1e-5, 'Media diaria distinta de POSTFILE24, revisar denominador')
    qa = dict(horas_calendario=len(mask), horas_validas=int(mask.estado.eq('VALIDA').sum()),
              recuentos_nativos=counts, valores_horarios=len(data), valores_enmascarados=int((~valid).sum()),
              maximo_1h_ug_m3=max1, error_max_POSTFILE24=error24, fuentes=sources, receptores=receptors)
    return qa, data, points, member_points, zones


def test_masks():
    root = base.OUT / 'Revision_QC_2026-10-21'
    evidence = base.read(root / 'Prueba_faltantes_AERMOD/Verificacion.json')
    mask = pd.read_csv(root / 'Cobertura_horaria.csv')
    result = []
    for case in evidence['casos']:
        base.verify(case['archivos'])
        folder = Path(case['archivos'][0]['path']).parent
        selected = mask.loc[mask.dia.eq(case['dia']) & pd.to_datetime(mask.fin_local).dt.hour.between(19, 21)]
        members = pd.DataFrame([dict(grupo='GENERAL', x_m=380148., y_m=6331485.)])
        qa, data, pts, _, _ = receive(folder, selected, members, sources=1, receptors=1)
        check = base.check
        check(qa['valores_enmascarados'] == 1 and data.C_ug_m3.isna().sum() == 1 and pts.horas_validas.iloc[0] == 2,
              'Máscara no excluye exactamente el faltante')
        bad = selected.copy(); bad['estado'] = 'VALIDA'
        try:
            receive(folder, bad, members, sources=1, receptors=1)
        except ValueError:
            pass
        else:
            raise AssertionError('Se aceptó el faltante como cero válido')
        result.append(qa)
    toy = pd.DataFrame({'x_m': [0, 0, 1, 1], 'y_m': [0, 0, 0, 0], 'C_ug_m3': [10., 0., 0., 10.]})
    members = pd.DataFrame({'grupo': ['Z', 'Z'], 'x_m': [0, 1], 'y_m': [0, 0]})
    _, _, zones = summarize(toy, members, 2)
    assert zones.maximo_media_disponible_ug_m3.iloc[0] == 5
    assert zones.maximo_1h_ug_m3.iloc[0] == 10
    one_member = pd.DataFrame({'grupo': ['Z'], 'x_m': [0], 'y_m': [0]})
    missing_day = pd.DataFrame({'x_m': [0] * 24, 'y_m': [0] * 24, 'C_ug_m3': [10.] * 23 + [np.nan]})
    points, _, _ = summarize(missing_day, one_member, 24)
    assert points.horas_validas.iloc[0] == 23 and points.media_24h_ug_m3.iloc[0] == 10
    assert points.media_24h_nativa_esperada_ug_m3.iloc[0] == 10
    partial = missing_day.iloc[:17].copy()
    points, _, _ = summarize(partial, one_member, 17)
    assert points.horas_validas.iloc[0] == 17 and points.media_24h_ug_m3.isna().all()
    assert points.media_24h_nativa_esperada_ug_m3.isna().all() and points.media_disponible_ug_m3.iloc[0] == 10
    return dict(pruebas_nativas_mascara=result, rechaza_cero_faltante=True, promedio_antes_de_maximo=True,
                denominador_23h=True, parcial_17h_sin_media24h=True)


if __name__ == '__main__':
    print(test_masks())
