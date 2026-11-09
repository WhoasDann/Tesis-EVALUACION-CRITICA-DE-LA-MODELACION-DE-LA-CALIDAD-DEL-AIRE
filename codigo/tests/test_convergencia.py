import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from shapely.geometry import box
from tesis.convergencia import refinar_fuentes,nuevos_receptores,repartir_houremis,clasificar_cambio


class ConvergenciaTests(unittest.TestCase):
    def sources(self):
        return pd.DataFrame([dict(id_fuente_aermod='L1',id_fuente_padre='R1',id_ruta_excel=1,
            x1_utm19s_m=0.,y1_utm19s_m=0.,x2_utm19s_m=81.37,y2_utm19s_m=23.91,
            ancho_m=16.,altura_m=5.95,sigma_z_m=5.535)])

    def test_anidado_extremos_y_parametros(self):
        s=self.sources();f=refinar_fuentes(s)
        self.assertEqual(len(f),2)
        self.assertTrue((f.largo_line_m<=50).all())
        self.assertEqual(set(f.id_fuente_padre),{'L1'})
        self.assertEqual(set(f.id_arco_original),{'R1'})
        self.assertEqual(f.x2_utm19s_m.iloc[0],f.x1_utm19s_m.iloc[1])
        self.assertTrue((f.altura_m==5.95).all())

    def test_masa_serializada_y_fuente_corta(self):
        s=self.sources();short=s.copy();short.loc[0,['x2_utm19s_m','y2_utm19s_m']]=[10.,0.]
        self.assertEqual(len(refinar_fuentes(short)),1)
        f=refinar_fuentes(s)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'in').write_text('SO HOUREMIS 16 12 21 1 L1 1.234567890123E-4\n')
            q=repartir_houremis(p/'in',p/'out',s,f,{(16,12,21,1)})
            written=[float(x.split()[-1]) for x in (p/'out').read_text().splitlines()]
            independent=sum(v*r.largo_line_m*r.ancho_m for v,r in zip(written,f.itertuples()))
            expected=1.234567890123e-4*np.hypot(81.37,23.91)*16
            self.assertAlmostEqual(independent,expected,places=11)
            self.assertLess(q['error_relativo_max_padre_hora'],1e-10)

    def test_rechaza_horas_incompletas_y_duplicadas(self):
        s=self.sources();f=refinar_fuentes(s)
        for text,hours in [('SO HOUREMIS 16 12 21 1 L1 1\n',{(16,12,21,1),(16,12,21,2)}),
                           ('SO HOUREMIS 16 12 21 1 L1 1\n'*2,{(16,12,21,1)})]:
            with tempfile.TemporaryDirectory() as d:
                p=Path(d);(p/'in').write_text(text)
                with self.assertRaises(ValueError):repartir_houremis(p/'in',p/'out',s,f,hours)

    def test_grilla_anidada_y_solapamientos(self):
        nodes=nuevos_receptores([(0,0),(500,500)],{'A':box(0,0,500,500),'B':box(250,250,500,500)},origen=(0,0))
        self.assertEqual(len(nodes),7)
        self.assertEqual(next(p for p in nodes if p['x_m']==250 and p['y_m']==250)['zonas'],['A','B'])
        self.assertEqual(len({(p['x_m'],p['y_m']) for p in nodes}),7)

    def test_criterio_y_baja_concentracion(self):
        self.assertEqual(clasificar_cambio(100,104)['estado'],'CUMPLE_CRITERIO_OPERATIVO')
        self.assertEqual(clasificar_cambio(100,106)['estado'],'REQUIERE_REFINAMIENTO')
        q=clasificar_cambio(0,1e-5)
        self.assertIsNone(q['cambio_pct']);self.assertEqual(q['estado'],'DIFERENCIA_BAJO_PRECISION_OPERATIVA')
        self.assertEqual(clasificar_cambio(0,.001)['estado'],'REQUIERE_REFINAMIENTO')


if __name__=='__main__':unittest.main()
