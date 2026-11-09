"""Recibe el cierre del usuario desde archivos nativos, sin repetir modelos."""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs"
OUT = O / "Meteorologia_comun_2026-10-20"
OLD = O / "Sensibilidad_meteorologica_puntos_2026-10-19"
WIND = O / "Prueba_viento_NetCDF_2026-10-15"
DEST = OUT / "Recepcion"
sys.path.insert(0, str(O / "Biblioteca_Tesis"))
from tesis.comun import sha256, guardar_json
from tesis.validacion_dispersion import verificar_dispersion
from tesis.multidia import revisar_log_mmif, revisar_met

LABELS = {"PCAR": "Piedra Carvajal", "LBCEN": "Los Bronces, estación",
          "SULF": "Sulfatos", "PALP": "La Paloma, punto"}
SFC = ["year", "month", "day", "julian", "hour", "H_W_m2", "ustar_m_s",
       "wstar_m_s", "VPTG_K_m", "ZiC_m", "ZiM_m", "L_m", "z0_m", "Bowen",
       "albedo", "WS_m_s", "WD_grados", "zWS_m", "T_K", "zT_m", "ipcode",
       "rain_mm", "RH_pct", "P_mb", "cloud"]


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def verify(entries):
    for entry in entries:
        assert sha256(entry["path"]) == entry["sha256"], entry["path"]


def main():
    assert not DEST.exists(), "Recepción existente: no sobrescribir."
    assert read(OUT / "Estado.json")["estado"] == "COMPARACION_METEOROLOGICA_COMUN_COMPLETA"
    for manifest in ("Entrega.json", "Lanzador.json", "Estado.json", "Identidad_BASE.json"):
        verify(read(OUT / manifest)["archivos"])
    met = read(OUT / "Preprocesamiento.json")
    oldmet = read(WIND / "Ejecuciones.json")
    for r in met.values(): verify(r["archivos"])
    for r in oldmet.values(): verify(r["archivos"])
    basepath = OUT / "Meteorologia/BASE"
    previous = Path(oldmet["BASE"]["carpeta"])
    for name in ("met.SFC", "met.PFL", "SURFACE.DAT", "ONSITE.DAT", "UPPER.DAT"):
        assert (basepath / name).read_text(encoding="ascii").splitlines() == (previous / name).read_text(encoding="ascii").splitlines()
    for case in ("BASE", "Tmas1"):
        p = OUT / "Meteorologia" / case
        revisar_log_mmif((p / "mmif_4.1.1.exe.consola.log").read_text(encoding="ascii", errors="replace"), "2016-12-21", "2016-12-23")
        revisar_met(p / "met.SFC", p / "met.PFL", "2016-12-21", "2016-12-23")
    rows = []
    a = np.loadtxt(basepath / "met.SFC", skiprows=1, usecols=range(25))
    b = np.loadtxt(OUT / "Meteorologia/Tmas1/met.SFC", skiprows=1, usecols=range(25))
    mask = np.isin(a[:, 2], [21, 22])
    assert mask.sum() == 48 and np.array_equal(a[:, :5], b[:, :5])
    for j, col in enumerate(SFC[5:], 5):
        delta = b[mask, j] - a[mask, j]
        rows.append(dict(campo=col, horas_cambiadas=int(np.count_nonzero(delta)),
                         delta_min=float(delta.min()), delta_max=float(delta.max())))
    np.testing.assert_array_equal(b[mask, 18] - a[mask, 18], np.ones(48))
    for j in (8, 9, 10, 12, 13, 15, 16):
        np.testing.assert_array_equal(a[mask, j], b[mask, j])
    p = np.loadtxt(basepath / "met.PFL")
    q = np.loadtxt(OUT / "Meteorologia/Tmas1/met.PFL")
    assert p.shape == q.shape and np.array_equal(p[:, :8], q[:, :8])
    valid_temperature = p[:, 8] != 99
    assert np.array_equal(valid_temperature, q[:, 8] != 99)
    # Ambas temperaturas se serializan a0,01°C; no confundir sentinelas con datos.
    assert np.max(abs(q[valid_temperature, 8] - p[valid_temperature, 8] - 1)) <= .011
    members = pd.read_csv(OLD / "Comunes/membresia.csv")
    newruns, oldruns = read(OUT / "Corridas.json"), read(OLD / "Corridas.json")
    jobs = {("Tmas1", pol): Path(r["carpeta"]) for pol, r in newruns.items()}
    for r in list(newruns.values()) + list(oldruns.values()): verify(r["archivos"])
    jobs.update({(r["escenario"], r["contaminante"]): Path(r["carpeta"]) for r in oldruns.values()})
    assert len(jobs) == 6
    daily, native = [], {}
    raw_count = 0
    cols = ["x_m", "y_m", "C", "elev", "hill", "flag", "avg", "group", "date"]
    for (scenario, pol), folder in jobs.items():
        reference = OLD / "Casos" / ("BASE_" + pol)
        for name in ("fuentes_aermod.inc", "receptores.inc", pol + ".emi"):
            assert sha256(folder / name) == sha256(reference / name)
        qa, _, _ = verificar_dispersion(folder, 12263, 4, members, "2016-12-21", "2016-12-23")
        native[scenario + "_" + pol] = qa
        raw = pd.read_csv(folder / "receptor_horas.out", sep=r"\s+", comment="*", header=None,
                          names=cols, usecols=range(9), dtype={"date": str})
        raw_count += len(raw)
        raw["dia"] = pd.to_datetime(raw.date.str[:6], format="%y%m%d").dt.strftime("%Y-%m-%d")
        agg = raw.groupby(["x_m", "y_m", "dia"]).C.agg(["size", "mean"]).reset_index()
        assert (agg["size"] == 24).all() and len(agg) == 8
        agg = agg.merge(members[["x_m", "y_m", "grupo"]], on=["x_m", "y_m"], validate="many_to_one")
        agg["escenario"] = scenario; agg["contaminante"] = pol
        daily.append(agg)
    assert raw_count == 1152
    for pol in ("MP10", "MP25"):
        assert native["Tmas1_" + pol]["advertencias"] == native["BASE_" + pol]["advertencias"]
    d = pd.concat(daily, ignore_index=True)
    lookup = d.set_index(["escenario", "contaminante", "grupo", "dia"])["mean"]
    comparison = pd.read_csv(OUT / "Contrastes.csv")
    for r in comparison.itertuples():
        baseline = lookup.loc[("BASE", r.contaminante, r.grupo, r.dia)]
        value = lookup.loc[(r.escenario, r.contaminante, r.grupo, r.dia)]
        np.testing.assert_allclose([r.BASE, r.concentracion, r.delta],
                                   [baseline, value, value-baseline], rtol=0, atol=1e-12)
        if baseline > .0004:
            np.testing.assert_allclose(r.porcentaje, 100*(value-baseline)/baseline, rtol=0, atol=1e-10)
        else:
            assert np.isnan(r.porcentaje)
    DEST.mkdir()
    pd.DataFrame(rows).to_csv(DEST / "Cambios_campos_AERMET_Tmas1.csv", index=False, encoding="utf-8-sig")
    d.to_csv(DEST / "Medias_reconstruidas.csv", index=False, encoding="utf-8-sig")
    # Figura científica: valores por punto, sin bandas de incertidumbre ficticias.
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2), layout="constrained")
    for ax, group in zip(axes.flat, LABELS):
        x = np.arange(2); width = .24
        for i, (scenario, color, label) in enumerate([
            ("BASE", "#566573", "BASE"), ("Tmas1", "#d68910", "T +1 °C"), ("VEC", "#2471a3", "Viento: u+1; v−0,5 m/s")]):
            values = [lookup.loc[(scenario, "MP10", group, day)] for day in ("2016-12-21", "2016-12-22")]
            ax.bar(x + (i-1)*width, values, width=width, color=color, label=label)
        ax.set_xticks(x, ["21 dic", "22 dic"]); ax.set_title(LABELS[group])
        ax.set_ylabel("MP10 medio de 24 h (µg/m³)")
        ax.grid(axis="y", alpha=.2); ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, fontsize=9)
    fig.suptitle("Respuesta a perturbaciones meteorológicas técnicas\nMismas fuentes, receptores y procesamiento · 21–22 diciembre 2016", fontsize=14)
    fig.savefig(DEST / "Concentraciones_por_receptor.png", dpi=165)
    fig.savefig(DEST / "Concentraciones_por_receptor.pdf")
    plt.close(fig)
    lines = [
        "# Recepción e interpretación de la comparación meteorológica",
        "",
        "**Comparación recibida:** seis corridas verificadas desde sus archivos nativos, "
        "1152 concentraciones horarias, de las cuales 384 son nuevas. Cuatro puntos exactos, dos días, "
        "12.263 fuentes físicas y dos contaminantes. Cero horas faltantes, cero calmas y cero errores fatales "
        "en este ensayo. Las advertencias coinciden con BASE; no se describen como inexistentes.",
        "",
        "El nuevo BASE coincide literalmente con el anterior de viento en los cinco productos meteorológicos. "
        "Fuentes, emisiones horarias, cotas y receptores coinciden por hash. Las medias y los 32 contrastes "
        "se reconstruyeron desde POSTFILE con agregación separada, sin ejecutar otra vez los modelos.",
        "",
        "| Receptor | Cambio T+1 °C, 21/22 dic | Cambio VEC, 21/22 dic |",
        "|---|---:|---:|"]
    for group, label in LABELS.items():
        sub = comparison.loc[(comparison.grupo == group) & (comparison.contaminante == "MP10")]
        t = sub.loc[sub.escenario == "Tmas1"].sort_values("dia")
        v = sub.loc[sub.escenario == "VEC"].sort_values("dia")
        lines.append(f"| {label} | {t.porcentaje.iloc[0]:+.3f} % / {t.porcentaje.iloc[1]:+.3f} % "
                     f"| {v.porcentaje.iloc[0]:+.2f} % / {v.porcentaje.iloc[1]:+.2f} % |")
    lines += [
        "",
        "En Sulfatos, el +749,79 % del primer día corresponde a pasar de 0,004700 a 0,039940 µg/m³: "
        "incremento absoluto de 0,035240 µg/m³. El porcentaje grande refleja también un BASE pequeño.",
        "",
        "## Qué explica la respuesta térmica pequeña",
        "",
        "La perturbación de +1 °C se recupera en las 48 horas SFC y en todas las temperaturas válidas del perfil. "
        "Por tanto, el cambio pequeño de concentración no se debe a que el incremento se haya perdido.",
        "",
        "Las alturas de mezcla, viento y Bowen no cambian a la precisión de SFC. Los flujos WRF y PBLH fueron "
        "mantenidos en las copias de entrada por diseño; AERMET sí modifica algunos diagnósticos: H hasta +0,2 W/m², "
        "u* hasta +0,001 m/s, w* hasta +0,002 m/s y L hasta +5,1 m. La humedad relativa disminuye entre 1 y 4 puntos "
        "porcentuales. El detalle queda en Cambios_campos_AERMET_Tmas1.csv.",
        "",
        "Esto es una sensibilidad condicionada al operador y a los campos conservados, no el efecto total de "
        "un error térmico que altere conjuntamente flujos, mezcla y circulación. No permite concluir que "
        "temperatura sea irrelevante ni jerarquizar incertidumbre frente a viento con amplitudes distintas.",
        "",
        "## Continuación de alcance fijo",
        "",
        "El siguiente contraste debe mantener u+1/v−0,5 m/s en superficie y comparar la transferencia uniforme "
        "con la acotada por PBLH ya documentada. Se verificará el adaptador y el procesamiento antes de "
        "interpretar concentraciones. No se cambia la geometría ni se abre otra campaña de fuentes.",
        "",
        "Después corresponde revisar la estabilidad del modelo conjunto de discrepancias. Su evaluación "
        "norte-sur fallida se conserva; todavía no se justifican bandas probabilísticas de concentración. "
        "Los máximos zonales de MINA/Olivares/GENERAL siguen fuera de esta comparación de cuatro puntos.",
        "",
        "## Texto de resultado utilizable en la tesis",
        "",
        "«En el ensayo de sensibilidad del 21–22 de diciembre de 2016 se mantuvieron constantes las fuentes, "
        "las emisiones horarias, los receptores y la configuración de procesamiento meteorológico. En el "
        "receptor de la estación Los Bronces, un incremento uniforme de 1 °C produjo cambios de −0,0113 % "
        "y −0,0306 % en las medias diarias de MP10. La perturbación vectorial de +1 m/s hacia el este y "
        "−0,5 m/s hacia el norte produjo aumentos de 17,87 % y 10,50 %, respectivamente. Estos resultados "
        "describen respuestas condicionadas a los operadores aplicados y no constituyen una jerarquización "
        "de incertidumbre, una validación de concentraciones ni una extrapolación al período estival completo.»",
        "",
        "Referencia documental corregida: manual MMIF 4.1.1, sección 2.3.1, página impresa 10. "
        "La fe de erratas del paquete conserva la trazabilidad de la cita anterior."
    ]
    (DEST / "Lectura_resultados.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    receipt = dict(estado="COMPARACION_COMUN_RECIBIDA", valores_nuevos=384, valores_recibidos=1152,
                   casos=6, horas_por_caso=48, receptores=4, fuentes=12263,
                   base_reconstruido_identico=True, fuentes_emisiones_receptores_identicos=True,
                   medias_reconstruidas_desde_POSTFILE=True, contrastes_verificados=32,
                   temperatura_SFC_mas1_en48_horas=True, perfiles_T_mas1_verificados=True,
                   advertencias_nuevas=False, nativos=native,
                   archivos=[{"path": str(p), "sha256": sha256(p)} for p in [
                       Path(__file__), OUT / "Estado.json", OUT / "Preprocesamiento.json",
                       OUT / "Corridas.json", *sorted(DEST.iterdir())] if p.is_file()])
    guardar_json(DEST / "Verificacion_recepcion.json", receipt)
    # Memoria operativa: sustituir espera de CMD ya resuelta, mantener historial útil.
    context = O / "Contexto_vigente.md"
    text = context.read_text(encoding="utf-8")
    start = text.index("## Ventana común y transferencia vertical")
    end = text.index("## Prioridad explícita del usuario")
    current = """## Comparación meteorológica común recibida

El usuario completó EJECUTAR_COMPARACION.cmd con código0. La entrega Meteorologia_comun_2026-10-20 está completa; **no pedir repetir CMD, MMIF, AERMET ni AERMOD**. Recepción separada mediante work/recibir_meteorologia_comun_20261020.py: seis casos,1152 valores desde POSTFILE,384 nuevos,32 contrastes reproducidos,48h y cuatro puntos por caso. Evidencia Recepcion/Verificacion_recepcion.json. Cero fatales/calmas/faltantes; advertencias iguales a BASE, no inexistentes.

BASE nuevo coincide literalmente en SFC/PFL/SURFACE/ONSITE/UPPER con BASE de viento. La diferencia anterior de Bowen0,64/0,30 provenía de ventanas216/96h. No imponer0,30 como valor estacional. MMIF manual§2.3.1p10 y output_onsite.f90:717–737/911–920. Fe_de_erratas_documental.md corrige referencia antigua2.3.2.

MP10 LBCEN21dic BASE94,230265→Tmas194,219641(−0,011274%) yVEC111,071131(+17,8720%). Día22 BASE106,553226→Tmas1106,520620(−0,030601%) yVEC117,741633(+10,5003%). PCAR VEC−6,8077%/+16,8554%; PALP+61,214%/+22,216%. SULF+749,787% equivale0,004700→0,039940µg/m³(delta0,035240); informar absolutos junto al porcentaje.

La temperatura sí sube1K en48h SFC y perfiles válidos. SFC conserva ZiC/ZiM, viento y Bowen; cambiaH≤+0,2W/m²,u*≤+0,001,w*≤+0,002,L≤+5,1m,RH−4 a−1puntos. No concluir que temperatura carece de importancia: es perturbación a campos WRF de flujo/mezcla constantes, sin reintegración dinámica. No comparar amplitudes técnicas como ranking de incertidumbre.

Recepcion/Lectura_resultados.md contiene interpretación y párrafo utilizable en tesis; figura Concentraciones_por_receptor.png/PDF. No calcula máximos MINA/Olivares/GENERAL ni sustituye sus ámbitos con cuatro puntos.

Siguiente ensayo acotado: misma perturbación vectorial superficial, uniforme frente a transferencia limitada por PBLH, con fuentes/receptores/ventana fijos. Falta adaptador y verificación de cadena; no anunciarlo ejecutado. Después revisar estabilidad del error, sin reciclar evaluación abierta del generador como reservada.

Transferencia_vertical_2026-10-20 sigue sólo como candidato algebraico. w=1−3s²+2s³, s=clip((z−10)/(PBLH_BASE−10),0,1), rechazaPBLH≤10.97instantes/59niveles, PBLH77,02–1773,09m, siete controles aprobados. No escribió WRF ni corrió cadena.10m es nivel de U10/V10, no altura conocida del sensor; hipótesis de tesis, no prescripción EPA ni transferencia espacial validada. No usar todavía las1024 realizaciones fallidas como incertidumbre calibrada.

El fallo WinError623 desde herramientas es histórico para esta entrega y quedó resuelto ejecutándola el usuario desdeCMD. No hay modelos activos de esta etapa ni acción del usuario pendiente para recibirla. Conservar paquetes congelados.

"""
    context.write_text(text[:start] + current + text[end:], encoding="utf-8")
    statepath = O / "Foco_meteorologico_2026-10-20.json"
    state = read(statepath)
    state.update(comparacion_meteorologica_comun="RECIBIDA", valores_comparacion=1152,
                 accion_usuario_requerida=False, siguiente="ADAPTADOR_TRANSFERENCIA_VERTICAL_Y_CONTRASTE_EMPAREJADO",
                 motivo="Comparación común terminada; preparar siguiente ensayo sin refinar fuentes.")
    guardar_json(statepath, state)
    print(json.dumps({k: receipt[k] for k in ("estado", "valores_recibidos", "valores_nuevos",
                      "casos", "contrastes_verificados", "base_reconstruido_identico", "advertencias_nuevas")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
