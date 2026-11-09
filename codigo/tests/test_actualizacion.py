import unittest
import numpy as np
import pandas as pd
from tesis.reloj import a_utc,muestrear_wrf,comparar
from tesis.escenario_emisiones import construir
from tesis.geometria_line import subdividir,repartir_masas

class RelojTest(unittest.TestCase):
    def test_comparacion_usa_muestra_comun(self):
        o=pd.DataFrame({'Fecha_original':['2017-01-01 00:49','2017-01-01 01:49'],
                        'Temperatura_aire_C':[1.,2.],'Velocidad_viento_m_s':[2.,2.],'Direccion_viento_grados':[0.,0.]})
        m=pd.DataFrame({'fecha_wrf_utc':pd.date_range('2017-01-01',periods=8,freq='h'),
                        'T2_C':np.arange(8.),'u_earth_m_s':np.zeros(8),'v_earth_m_s':-np.ones(8)*2})
        r=comparar(o,m);s=r.loc[r.periodo.eq('VERANO')]
        self.assertEqual(set(s.n_comun),{2});self.assertEqual(len(s),45)
    def test_salto_dst_no_es_hueco_utc(self):
        u=a_utc(['2017-08-12 23:49','2017-08-13 01:49'],'civil_santiago')
        self.assertEqual(u[0],pd.Timestamp('2017-08-13 03:49Z'))
        self.assertEqual(u[1]-u[0],pd.Timedelta(hours=1))
    def test_invierno_y_verano_offsets_distintos(self):
        dates=['2017-07-01 12:49','2017-09-01 12:49']
        u=a_utc(dates,'civil_santiago')
        self.assertEqual(list(u.hour),[16,15]);self.assertEqual(list(u.minute),[49,49])
    def test_hora_inexistente_no_se_inventa(self):
        with self.assertRaises(Exception):a_utc(['2017-08-13 00:49'],'civil_santiago')
    def test_hora_ambigua_requiere_metadatos(self):
        with self.assertRaises(Exception):a_utc(['2017-05-13 23:49'],'civil_santiago')
    def test_interpolacion_vectorial_y_rechazo_hueco(self):
        m=pd.DataFrame({'fecha_wrf_utc':['2017-01-01 00:00','2017-01-01 01:00','2017-01-01 03:00'],
                        'T2_C':[0,60,180],'u_earth_m_s':[0,60,180],'v_earth_m_s':[60,0,-120]})
        t=pd.to_datetime(['2017-01-01 00:49Z','2017-01-01 02:00Z','2017-01-01 03:00Z','2017-01-01 04:00Z'])
        r=muestrear_wrf(m,t,operador='interpolacion_instantanea')
        self.assertAlmostEqual(r.T2_C[0],49);self.assertAlmostEqual(r.v_earth_m_s[0],11)
        self.assertTrue(np.isnan(r.T2_C[1]));self.assertEqual(r.T2_C[2],180);self.assertTrue(np.isnan(r.T2_C[3]))
    def test_vecino_distancia_explicita(self):
        m=pd.DataFrame({'fecha_wrf_utc':['2017-01-01 00:00','2017-01-01 01:00'],
                        'T2_C':[0,60],'u_earth_m_s':[0,60],'v_earth_m_s':[0,60]})
        r=muestrear_wrf(m,pd.to_datetime(['2017-01-01 00:49Z','2017-01-01 00:30Z']),operador='vecino_15min')
        self.assertEqual(r.T2_C[0],60);self.assertEqual(r.diferencia_vecino_min[0],11)
        self.assertTrue(np.isnan(r.T2_C[1]))

class EscenarioTest(unittest.TestCase):
    def setUp(self):
        self.d=pd.DataFrame([{'fecha':str(day.date()),'id_fuente_aermod':s,'id_ruta_excel':i,
                             'emision_mp10_g_dia':day.day*i} for day in pd.date_range('2017-12-01','2017-12-31') for s,i in [('R1',1),('R2',2)]])
    def test_donante_trazable_y_no_doble_control(self):
        r=construir(self.d,inicio='2016-12-21',fin='2016-12-22',politica='diciembre_mismo_dia')
        self.assertEqual(r.emision_mp10_g_dia.sum(),63)
        self.assertEqual(set(r.fecha_o_intervalo_donante),{'2017-12-21'})
    def test_promedio_por_fuente(self):
        r=construir(self.d,inicio='2016-12-21',fin='2016-12-23',politica='diciembre_promedio_mensual')
        self.assertEqual(r.emision_mp10_g_dia.sum(),96)
    def test_falta_donante_rechazada(self):
        with self.assertRaises(ValueError):construir(self.d.iloc[:-1],inicio='2016-12-31',fin='2017-01-01',politica='diciembre_mismo_dia')
    def test_otro_mes_no_se_extrapola(self):
        with self.assertRaises(ValueError):construir(self.d,inicio='2016-11-01',fin='2016-11-02',politica='diciembre_mismo_dia')
    def test_inventario_2017_se_conserva(self):
        r=construir(self.d,inicio='2017-12-01',fin='2017-12-03',politica='diciembre_mismo_dia')
        self.assertEqual(r.emision_mp10_g_dia.sum(),9)

class GeometriaTest(unittest.TestCase):
    def setUp(self):
        self.s=pd.DataFrame({'id_fuente_aermod':['R1'],'id_ruta_excel':[25],
                            'x1_utm19s_m':[0.],'y1_utm19s_m':[0.],'x2_utm19s_m':[2337.],'y2_utm19s_m':[8.]})
    def test_subdivision_cubre_eje_y_conserva_ancho(self):
        r=subdividir(self.s,ancho=3)
        self.assertEqual(len(r),8);self.assertLessEqual(r.razon_largo_ancho.max(),100)
        np.testing.assert_array_equal(r[['x2_utm19s_m','y2_utm19s_m']].to_numpy()[:-1],r[['x1_utm19s_m','y1_utm19s_m']].to_numpy()[1:])
        self.assertEqual(r.x2_utm19s_m.iloc[-1],2337);self.assertAlmostEqual(r.fraccion_masa.sum(),1)
    def test_masa_no_se_multiplica_por_hijos(self):
        r=subdividir(self.s,ancho=3)
        d=pd.DataFrame({'fecha':['2017-01-01'],'id_fuente_aermod':['R1'],'id_ruta_excel':[25],'emision_mp10_g_dia':[98765.4321]})
        out=repartir_masas(d,r)
        self.assertAlmostEqual(out.emision_mp10_g_dia.sum(),98765.4321)
        np.testing.assert_allclose(out.emision_mp10_g_dia/r.largo_line_m,out.emision_mp10_g_dia.iloc[0]/r.largo_line_m.iloc[0])
    def test_coordenadas_que_redondean_a_cero_rechazadas(self):
        self.s['x2_utm19s_m']=.001;self.s['y2_utm19s_m']=0
        with self.assertRaises(ValueError):subdividir(self.s,ancho=3)

if __name__=='__main__':unittest.main()
