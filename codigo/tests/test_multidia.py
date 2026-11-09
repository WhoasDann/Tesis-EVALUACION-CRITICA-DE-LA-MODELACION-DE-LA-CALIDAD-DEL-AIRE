from datetime import datetime,timedelta
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from tesis.multidia import ventana,etiqueta,control_mmif,revisar_met,seleccionar_met,control_aermod
from tesis.receptores import resumir

START, END = '2016-12-21','2016-12-28'


def met(root, start=START, end=END):
    _, aux, _=ventana(start,end)
    sfc=['33.156S 70.295W UA_ID: 99999 SF_ID: OS_ID: 99999 VERSION: 26135'];pfl=[]
    for stamp in aux:
        d=stamp-timedelta(hours=1);h=d.hour+1
        nums=[d.year,d.month,d.day,int(d.strftime('%j')),h,-50,.3,-9,-9,-999,400,30,.01,1,.2,6,57,10,280,2,0,0,30,673,0]
        sfc.append(' '.join(map(str,nums))+' PROG-OS NoSubs')
        for z,top,direction,speed,temp in [(2,0,999,99,7),(10,0,57,6,99),(50,1,60,7,8)]:
            pfl.append(f'{d.year} {d.month} {d.day} {h} {z} {top} {direction} {speed} {temp} 99 99')
    a=root/'met.SFC';b=root/'met.PFL'
    a.write_text('\n'.join(sfc),encoding='ascii');b.write_text('\n'.join(pfl),encoding='ascii')
    return a,b


class Multidia(unittest.TestCase):
    def test_hora_previa_lluvia_y_fin_exclusivo(self):
        target,aux,utc=ventana(START,END)
        self.assertEqual((len(target),len(aux),len(utc)),(168,216,217))
        self.assertEqual((utc[0],utc[-1]),(datetime(2016,12,20,3),datetime(2016,12,29,3)))
        self.assertEqual((etiqueta(target[0]),etiqueta(target[-1])),('16122101','16122724'))

    def test_cruce_anio_no_cambia_dia_hora24(self):
        target,_,_=ventana('2016-12-31','2017-01-02')
        self.assertEqual(etiqueta(target[23]),'16123124')
        self.assertEqual(etiqueta(target[24]),'17010101')

    def test_rechaza_limites_parciales_e_invertidos(self):
        for a,b in [('2016-12-21T01:00','2016-12-22'),(END,START),(START,START)]:
            with self.assertRaises(ValueError):ventana(a,b)

    def test_controles_tienen_fechas_distintas_para_aux_y_objetivo(self):
        text=control_mmif(['test.nc'],'MMIF',START,END)
        self.assertIn('START 2016 12 20 01',text)
        self.assertIn('STOP 2016 12 29 00',text)
        text=control_aermod('MP10',dict(SF_ID=0,UA_ID=99999,OS_ID=99999),START,END)
        self.assertIn('ME STARTEND 2016 12 21 1 2016 12 27 24',text)

    def test_seleccion_de_siete_dias_es_literal(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);a,b=met(root);before=(a.read_bytes(),b.read_bytes());dest=root/'run';dest.mkdir()
            qa=seleccionar_met(a,b,dest,START,END)
            self.assertEqual(qa['horas'],168)
            self.assertEqual((dest/'met.SFC').read_text().splitlines()[1:],a.read_text().splitlines()[25:193])
            self.assertEqual(len((dest/'met.PFL').read_text().splitlines()),168*3)
            self.assertEqual(before,(a.read_bytes(),b.read_bytes()))

    def test_falta_hora_se_detiene(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=met(Path(t));a.write_text('\n'.join(a.read_text().splitlines()[:-1]))
            with self.assertRaisesRegex(ValueError,'Cobertura'):revisar_met(a,b,START,END)

    def test_duplicado_se_detiene(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=met(Path(t));a.write_text(a.read_text()+'\n'+a.read_text().splitlines()[1])
            with self.assertRaisesRegex(ValueError,'duplicada'):revisar_met(a,b,START,END)

    def test_perfil_sin_cierre_se_detiene(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=met(Path(t));b.write_text(b.read_text().replace('50 1','50 0'))
            with self.assertRaisesRegex(ValueError,'Perfil'):revisar_met(a,b,START,END)

    def test_calma_se_registra_sin_borrarla(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=met(Path(t));a.write_text(a.read_text().replace(' 6 57 ',' 0 57 '))
            self.assertEqual(revisar_met(a,b,START,END)['calmas_objetivo'],168)

    def test_direccion_conservada_en_diagnostico(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=met(Path(t))
            self.assertTrue(all(row['WD_deg']==57 for row in revisar_met(a,b,START,END)['serie_objetivo']))

    def test_no_sobrescribe_met_original(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=met(Path(t))
            with self.assertRaisesRegex(ValueError,'sobrescribir'):seleccionar_met(a,b,Path(t),START,END)

    def test_maximo_diario_no_es_media_semanal(self):
        target,_,_=ventana(START,END);labels=[etiqueta(t) for t in target]
        data=[]
        for i,label in enumerate(labels):
            for x in (0,1):
                data.append((x,0,label,pd.to_datetime(label[:6],format='%y%m%d'),100. if i//24==x else 0.))
        d=pd.DataFrame(data,columns=['x_m','y_m','fecha_AERMOD','dia','C_ug_m3'])
        members=pd.DataFrame([('mina',0,0),('mina',1,0)],columns=['grupo','x_m','y_m'])
        _,daily,summary=resumir(d,members,labels)
        self.assertEqual(len(summary),7)
        self.assertEqual(summary.maximo_media_24h_ug_m3.tolist(),[100,100,0,0,0,0,0])
        self.assertTrue(daily.horas.eq(24).all())


if __name__=='__main__':unittest.main()
