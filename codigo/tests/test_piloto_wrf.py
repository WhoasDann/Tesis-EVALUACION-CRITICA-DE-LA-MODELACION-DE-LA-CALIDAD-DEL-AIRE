import unittest,tempfile,json
from pathlib import Path
import numpy as np
import pandas as pd
from netCDF4 import Dataset
from pyproj import CRS,Transformer
from tesis.piloto_wrf import ejecutar,inspeccionar,comprobar_inventario,comprobar_cache,resumir

TEMP=Path(__file__).resolve().parents[3]/'work'/'test_tmp'
LON=-70.;LAT=-33.

def wrf(path,times,physics=8):
    with Dataset(path,'w') as n:
        for k,size in [('Time',len(times)),('DateStrLen',19),('south_north',3),('west_east',3),('bottom_top',2),('bottom_top_stag',3)]:
            n.createDimension(k,size)
        for k,v in {'TITLE':'TEST WRF','SIMULATION_START_DATE':'2016-12-01_00:00:00','START_DATE':times[0],
                    'GRID_ID':3,'MAP_PROJ':1,'DX':1000.,'DY':1000.,'TRUELAT1':-30.,'TRUELAT2':-60.,
                    'CEN_LAT':LAT,'CEN_LON':LON,'STAND_LON':LON,'MP_PHYSICS':physics}.items():setattr(n,k,v)
        t=n.createVariable('Times','S1',('Time','DateStrLen'));t[:]=np.array([list(x) for x in times],dtype='S1')
        crs=CRS.from_proj4('+proj=lcc +lat_1=-30 +lat_2=-60 +lat_0=-33 +lon_0=-70 +a=6370000 +b=6370000 +units=m')
        tr=Transformer.from_crs(crs,CRS.from_proj4('+proj=longlat +a=6370000 +b=6370000'),always_xy=True)
        xx,yy=np.meshgrid([-1000.,0.,1000.],[-1000.,0.,1000.]);lon,lat=tr.transform(xx,yy)
        for name,val in [('XLAT',lat),('XLONG',lon),('HGT',3000.),('COSALPHA',0.),('SINALPHA',1.),('T2',283.15),('U10',2.),('V10',0.)]:
            var=n.createVariable(name,'f8',('Time','south_north','west_east'));var[:]=val
            if name in ('T2','U10','V10'):var.units='K' if name=='T2' else 'm s-1'
        for name,dim in [('ZNU','bottom_top'),('ZNW','bottom_top_stag')]:
            var=n.createVariable(name,'f8',('Time',dim));var[:]=np.linspace(1,0,len(n.dimensions[dim]))

class PilotoWRFTest(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(parents=True,exist_ok=True);self.tmp=tempfile.TemporaryDirectory(dir=TEMP)
        self.root=Path(self.tmp.name);self.raw=self.root/'raw';self.raw.mkdir()
    def tearDown(self):self.tmp.cleanup()
    def file(self,name,times,physics=8):
        p=self.raw/name;wrf(p,times,physics);return p
    def run_case(self,name,fin='2016-12-21 02:00',cache=None):
        return ejecutar(self.raw,self.root/name,inicio_utc='2016-12-01 00:00',fin_utc=fin,
          corrida_id='PRUEBA',estado_origen='historica_no_confirmada',lon=LON,lat=LAT,cache=cache)
    def test_extrae_filtra_y_rota(self):
        self.file('wrfout_d03_test.nc',['2016-12-20_23:00:00','2016-12-21_00:00:00','2016-12-21_01:00:00','2016-12-21_02:00:00'])
        m=self.run_case('result');self.assertEqual(m['n_horas'],2);self.assertEqual(m['horas_ausentes'],0)
        d=pd.read_csv(self.root/'result'/'wrf_estacion.csv')
        np.testing.assert_allclose(d.T2_C,10);np.testing.assert_allclose(d.u_earth_m_s,0);np.testing.assert_allclose(d.v_earth_m_s,2)
    def test_rechaza_solape_restart(self):
        a=self.file('wrfout_d03_a',['2016-12-21_00:00:00']);b=self.file('wrfout_d03_b',['2016-12-21_00:00:00'])
        with self.assertRaisesRegex(ValueError,'duplicadas'):comprobar_inventario([inspeccionar(a),inspeccionar(b)])
    def test_rechaza_fisica_distinta_mismo_inicio(self):
        a=self.file('wrfout_d03_a',['2016-12-21_00:00:00']);b=self.file('wrfout_d03_b',['2016-12-21_01:00:00'],physics=10)
        with self.assertRaisesRegex(ValueError,'Cabecera'):comprobar_inventario([inspeccionar(a),inspeccionar(b)])
    def test_dt_adaptativo_no_confunde_corridas(self):
        a=self.file('wrfout_d03_a',['2016-12-21_00:00:00']);b=self.file('wrfout_d03_b',['2016-12-21_01:00:00'])
        with Dataset(a,'r+') as n:n.DT=4.
        with Dataset(b,'r+') as n:n.DT=3.15
        self.assertEqual(len(comprobar_inventario([inspeccionar(a),inspeccionar(b)])),2)
    def test_cache_reemplazado(self):
        a=self.file('wrfout_d03_a',['2016-12-21_00:00:00']);meta=self.run_case('old')
        with Dataset(a,'r+') as n:n['T2'][:]=285.
        with self.assertRaisesRegex(ValueError,'reemplazado'):comprobar_cache(meta,[inspeccionar(a)],corrida_id='PRUEBA',
           estado_origen='historica_no_confirmada',lon=LON,lat=LAT,spinup_days=20)
    def test_incremental_solo_nuevo_archivo(self):
        self.file('wrfout_d03_a',['2016-12-21_00:00:00','2016-12-21_01:00:00']);self.run_case('old')
        self.file('wrfout_d03_b',['2016-12-21_02:00:00','2016-12-21_03:00:00'])
        m=self.run_case('new',fin='2016-12-21 04:00',cache=self.root/'old')
        self.assertEqual(m['n_horas'],4);self.assertEqual(m['archivos_reutilizados'],['wrfout_d03_a'])
        self.assertEqual(m['archivos_extraidos_ahora'],['wrfout_d03_b'])
    def test_rechaza_otra_identidad_cache(self):
        self.file('wrfout_d03_a',['2016-12-21_00:00:00']);m=self.run_case('old');m['corrida_id']='OTRA'
        with self.assertRaisesRegex(ValueError,'otra corrida_id'):comprobar_cache(m,[],corrida_id='PRUEBA',
          estado_origen='historica_no_confirmada',lon=LON,lat=LAT,spinup_days=20)
    def test_hueco_no_se_puentea_en_lag(self):
        d=pd.DataFrame({'fecha_wrf_utc':pd.to_datetime(['2016-12-21 00:00','2016-12-21 02:00']),
          'archivo':['a','b'],'T2_C':[1.,2.],'u_earth_m_s':[1.,2.],'v_earth_m_s':[1.,2.]})
        q,cycle,day,lag=resumir(d,pd.Timestamp('2016-12-21'),pd.Timestamp('2016-12-21 03:00'))
        self.assertEqual(q.presente.sum(),2);self.assertEqual(len(q),3)
        self.assertTrue((lag.loc[lag.lag_horas==1,'n_pares']==0).all())
    def test_filtro_todo_spinup_rechazado(self):
        self.file('wrfout_d03_a',['2016-12-01_00:00:00'])
        with self.assertRaisesRegex(ValueError,'spin-up'):self.run_case('out',fin='2016-12-02')

if __name__=='__main__':unittest.main()
