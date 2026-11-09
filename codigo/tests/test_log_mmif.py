"""Regresión con el registro real que causó el falso cambio de celda."""
from pathlib import Path
import unittest
from tesis.multidia import revisar_log_mmif

LOG=(Path(__file__).parent/'fixtures/mmif_411_7dias.log').read_text(encoding='ascii')


class LogMMIF(unittest.TestCase):
    def parse(self,text=LOG):
        return revisar_log_mmif(text,'2016-12-21','2016-12-28')

    def test_registro_real_separa_esquinas_y_cinco_puntos(self):
        result=self.parse()
        self.assertEqual(result['horas_salida'],216)
        self.assertEqual(len(result['puntos']),5)
        self.assertTrue(all((v['i'],v['j'])==(43,44) for v in result['puntos'].values()))

    def test_cambio_de_esquina_no_es_cambio_de_punto(self):
        text=LOG.replace('Low-Lft I/J cell center:            6            6',
                         'Low-Lft I/J cell center:           10           12')
        self.assertNotEqual(text,LOG)
        self.assertEqual(self.parse(text),self.parse())

    def test_cambio_real_de_punto_se_rechaza(self):
        text=LOG.replace('I/J cell center:           43           44','I/J cell center:           43           45',1)
        with self.assertRaisesRegex(ValueError,'otra celda puntual'):self.parse(text)

    def test_punto_sin_celda_no_se_suplanta_por_esquina(self):
        text=LOG.replace('         I/J cell center:           43           44','',1)
        with self.assertRaisesRegex(ValueError,'sin celda'):self.parse(text)

    def test_no_acepta_solo_esquinas_y_horas(self):
        lines=[x for x in LOG.splitlines() if not ('Output 1-D point' in x or x.strip().startswith('I/J cell center:'))]
        with self.assertRaisesRegex(ValueError,'Faltan bloques'):self.parse('\n'.join(lines))

    def test_hora_omitida_o_duplicada_se_rechaza(self):
        line=next(x for x in LOG.splitlines() if 'Hourly output written' in x)
        for text in (LOG.replace(line,'',1),LOG+'\n'+line):
            with self.assertRaisesRegex(ValueError,'Cobertura'):self.parse(text)

    def test_cierre_incompleto_se_rechaza(self):
        with self.assertRaisesRegex(ValueError,'cierre normal'):
            self.parse(LOG.replace('run completed normally.','run interrupted.'))

    def test_desfase_utc_incorrecto_se_rechaza(self):
        line=next(x for x in LOG.splitlines() if 'Hourly output written' in x)
        invalid=line[:-14]+'2016122000 UTC'
        with self.assertRaisesRegex(ValueError,'Cobertura'):self.parse(LOG.replace(line,invalid,1))


if __name__=='__main__':unittest.main()
