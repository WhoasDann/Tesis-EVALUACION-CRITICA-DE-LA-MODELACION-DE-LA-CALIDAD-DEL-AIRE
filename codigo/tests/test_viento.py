import unittest
import numpy as np
from tesis.viento import a_malla, sumar_residuo, sumar_perfil
from tesis.validacion import rotar_a_tierra, componentes, direccion, diferencia_angular


class VientoTests(unittest.TestCase):
    def test_calma_y_casi_calma_sin_amplificacion(self):
        u = np.array([0., 1e-12, .001, 10.])
        v = np.zeros(4)
        newu, newv = sumar_residuo(u, v, 1., -2.)
        np.testing.assert_allclose(newu-u, 1., rtol=0, atol=1e-15)
        np.testing.assert_array_equal(newv-v, -2*np.ones(4))
        self.assertTrue(np.isfinite(newu).all())

    def test_signo_observado_menos_modelo(self):
        model = np.array([2., -3.])
        observed = np.array([-1., 4.])
        result = sumar_residuo(model[0], model[1], *(observed-model))
        np.testing.assert_array_equal(result, observed)

    def test_inversa_con_signos_y_coeficientes_float32(self):
        angle = np.deg2rad(np.array([-80., 0., 30., 179.]))
        c, s = np.cos(angle).astype('f4'), np.sin(angle).astype('f4')
        u, v = np.array([-1., 0., 2., 3.]), np.array([4., -3., 2., 1.])
        earth = rotar_a_tierra(u, v, c, s)
        recovered = a_malla(*earth, c, s)
        np.testing.assert_allclose(recovered, (u, v), rtol=0, atol=2e-15)

    def test_rotacion_no_unitaria_rechazada(self):
        with self.assertRaises(ValueError): a_malla([1], [2], [1], [1])

    def test_pesos_cero_uno_e_intermedio(self):
        u, v = np.array([10., 20., 30.]), np.array([1., 2., 3.])
        newu, newv = sumar_perfil(u, v, 2., -1., pesos=[1., .5, 0.])
        np.testing.assert_array_equal(newu-u, [2., 1., 0.])
        np.testing.assert_array_equal(newv-v, [-1., -.5, 0.])

    def test_perfil_sin_peso_implicito(self):
        with self.assertRaises(TypeError): sumar_perfil([1], [2], 1, 1)

    def test_no_recorte_de_pesos(self):
        for w in (-.01, 1.01):
            with self.assertRaises(ValueError): sumar_perfil([1], [2], 1, 1, pesos=w)

    def test_nan_inf_mascara_rechazados(self):
        for bad in (np.nan, np.inf, np.ma.array([1.], mask=[True])):
            with self.assertRaises(ValueError): sumar_residuo([1.], [2.], bad, 0.)

    def test_direction_359_1_y_componentes(self):
        obs_u, obs_v = componentes(5., 1.)
        mod_u, mod_v = componentes(5., 359.)
        u, v = sumar_residuo(mod_u, mod_v, obs_u-mod_u, obs_v-mod_v)
        self.assertAlmostEqual(float(diferencia_angular(direccion(u, v), 1.)), 0.)

    def test_cero_no_modifica_entrada(self):
        u, v = np.array([1., 2.]), np.array([3., 4.])
        newu, newv = sumar_residuo(u, v, 0, 0)
        newu[0] = 999
        np.testing.assert_array_equal(u, [1., 2.])
        np.testing.assert_array_equal(v, newv)

    def test_formas_no_expanden_silenciosamente(self):
        with self.assertRaises(ValueError): sumar_residuo([1, 2], [3, 4], [[1], [2]], 0)
        with self.assertRaises(ValueError): sumar_residuo([1, 2], [3], 0, 0)


if __name__ == '__main__': unittest.main()
