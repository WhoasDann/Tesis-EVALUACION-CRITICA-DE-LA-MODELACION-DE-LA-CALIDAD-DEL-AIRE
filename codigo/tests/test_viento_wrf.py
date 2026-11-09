import unittest
import numpy as np
from tesis.viento_wrf import incremento_caras, a_centros, sumar_wrf
from tesis.validacion import rotar_a_tierra


class CarasTests(unittest.TestCase):
    def test_contra_solucion_densa_independiente(self):
        rng = np.random.default_rng(1701)
        for n in (1, 2, 5, 6, 81):
            d = rng.normal(size=(3, n))
            A = .5*(np.eye(n, n+1)+np.eye(n, n+1, k=1))
            g = np.concatenate([d[:, :1], .5*(d[:, :-1]+d[:, 1:]), d[:, -1:]], axis=1)
            expected = g+np.linalg.solve(A@A.T, (d-g@A.T).T).T@A
            found = incremento_caras(d, -1)
            np.testing.assert_allclose(found, expected, rtol=0, atol=5e-13)
            np.testing.assert_allclose(found@A.T, d, rtol=0, atol=5e-13)

    def test_eje_y_y_trasposicion(self):
        d = np.arange(24, dtype=float).reshape(2, 3, 4)/100
        np.testing.assert_allclose(a_centros(incremento_caras(d, -2), -2), d, atol=1e-15)

    def test_uniforme_no_introduce_alternancia(self):
        for n in (4, 5, 81):
            np.testing.assert_array_equal(incremento_caras(np.full(n, .25), 0), np.full(n+1, .25))

    def test_wrf_vector_geografico_y_pesos(self):
        rng = np.random.default_rng(13)
        u10, v10 = np.zeros((3, 5)), np.zeros((3, 5))
        us, vs = rng.normal(size=(4, 3, 6)), rng.normal(size=(4, 4, 5))
        angle = np.linspace(-.4, .4, 15).reshape(3, 5)
        c, s = np.cos(angle), np.sin(angle)
        w = np.array([1, .5, .1, 0])[:, None, None]
        fields, qa = sumar_wrf(u10, v10, us, vs, c, s, 1, -.5, pesos=w)
        su, sv = rotar_a_tierra(fields['U10'], fields['V10'], c, s)
        np.testing.assert_allclose(su, 1, atol=1e-14)
        np.testing.assert_allclose(sv, -.5, atol=1e-14)
        du, dv = rotar_a_tierra(a_centros(fields['U']-us, -1), a_centros(fields['V']-vs, -2), c, s)
        np.testing.assert_allclose(du, np.broadcast_to(w, du.shape), atol=1e-14)
        np.testing.assert_allclose(dv, np.broadcast_to(-.5*w, dv.shape), atol=1e-14)
        self.assertLess(qa['error_centros_ms'], 1e-14)
        np.testing.assert_array_equal(us[-1], fields['U'][-1])

    def test_cero_conserva_caras_originales(self):
        us = np.arange(24, dtype=float).reshape(2, 3, 4)
        vs = np.arange(24, dtype=float).reshape(2, 4, 3)
        fields, _ = sumar_wrf(np.zeros((3,3)), np.zeros((3,3)), us, vs, 1, 0, 0, 0, pesos=1)
        np.testing.assert_array_equal(fields['U'], us)
        np.testing.assert_array_equal(fields['V'], vs)

    def test_rechaza_formas_o_no_finitos(self):
        with self.assertRaises(ValueError): incremento_caras([np.nan], 0)
        with self.assertRaises(ValueError): a_centros([1], 0)
        with self.assertRaises(ValueError):
            sumar_wrf(np.zeros((2,2)), np.zeros((2,2)), np.zeros((3,2,2)), np.zeros((3,3,2)), 1, 0, 1, 0, pesos=1)


if __name__ == '__main__': unittest.main()
