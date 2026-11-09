"""Termodinámica de variables de salida WRF ARW 4.3.3.

T = theta seca - 300, incluso con USE_THETA_M=1.
THM = theta seca*(1+Rv/Rd*qv)-300 cuando USE_THETA_M=1.
Perturbaciones a presión/humedad fijas son sensibilidad diagnóstica y
NO un estado atmosférico reintegrado dinámicamente.
"""
import numpy as np
from .comun import finito
KAPPA=2.0/7.0
RV_RD=461.6/287.0

def temperatura_fisica(t_pert,p,pb):
    finito(t_pert,p,pb)
    pressure=np.asarray(p)+np.asarray(pb)
    if np.any(pressure<=0):raise ValueError('Presión absoluta no positiva.')
    return (np.asarray(t_pert)+300)*(pressure/100000)**KAPPA

def perturbar(t_pert,p,pb,delta_k,*,qv=None,use_theta_m=0,thm=None):
    if use_theta_m not in (0,1):raise ValueError('USE_THETA_M debe ser 0 o 1.')
    finito(delta_k)
    base=temperatura_fisica(t_pert,p,pb)
    if np.any(base+delta_k<=0):raise ValueError('Temperatura absoluta no positiva.')
    exner=((np.asarray(p)+np.asarray(pb))/100000)**KAPPA
    # La humedad no participa en la interpretación de T.
    new=np.asarray(t_pert)+np.asarray(delta_k)/exner
    new_thm=None
    if thm is not None:
        factor=1.0
        if use_theta_m:
            if qv is None:raise ValueError('Actualizar THM húmeda requiere QVAPOR.')
            finito(qv)
            if np.any(np.asarray(qv)<0):raise ValueError('QVAPOR negativa.')
            factor=1+RV_RD*np.asarray(qv)
        expected=(np.asarray(t_pert)+300)*factor-300
        if not np.allclose(thm,expected,rtol=0,atol=.005):
            raise ValueError('T y THM de entrada no cumplen la relación documentada; revisar versión WRF.')
        # Incremento, para preservar el residuo de precisión de la entrada y delta=0.
        new_thm=np.asarray(thm)+np.asarray(delta_k)/exner*factor
    return new,new_thm
