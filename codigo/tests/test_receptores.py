from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
from tesis.receptores import leer_aermap, resumir


def grid(name, x, z=100):
    return f'RE GRIDCART {name} STA\n XYINC {x} 2 500 6000000 1 500\n GRIDCART {name} ELEV 1 {z} {z}\n GRIDCART {name} HILL 1 200 200\n RE GRIDCART {name} END\n'


class Receptores(unittest.TestCase):
    def parse(self, content):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'aermap.rec';p.write_text(content,encoding='ascii')
            return leer_aermap(p)

    def test_dos_grillas_y_discreto_sin_perder_segunda(self):
        rows=self.parse(grid('CG1',370000)+grid('CG2',380000)+'RE DISCCART 381128 6323667 3280 5820\n')
        self.assertEqual(len(rows),5)
        self.assertEqual(rows[-1]['redes'],['CG2'])
        self.assertEqual(sum('CG2' in r['redes'] for r in rows),2)

    def test_solape_conserva_membresias_sin_duplicar_receptor(self):
        rows=self.parse(grid('CG1',370000)+grid('CG2',370500))
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[1]['redes'],['CG1','CG2'])

    def test_solape_con_cotas_distintas_se_rechaza(self):
        with self.assertRaisesRegex(ValueError,'cotas diferentes'):
            self.parse(grid('CG1',370000)+grid('CG2',370500,101))

    def test_segunda_grilla_incompleta_no_se_ignora(self):
        with self.assertRaisesRegex(ValueError,'CG2 HILL'):
            self.parse(grid('CG1',370000)+grid('CG2',380000).replace('HILL 1 200 200','HILL 1 200'))

    def test_rechaza_unidades_y_flags_no_implementados(self):
        for content in ('RE ELEVUNIT FEET\n'+grid('CG1',370000),'RE DISCCART 1 2 100 200 1.5'):
            with self.assertRaises(ValueError):self.parse(content)

    def series(self,n=24):
        times=[f'170101{h:02d}' for h in range(1,n+1)]
        d=pd.DataFrame([(x,2,t,pd.Timestamp('2017-01-01'),100 if ((int(t[-2:])%2)==x) else 0) for x in (0,1) for t in times],columns=['x_m','y_m','fecha_AERMOD','dia','C_ug_m3'])
        m=pd.DataFrame([('MINA',0,2),('MINA',1,2),('PUNTO',0,2)],columns=['grupo','x_m','y_m'])
        return d,m,times

    def test_media_diaria_por_receptor_antes_del_maximo(self):
        d,m,t=self.series();_,daily,result=resumir(d,m,t)
        # Máximos horarios alternan entre receptores: media de máximos sería 100.
        self.assertTrue(daily.media_24h_ug_m3.eq(50).all())
        self.assertTrue(result.maximo_media_24h_ug_m3.eq(50).all())
        self.assertTrue(result.maximo_1h_ug_m3.eq(100).all())

    def test_punto_ausente_no_se_sustituye_por_vecino(self):
        d,m,t=self.series();m=m.astype({'x_m':float});m.loc[2,'x_m']=.1
        with self.assertRaisesRegex(ValueError,'exacto ausente'):resumir(d,m,t)

    def test_dia_parcial_no_se_publica_como_24h(self):
        d,m,t=self.series(17);_,daily,result=resumir(d,m,t)
        self.assertTrue(daily.media_24h_ug_m3.isna().all())
        self.assertTrue(result.maximo_media_24h_ug_m3.isna().all())
        self.assertTrue(result.horas.eq(17).all())

    def test_hueco_o_duplicado_no_pasa(self):
        d,m,t=self.series()
        with self.assertRaisesRegex(ValueError,'Cobertura'):resumir(d.iloc[1:],m,t)
        with self.assertRaisesRegex(ValueError,'duplicado'):resumir(pd.concat([d,d.iloc[:1]]),m,t)


if __name__=='__main__':unittest.main()
