"""Reconstruye observaciones con tipos de celda y descargas HTML verificables.

El Excel consolidado mezcla números ampliados por 1000 y valores físicos.
No se infieren escalas por magnitud. Se lee YerbaLoca.xlsx: celdas numéricas
con formato #,##0 requieren /1000; cadenas decimales permanecen físicas.
Esta regla específica se contrasta con TODOS los solapamientos HTML.
Una discrepancia detiene la normalización; nunca se promedian conflictos.
"""
from pathlib import Path
import argparse
import math
import numpy as np
import pandas as pd
import openpyxl
from lxml import html
from .comun import sha256, guardar_json, salida_nueva, periodo, PERIODOS

COLUMNAS = ['Temperatura_aire_C', 'Humedad_pct', 'Direccion_viento_grados',
            'Presion_atmosferica_mb', 'Velocidad_viento_m_s', 'Temperatura_aire_2_C']

def valor_legacy(value, number_format, data_type):
    if value is None:
        return np.nan, 'ausente'
    if isinstance(value, str):
        txt = value.strip().replace('\xa0', '').replace(',', '.')
        # No se eliminan puntos: 0.600 representa 0.6, no 600.
        return float(txt), 'texto_decimal_fisico'
    if data_type == 'n' and number_format == '#,##0':
        return float(value) / 1000.0, 'numero_legacy_dividido_1000'
    raise ValueError(f'Codificación legacy no reconocida: {value!r}, {number_format}, {data_type}')

def leer_legacy(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    result = []
    try:
        for cells in wb.worksheets[0].iter_rows(min_row=3, max_col=8):
            if cells[1].value is None:
                continue
            date = pd.to_datetime(str(cells[1].value).strip(), format='%d/%m/%Y %H:%M')
            for col, cell in zip(COLUMNAS, cells[2:]):
                value, rule = valor_legacy(cell.value, cell.number_format, cell.data_type)
                result.append({'Fecha_original': date, 'Variable': col, 'Valor_original': cell.value,
                               'Valor_fisico': value, 'Regla': rule, 'Fuente': Path(path).name,
                               'Celda_o_fila': cell.coordinate})
    finally:
        wb.close()
    return result

def leer_html(path):
    result = []
    doc = html.fromstring(Path(path).read_bytes())
    for row_number, tr in enumerate(doc.xpath('//tbody/tr'), 1):
        fields = [' '.join(td.itertext()).strip() for td in tr.xpath('./td')]
        if len(fields) != 8:
            continue
        date = pd.to_datetime(fields[1], format='%d/%m/%Y %H:%M')
        for col, text in zip(COLUMNAS, fields[2:]):
            clean = text.strip().replace('\xa0', '').replace(',', '.')
            try:
                value = float(clean)
            except ValueError:
                if clean not in ('', '-', '--', 'S/D', 's/d'):
                    raise ValueError(f'{path}, fila {row_number}: valor desconocido {text!r}')
                value = np.nan
            result.append({'Fecha_original': date, 'Variable': col, 'Valor_original': text,
                           'Valor_fisico': value, 'Regla': 'HTML_unidad_fisica',
                           'Fuente': Path(path).name, 'Celda_o_fila': str(row_number)})
    if not result:
        raise ValueError(f'{path}: no se encontraron registros meteorológicos HTML.')
    return result

def reconciliar(records):
    long = pd.DataFrame(records)
    output = []
    for (date, variable), group in long.groupby(['Fecha_original', 'Variable'], sort=True):
        finite = group.Valor_fisico.dropna().to_numpy(float)
        if len(finite) and not np.allclose(finite, finite[0], rtol=0, atol=1e-8):
            raise ValueError(f'Conflicto no resuelto {date} {variable}: {group.to_dict("records")}')
        output.append({'Fecha_original': date, 'Variable': variable,
                       'Valor': float(finite[0]) if len(finite) else np.nan})
    tidy = pd.DataFrame(output).pivot(index='Fecha_original', columns='Variable', values='Valor').reset_index()
    sources = long.groupby('Fecha_original').Fuente.agg(lambda s: '; '.join(sorted(set(s))))
    tidy['Fuentes'] = tidy.Fecha_original.map(sources)
    return tidy, long

def preparar(folder, destination):
    folder = Path(folder)
    legacy = folder / 'YerbaLoca.xlsx'
    consolidated = folder / 'ESTERO_YERBA_CONSOLIDADO.xlsx'
    raw = sorted(folder.glob('descarga*.xls'))
    if not raw:
        raise ValueError('Se necesitan las descargas HTML originales para verificar las unidades.')
    records = leer_legacy(legacy)
    for path in raw:
        records.extend(leer_html(path))
    clean, evidence = reconciliar(records)
    old = pd.read_excel(consolidated, sheet_name='Datos_unificados')
    old['Fecha_Hora'] = pd.to_datetime(old.Fecha_Hora)
    if old.Fecha_Hora.duplicated().any() or set(old.Fecha_Hora) != set(clean.Fecha_original):
        raise ValueError('El conjunto de fechas reconstruido no coincide con el consolidado.')
    clean['Fecha_analisis_legacy'] = clean.Fecha_original + pd.Timedelta(minutes=11)
    clean['Periodo_legacy'] = periodo(clean.Fecha_analisis_legacy)
    # No se convierte a UTC: el huso y la representatividad de :49 siguen pendientes.
    clean['Estado_reloj'] = 'PROVISIONAL_obs_mas_11min_sin_conversion_UTC'
    corrections = []
    comparison = old.set_index('Fecha_Hora')
    for row in clean.to_dict('records'):
        for col in COLUMNAS:
            before = comparison.at[row['Fecha_original'], col]
            after = row[col]
            if not np.isclose(before, after, rtol=0, atol=1e-8, equal_nan=True):
                corrections.append({'Fecha_original': row['Fecha_original'], 'Variable': col,
                                    'Consolidado': before, 'Normalizado': after})
    coverage = []
    for name, (start, end) in PERIODOS.items():
        sub = clean.loc[clean.Periodo_legacy == name]
        expected = pd.date_range(start, end, freq='h', inclusive='left')
        absent = expected.difference(sub.Fecha_analisis_legacy)
        coverage.append({'periodo': name, 'inicio_inclusivo': start, 'fin_exclusivo': end,
                         'horas_esperadas': len(expected), 'horas_presentes': len(sub),
                         'horas_ausentes': len(absent), 'validos': sub[COLUMNAS].count().to_dict(),
                         'fechas_ausentes': [str(t) for t in absent]})
    paths = [legacy, consolidated] + raw
    manifest = {'estacion': '05721017-6', 'registros': len(clean),
                'fuentes': [{'path': str(p.resolve()), 'sha256': sha256(p)} for p in paths],
                'reglas_celdas': evidence.Regla.value_counts().to_dict(),
                'celdas_corregidas_consolidado': len(corrections),
                'cobertura_reloj_provisional': coverage,
                'restricciones': ['No se imputaron ausencias.', 'Junio de 2016 queda fuera de INVIERNO 2017.',
                                  'Confirmar reloj, altura de sensores y significado de temperatura 2.']}
    dest = salida_nueva(destination)
    clean.to_csv(dest / 'observaciones_normalizadas.csv', index=False, encoding='utf-8-sig')
    evidence.to_csv(dest / 'trazabilidad_por_celda.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(corrections).to_csv(dest / 'correcciones_consolidado.csv', index=False, encoding='utf-8-sig')
    guardar_json(dest / 'manifest.json', manifest)
    return manifest

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fuentes', required=True)
    p.add_argument('--salida', required=True)
    a = p.parse_args()
    result = preparar(a.fuentes, a.salida)
    print(f"Normalizados {result['registros']} registros; reloj todavía provisional.")

if __name__ == '__main__':
    main()
