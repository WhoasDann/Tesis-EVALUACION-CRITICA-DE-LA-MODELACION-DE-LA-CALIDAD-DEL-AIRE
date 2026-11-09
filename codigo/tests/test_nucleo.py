import unittest
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from tesis.comun import periodo
from tesis.observaciones import valor_legacy,reconciliar
from tesis.validacion import diferencia_angular,componentes,direccion,rotar_a_tierra,bilineal,alinear
from tesis.residuos import tabla_p90,bloques_validos,muestrear_bloque
from tesis.termica import temperatura_fisica,perturbar,RV_RD
from tesis.emisiones import masa_controlada,tasa_line,houremis_line,generar
from tesis.terreno import location_aermap,location_aermod,leer_cotas_aermap
from tesis.preprocesadores import horas_mmif,texto_mmif

TEST_TEMP=Path(__file__).resolve().parents[3]/'work'/'test_tmp'
TEST_TEMP.mkdir(parents=True,exist_ok=True)

class ObservacionesTest(unittest.TestCase):
    def test_tipo_numerico_vs_texto(self):
        self.assertEqual(valor_legacy(10500,'#,##0','n')[0],10.5)
        self.assertEqual(valor_legacy('0.600','General','s')[0],.6)
        self.assertEqual(valor_legacy('-0.200','General','s')[0],-.2)
    def test_tipo_desconocido_no_se_adivina(self):
        with self.assertRaises(ValueError):valor_legacy(10.5,'General','n')
    def test_conflicto_no_se_promedia(self):
        rows=[{'Fecha_original':pd.Timestamp('2017-01-01'),'Variable':'T','Valor_fisico':v,'Fuente':str(v)} for v in (1,2)]
        with self.assertRaises(ValueError):reconciliar(rows)
    def test_fechas_21_exclusivo(self):
        self.assertEqual(periodo(['2016-12-20 23:00','2016-12-21','2017-03-20 23:00','2017-03-21','2017-06-21','2017-09-21']).tolist(),['FUERA','VERANO','VERANO','FUERA','INVIERNO','FUERA'])

class VientoTest(unittest.TestCase):
    def test_cruce_norte(self):self.assertEqual(diferencia_angular([1],[359])[0],2)
    def test_convencion_meteorologica(self):
        u,v=componentes(np.ones(4),[0,90,180,270]);np.testing.assert_allclose(direccion(u,v),[0,90,180,270],atol=1e-12)
    def test_rotacion_antes_interpolar(self):
        u,v=rotar_a_tierra(np.ones((2,2)),np.zeros((2,2)),np.zeros((2,2)),np.ones((2,2)))
        self.assertEqual(bilineal(u,.5,.5),0);self.assertEqual(bilineal(v,.5,.5),1)
    def test_bilineal_plano(self):self.assertAlmostEqual(bilineal([[0,2],[3,5]],.2,.4),1.6)
    def test_fuera_malla(self):
        with self.assertRaises(ValueError):bilineal(np.zeros((2,2)),-.1,0)
    def test_signo_reloj_y_filtro(self):
        obs=pd.DataFrame({'Fecha_original':['2017-01-01 00:49'],'Temperatura_aire_C':[12.],
                          'Velocidad_viento_m_s':[.5],'Direccion_viento_grados':[1.]})
        wrf=pd.DataFrame({'fecha_wrf_utc':['2017-01-01 03:00'],'T2_C':[10.],'u_earth_m_s':[0.],'v_earth_m_s':[-2.]})
        p=alinear(obs,wrf,reloj='legacy_provisional')
        self.assertEqual(p.residuo_T_C.iloc[0],2);self.assertTrue(np.isnan(p.residuo_WD_deg.iloc[0]))
        self.assertEqual(str(p.fecha_wrf_utc.iloc[0]),'2017-01-01 03:00:00')
    def test_utc_offset_obligatorio(self):
        obs=pd.DataFrame({'Fecha_original':[]});wrf=pd.DataFrame({'fecha_wrf_utc':[]})
        with self.assertRaises(ValueError):alinear(obs,wrf,reloj='estandar_fijo')

class EstadisticaTest(unittest.TestCase):
    def test_mmif_fin_hora_y_conversion_utc(self):
        local,utc=horas_mmif('VERANO')
        self.assertEqual(len(local),2160)
        self.assertEqual(str(local[0]),'2016-12-21 01:00:00')
        self.assertEqual(str(local[-1]),'2017-03-21 00:00:00')
        self.assertEqual(str(utc[-1]),'2017-03-21 03:00:00')
    def test_mmif_parametros_referencia(self):
        text=texto_mmif([], 'INVIERNO')
        for setting in ['TIMEZONE -3','AER_MIN_SPEED 0','FSL_INTERVAL 12','AER_MIXHT WRF']:
            self.assertIn(setting,text)
    def test_p90_no_imputa(self):
        d=pd.DataFrame({'fecha_analisis':pd.date_range('2017-01-01',periods=20,freq='D'),'residuo_T_C':range(20),'residuo_WS_m_s':range(20)})
        p=tabla_p90(d);self.assertAlmostEqual(p.loc[(p.periodo=='VERANO')&(p.hora==0)&(p.variable=='T_C'),'P90_abs'].iloc[0],17.1)
        self.assertEqual(int(p.P90_abs.notna().sum()),2)
    def test_bloques_no_cruzan_huecos(self):
        t=list(pd.date_range('2017-01-01',periods=4,freq='h'))+list(pd.date_range('2017-01-01 06:00',periods=4,freq='h'))
        d=pd.DataFrame({'fecha_analisis':t,'residuo_T_C':range(8),'residuo_u_m_s':range(8),'residuo_v_m_s':range(8)})
        self.assertEqual([x.tolist() for x in bloques_validos(d,4)],[[0,1,2,3],[4,5,6,7]])
        block=muestrear_bloque(d,4,periodo_objetivo='VERANO',hora_inicio=6,semilla=1)
        self.assertEqual(block.residuo_T_C.tolist(),[4,5,6,7])
    def test_bloque_no_cruza_fin_periodo(self):
        d=pd.DataFrame({'fecha_analisis':pd.date_range('2017-03-20 22:00',periods=4,freq='h'),'residuo_T_C':0,'residuo_u_m_s':0,'residuo_v_m_s':0})
        self.assertEqual(bloques_validos(d,4),[])

class TermicaTest(unittest.TestCase):
    def test_incremento_fisico_con_humedad(self):
        theta=np.array([300.,320.]);p=np.array([70000.,50000.]);pb=np.zeros(2);q=np.array([.01,.02])
        t=theta-300;thm=theta*(1+RV_RD*q)-300
        new,new_m=perturbar(t,p,pb,2,qv=q,use_theta_m=1,thm=thm)
        # Oráculo independiente: theta * Exner, sin reutilizar temperatura_fisica.
        np.testing.assert_allclose((new+300)*(p/100000)**(2/7)-theta*(p/100000)**(2/7),2,atol=1e-12)
        np.testing.assert_allclose(new_m+300,(new+300)*(1+RV_RD*q))
    def test_escenario_cero(self):
        t=np.array([5.],dtype=np.float32);m=np.array([5.],dtype=np.float32)
        a,b=perturbar(t,70000,0,0,thm=m);np.testing.assert_array_equal(a,t);np.testing.assert_array_equal(b,m)
    def test_presion_invalida(self):
        with self.assertRaises(ValueError):temperatura_fisica(0,0,0)

class EmisionesTest(unittest.TestCase):
    def test_control_una_vez(self):self.assertAlmostEqual(masa_controlada(100,20,1,90),200)
    def test_faltante_no_es_cero(self):
        with self.assertRaises(ValueError):masa_controlada(np.nan,20,1,90)
    def test_formatos_aermap_aermod_distintos(self):
        a=location_aermap('R1',[1,2,3,4],3).split();b=location_aermod('R1',[1,2,3,4],3000).split()
        self.assertEqual(a[-1],'3.000');self.assertEqual(b[-1],'3000.000');self.assertEqual(len(a),9)
    def test_houremis_sin_ancho_ni_sigma_implicita(self):
        line=houremis_line(pd.Timestamp('2017-01-01'),24,'R1',tasa_line(1e-5,100,3))
        self.assertEqual(len(line.split()),8);self.assertGreater(float(line.split()[-1]),0)
    def test_hora_24_pertenece_al_dia_de_emision(self):
        self.assertEqual(houremis_line(pd.Timestamp('2017-01-01'),24,'R1',1).split()[2:6],['17','1','1','24'])
    def test_ids_cotas_y_emisiones(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as tmp:
            p=Path(tmp)/'aermap.src';p.write_text(location_aermod('R2',[0,0,100,0],1000))
            with self.assertRaises(ValueError):leer_cotas_aermap(p,pd.DataFrame({'id_fuente_aermod':['R1']}))
    def test_integracion_masa_serializada(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as tmp:
            p=Path(tmp);s=pd.DataFrame([{'id_fuente_aermod':'R1','id_ruta_excel':42,'x1_utm19s_m':0,'y1_utm19s_m':0,'x2_utm19s_m':100,'y2_utm19s_m':0}]);s.to_csv(p/'sources.csv',index=False)
            d=pd.DataFrame([{'fecha':'2017-01-01','id_fuente_aermod':'R1','id_ruta_excel':42,'emision_mp10_g_dia':200}]);d.to_csv(p/'daily.csv',index=False)
            (p/'aermap.src').write_text(location_aermod('R1',[0,0,100,0],3000))
            generar(p/'sources.csv',p/'daily.csv',p/'aermap.src',p/'out',inicio='2017-01-01',fin='2017-01-02',pollutant='MP10',sigma_z=0)
            lines=(p/'out'/'MP10.emi').read_text().splitlines();self.assertEqual(len(lines),24)
            self.assertAlmostEqual(sum(float(x.split()[-1])*100*3*3600 for x in lines),200,places=8)
    def test_inventario_no_se_extrapola_a_2016(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as tmp:
            p=Path(tmp);s=pd.DataFrame([{'id_fuente_aermod':'R1','id_ruta_excel':42,'x1_utm19s_m':0,'y1_utm19s_m':0,'x2_utm19s_m':100,'y2_utm19s_m':0}]);s.to_csv(p/'sources.csv',index=False)
            pd.DataFrame([{'fecha':'2017-01-01','id_fuente_aermod':'R1','id_ruta_excel':42,'emision_mp10_g_dia':1}]).to_csv(p/'daily.csv',index=False)
            (p/'aermap.src').write_text(location_aermod('R1',[0,0,100,0],3000))
            with self.assertRaises(ValueError):generar(p/'sources.csv',p/'daily.csv',p/'aermap.src',p/'out',inicio='2016-12-31',fin='2017-01-02',pollutant='MP10')

if __name__=='__main__':unittest.main(verbosity=2)
