"""Núcleo vectorial de prueba. No edita WRF ni define transferencia espacial/vertical.

Convención: u hacia el este, v hacia el norte; r = observado - WRF.
Los pesos del perfil son una hipótesis explícita del llamador, sin valor por defecto.
"""
import numpy as np


def _finito(value):
    arr = np.ma.asarray(value, dtype=np.float64).filled(np.nan)
    if not np.isfinite(arr).all():
        raise ValueError('Campo, incremento o peso con valores faltantes/NaN/Inf.')
    return arr


def a_malla(u_este, v_norte, cosalpha, sinalpha):
    """Inversa de la rotación grid->earth ya usada por la extracción WRF."""
    u, v, c, s = map(_finito, (u_este, v_norte, cosalpha, sinalpha))
    if u.shape != v.shape:
        raise ValueError('Componentes con formas distintas.')
    c, s = np.broadcast_to(c, u.shape), np.broadcast_to(s, u.shape)
    norm2 = c*c+s*s
    if not np.allclose(norm2, 1, rtol=0, atol=2e-6):
        raise ValueError('COSALPHA/SINALPHA no representan una rotación unitaria.')
    # Dividir por la norma sólo corrige el redondeo de los coeficientes WRF.
    return (u*c+v*s)/norm2, (v*c-u*s)/norm2


def sumar_residuo(u_este, v_norte, du_este, dv_norte):
    """Suma componentes con signo, incluso en calma; no divide por la rapidez."""
    u, v, du, dv = map(_finito, (u_este, v_norte, du_este, dv_norte))
    if u.shape != v.shape:
        raise ValueError('Componentes con formas distintas.')
    du, dv = np.broadcast_to(du, u.shape), np.broadcast_to(dv, u.shape)
    with np.errstate(over='raise', invalid='raise'):
        return u+du, v+dv


def sumar_perfil(u_este, v_norte, du_este, dv_norte, *, pesos):
    """Adición ponderada explícita sobre un perfil ya situado en puntos de masa.

    No reconstruye caras U/V staggered ni afirma plausibilidad dinámica del perfil.
    Los pesos [0,1] evitan amplificar el incremento superficial por esta función.
    No se recortan pesos ni componentes inválidos: se rechaza la llamada.
    """
    u, v, du, dv, w = map(_finito, (u_este, v_norte, du_este, dv_norte, pesos))
    if u.shape != v.shape:
        raise ValueError('Componentes con formas distintas.')
    w = np.broadcast_to(w, u.shape)
    if np.any((w < 0) | (w > 1)):
        raise ValueError('Pesos fuera de [0,1]; no se aplica recorte silencioso.')
    du, dv = np.broadcast_to(du, u.shape), np.broadcast_to(dv, u.shape)
    return sumar_residuo(u, v, du*w, dv*w)
