"""Adaptador numérico de incrementos vectoriales a las caras U/V de WRF.

Opera sobre arrays de un instante. No modifica archivos ni el viento vertical W.
La transferencia al perfil sigue siendo un peso explícito del llamador.
"""
import numpy as np
from .viento import _finito, a_malla, sumar_residuo, sumar_perfil
from .validacion import rotar_a_tierra


def a_centros(caras, eje):
    a = _finito(caras)
    axis = np.core.numeric.normalize_axis_index(eje, a.ndim)
    if a.shape[axis] < 2:
        raise ValueError('Se necesitan al menos dos caras.')
    lo, hi = [slice(None)]*a.ndim, [slice(None)]*a.ndim
    lo[axis], hi[axis] = slice(None, -1), slice(1, None)
    return .5*(a[tuple(lo)]+a[tuple(hi)])


def incremento_caras(incremento_centros, eje):
    """Reconstrucción exacta cercana a la interpolación entre centros.

    min ||s-g||² sujeto a A s = d, con A promedio de caras adyacentes.
    g interpola d entre centros, conserva extremos; corrección Aᵀ(AAᵀ)⁻¹(d-Ag).
    No modifica la componente alternante del viento original.
    """
    d = _finito(incremento_centros)
    axis = np.core.numeric.normalize_axis_index(eje, d.ndim)
    if not d.shape[axis]:
        raise ValueError('Eje vacío.')
    m = np.moveaxis(d, axis, 0)
    n = len(m)
    g = np.empty((n+1,)+m.shape[1:], dtype='f8')
    g[0], g[-1] = m[0], m[-1]
    g[1:-1] = .5*(m[:-1]+m[1:])
    residual = m-.5*(g[:-1]+g[1:])
    r = residual.reshape(n, -1)
    diagonal = np.empty(n)
    rhs = np.empty_like(r)
    diagonal[0], rhs[0] = .5, r[0]
    for k in range(1, n):
        mult = .25/diagonal[k-1]
        diagonal[k] = .5-mult*.25
        rhs[k] = r[k]-mult*rhs[k-1]
    lam = np.empty_like(rhs)
    lam[-1] = rhs[-1]/diagonal[-1]
    for k in range(n-2, -1, -1):
        lam[k] = (rhs[k]-.25*lam[k+1])/diagonal[k]
    lam = lam.reshape(m.shape)
    g[0] += .5*lam[0]
    g[-1] += .5*lam[-1]
    g[1:-1] += .5*(lam[:-1]+lam[1:])
    result = _finito(np.moveaxis(g, 0, axis))
    if not np.allclose(a_centros(result, axis), d, rtol=0, atol=1e-10):
        raise ValueError('No se recuperó el incremento en puntos de masa.')
    return result


def sumar_wrf(u10, v10, u_caras, v_caras, cosalpha, sinalpha, du_este, dv_norte, *, pesos):
    """Un instante WRF, incremento superficial y pesos de perfil declarados.

    Devuelve U10,V10,U,V nuevos en float64 y diagnóstico de incrementos.
    El llamador debe verificar redondeo, variables ajenas y metadatos al guardar.
    """
    u10, v10, us, vs = map(_finito, (u10, v10, u_caras, v_caras))
    if u10.ndim != 2 or u10.shape != v10.shape or us.ndim != 3 or vs.ndim != 3:
        raise ValueError('Se espera superficie[y,x] y caras[z,y,x].')
    nz, ny, nx = us.shape[0], *u10.shape
    if us.shape != (nz, ny, nx+1) or vs.shape != (nz, ny+1, nx):
        raise ValueError('Las caras U/V no corresponden a la grilla de superficie.')
    # Validar rotación y formas antes de aplicar incrementos.
    a_malla(u10, v10, cosalpha, sinalpha)
    eu10, ev10 = rotar_a_tierra(u10, v10, cosalpha, sinalpha)
    nu10, nv10 = sumar_residuo(eu10, ev10, du_este, dv_norte)
    gu10, gv10 = a_malla(nu10, nv10, cosalpha, sinalpha)
    um, vm = a_centros(us, -1), a_centros(vs, -2)
    eu, ev = rotar_a_tierra(um, vm, cosalpha, sinalpha)
    nu, nv = sumar_perfil(eu, ev, du_este, dv_norte, pesos=pesos)
    dgu, dgv = a_malla(nu-eu, nv-ev, cosalpha, sinalpha)
    delta_u, delta_v = incremento_caras(dgu, -1), incremento_caras(dgv, -2)
    out_u, out_v = us+delta_u, vs+delta_v
    back_u, back_v = rotar_a_tierra(a_centros(out_u, -1), a_centros(out_v, -2), cosalpha, sinalpha)
    error = float(max(np.max(np.abs(back_u-nu)), np.max(np.abs(back_v-nv))))
    if error > 1e-9:
        raise ValueError('La reconstrucción de caras cambió el incremento vectorial objetivo.')
    return {'U10': gu10, 'V10': gv10, 'U': _finito(out_u), 'V': _finito(out_v)}, {
        'error_centros_ms': error,
        'incremento_U_cara_max_ms': float(np.max(np.abs(delta_u))),
        'incremento_V_cara_max_ms': float(np.max(np.abs(delta_v))),
        'incremento_vector_centros_max_ms': float(np.max(np.hypot(nu-eu, nv-ev)))}
