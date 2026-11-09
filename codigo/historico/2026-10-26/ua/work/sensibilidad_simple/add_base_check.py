from pathlib import Path
p=Path('work/sensibilidad_simple/receive_sensitivity.py')
s=p.read_text(encoding='utf-8')
needle=" grouped=data.groupby(['x_m','y_m']).C_ug_m3.agg(['sum','mean','max','count']).reset_index()"
replacement=""" if c['scenario']=='BASE':
  oldroot=ROOT/'outputs/Piloto_conjunto_14dias_2026-10-27'
  oldreceipt=oldroot/'Recibos'/(c['id']+'.json')
  if oldreceipt.exists():
   oldfolder=oldroot/'Lotes/panel'/c['folder'];previous=read(oldreceipt)
   assert sha(oldfolder/'receptor_horas.out')==previous['outputs']['receptor_horas.out']
   previous_hourly=summer.postfile(oldfolder/'receptor_horas.out')
   new_hourly=summer.postfile(folder/'receptor_horas.out')
   pd.testing.assert_frame_equal(previous_hourly,new_hourly,check_exact=True)
   qa['BASE_matches_previous_pilot_all_hourly_values']=True
"""+needle
assert needle in s;s=s.replace(needle,replacement);p.write_text(s,encoding='utf-8')

