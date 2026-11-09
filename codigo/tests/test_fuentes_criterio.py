import unittest, tempfile, json
from pathlib import Path
import numpy as np
import pandas as pd
from tesis.fuentes_criterio import parametrizar
from tesis.geometria_line import subdividir, repartir_masas
from tesis.emisiones import generar
from tesis.terreno import preparar, location_aermod

TEMP=Path(__file__).resolve().parents[3]/'work'/'test_tmp'

class CriterioFuentesTest(unittest.TestCase):
    def setUp(self):
        self.s=pd.DataFrame({'id_fuente_aermod':['R1','R2'],'id_ruta_excel':[1,2],
            'x1_utm19s_m':[0.,0.],'y1_utm19s_m':[0.,500.],
            'x2_utm19s_m':[2337.,150.],'y2_utm19s_m':[8.,500.]})
        self.r=pd.DataFrame({'ID':[1,2],'RED':['MINA','OTROS']})
    def test_referencia_y_vinculo_vertical(self):
        s=parametrizar(self.s,self.r)
        np.testing.assert_allclose(s.ancho_m,[16,9])
        np.testing.assert_allclose(s.altura_m,[5.95,2.55])
        np.testing.assert_allclose(s.sigma_z_m,[5.535,2.372])
    def test_ancho_no_depende_de_altura(self):
        a=parametrizar(self.s,self.r,lateral='calzada_estela',vertical='baja')
        b=parametrizar(self.s,self.r,lateral='calzada_estela',vertical='alta')
        np.testing.assert_array_equal(a.ancho_m,b.ancho_m)
        np.testing.assert_allclose(a.ancho_m,[41,16.5])
    def test_clasificacion_incompleta_rechazada(self):
        with self.assertRaises(ValueError):parametrizar(self.s,self.r.iloc[:1])
    def test_red_desconocida_rechazada(self):
        self.r.loc[0,'RED']='INVENTADA'
        with self.assertRaises(ValueError):parametrizar(self.s,self.r)
    def test_segmentos_respetan_longitud_y_parametros(self):
        s=parametrizar(self.s,self.r)
        children=subdividir(s,largo_maximo=100)
        self.assertLessEqual(children.largo_line_m.max(),100)
        for parent,part in children.groupby('id_fuente_padre'):
            self.assertTrue((part.ancho_m==s.set_index('id_fuente_aermod').loc[parent,'ancho_m']).all())
            self.assertAlmostEqual(part.fraccion_masa.sum(),1)
    def test_eje_demasiado_corto_no_se_disfraza(self):
        s=parametrizar(self.s,self.r);s.loc[0,['x2_utm19s_m','y2_utm19s_m']]=[.02,0]
        with self.assertRaises(ValueError):subdividir(s)
    def test_masa_por_fuente_con_ancho_distinto(self):
        s=subdividir(parametrizar(self.s,self.r),largo_maximo=100)
        d=pd.DataFrame({'fecha':['2017-01-01']*2,'id_fuente_aermod':['R1','R2'],
                        'id_ruta_excel':[1,2],'emision_mp10_g_dia':[100.,900.]})
        d=repartir_masas(d,s)
        with tempfile.TemporaryDirectory(dir=TEMP) as tmp:
            p=Path(tmp);s.to_csv(p/'sources.csv',index=False);d.to_csv(p/'mass.csv',index=False)
            (p/'cotas.src').write_text(''.join(location_aermod(r.id_fuente_aermod,[r.x1_utm19s_m,r.y1_utm19s_m,r.x2_utm19s_m,r.y2_utm19s_m],3000) for r in s.itertuples()))
            generar(p/'sources.csv',p/'mass.csv',p/'cotas.src',p/'out',inicio='2017-01-01',fin='2017-01-02',pollutant='MP10',parametros_por_fuente=True)
            mass={k:0. for k in s.id_fuente_aermod};m=s.set_index('id_fuente_aermod')
            for line in (p/'out'/'MP10.emi').read_text().splitlines():
                t=line.split();source=t[-2];row=m.loc[source]
                mass[source]+=float(t[-1])*row.largo_line_m*row.ancho_m*3600
            actual=pd.Series(mass).groupby(m.id_fuente_padre).sum()
            self.assertAlmostEqual(actual['R1'],100);self.assertAlmostEqual(actual['R2'],900)
            cards=[line.split() for line in (p/'out'/'fuentes_aermod.inc').read_text().splitlines() if 'SRCPARAM' in line]
            for t in cards:
                row=m.loc[t[2]];np.testing.assert_allclose(list(map(float,t[4:7])),[row.altura_m,row.ancho_m,row.sigma_z_m])
    def test_aermap_usa_ancho_por_fuente(self):
        s=parametrizar(self.s,self.r)
        with tempfile.TemporaryDirectory(dir=TEMP) as tmp:
            p=Path(tmp);s.to_csv(p/'sources.csv',index=False);(p/'dem.tif').write_bytes(b'test_placeholder_not_real_dem')
            preparar(p/'sources.csv',p/'dem.tif',p/'out',width=None)
            widths=[float(x.split()[-1]) for x in (p/'out'/'fuentes_aermap.inc').read_text().splitlines()]
            self.assertEqual(widths,[16,9])
            with self.assertRaises(ValueError):preparar(p/'sources.csv',p/'dem.tif',p/'bad',width=3)

if __name__=='__main__':unittest.main()
