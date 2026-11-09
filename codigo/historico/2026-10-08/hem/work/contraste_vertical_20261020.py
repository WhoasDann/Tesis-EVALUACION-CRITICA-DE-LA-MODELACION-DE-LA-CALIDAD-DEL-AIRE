"""Contraste cinemático uniforme/PBL en copias WRF; fuentes y ventana fijas."""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import sys
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from netCDF4 import Dataset, chartostring

import meteorologia_comun_20261020 as common
from transferencia_vertical_20261020 import pesos_pbl, tests
from tesis.comun import guardar_json, sha256
from tesis.viento_wrf import sumar_wrf, a_centros
from tesis.validacion import rotar_a_tierra
from tesis.multidia import control_mmif, revisar_log_mmif, revisar_met, ventana
from tesis.cadena_corta import ajustar_aermet
from tesis.validacion_dispersion import verificar_dispersion

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/Contraste_vertical_2026-10-20"
WIND, CONC = common.WIND, common.CONC
START, END = common.START, common.END
CHANGED = {"U10", "V10", "U", "V"}
MID_REQUESTED = np.array([25, 50, 75, 100, 125, 150, 175, 200, 250, 300,
                         350, 400, 450, 500, 600, 700, 800, 900, 1000,
                         1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000.])
FACES_OUT = np.r_[0., (MID_REQUESTED[:-1] + MID_REQUESTED[1:])/2,
                  MID_REQUESTED[-1] + (MID_REQUESTED[-1]-MID_REQUESTED[-2])/2]
MID_OUT = (FACES_OUT[:-1] + FACES_OUT[1:])/2
read, records, verify = common.read, common.records, common.verify


def check(ok, message):
    if not ok:
        raise ValueError(message)


def hour_label(timestamp):
    local = pd.Timestamp(timestamp) - pd.Timedelta(hours=3)
    if local.hour == 0:
        return (local-pd.Timedelta(days=1)).strftime("%Y%m%d") + "24"
    return local.strftime("%Y%m%d%H")


def overlap_matrix(z_faces_mmif, sigma_faces):
    """Integral por cajas en coordenada sigma; interpolate.f90, casos 2 y 3.

    El primer estrato de SALIDA atraviesa el primer estrato WRF en este caso.
    Se rechaza el caso logarítmico, que requeriría otro operador.
    """
    z, s = np.asarray(z_faces_mmif, float), np.asarray(sigma_faces, float)
    check(len(z) == len(s) and np.all(np.diff(z)>0) and np.all(np.diff(s)<0),
          "Coordenadas verticales inválidas")
    check(FACES_OUT[1] > z[1] and FACES_OUT[-1] < z[-1],
          "Este verificador no cubre capa logarítmica/extrapolación vertical")
    so = np.interp(FACES_OUT, z, s)
    overlap = np.maximum(0., np.minimum(so[:-1, None], s[None, :-1]) -
                         np.maximum(so[1:, None], s[None, 1:]))
    matrix = overlap / (so[:-1] - so[1:])[:, None]
    np.testing.assert_allclose(matrix.sum(axis=1), 1., atol=1e-12, rtol=0)
    return matrix


def onsite(path):
    lines = Path(path).read_text(encoding="ascii").splitlines()
    check(len(lines) == 96*30, "ONSITE no tiene 96 perfiles de 30 líneas")
    result = []
    for offset in range(0, len(lines), 30):
        stamp = lines[offset][:10]
        for line in lines[offset+2:offset+30]:
            vals = list(map(float, line.split()))
            h, speed, direction = vals[:3]
            angle = np.deg2rad(direction)
            result.append(dict(hora=stamp, z_m=h, u=-speed*np.sin(angle),
                               v=-speed*np.cos(angle)))
    return pd.DataFrame(result)


def verify_profile(expected, actual, case):
    got = onsite(actual)
    join = expected.merge(got, on=["hora", "z_m"], validate="one_to_one")
    check(len(join) == 96*28, "Horas/alturas distintas en ONSITE")
    error = max(float(np.abs(join.u-join["u_"+case]).max()),
                float(np.abs(join.v-join["v_"+case]).max()))
    # ONSITE redondea rapidez a .001 m/s y dirección a .001 grados.
    # Incluye cálculo Fortran en precisión simple y promedios de capas.
    check(error < .002, f"ONSITE {case} no reproduce componentes: {error} m/s")
    return error


def freeze_launcher():
    (OUT / "ejecutar_vertical.py").write_text(
        'from pathlib import Path\nimport sys\n'
        'sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "work"))\n'
        'from contraste_vertical_20261020 import run\n'
        'if __name__ == "__main__":\n    run()\n', encoding="utf-8")
    cmd = (
        '@echo off\nsetlocal\ncd /d "%~dp0"\n'
        'set "PATH=/archivo/usuario\\anaconda3\\envs\\wrf_clean;'
        '/archivo/usuario\\anaconda3\\envs\\wrf_clean\\Library\\bin;%PATH%"\n'
        '"/archivo/usuario\\anaconda3\\envs\\wrf_clean\\python.exe" "%~dp0ejecutar_vertical.py"\n'
        'set "TESIS_EXIT=%ERRORLEVEL%"\necho.\n'
        'echo Codigo de salida: %TESIS_EXIT%\n'
        'echo Si termina correctamente: Resultados.md y Contrastes.csv.\n'
        'echo Calcula MP10 y MP2,5 en los mismos cuatro puntos y dos dias.\n'
        'exit /b %TESIS_EXIT%\n')
    (OUT / "EJECUTAR_VERTICAL.cmd").write_bytes(cmd.replace("\n", "\r\n").encode("ascii"))


def prepare():
    check(not OUT.exists(), "Entrega existente; no sobrescribir")
    tests()
    original_plan = read(WIND / "Plan.json")
    originals = [r for r in original_plan["copias"] if Path(r["path"]).parent.name == "BASE"]
    verify(originals)
    check(len(originals) == 5, "Se esperaban cinco copias BASE")
    oldmet = read(WIND / "Ejecuciones.json")
    for info in oldmet.values():
        verify(info["archivos"])
    verify(read(common.OUT / "Estado.json")["archivos"])
    verify(read(CONC / "Entrega.json")["archivos"])
    for info in read(CONC / "Corridas.json").values():
        verify(info["archivos"])
    OUT.mkdir()
    (OUT / "WRF/PBL").mkdir(parents=True)
    expected, checks, dates, files = [], [], [], []
    maxerr, maxfaces, hmin = 0., 0., float("inf")
    for entry in originals:
        source = Path(entry["path"])
        dest = OUT / "WRF/PBL" / source.name
        print("Preparando y verificando " + source.name, flush=True)
        shutil.copyfile(source, dest)
        with Dataset(source) as b, Dataset(dest, "r+") as d:
            b.set_auto_mask(False); d.set_auto_mask(False)
            for t, timestamp in enumerate(chartostring(b["Times"][:])):
                dates.append(timestamp)
                geop = np.asarray(b["PH"][t], float) + np.asarray(b["PHB"][t], float)
                z_faces = geop/9.81 - np.asarray(b["HGT"][t], float)
                z_mass = (z_faces[:-1]+z_faces[1:])/2
                h = np.asarray(b["PBLH"][t], float)
                check(np.all(np.diff(z_mass, axis=0)>0), "Alturas WRF desordenadas")
                w = pesos_pbl(z_mass, h)
                hmin = min(hmin, float(h.min()))
                c, s = (np.asarray(b[n][t], float) for n in ("COSALPHA", "SINALPHA"))
                fields, qa = sumar_wrf(b["U10"][t], b["V10"][t], b["U"][t], b["V"][t],
                                       c, s, 1., -.5, pesos=w)
                maxfaces = max(maxfaces, qa["incremento_U_cara_max_ms"], qa["incremento_V_cara_max_ms"])
                for name, values in fields.items():
                    d[name][t] = values.astype(d[name].dtype)
                for names, axes, target in [(("U10","V10"), (None,None), 1.),
                                             (("U","V"), (-1,-2), w)]:
                    old, new = [], []
                    for name, axis in zip(names, axes):
                        a, v = np.asarray(b[name][t], float), np.asarray(d[name][t], float)
                        old.append(a if axis is None else a_centros(a, axis))
                        new.append(v if axis is None else a_centros(v, axis))
                    du, dv = rotar_a_tierra(new[0]-old[0], new[1]-old[1], c, s)
                    maxerr = max(maxerr, float(np.abs(du-target).max()), float(np.abs(dv+.5*target).max()))
                check(maxerr < 2e-5, "No se recupera el operador en centros después de guardar")
                # Auditoría independiente del transporte a las cajas MMIF:
                # read_wrf.f90 usa g=9.8 y resta la cara inferior, no HGT.
                zz = (geop[:,43,42]-geop[0,43,42])/9.8
                matrix = overlap_matrix(zz, b["ZNW"][t])
                ub = np.asarray(b["U"][t,:,43,42:44], float).mean(axis=1)
                vb = np.asarray(b["V"][t,:,43:45,42], float).mean(axis=1)
                u, v = rotar_a_tierra(matrix@ub, matrix@vb, c[43,42], s[43,42])
                effective = matrix@w[:,43,42]
                us, vs = rotar_a_tierra(float(b["U10"][t,43,42]), float(b["V10"][t,43,42]), c[43,42], s[43,42])
                for z, eu, ev, weight in zip(np.r_[10., MID_OUT], np.r_[us,u], np.r_[vs,v], np.r_[1.,effective]):
                    expected.append(dict(hora=hour_label(timestamp.replace("_", " ")), z_m=z,
                        PBLH_m=h[43,42], peso_efectivo=weight,
                        u_BASE=eu, v_BASE=ev, u_VEC=eu+1, v_VEC=ev-.5,
                        u_PBL=eu+weight, v_PBL=ev-.5*weight))
                checks.append(dict(fecha_UTC=timestamp, PBLH_min_dominio=float(h.min()),
                    PBLH_columna=float(h[43,42]), caras_incremento_max=max(
                        qa["incremento_U_cara_max_ms"], qa["incremento_V_cara_max_ms"]),
                    error_acumulado_recuperacion=maxerr))
        with Dataset(source) as b, Dataset(dest) as d:
            b.set_auto_mask(False); d.set_auto_mask(False)
            check(b.data_model == d.data_model == "NETCDF3_64BIT_OFFSET", "Formato NetCDF cambiado")
            check(b.ncattrs() == d.ncattrs(), "Atributos globales cambiados")
            check(list(b.dimensions) == list(d.dimensions), "Dimensiones cambiadas")
            for name, dim in b.dimensions.items():
                check(len(dim)==len(d.dimensions[name]) and dim.isunlimited()==d.dimensions[name].isunlimited(),
                      "Dimensión cambiada: "+name)
            for name in b.ncattrs():
                np.testing.assert_array_equal(b.getncattr(name), d.getncattr(name))
            for name, var in b.variables.items():
                other = d[name]
                check(var.dtype==other.dtype and var.dimensions==other.dimensions and var.ncattrs()==other.ncattrs(),
                      "Metadatos cambiados: "+name)
                for a in var.ncattrs():
                    np.testing.assert_array_equal(var.getncattr(a), other.getncattr(a))
                if name not in CHANGED:
                    check(np.array_equal(var[:], other[:], equal_nan=var.dtype.kind=="f"),
                          "Campo ajeno modificado: "+name)
        check(sha256(source)==entry["sha256"], "BASE alterado")
        files.append(dest)
    check(dates == [d.strftime("%Y-%m-%d_%H:%M:%S") for d in ventana(START, END)[2]],
          "Los 97 instantes no coinciden")
    expect = pd.DataFrame(expected)
    expect = expect[expect.hora != hour_label(dates[0].replace("_"," "))].copy()
    check(len(expect)==96*28, "Perfiles esperados incompletos")
    errors = {case: verify_profile(expect, Path(oldmet[case]["carpeta"])/"ONSITE.DAT", case)
              for case in ("BASE", "VEC")}
    expect.to_csv(OUT / "Perfiles_esperados_MMIF.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(checks).to_csv(OUT / "QA_por_instante.csv", index=False, encoding="utf-8-sig")
    metdir = OUT / "Meteorologia/PBL"
    metdir.mkdir(parents=True)
    (metdir / "mmif.inp").write_text(control_mmif(files,"WRF",START,END), encoding="ascii")
    oldcontrol = (Path(oldmet["BASE"]["carpeta"])/"mmif.inp").read_text(encoding="ascii")
    strip_inputs = lambda txt: [line for line in txt.splitlines() if not line.startswith("INPUT ")]
    check(strip_inputs(oldcontrol)==strip_inputs((metdir/"mmif.inp").read_text()),
          "Control MMIF distinto fuera de las rutas INPUT")
    plan = dict(fecha="2026-10-20", inicio=START, fin_exclusivo=END,
        horas_objetivo=48, horas_auxiliares=96, instantes_WRF=97, fuentes=12263, receptores=4,
        escenarios=["BASE", "VEC uniforme", "PBL acotado"],
        amplitud={"du_este_ms":1., "dv_norte_ms":-.5},
        operador="s=clip((z-10)/(PBLH_BASE-10),0,1); w=1-3*s*s+2*s*s*s",
        extension_horizontal="Misma amplitud en todo d03; cada columna usa su propia z y PBLH BASE.",
        dominio_h_min_m=hmin, columna_MMIF_indices_python=[42,43],
        error_max_recuperacion_ms=maxerr, incremento_cara_max_ms=maxfaces,
        error_ONSITE_control_ms=errors, campos_modificados=sorted(CHANGED),
        campos_ajenos_y_metadatos_identicos=True,
        interpretacion="Sensibilidad cinemática al supuesto vertical; no incertidumbre calibrada ni reintegración WRF.",
        detalle_capa="El corte exacto se aplica a centros WRF; cajas MMIF que cruzan el corte pueden retener incremento.",
        referencia_altura="10 m corresponde a U10/V10; altura del sensor desconocida.",
        ejecuciones_nuevas="Un MMIF, un AERMET y dos AERMOD. BASE/VEC previos se reciben por hashes.",
        entradas=originals, copias=records(files))
    guardar_json(OUT/"Plan.json", plan)
    freeze_launcher()
    (OUT/"LEEME.md").write_text(
        "# Contraste del supuesto vertical del viento\n\n"
        "Ejecutar EJECUTAR_VERTICAL.cmd desde Símbolo del sistema. Procesa la copia PBL con MMIF/AERMET "
        "y calcula MP10/MP2,5 en Piedra Carvajal, Los Bronces estación, Sulfatos y La Paloma. "
        "Conserva las 12.263 fuentes, emisiones, terreno, cuatro puntos y días 21–22 de diciembre de 2016. "
        "Reutiliza los controles BASE/VEC recibidos. Ventana auxiliar común: 96 h.\n\n"
        "Pregunta: cuánto cambia la respuesta de concentración al limitar en altura el mismo vector superficial "
        "(+1 m/s este, −0,5 m/s norte), frente a extenderlo uniformemente. La función cúbica es una hipótesis "
        "de esta tesis, no una prescripción bibliográfica ni una transferencia validada desde la estación.\n\n"
        "El peso se calcula en centros WRF con z=(PH+PHB)/9,81−HGT y PBLH horario original de cada columna. "
        "Es uno hasta 10 m y cero desde PBLH. Todos los PBLH superan 10 m; no se recortan ni reemplazan. "
        "El incremento uniforme superficial se mantiene en todo d03 como en el control VEC; "
        "la extensión horizontal sigue siendo una hipótesis diagnóstica.\n\n"
        "La reconstrucción de U/V en caras conserva los incrementos requeridos al desescalonar. "
        f"Máximo cambio en caras: {maxfaces:.6f} m/s, por encima del incremento en centros. "
        "Las caras se usan aquí como representación numérica para MMIF, que las promedia; "
        "estas copias no son reinicios dinámicos de WRF. Se registra el máximo sin recortar caras "
        "ni modificar la perturbación para ajustarse al resultado de concentración.\n\n"
        "MMIF promedia por cajas sigma. El control independiente reproduce interpolate.f90 (casos 2 y 3), "
        "read_wrf.f90 (g=9,8 y origen en cara inferior) y parse_control.f90 (LAYERS MID). "
        "Comprueba los controles BASE y VEC nativos y deja todos los perfiles PBL esperados antes de ejecutar. "
        "Una caja que atraviesa PBLH puede conservar incremento aunque su centro esté por encima del límite; "
        "no se exige artificialmente cero a esa caja. ONSITE se verifica en componentes, tolerancia 0,002 m/s "
        "por formato y precisión Fortran. Los archivos UPPER también se generan desde la misma copia.\n\n"
        "Se mantienen temperatura, humedad, presión, flujos, UST, PBLH y demás campos originales. "
        "AERMET puede recalcular diagnósticos a partir de los perfiles nuevos; esos cambios se registran. "
        "No es una perturbación meteorológica dinámicamente reintegrada, ni produce percentiles de incertidumbre. "
        "El generador conjunto que falló la evaluación no se usa. Los cuatro puntos no sustituyen "
        "máximos en MINA, Olivares o GENERAL.\n\n"
        "Resultados.md separará PBL−BASE, VEC−BASE y PBL−VEC en µg/m³ y porcentaje cuando el denominador "
        "sea resoluble. No se elegirá un operador por producir la concentración mayor. "
        "No se necesitan nuevas corridas de AERMAP.\n", encoding="utf-8")
    sources = Path(r"/archivo/usuario\Downloads\MMIF4.1.1")
    dependencies = [Path(__file__), ROOT/"work/transferencia_vertical_20261020.py",
                    ROOT/"work/meteorologia_comun_20261020.py",
                    *sorted((ROOT/"outputs/Biblioteca_Tesis/tesis").glob("*.py")),
                    *[sources/n for n in ("read_wrf.f90","interpolate.f90","parse_control.f90","output_onsite.f90")],
                    *[common.THERM/"Binarios"/n for n in ("mmif_4.1.1.exe","aermet.exe","aermod.exe")],
                    WIND/"Ejecuciones.json", CONC/"Corridas.json", CONC/"Entrega.json",
                    CONC/"Comunes/membresia.csv", common.OUT/"Estado.json",
                    OUT/"Plan.json", OUT/"Perfiles_esperados_MMIF.csv", OUT/"QA_por_instante.csv",
                    OUT/"LEEME.md", OUT/"ejecutar_vertical.py", OUT/"EJECUTAR_VERTICAL.cmd", metdir/"mmif.inp"]
    guardar_json(OUT/"Entrega.json", dict(archivos=records(dependencies)+originals+records(files)))
    guardar_json(OUT/"Estado.json", dict(estado="PREPARADO_VERIFICADO_SIN_EJECUCION_NATIVA",
        campos_WRF_verificados=True, MMIF_AERMET_ejecutados=False, AERMOD_ejecutado=False))
    print(json.dumps({k:plan[k] for k in ("error_max_recuperacion_ms","incremento_cara_max_ms","error_ONSITE_control_ms")}))


def meteorology():
    dest = OUT/"Meteorologia/PBL"
    result = OUT/"Preprocesamiento.json"
    if result.exists():
        verify(read(result)["archivos"])
        print("Meteorología PBL ya verificada.", flush=True)
        return
    check(not (dest/"met.IN1").exists(), "Meteorología parcial existente; inspeccionar antes de reintentar")
    common.native("mmif_4.1.1.exe", ["mmif.inp"], dest)
    qmmif = revisar_log_mmif((dest/"mmif_4.1.1.exe.consola.log").read_text(errors="replace"), START, END)
    expected = pd.read_csv(OUT/"Perfiles_esperados_MMIF.csv", dtype={"hora":str})
    error = verify_profile(expected, dest/"ONSITE.DAT", "PBL")
    old = read(WIND/"Ejecuciones.json")
    base, vec = (Path(old[c]["carpeta"]) for c in ("BASE","VEC"))
    for info in old.values():
        verify(info["archivos"])
    check((base/"SURFACE.DAT").read_bytes()==(vec/"SURFACE.DAT").read_bytes()==(dest/"SURFACE.DAT").read_bytes(),
          "Características superficiales diferentes")
    b, v, p = [(folder/"ONSITE.DAT").read_text(encoding="ascii").splitlines() for folder in (base,vec,dest)]
    check(b[1::30] == p[1::30], "Cambió termodinámica a 2 m")
    check(v[2::30] == p[2::30], "La perturbación a 10 m difiere de VEC")
    for offset in range(0, len(b), 30):
        for k in range(3,30):
            check(b[offset+k].split()[3:]==p[offset+k].split()[3:],
                  "Cambió temperatura/humedad en perfiles ONSITE")
    original = (dest/"met.IN1").read_text(encoding="ascii")
    (dest/"met.IN1.original").write_text(original, encoding="ascii")
    (dest/"met.IN1").write_text(ajustar_aermet(original,"WRF"), encoding="ascii")
    common.native("aermet.exe", ["met.IN1"], dest)
    messages = (dest/"met.ER1").read_text(encoding="ascii", errors="replace")
    check(not re.search(r"(?m)^\s*(?:\w+\s+)?E\d{2}\s", messages), "Errores AERMET")
    qmet = revisar_met(dest/"met.SFC", dest/"met.PFL", START, END)
    pb = np.loadtxt(base/"met.SFC", skiprows=1, usecols=range(25))
    pp = np.loadtxt(dest/"met.SFC", skiprows=1, usecols=range(25))
    pv = np.loadtxt(vec/"met.SFC", skiprows=1, usecols=range(25))
    np.testing.assert_array_equal(pb[:,:5], pp[:,:5])
    np.testing.assert_array_equal(pv[:,15:18], pp[:,15:18])
    np.testing.assert_array_equal(pb[:,12:15], pp[:,12:15])
    np.testing.assert_array_equal(pb[:,18:20], pp[:,18:20])
    fields = ["year","month","day","julian","hour","H","ustar","wstar","VPTG","ZiC","ZiM",
              "L","z0","Bowen","albedo","WS","WD","zrefWS","T","zrefT","precip_code","precip","RH","pressure","cloud"]
    changes = []
    for j in range(5,25):
        delta = pp[:,j]-pb[:,j]
        delta_v = pp[:,j]-pv[:,j]
        changes.append(dict(campo=fields[j], horas_difiere_BASE=int(np.sum(delta!=0)),
                            delta_BASE_min=float(delta.min()), delta_BASE_max=float(delta.max()),
                            horas_difiere_VEC=int(np.sum(delta_v!=0)),
                            delta_VEC_min=float(delta_v.min()), delta_VEC_max=float(delta_v.max())))
    pd.DataFrame(changes).to_csv(OUT/"Cambios_AERMET.csv", index=False, encoding="utf-8-sig")
    guardar_json(result, dict(estado="PBL_MMIF_AERMET_VERIFICADO", MMIF=qmmif, MET=qmet,
        error_perfil_ONSITE_ms=error, superficie_igual=True, viento_10m_igual_VEC=True,
        advertencias=dict(Counter(re.findall(r"\bW\d{2}\b",messages))),
        archivos=records([p for p in dest.iterdir() if p.is_file()]+[OUT/"Cambios_AERMET.csv"])))
    print("PBL verificado: perfiles esperados, mismo viento a 10 m y superficie común.", flush=True)


def dispersion():
    verify(read(OUT/"Preprocesamiento.json")["archivos"])
    old = read(CONC/"Corridas.json")
    members = pd.read_csv(CONC/"Comunes/membresia.csv")
    results, all_daily = {}, []
    for info in old.values():
        verify(info["archivos"])
        _, daily, _ = verificar_dispersion(info["carpeta"],12263,4,members,START,END)
        daily["escenario"], daily["contaminante"] = info["escenario"], info["contaminante"]
        all_daily.append(daily)
    for pol in ("MP10","MP25"):
        dest = OUT/"Dispersion"/("PBL_"+pol)
        if not dest.exists():
            dest.mkdir(parents=True)
            src = Path(old["BASE_"+pol]["carpeta"])
            for name in ("fuentes_aermod.inc","receptores.inc",pol+".emi"):
                shutil.copy2(src/name,dest/name)
                check(sha256(src/name)==sha256(dest/name), "Cambió entrada fija")
            (dest/"aermod.inp").write_text((src/"aermod.inp").read_text(encoding="ascii").replace(
                "Sensibilidad meteorologica BASE","Contraste vertical PBL misma superficie"),encoding="ascii")
            for suffix in ("SFC","PFL"):
                (dest/("met."+suffix)).write_text(common.selected(OUT/"Meteorologia/PBL"/("met."+suffix)),encoding="ascii")
            guardar_json(dest/"Entradas.json",dict(archivos=records(p for p in dest.iterdir() if p.is_file())))
        verify(read(dest/"Entradas.json")["archivos"])

    def worker(pol):
        dest = OUT/"Dispersion"/("PBL_"+pol)
        if not (dest/"aermod.out").exists():
            common.native("aermod.exe",[],dest)
        qa, daily, _ = verificar_dispersion(dest,12263,4,members,START,END)
        check(qa["advertencias"]==old["BASE_"+pol]["qa"]["advertencias"],"Advertencias distintas de BASE")
        daily["escenario"], daily["contaminante"] = "PBL",pol
        guardar_json(dest/"QA.json",qa)
        return daily, dict(carpeta=str(dest),qa=qa,archivos=records(p for p in dest.iterdir() if p.is_file()))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(worker,pol):pol for pol in ("MP10","MP25")}
        for future in as_completed(futures):
            daily, info = future.result()
            all_daily.append(daily); results[futures[future]]=info
            guardar_json(OUT/"Corridas.json",results)
    data = pd.concat(all_daily,ignore_index=True)
    data["dia"]=pd.to_datetime(data.dia).dt.strftime("%Y-%m-%d")
    check(len(data)==48, "Número de medias diarias distinto")
    data.to_csv(OUT/"Medias_diarias.csv",index=False,encoding="utf-8-sig")
    keys=["contaminante","grupo","x_m","y_m","dia"]
    contrasts=[]
    for target, ref in (("VEC","BASE"),("PBL","BASE"),("PBL","VEC")):
        joined=data[data.escenario==target].merge(data[data.escenario==ref],on=keys,validate="one_to_one",suffixes=("_target","_ref"))
        for r in joined.itertuples():
            delta=r.media_24h_ug_m3_target-r.media_24h_ug_m3_ref
            contrasts.append(dict(contraste=target+"-"+ref,contaminante=r.contaminante,grupo=r.grupo,dia=r.dia,
                referencia=r.media_24h_ug_m3_ref,concentracion=r.media_24h_ug_m3_target,delta=delta,
                porcentaje=100*delta/r.media_24h_ug_m3_ref if r.media_24h_ug_m3_ref>.0004 else np.nan))
    comp=pd.DataFrame(contrasts)
    check(len(comp)==48,"Contrastes incompletos")
    comp.to_csv(OUT/"Contrastes.csv",index=False,encoding="utf-8-sig")
    rows=["# Respuesta al supuesto vertical del viento","",
        "Dos nuevas corridas PBL y cuatro controles recibidos: 384 valores horarios nuevos, "
        "1152 en total. Ventana 21–22 de diciembre de 2016, cuatro puntos y fuentes/emisiones fijas. "
        "Mismo vector a 10 m (+1, −0,5 m/s), extensión uniforme (VEC) o limitada por PBLH BASE (PBL).","",
        "| Punto | Día | BASE MP10 | VEC | PBL | PBL−VEC (µg/m³) |",
        "|---|---|---:|---:|---:|---:|"]
    for group in ("PCAR","LBCEN","SULF","PALP"):
        for day in ("2016-12-21","2016-12-22"):
            sub=data[(data.grupo==group)&(data.dia==day)&(data.contaminante=="MP10")].set_index("escenario").media_24h_ug_m3
            rows.append(f"| {group} | {day} | {sub.BASE:.6f} | {sub.VEC:.6f} | {sub.PBL:.6f} | {sub.PBL-sub.VEC:.6f} |")
    rows+=["","MP2,5, diferencias absolutas y porcentajes en Contrastes.csv. Aportes sin fondo. "
        "Los perfiles ONSITE se contrastaron contra promedios sigma calculados desde WRF antes de la corrida. "
        "Cambios_AERMET.csv documenta los diagnósticos que cambian al procesar el perfil.",
        "","Este contraste cuantifica dependencia respecto del supuesto de transferencia vertical; "
        "no demuestra que uno sea verdadero ni es una banda probabilística. No se selecciona por dar "
        "mayor o menor concentración. No jerarquiza incertidumbre de temperatura y viento ni usa el "
        "generador meteorológico que falló evaluación. La siguiente discusión vuelve a la estabilidad "
        "del error observado, sin abrir otro refinamiento de fuentes.",
        "","Las hipótesis, redondeos y alcance horizontal están en LEEME.md y Plan.json. "
        "No se validan máximos de MINA, Olivares ni GENERAL con cuatro puntos."]
    (OUT/"Resultados.md").write_text("\n".join(rows)+"\n",encoding="utf-8")
    guardar_json(OUT/"Estado.json",dict(estado="CONTRASTE_VERTICAL_COMPLETO",valores_nuevos=384,
        valores_totales=1152,fuentes_receptores_fijos=True,comparacion_superficial_pareada=True,
        archivos=records(OUT/n for n in ("Resultados.md","Medias_diarias.csv","Contrastes.csv",
            "Corridas.json","Preprocesamiento.json","Cambios_AERMET.csv"))))
    print(comp[(comp.contaminante=="MP10")&(comp.grupo=="LBCEN")].to_string(index=False))


def check_delivery():
    verify(read(OUT/"Entrega.json")["archivos"])
    for info in read(WIND/"Ejecuciones.json").values():
        verify(info["archivos"])
    for info in read(CONC/"Corridas.json").values():
        verify(info["archivos"])
    expected=pd.read_csv(OUT/"Perfiles_esperados_MMIF.csv",dtype={"hora":str})
    errors={c:verify_profile(expected,Path(info["carpeta"])/"ONSITE.DAT",c)
            for c,info in read(WIND/"Ejecuciones.json").items()}
    print("Entrega y controles anteriores verificados. Errores ONSITE: "+str(errors),flush=True)


def run():
    lock=OUT/"Ejecucion.lock"
    with lock.open("x",encoding="ascii") as f:
        f.write(str(os.getpid()))
    try:
        check_delivery()
        state=read(OUT/"Estado.json")
        if state["estado"]=="CONTRASTE_VERTICAL_COMPLETO":
            verify(state["archivos"])
            print("Contraste completo; no se repiten modelos.")
            return
        meteorology()
        dispersion()
        print("Contraste vertical cerrado. Consultar Resultados.md.",flush=True)
    except Exception as exc:
        guardar_json(OUT/"Fallo_ejecucion.json",dict(error=repr(exc),winerror=getattr(exc,"winerror",None)))
        traceback.print_exc()
        sys.exit(1)
    finally:
        if lock.exists() and lock.read_text().strip()==str(os.getpid()):
            lock.unlink()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("etapa",choices=["preparar","verificar","ejecutar"])
    args=parser.parse_args()
    {"preparar":prepare,"verificar":check_delivery,"ejecutar":run}[args.etapa]()
