"""Iguala ventana MMIF/AERMET y compara temperatura/viento con fuentes fijas."""
from pathlib import Path
import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs"
OUT = O / "Meteorologia_comun_2026-10-20"
THERM = O / "Ensayo_7dias_20161221_2026-10-14"
WIND = O / "Prueba_viento_NetCDF_2026-10-15"
CONC = O / "Sensibilidad_meteorologica_puntos_2026-10-19"
sys.path.insert(0, str(O / "Biblioteca_Tesis"))
from tesis.comun import sha256, guardar_json
from tesis.multidia import control_mmif, revisar_log_mmif, revisar_met
from tesis.cadena_corta import ajustar_aermet
from tesis.validacion_dispersion import verificar_dispersion
from tesis.receptores import leer_postfile

START, END = "2016-12-21", "2016-12-23"


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def records(paths):
    return [{"path": str(p.resolve()), "sha256": sha256(p)} for p in paths]


def verify(items):
    for r in items:
        if sha256(r["path"]) != r["sha256"]:
            raise ValueError("Archivo cambiado: " + r["path"])


def native(exe, args, folder):
    print("Ejecutando " + exe + " en " + str(folder), flush=True)
    with (folder / (exe + ".consola.log")).open("wb") as log:
        result = subprocess.run([str(THERM / "Binarios" / exe), *args], cwd=folder,
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW, timeout=1800)
    if result.returncode:
        raise ValueError(f"{exe}: código {result.returncode}")


def selected(path):
    lines = path.read_text(encoding="ascii").splitlines()
    header = lines[:1] if path.suffix.upper() == ".SFC" else []
    return "\n".join(header + [s for s in lines if s.split()[:3] in
                              [["2016", "12", "21"], ["2016", "12", "22"]]]) + "\n"


def prepare():
    if OUT.exists():
        raise FileExistsError("Entrega existente: no sobrescribir.")
    qa = read(THERM / "QA_WRF.json")
    inputs = []
    paths = {}
    for case in ("BASE", "Tmas1"):
        paths[case] = []
        for entry in qa["archivos"][:5]:
            path = THERM / "WRF" / case / Path(entry["original"]).name
            assert sha256(path) == entry[case + "_sha256"]
            paths[case].append(path)
            inputs.append({"path": str(path), "sha256": entry[case + "_sha256"]})
    verify(read(CONC / "Entrega.json")["archivos"])
    verify(read(CONC / "Estado.json")["archivos"])
    OUT.mkdir()
    for case in paths:
        dest = OUT / "Meteorologia" / case
        dest.mkdir(parents=True)
        (dest / "mmif.inp").write_text(control_mmif(paths[case], "WRF", START, END), encoding="ascii")
    plan = dict(inicio=START, fin_exclusivo=END, horas_objetivo=48, horas_auxiliares=96,
                UTC_instantes=["2016-12-20T03:00:00", "2016-12-24T03:00:00"],
                control="Misma ventana, punto, capas, mezcla WRF, binarios y ajuste AERMET.",
                superficie="Generada por MMIF; no se sustituye manualmente Bowen.",
                fuente_causa="MMIF4.1.1 output_onsite.f90:717-737,911-920; media por mes de horas diurnas del run.",
                campos_TERM="T2,TH2,T,THM +1K física; presión/humedad/flujo constantes, sin reintegración.",
                alcance="Sensibilidad diagnóstica: no incertidumbre calibrada ni transferencia de error observacional.",
                ejecuciones_nuevas="BASE y Tmas1 MMIF/AERMET; AERMOD Tmas1 MP10/MP25. BASE/VEC de concentración sólo se reutilizan si BASE coincide.",
                fuentes=12263, receptores=4, copias_WRF_nuevas=False,
                manual="https://gaftp.epa.gov/Air/aqmg/SCRAM/models/related/mmif/MMIFv4.1.1_Users_Guide.pdf")
    guardar_json(OUT / "Plan.json", plan)
    inputs += records([Path(__file__), OUT / "Plan.json", THERM / "QA_WRF.json",
                       CONC / "Entrega.json", CONC / "Corridas.json",
                       *[THERM / "Binarios" / n for n in ("mmif_4.1.1.exe", "aermet.exe", "aermod.exe")],
                       *[OUT / "Meteorologia" / c / "mmif.inp" for c in paths]])
    guardar_json(OUT / "Entrega.json", {"archivos": inputs})
    guardar_json(OUT / "Estado.json", {"estado": "PREPARADO"})


def met():
    verify(read(OUT / "Entrega.json")["archivos"])
    statepath = OUT / "Preprocesamiento.json"
    state = read(statepath) if statepath.exists() else {}
    for case in ("BASE", "Tmas1"):
        dest = OUT / "Meteorologia" / case
        if case in state:
            verify(state[case]["archivos"]); continue
        # No reescribir una corrida parcial sin inspeccionarla.
        if (dest / "met.IN1").exists():
            raise ValueError("Corrida parcial existente: inspeccionar antes de reintentar " + str(dest))
        native("mmif_4.1.1.exe", ["mmif.inp"], dest)
        qmmif = revisar_log_mmif((dest / "mmif_4.1.1.exe.consola.log").read_text(encoding="ascii", errors="replace"), START, END)
        original = (dest / "met.IN1").read_text(encoding="ascii")
        (dest / "met.IN1.original").write_text(original, encoding="ascii")
        (dest / "met.IN1").write_text(ajustar_aermet(original, "WRF"), encoding="ascii")
        native("aermet.exe", ["met.IN1"], dest)
        messages = (dest / "met.ER1").read_text(encoding="ascii", errors="replace")
        assert not re.search(r"(?m)^\s*(?:\w+\s+)?E\d{2}\s", messages)
        qmet = revisar_met(dest / "met.SFC", dest / "met.PFL", START, END)
        state[case] = dict(MMIF=qmmif, MET=qmet, advertencias=dict(Counter(re.findall(r"\bW\d{2}\b", messages))),
                           archivos=records(p for p in dest.iterdir() if p.is_file()))
        guardar_json(statepath, state)
    wind = read(WIND / "Ejecuciones.json")
    base = Path(wind["BASE"]["carpeta"])
    verify(wind["BASE"]["archivos"])
    matches = {}
    for name in ("met.SFC", "met.PFL", "SURFACE.DAT", "ONSITE.DAT", "UPPER.DAT"):
        # Encabezados y valores físicos: igualdad literal, incluidas96h auxiliares.
        a = (base / name).read_text(encoding="ascii").splitlines()
        b = (OUT / "Meteorologia/BASE" / name).read_text(encoding="ascii").splitlines()
        assert a == b, "BASE no coincide: " + name
        matches[name] = True
    b = np.loadtxt(OUT / "Meteorologia/BASE/met.SFC", skiprows=1, usecols=range(25))
    t = np.loadtxt(OUT / "Meteorologia/Tmas1/met.SFC", skiprows=1, usecols=range(25))
    assert np.array_equal(b[:, :5], t[:, :5])
    np.testing.assert_allclose(t[:, 18] - b[:, 18], 1, atol=.101, rtol=0)
    assert np.array_equal(b[:, 15:18], t[:, 15:18])
    assert (OUT / "Meteorologia/BASE/SURFACE.DAT").read_bytes() == (OUT / "Meteorologia/Tmas1/SURFACE.DAT").read_bytes()
    guardar_json(OUT / "Identidad_BASE.json", dict(estado="BASE_COMUN_VERIFICADO", archivos_coincidentes=matches,
        Bowen_BASE=float(b[0, 13]), Bowen_Tmas1=float(t[0, 13]), temperatura_incrementada=True,
        viento_superficial_igual=True, referencia_concentraciones=str(CONC),
        archivos=records([OUT / "Preprocesamiento.json"])))
    print("BASE idéntico al viento; temperatura +1 K con superficie común.", flush=True)


def dispersion():
    assert read(OUT / "Identidad_BASE.json")["estado"] == "BASE_COMUN_VERIFICADO"
    verify(read(OUT / "Entrega.json")["archivos"])
    for case in read(OUT / "Preprocesamiento.json").values():
        verify(case["archivos"])
    old = read(CONC / "Corridas.json")
    for entry in old.values():
        verify(entry["archivos"])
    jobs = {}
    for pol in ("MP10", "MP25"):
        dest = OUT / "Dispersion" / ("Tmas1_" + pol)
        if not dest.exists():
            dest.mkdir(parents=True)
            src = CONC / "Casos" / ("BASE_" + pol)
            for name in ("fuentes_aermod.inc", "receptores.inc", pol + ".emi"):
                shutil.copy2(src / name, dest / name)
                assert sha256(src / name) == sha256(dest / name)
            control = (src / "aermod.inp").read_text(encoding="ascii").replace(
                "Sensibilidad meteorologica BASE", "Sensibilidad meteorologica Tmas1 misma ventana")
            (dest / "aermod.inp").write_text(control, encoding="ascii")
            for suffix in ("SFC", "PFL"):
                (dest / ("met." + suffix)).write_text(selected(OUT / "Meteorologia/Tmas1" / ("met." + suffix)), encoding="ascii")
            guardar_json(dest / "Entradas.json", {"archivos": records(p for p in dest.iterdir() if p.is_file())})
        verify(read(dest / "Entradas.json")["archivos"])
        jobs[pol] = dest
    members = pd.read_csv(CONC / "Comunes/membresia.csv")
    def worker(pol, dest):
        log = dest / "aermod.out"
        if not log.exists():
            native("aermod.exe", [], dest)
        elif "AERMOD Finishes Successfully" not in log.read_text(encoding="ascii", errors="replace"):
            raise ValueError("Corrida parcial existente; inspeccionar " + str(dest))
        qa, daily, _ = verificar_dispersion(dest, 12263, 4, members, START, END)
        assert qa["valores"] == 192
        guardar_json(dest / "QA.json", qa)
        daily["escenario"] = "Tmas1"; daily["contaminante"] = pol
        return daily, dict(carpeta=str(dest), qa=qa, archivos=records(p for p in dest.iterdir() if p.is_file()))
    dailynew, runs = [], {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(worker, pol, dest): pol for pol, dest in jobs.items()}
        for f in as_completed(futures):
            d, entry = f.result(); pol = futures[f]
            dailynew.append(d); runs[pol] = entry
            guardar_json(OUT / "Corridas.json", runs)
    # Reconstruir también BASE/VEC desde POSTFILE sin alterar paquetes previos.
    all_daily = list(dailynew)
    for key, info in old.items():
        folder = Path(info["carpeta"])
        _, daily, _ = verificar_dispersion(folder, 12263, 4, members, START, END)
        daily["escenario"] = info["escenario"]; daily["contaminante"] = info["contaminante"]
        all_daily.append(daily)
    data = pd.concat(all_daily, ignore_index=True)
    data["dia"] = pd.to_datetime(data.dia).dt.strftime("%Y-%m-%d")
    data.to_csv(OUT / "Medias_diarias.csv", index=False, encoding="utf-8-sig")
    base = data.loc[data.escenario == "BASE"]
    keys = ["contaminante", "grupo", "x_m", "y_m", "dia"]
    contrasts = []
    for case in ("Tmas1", "VEC"):
        j = base.merge(data.loc[data.escenario == case], on=keys, suffixes=("_base", "_esc"), validate="one_to_one")
        for r in j.itertuples():
            delta = r.media_24h_ug_m3_esc - r.media_24h_ug_m3_base
            contrasts.append(dict(escenario=case, contaminante=r.contaminante, grupo=r.grupo, dia=r.dia,
                                  BASE=r.media_24h_ug_m3_base, concentracion=r.media_24h_ug_m3_esc, delta=delta,
                                  porcentaje=100*delta/r.media_24h_ug_m3_base if r.media_24h_ug_m3_base>.0004 else np.nan))
    comp = pd.DataFrame(contrasts)
    assert len(comp) == 32
    comp.to_csv(OUT / "Contrastes.csv", index=False, encoding="utf-8-sig")
    rows = ["# Sensibilidad meteorológica con procesamiento común", "",
            "Dos corridas AERMOD nuevas y cuatro previas recibidas con BASE idéntico: 384 valores nuevos, "
            "1152 en la comparación de tres escenarios. Dos días, cuatro receptores exactos y fuentes físicas fijas.", "",
            "MMIF promedia características superficiales sobre el período procesado. La ventana auxiliar común "
            "es20dic00–24dic00 local,96 horas; objetivo21–22dic,48 horas. BASE, T+1K y VEC tienen Bowen0,30. "
            "No se impuso ese número: surgió del procesamiento común. La identidad BASE se verificó en SFC/PFL, "
            "ONSITE, UPPER y SURFACE completos.", "",
            "| Punto | Día | BASE MP10 | T+1K | Cambio T (%) | VEC | Cambio VEC (%) |",
            "|---|---|---:|---:|---:|---:|---:|"]
    for group in ("PCAR", "LBCEN", "SULF", "PALP"):
        for day in ("2016-12-21", "2016-12-22"):
            sub = comp.loc[(comp.grupo == group) & (comp.dia == day) & (comp.contaminante == "MP10")].set_index("escenario")
            a, b = sub.loc["Tmas1"], sub.loc["VEC"]
            rows.append(f"| {group} | {day} | {a.BASE:.6f} | {a.concentracion:.6f} | {a.porcentaje:.3f} | {b.concentracion:.6f} | {b.porcentaje:.3f} |")
    rows += ["", "Concentraciones en µg/m³, aportes sin fondo. MP2,5 y diferencias absolutas en Contrastes.csv. "
             "T+1K y VEC(u+1,v−0,5m/s) son perturbaciones técnicas con distinta amplitud y no permiten jerarquizar "
             "incertidumbre ni sumar efectos como varianzas. La transferencia uniforme del perfil sigue siendo diagnóstica; "
             "no se propagaron las realizaciones del generador que falló su evaluación.",
             "", "La ventana debe permanecer fija dentro de cada comparación. Al ampliar a otra ventana se genera "
             "su BASE propio; no se arrastra Bowen0,30 como constante estacional. Para ejecutar sublotes de una misma "
             "ventana se preprocesa la meteorología completa una vez y después se recortan SFC/PFL.",
             "", "Fundamento: [manual MMIF4.1.1, §2.3.2 y §2.6](https://gaftp.epa.gov/Air/aqmg/SCRAM/models/related/mmif/MMIFv4.1.1_Users_Guide.pdf), "
             "y código local output_onsite.f90, líneas717–737/911–920. Los promedios mensuales se basan en la fracción del mes procesada."]
    (OUT / "Resultados.md").write_text("\n".join(rows)+"\n", encoding="utf-8")
    guardar_json(OUT / "Estado.json", dict(estado="COMPARACION_METEOROLOGICA_COMUN_COMPLETA", valores_nuevos=384,
        valores_comparacion=1152, casos_nuevos=2, casos_reutilizados=4, fuentes_receptores_fijos=True,
        base_literalmente_identico=True, archivos=records(OUT / name for name in ("Resultados.md", "Contrastes.csv", "Medias_diarias.csv", "Identidad_BASE.json", "Corridas.json"))))
    print(comp.loc[(comp.contaminante == "MP10") & (comp.grupo == "LBCEN")].to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("etapa", choices=["preparar", "meteorologia", "dispersion"])
    args = parser.parse_args()
    {"preparar": prepare, "meteorologia": met, "dispersion": dispersion}[args.etapa]()
