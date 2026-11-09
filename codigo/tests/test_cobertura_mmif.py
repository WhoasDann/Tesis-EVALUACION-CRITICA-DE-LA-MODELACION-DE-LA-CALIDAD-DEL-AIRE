import unittest,json,tempfile
from pathlib import Path
import pandas as pd
from tesis.preprocesadores import horas_mmif,cobertura_mmif,preparar_desde_inventario


class CoberturaMMIF(unittest.TestCase):
    def setUp(self):
        self.local,self.utc=horas_mmif('VERANO')

    def test_verano_90_dias_fin_hora(self):
        self.assertEqual(len(self.utc),2160)
        self.assertEqual(self.local[0],pd.Timestamp('2016-12-21 01:00'))
        self.assertEqual(self.utc[-1],pd.Timestamp('2017-03-21 03:00'))

    def test_fin_exclusivo_analitico_requiere_etiqueta_final_mmif(self):
        # Intervalo analítico [inicio,fin): su última media horaria termina en fin.
        available=pd.date_range('2016-12-21 03:00','2017-03-21 02:00',freq='h')
        c=cobertura_mmif(available,'VERANO')
        self.assertFalse(c['cobertura_completa'])
        self.assertEqual(c['faltantes_entrada_UTC'],['2017-03-21 03:00:00'])

    def test_requiere_previa_lluvia_aunque_todas_salidas_presentes(self):
        c=cobertura_mmif(self.utc,'VERANO')
        self.assertEqual(c['faltantes_salida_MMIF'],0)
        self.assertFalse(c['hora_previa_presente'])
        self.assertFalse(c['cobertura_completa'])

    def test_detecta_ultimo_dia_ausente(self):
        available=pd.date_range('2016-12-01 03:00','2017-03-20 03:00',freq='h')
        c=cobertura_mmif(available,'VERANO')
        self.assertEqual(c['faltantes_salida_MMIF'],24)
        self.assertEqual(c['faltantes_entrada_UTC'][0],'2017-03-20 04:00:00')
        self.assertEqual(c['faltantes_entrada_UTC'][-1],'2017-03-21 03:00:00')

    def test_completo_con_previa(self):
        c=cobertura_mmif(pd.date_range('2016-12-21 03:00','2017-03-21 03:00',freq='h'),'VERANO')
        self.assertTrue(c['cobertura_completa'])
        self.assertEqual(c['instantes_entrada_incluida_lluvia'],2161)

    def test_rechaza_duplicados_y_minutos(self):
        with self.assertRaises(ValueError):cobertura_mmif(self.utc.append(self.utc[:1]),'VERANO')
        with self.assertRaises(ValueError):cobertura_mmif(self.utc+pd.Timedelta(minutes=1),'VERANO')

    def test_utc_con_zona_equivalente(self):
        c=cobertura_mmif(self.utc.tz_localize('UTC').tz_convert('America/Santiago'),'VERANO')
        self.assertEqual(c['faltantes_salida_MMIF'],0)
        self.assertEqual(c['faltantes_entrada_UTC'],['2016-12-21 03:00:00'])

    def crear_inventario_incompleto(self,root):
        f=root/'entrada';f.write_bytes(b'contenido de prueba')
        st=f.stat()
        inv=root/'inventario.json'
        inv.write_text(json.dumps([{'path':str(f),'archivo':f.name,'bytes':st.st_size,
            'mtime_ns':st.st_mtime_ns,'sha256':'hash auditado de prueba','huella_cabecera_malla':'malla',
            'times':[str(t) for t in pd.date_range('2016-12-01 03:00','2017-03-20 03:00',freq='h')]}]),encoding='utf-8')
        return inv,f

    def test_incompleto_guarda_diagnostico_sin_control_ejecutable(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);inv,_=self.crear_inventario_incompleto(root)
            result=preparar_desde_inventario(inv,root/'salida','VERANO')
            self.assertFalse(result['control_ejecutable_generado'])
            self.assertEqual(result['faltantes_salida_MMIF'],24)
            self.assertTrue((root/'salida/cobertura.json').is_file())
            self.assertFalse((root/'salida/mmif.inp').exists())

    def test_rechaza_archivo_cambiado_desde_inventario(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);inv,f=self.crear_inventario_incompleto(root)
            f.write_bytes(b'nuevo contenido y longitud')
            with self.assertRaisesRegex(ValueError,'cambiado'):
                preparar_desde_inventario(inv,root/'salida','VERANO')


if __name__=='__main__':unittest.main()
