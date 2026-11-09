import json,tempfile,unittest
from pathlib import Path
import pandas as pd
from tesis.preprocesadores import horas_mmif,cobertura_mmif,texto_mmif
from tesis.emisiones import generar,tasa_line
from tesis.terreno import location_aermod

TEMP=Path(__file__).resolve().parents[3]/'work/test_tmp'
TEMP.mkdir(parents=True,exist_ok=True)


class CierreEfectivoTest(unittest.TestCase):
    def test_mmif_cierre_parcial_explicito(self):
        available=pd.date_range('2016-12-01 03:00','2017-03-20 20:00',freq='h')
        r=cobertura_mmif(available,'VERANO',fin_local='2017-03-20 17:00')
        self.assertTrue(r['cobertura_completa'])
        self.assertEqual(r['horas_salida_MMIF'],2153)
        self.assertEqual(r['horas_fuera_por_cierre_efectivo'],7)
        self.assertEqual(r['ultima_salida_UTC'],'2017-03-20 20:00:00')

    def test_no_trunca_sin_decision_explicita(self):
        available=pd.date_range('2016-12-01 03:00','2017-03-20 20:00',freq='h')
        r=cobertura_mmif(available,'VERANO')
        self.assertFalse(r['cobertura_completa'])
        self.assertEqual(r['faltantes_salida_MMIF'],7)

    def test_control_mmif_termina_en_hora_efectiva(self):
        t=texto_mmif([], 'VERANO',fin_local='2017-03-20 17:00')
        self.assertIn('STOP 2017 03 20 17\n',t)
        self.assertIn('START 2016 12 21 01\n',t)

    def test_rechaza_fin_invalido(self):
        for end in ('2017-03-20 17:30','2017-03-22','2016-12-21','2017-03-20 17:00Z'):
            with self.assertRaises(ValueError):horas_mmif('VERANO',fin_local=end)

    def caso_emision(self,root,inicio,fin):
        pd.DataFrame([{'id_fuente_aermod':'R1','id_ruta_excel':1,'x1_utm19s_m':0,'y1_utm19s_m':0,
                       'x2_utm19s_m':100,'y2_utm19s_m':0}]).to_csv(root/'fuentes.csv',index=False)
        pd.DataFrame([{'fecha':d,'id_fuente_aermod':'R1','id_ruta_excel':1,'emision_mp10_g_dia':2400}
                      for d in ('2017-03-19','2017-03-20')]).to_csv(root/'diarias.csv',index=False)
        (root/'cotas.src').write_text(location_aermod('R1',[0,0,100,0],3000))
        generar(root/'fuentes.csv',root/'diarias.csv',root/'cotas.src',root/'salida',
                inicio=inicio,fin=fin,pollutant='MP10')
        lines=[x.split() for x in (root/'salida/MP10.emi').read_text().splitlines()]
        m=json.loads((root/'salida/manifest.json').read_text(encoding='utf-8'))
        return lines,m

    def test_ultimo_dia_17horas_sin_redistribuir_masa(self):
        with tempfile.TemporaryDirectory(dir=TEMP) as t:
            rows,m=self.caso_emision(Path(t),'2017-03-20 00:00','2017-03-20 17:00')
            self.assertEqual([int(x[5]) for x in rows],list(range(1,18)))
            self.assertAlmostEqual(m['masa_reconstruida_g'],1700)
            self.assertAlmostEqual(m['masa_controlada_entrada_g'],1700)
            self.assertTrue(all(abs(float(x[-1])-tasa_line(2400,100,3))<1e-13 for x in rows))

    def test_dia_completo_mas_parcial(self):
        with tempfile.TemporaryDirectory(dir=TEMP) as t:
            rows,m=self.caso_emision(Path(t),'2017-03-19','2017-03-20 17:00')
            self.assertEqual(len(rows),41)
            self.assertAlmostEqual(m['masa_controlada_entrada_g'],4100)
            self.assertEqual(m['horas_por_dia'],{'2017-03-19':24,'2017-03-20':17})

    def test_inicio_y_fin_parciales_con_horas_fin_correctas(self):
        with tempfile.TemporaryDirectory(dir=TEMP) as t:
            rows,m=self.caso_emision(Path(t),'2017-03-20 08:00','2017-03-20 17:00')
            self.assertEqual([int(x[5]) for x in rows],list(range(9,18)))
            self.assertAlmostEqual(m['masa_controlada_entrada_g'],900)


if __name__=='__main__':unittest.main()
