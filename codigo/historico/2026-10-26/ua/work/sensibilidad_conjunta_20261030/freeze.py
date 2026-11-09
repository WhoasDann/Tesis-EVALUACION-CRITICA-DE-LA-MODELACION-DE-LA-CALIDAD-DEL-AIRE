"""Check complete reproducibility contract before authorizing dispatch."""
from pathlib import Path
import sys
import pandas as pd
import numpy as np
from campaign import OUT,WORK,OLD,PILOT,SCENARIOS,read,save,sha,rec,now
from interaction import contrasts

def main():
    a=read(OUT/'Reparto.json');cases=read(OUT/'Casos.json')['cases']
    assert a['new']==728 and a['reused']==728 and len(cases)==1456
    groups={h:{c['id'] for c in cases if c['host']==h} for h in ['local','rocky','windows3','reused']}
    assert sum(map(len,groups.values()))==len(set.union(*groups.values()))==1456
    for h,v in a['hosts'].items():
        assert sha(v['plan'])==v['plan_sha256'];p=read(v['plan'])
        assert {c['id'] for c in p['cases']}==groups[h] and p['max_workers']==2
        assert p['binary_sha256']==read(read(PILOT/'Reparto.json')['hosts'][h]['plan'])['binary_sha256']
    sample=pd.DataFrame(dict(BASE=[10.,0.],T_PLUS=[12.,1.],WS_PLUS=[14.,2.],T_WS_PLUS=[18.,3.]))
    q=contrasts(sample);np.testing.assert_array_equal(q.interaccion_ug_m3,[2.,0.]);assert np.isnan(q.interaccion_pct_BASE.iloc[1])
    sys.path.insert(0,str(OLD/'work'));sys.path.insert(0,str(OLD/'outputs/Biblioteca_Tesis'))
    import salidas_estacionales_20261021 as summer
    import salidas_invierno_20261026 as winter
    save(OUT/'Pruebas_lectores.json',dict(status='PASSED',summer=summer.test_masks(),winter=winter.tests(),interaction_synthetic_additive_and_nonadditive='PASSED'))
    files=[OUT/n for n in ['Diseno.json','Reparto.json','Casos.json','Catalogo_inputs.json','Reutilizacion.json','Verificacion_meteorologia.json','Verificacion_operador.json','Comunes/membresia.csv','Comunes/receptores.inc','Calendarios/VERANO.csv','Calendarios/INVIERNO.csv']]
    files += [WORK/n for n in ['campaign.py','collect.py','supervisor.py','run_local.py','batch_runner.py','interaction.py']]
    files += [OLD/'work'/n for n in ['salidas_estacionales_20261021.py','salidas_invierno_20261026.py','ejecutar_base_verano_20261021.py']]
    files += [Path(v['plan']) for v in a['hosts'].values()]
    save(OUT/'Contrato_recepcion.json',dict(created_utc=now(),files=[rec(p) for p in files]))
    rows=['# Efecto conjunto de temperatura y rapidez del viento','','Autorizado por Daniel el 30 de octubre de 2026. Campaña independiente; preservar íntegra la entrega estacional anterior.','',
      '## Diseño','',
      'Se añade el caso T_WS_PLUS (ambas variables aumentadas) y el control WS_PLUS (solo rapidez). BASE y T_PLUS se reutilizan de la campaña completa auditada: cuatro esquinas de un diseño 2×2 con niveles BASE y +1 SD. Son 728 casos nuevos y 728 referencias reutilizadas; 1456 comparaciones caso-día, 90 fechas de verano y 92 de invierno, MP10/MP2,5, panel fijo de 40 puntos.','',
      'La rapidez es la magnitud del vector. Se calcula su discrepancia como |viento observado| − |viento WRF|; no se usa la magnitud del error vectorial ni se confunde u+ con mayor rapidez. SD muestral de promedios diarios, con al menos 18 horas válidas conjuntas, en las mismas ventanas de ajuste originales. No se aplica corrección de sesgo.','',
      '| Temporada | Delta T (°C) | Delta rapidez (m/s) | Días de ajuste |','|---|---:|---:|---:|']
    for s,v in read(OUT/'Diseno.json')['scales'].items():rows.append(f"| {s} | {v['T_C']:.6f} | {v['WS_m_s']:.6f} | {v['training_days']} |")
    rows += ['', 'Se mantiene exactamente la dirección ONSITE; se conserva velocidad cero donde la dirección no está definida. La perturbación disminuye con la altura mediante la misma función cúbica hasta la PBL BASE. T+ es idéntico al anterior. El sentido positivo se fijó antes de las nuevas concentraciones; no implica escenario probable, combinación extrema ni peor caso legal.',
      '', '## Qué se medirá','',
      'Efecto conjunto = C(T+,WS+) − C(BASE). Interacción = C(T+,WS+) − C(T+) − C(WS+) + C(BASE). Una interacción distinta de cero significa que el efecto conjunto difiere de la suma de los cambios individuales en estas condiciones. Es un contraste determinista, sin p-valores ni intervalos de confianza inferidos de fechas dependientes.',
      '', 'Diseño factorial de referencia: [NIST, diseños de dos niveles](https://www.itl.nist.gov/div898/handbook/pri/section3/pri3331.htm) y [efectos de interacción](https://itl.nist.gov/div898/handbook/pri/section5/pri594.htm). El esquema experimental no valida por sí mismo la transferencia física a ONSITE ni una distribución de incertidumbre.',
      '', '## Ejecución y recepción','', '| Equipo | Casos nuevos | Verano (fechas) | Invierno (fechas) |','|---|---:|---:|---:|']
    for h,v in a['hosts'].items():rows.append(f"| {h} | {v['assigned']} | {v['days_by_season']['VERANO']} | {v['days_by_season']['INVIERNO']} |")
    rows += ['', 'Dos procesos por equipo; lotes exclusivos. Linux debe superar cuatro pruebas nuevas contra resultados locales antes de su cola. Los canarios son controles técnicos adicionales, no parte de los 728 casos científicos nuevos. No reanudar otros lotes. En fallos, conservar intentos y utilizar STOP_AFTER_CURRENT.',
      '', 'Estado.json cuenta recibos científicos; no basta un archivo de estado antiguo. Supervisor_local.json y registros permiten verificar ejecución viva. Comprobación SSH estricta. Los productos nativos voluminosos se comprimen después de verificar hashes.',
      '', 'Las comparaciones usan las mismas horas y fechas. Invierno se reconstruye en calendario civil (92 días). El último día de verano conserva 17 horas y se excluye de estadísticas de días completos; sí aporta a la media estacional. No confundir las tablas LST operativas con medias civiles.',
      '', 'Resultados: Interaccion_periodo_comparable.csv usa horas comunes disponibles; Interaccion_diaria_LST.csv es provisional por ventana de ejecución. Al cierre, auditar todos los productos, construir Interaccion_diaria_civil.csv y gráficos con las cuatro esquinas, diferencias conjuntas e interacción en los cuatro receptores. Panel 40 sin máximos de malla completa. Sensibilidad prescrita ONSITE, no reintegración WRF ni incertidumbre calibrada.']
    (OUT/'LEEME.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    print('Frozen campaign: 728 new +728 reused; scientific reader and interaction checks PASSED',flush=True)
if __name__=='__main__':main()
