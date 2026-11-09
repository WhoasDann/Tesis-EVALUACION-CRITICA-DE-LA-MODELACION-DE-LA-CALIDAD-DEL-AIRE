from datetime import datetime,timedelta
from pathlib import Path
import tempfile
import unittest
from tesis.cadena_corta import horas,ajustar_aermet,receptores,revisar_met,seleccionar_met_objetivo

CONTROL='''JOB
PROG
 DATA ONSITE.DAT OL
 READ 1 OSYR OSMO OSDY OSHR INSO PRCP PRES MHGT TSKC HFLX LFLX USTR ZOHT VPTG MOBL WSTR
 FORMAT 1 (I4,3I2.2,4F10.3,F10.0,2F10.3,2F10.5,3F10.3)
 RANGE PRES 7500 < 10999 99999
 RANGE MHGT 0 < 4000 9999
 AUDIT TT01 PRES MHGT TSKC
'''


def met_files(root):
    sfc=['33.156S 70.295W UA_ID: 99999 SF_ID: OS_ID: 99999 VERSION: 26135']
    pfl=[]
    for stamp in horas()[0]:
        d=stamp-timedelta(hours=1);h=d.hour+1
        nums=[d.year,d.month,d.day,int(d.strftime('%j')),h,-50,.3,-9,-9,-999,400,30,.01,1,.2,6,57,10,280,2,0,0,30,673,0]
        sfc.append(' '.join(map(str,nums))+' PROG-OS NoSubs')
        for z,top,direction,speed,temp in [(2,0,999,99,7),(10,0,57,6,99),(50,1,60,7,8)]:
            pfl.append(f'{d.year} {d.month} {d.day} {h} {z} {top} {direction} {speed} {temp} 99 99')
    a=root/'met.SFC';b=root/'met.PFL';a.write_text('\n'.join(sfc),encoding='ascii');b.write_text('\n'.join(pfl),encoding='ascii')
    return a,b


class CadenaCorta(unittest.TestCase):
    def test_reloj_y_hora_auxiliar(self):
        local,utc=horas()
        self.assertEqual((len(local),len(utc)),(72,73))
        self.assertEqual(utc[0],datetime(2016,12,31,3))
        self.assertEqual(utc[-1],datetime(2017,1,3,3))
        self.assertEqual(local[-1],datetime(2017,1,3))

    def test_aermet_omite_columna_sin_desplazar(self):
        s=ajustar_aermet(CONTROL,'AERMET')
        self.assertNotIn('MHGT',s)
        self.assertIn('3F10.3,10X,F10.0',s)
        self.assertIn('RANGE PRES 4000 < 10999 99999',s)
        # La columna que se omite es la cuarta F10.3 (posiciones 41 a 50).
        row='2017010101'+''.join(f'{v:10.3f}' for v in (10,0,6730,600))+f'{3:10.0f}'
        self.assertEqual(float(row[30:40]),6730)
        self.assertEqual(float(row[50:60]),3)

    def test_otros_metodos_retienen_mezcla(self):
        for m in ('WRF','MMIF'):
            s=ajustar_aermet(CONTROL,m)
            self.assertEqual(s.count('MHGT'),3)
            self.assertIn('4F10.3',s)

    def test_rechaza_formato_desconocido_y_doble_parche(self):
        with self.assertRaises(ValueError):ajustar_aermet(CONTROL.replace('4F10.3','5F10.3'),'AERMET')
        with self.assertRaises(ValueError):ajustar_aermet(ajustar_aermet(CONTROL,'WRF'),'WRF')

    def test_rechaza_procesamiento_sobre_agua(self):
        with self.assertRaises(ValueError):ajustar_aermet(CONTROL.replace(' OL',' OW'),'AERMET')

    def test_lee_receptores_con_filas_continuadas(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'aermap.rec'
            p.write_text('XYINC 10 2 5 20 1 5\n GRIDCART CG1 ELEV 1 100\n GRIDCART CG1 ELEV 1 101\n GRIDCART CG1 HILL 1 110 111\n')
            self.assertEqual(receptores(p),[(10,20,100,110),(15,20,101,111)])
            p.write_text(p.read_text().replace('110 111','110'))
            with self.assertRaises(ValueError):receptores(p)

    def test_met_72_horas_perfiles_celsius(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=met_files(Path(t));r=revisar_met(a,b)
            self.assertEqual(r['horas_objetivo'],24)
            self.assertEqual(r['ids']['SF_ID'],0)
            self.assertEqual(r['niveles_PFL'],[3])

    def test_rechaza_sfc_duplicado(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=met_files(Path(t));a.write_text(a.read_text()+'\n'+a.read_text().splitlines()[1])
            with self.assertRaisesRegex(ValueError,'duplicada'):revisar_met(a,b)

    def test_rechaza_perfil_sin_cierre(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=met_files(Path(t));b.write_text(b.read_text().replace('50 1','50 0'))
            with self.assertRaises(ValueError):revisar_met(a,b)

    def test_rechaza_meteorologia_faltante_objetivo(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=met_files(Path(t));a.write_text(a.read_text().replace(' 280 ',' 999 '))
            with self.assertRaises(ValueError):revisar_met(a,b)

    def test_seleccion_24h_coincide_con_emisiones_y_conserva_valores(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);a,b=met_files(root);before=(a.read_bytes(),b.read_bytes())
            dest=root/'aermod';dest.mkdir()
            qa=seleccionar_met_objetivo(a,b,dest)
            selected=(dest/'met.SFC').read_text().splitlines()
            self.assertEqual(len(selected),25)
            self.assertEqual(selected[1].split()[:5],['2017','1','1','1','1'])
            self.assertEqual(selected[-1].split()[:5],['2017','1','1','1','24'])
            self.assertEqual(selected[1:],a.read_text().splitlines()[25:49])
            profile=(dest/'met.PFL').read_text().splitlines()
            self.assertEqual(profile,b.read_text().splitlines()[24*3:48*3])
            self.assertEqual((a.read_bytes(),b.read_bytes()),before)
            self.assertEqual((qa['horas'],qa['anio_inicial']),(24,2017))

    def test_seleccion_no_sobrescribe_original(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);a,b=met_files(root)
            with self.assertRaisesRegex(ValueError,'sobrescribir'):seleccionar_met_objetivo(a,b,root)


if __name__=='__main__':unittest.main()
