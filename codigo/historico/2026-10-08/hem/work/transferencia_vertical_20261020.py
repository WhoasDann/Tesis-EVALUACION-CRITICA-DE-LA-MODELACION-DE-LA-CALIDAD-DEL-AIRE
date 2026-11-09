"""Operador diagnóstico de viento en una columna, limitado por PBLH de BASE.

No estima covarianza espacial ni modifica WRF. El peso es una hipótesis explícita,
no un resultado atribuido a la EPA o validado con la estación.
"""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd
from netCDF4 import Dataset, chartostring

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/Transferencia_vertical_2026-10-20"
WIND = ROOT / "outputs/Prueba_viento_NetCDF_2026-10-15"
sys.path.insert(0, str(ROOT / "outputs/Biblioteca_Tesis"))
from tesis.comun import sha256, guardar_json


def pesos_pbl(z_agl, pblh, altura_referencia=10.0):
    z = np.asarray(z_agl, dtype=float)
    h = np.asarray(pblh, dtype=float)
    if not np.isfinite(z).all() or not np.isfinite(h).all() or not np.isfinite(altura_referencia):
        raise ValueError("Alturas no finitas.")
    if altura_referencia <= 0 or (z < 0).any() or (h <= altura_referencia).any():
        raise ValueError("Se requiere PBLH > altura de referencia positiva, y z >= 0.")
    s = np.clip((z - altura_referencia) / (h - altura_referencia), 0, 1)
    return 1 - 3*s*s + 2*s*s*s


def perturbar_columna(u, v, z, h, du, dv):
    u, v = np.asarray(u, float), np.asarray(v, float)
    w = pesos_pbl(z, h)
    if u.shape != v.shape or u.shape != w.shape:
        raise ValueError("U, V y alturas deben compartir forma.")
    if not np.isfinite(u).all() or not np.isfinite(v).all() or not np.isfinite([du, dv]).all():
        raise ValueError("Viento o perturbación no finitos.")
    return u + w*du, v + w*dv, w


def tests():
    z = np.array([0., 2., 10., 30., 50., 90., 110., 1000.])
    w = pesos_pbl(z, 110.)
    assert np.all(np.diff(w) <= 0) and (w[:3] == 1).all() and (w[-2:] == 0).all()
    u, v = np.zeros_like(z), np.zeros_like(z)
    a, b, _ = perturbar_columna(u, v, z, 110, 1, -.5)
    c, d, _ = perturbar_columna(a, b, z, 110, -1, .5)
    np.testing.assert_allclose(c, u, atol=1e-15); np.testing.assert_allclose(d, v, atol=1e-15)
    a, b, _ = perturbar_columna(u, v, z, 110, 0, 0)
    np.testing.assert_array_equal(a, u); np.testing.assert_array_equal(b, v)
    for h in (10., 0., float("nan")):
        try: pesos_pbl(z, h)
        except ValueError: pass
        else: raise AssertionError("Se aceptó una capa límite inválida.")
    return {"calmas_sin_division": True, "perturbacion_cero_identidad": True,
            "signo_reversible": True, "peso_unidad_superficial": True,
            "peso_nulo_sobre_PBLH": True, "monotonia": True, "PBLH_invalida_rechazada": True}


def main():
    if OUT.exists():
        raise FileExistsError("No sobrescribir la evaluación del operador.")
    checks = tests()
    records, inputs = [], []
    plan = json.loads((WIND / "Plan.json").read_text(encoding="utf-8"))
    expected = {Path(r["path"]): r["sha256"] for r in plan["copias"] if Path(r["path"]).parent.name == "BASE"}
    for path in sorted(expected):
        assert sha256(path) == expected[path]
        inputs.append({"path": str(path), "sha256": expected[path]})
        with Dataset(path) as n:
            n.set_auto_mask(False)
            times = pd.to_datetime(chartostring(n["Times"][:]).tolist(), format="%Y-%m-%d_%H:%M:%S", utc=True)
            for k, date in enumerate(times):
                zf = (np.asarray(n["PH"][k, :, 43, 42], float) + np.asarray(n["PHB"][k, :, 43, 42], float)) / 9.81 - float(n["HGT"][k, 43, 42])
                zm = (zf[1:] + zf[:-1]) / 2
                assert np.all(np.diff(zm) > 0)
                h = float(n["PBLH"][k, 43, 42])
                # Componentes terrestres: desescalonar antes de rotar.
                ug = np.asarray(n["U"][k, :, 43, 42:44], float).mean(axis=-1)
                vg = np.asarray(n["V"][k, :, 43:45, 42], float).mean(axis=-1)
                c = float(n["COSALPHA"][k, 43, 42]); s = float(n["SINALPHA"][k, 43, 42])
                assert abs(c*c + s*s - 1) < 1e-6
                u, v = c*ug - s*vg, s*ug + c*vg
                un, vn, w = perturbar_columna(u, v, zm, h, 1., -.5)
                np.testing.assert_allclose(un-u, w, atol=1e-13)
                np.testing.assert_allclose(vn-v, -.5*w, atol=1e-13)
                assert np.array_equal(un[zm >= h], u[zm >= h])
                assert np.array_equal(vn[zm >= h], v[zm >= h])
                for level in range(len(zm)):
                    records.append(dict(fecha_utc=str(date), nivel=level, z_agl_m=zm[level], PBLH_m=h,
                        peso=w[level], u_BASE_m_s=u[level], v_BASE_m_s=v[level],
                        u_acotado_m_s=un[level], v_acotado_m_s=vn[level],
                        delta_u_uniforme=1., delta_v_uniforme=-.5))
    data = pd.DataFrame(records)
    assert data.fecha_utc.nunique() == 97 and len(data) == 97*59
    OUT.mkdir()
    data.to_csv(OUT / "Perfiles_diagnosticos.csv", index=False, encoding="utf-8-sig")
    hourly = data.groupby("fecha_utc").agg(PBLH_m=("PBLH_m", "first"),
        niveles_modificados=("peso", lambda a: int((a>0).sum())),
        altura_ultima_modificada_m=("z_agl_m", lambda a: float(a[data.loc[a.index, "peso"]>0].max())))
    hourly.to_csv(OUT / "Alcance_por_hora.csv", encoding="utf-8-sig")
    config = dict(estado="OPERADOR_DIAGNOSTICO_VERIFICADO_EN_COLUMNA", fecha="2026-10-20",
        operador="s=clip((z-10)/(H_BASE-10),0,1); w=1-3s²+2s³; (u*,v*)=(u,v)+w*(du,dv)",
        altura_referencia_m=10, justificacion_altura="Nivel U10/V10 de WRF; no se afirma altura observada del sensor.",
        limite_vertical="PBLH horario BASE, sin reemplazarlo ni optimizarlo por concentración.",
        rechazo="PBLH<=10 o alturas no finitas; no imponer una altura de mezcla artificial.",
        punto_MMIF_indices_python=[42,43], instantes=97, niveles_por_instante=59,
        PBLH_min_m=float(hourly.PBLH_m.min()), PBLH_max_m=float(hourly.PBLH_m.max()),
        hipotesis_horizontal="Aplicar amplitud diagnóstica en la columna MMIF. La estación a otro punto no valida esta transferencia.",
        amplitud_prueba={"du_este_m_s": 1, "dv_norte_m_s": -.5},
        decision="Candidato para contraste estructural con uniforme; no modelo observado/calibrado.",
        campos_WRF_modificados=False, MMIF_AERMET_ejecutados=False, AERMOD_ejecutado=False,
        termo="Temperatura/humedad/presión/flujo/PBLH de BASE conservados: sensibilidad cinemática sin reintegración.",
        pruebas=checks, fuentes=inputs)
    guardar_json(OUT / "Operador.json", config)
    (OUT / "Criterio.md").write_text("""# Transferencia vertical: hipótesis acotada para el siguiente contraste

El error observado en una estación superficial no permite conocer el error de toda la columna ni del punto MMIF. El generador conjunto tampoco superó la evaluación de viento norte-sur. Se prepara por ello un **contraste de sensibilidad**, conservando explícita esa limitación.

Se comparará la perturbación uniforme anterior con una que vale el incremento completo hasta10m AGL y disminuye suavemente a cero al llegar a la PBLH horaria de BASE. Por encima de esa altura el viento permanece idéntico. La transición cúbica tiene pendiente cero en ambos extremos; es una elección de implementación de esta tesis, no una prescripción de EPA ni una función estimada de observaciones.

Para z entre10m y H: s=(z−10)/(H−10), w=1−3s²+2s³. Fuera de esa franja w=1 por debajo y w=0 por encima. Se suma el mismo vector (du,dv) multiplicado por w; no se remuestrean rapidez y dirección por separado, ni se divide por la rapidez de BASE. Se rechazan H≤10 y datos inválidos.

Los10m corresponden a U10/V10 de WRF; no reemplazan la altura desconocida del sensor. No se ajusta la amplitud entre estación y mina usando una correlación o la distancia sin validación. El alcance horizontal del futuro ensayo será la columna de entrada meteorológica de AERMOD y quedará registrado en el adaptador concreto.

Se verificaron97 instantes de la ventana común y59 niveles WRF por instante en la celda MMIF, con PBLH entre77,02 y1773,09m. Los datos se leyeron sin modificar NetCDF. Hay pruebas de calmas, signo, identidad, alturas inválidas y conservación exacta por encima de PBLH.

**Pendiente antes de usarlo en concentración:** decidir y verificar el adaptador a entradas MMIF/AERMET, comprobar perfiles y diagnósticos tras el procesamiento, y ejecutar el contraste emparejado. Una prueba algebraica no acredita plausibilidad dinámica. La perturbación del viento puede modificar cizalladura aunque se mantengan los flujos de BASE.

El siguiente contraste usa amplitudes técnicas, no los1024 miembros del generador. Si se aplica a residuos posteriormente, deberá reevaluarse el modelo de discrepancias y declarar las hipótesis espacial y vertical. Este documento no adopta una distribución calibrada ni promete incertidumbre total.
""", encoding="utf-8")
    guardar_json(OUT / "Entrega.json", {"archivos": [
        {"path": str(p), "sha256": sha256(p)} for p in [Path(__file__), *sorted(OUT.iterdir())] if p.is_file()]})
    print(json.dumps({k: config[k] for k in ("estado", "instantes", "PBLH_min_m", "PBLH_max_m", "campos_WRF_modificados", "pruebas")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
