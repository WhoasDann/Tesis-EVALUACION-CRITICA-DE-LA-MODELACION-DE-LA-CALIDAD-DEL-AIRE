"""Finite-difference interaction, in concentration units, not probabilistic uncertainty."""
import numpy as np

def contrasts(df):
    q=df.copy()
    q['efecto_T_ug_m3']=q.T_PLUS-q.BASE
    q['efecto_WS_ug_m3']=q.WS_PLUS-q.BASE
    q['efecto_conjunto_ug_m3']=q.T_WS_PLUS-q.BASE
    q['suma_efectos_separados_ug_m3']=q.efecto_T_ug_m3+q.efecto_WS_ug_m3
    q['interaccion_ug_m3']=q.efecto_conjunto_ug_m3-q.suma_efectos_separados_ug_m3
    q['efecto_T_con_WS_alta_ug_m3']=q.T_WS_PLUS-q.WS_PLUS
    q['efecto_WS_con_T_alta_ug_m3']=q.T_WS_PLUS-q.T_PLUS
    q['conjunto_pct_BASE']=np.where(q.BASE>0,100*q.efecto_conjunto_ug_m3/q.BASE,np.nan)
    q['interaccion_pct_BASE']=np.where(q.BASE>0,100*q.interaccion_ug_m3/q.BASE,np.nan)
    np.testing.assert_allclose(q.efecto_T_con_WS_alta_ug_m3-q.efecto_T_ug_m3,q.interaccion_ug_m3,atol=1e-10,rtol=1e-10)
    return q
