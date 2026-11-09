"""Recepción numérica separada e interpretación; no reajusta el modelo congelado."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/Generador_meteorologico_2026-10-20"
FIT = ROOT / "outputs/Discrepancias_ajuste_2026-10-19"
REV = OUT / "Revision"
COLS = ["residuo_T_C", "residuo_u_m_s", "residuo_v_m_s"]
OBS = ["Temperatura_aire_C", "u_obs_m_s", "v_obs_m_s"]
BASE = ["T2_C", "u_earth_m_s", "v_earth_m_s"]


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""): h.update(b)
    return h.hexdigest()


def crps_cdf(x, y):
    """Integral exacta por escalones de (F(z)-1[z>=y])²."""
    x = np.sort(x)
    edges = np.unique(np.r_[x, y])
    cdf = np.searchsorted(x, edges[:-1], side="right") / len(x)
    return float(np.sum(np.diff(edges) * (cdf - (edges[:-1] >= y))**2))


def main():
    assert not REV.exists(), "No sobrescribir recepción."
    frozen = json.loads((OUT / "Congelacion.json").read_text(encoding="utf-8"))
    evaluation = json.loads((OUT / "Evaluacion/Verificacion.json").read_text(encoding="utf-8"))
    for record in frozen["archivos"] + evaluation["archivos"]:
        assert sha(record["path"]) == record["sha256"], record["path"]
    fit = pd.read_csv(FIT / "Residuos_ajuste.csv")
    d = pd.read_csv(OUT / "Evaluacion/Pares_evaluacion.csv")
    times = pd.to_datetime(d.fecha_utc, utc=True)
    local = times.dt.tz_convert("Etc/GMT+3").dt.tz_localize(None)
    obs, base = d[OBS].to_numpy(), d[BASE].to_numpy()
    actual = obs - base
    np.testing.assert_allclose(actual, d[COLS].to_numpy(), atol=1e-10, rtol=0)
    assert len(times) == 168 and np.isfinite(np.c_[obs, base]).all()
    assert times.iloc[0] == pd.Timestamp("2017-01-24T03:49Z")
    assert times.iloc[-1] == pd.Timestamp("2017-01-31T02:49Z")
    table = pd.read_csv(OUT / "Evaluacion/Metricas.csv")
    daily = []
    for stage, frame, values in [("ajuste", fit, fit[COLS].to_numpy()), ("evaluacion", d, actual)]:
        dates = pd.to_datetime(frame.fecha_utc, utc=True).dt.tz_convert("Etc/GMT+3").dt.date
        for day in sorted(dates.unique()):
            mask = (dates == day).to_numpy()
            for j, label in enumerate(("T_C", "u_m_s", "v_m_s")):
                daily.append(dict(rol=stage, dia_local=str(day), variable=label,
                                  n=int(np.isfinite(values[mask, j]).sum()), media=float(np.nanmean(values[mask, j]))))
    check_errors = []
    ranges = []
    for length in (24, 48):
        z = np.load(OUT / f"Realizaciones_L{length}.npz")
        r, indices, starts = z["residuos"], z["indices_ajuste"], z["inicios_bloques"]
        np.testing.assert_array_equal(r, fit[COLS].to_numpy()[indices])
        assert np.array_equal(indices % 24, np.broadcast_to(np.arange(168) % 24, indices.shape))
        for block in range(starts.shape[1]):
            n = min(length, 168 - block * length)
            np.testing.assert_array_equal(indices[:, block * length:block * length + n], starts[:, block, None] + np.arange(n))
        pred = base[None] + r
        scores = np.array([[crps_cdf(pred[:, h, j], obs[h, j]) for j in range(3)] for h in range(168)])
        summary = table.loc[(table.modelo == f"BLOQUES_{length}h") & (table.franja == "todas")].set_index("variable")
        for j, label in enumerate(("T_C", "u_m_s", "v_m_s")):
            diff = abs(scores[:, j].mean() - summary.loc[label, "CRPS"])
            assert diff < 1e-12
            check_errors.append(diff)
            for p in (.5, .8, .9):
                lo, hi = np.quantile(pred[:, :, j], [(1-p)/2, (1+p)/2], axis=0)
                cover = ((obs[:, j] >= lo) & (obs[:, j] <= hi)).mean()
                np.testing.assert_allclose(cover, summary.loc[label, f"cobertura_{int(100*p)}"], atol=1e-14, rtol=0)
            ranges.append(dict(longitud_h=length, variable=label, sesgo_ajuste=float(fit[COLS[j]].mean()),
                               sesgo_evaluacion=float(actual[:, j].mean()),
                               media_residuos_generados=float(r[:, :, j].mean())))
    REV.mkdir()
    pd.DataFrame(daily).to_csv(REV / "Discrepancias_medias_diarias.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(ranges).to_csv(REV / "Cambio_entre_periodos.csv", index=False, encoding="utf-8-sig")
    r = np.load(OUT / "Realizaciones_L48.npz")["residuos"]
    lo, hi = np.quantile(r, [.05, .95], axis=0)
    fig, axes = plt.subplots(3, 1, figsize=(11, 8.8), sharex=True, layout="constrained")
    names = ["Temperatura (°C)", "Viento este-oeste u (m/s)", "Viento norte-sur v (m/s)"]
    for j, ax in enumerate(axes):
        ax.fill_between(local, lo[:, j], hi[:, j], color="#bdd9ee", label="Intervalo central 90 % del generador")
        ax.plot(local, r[:, :, j].mean(axis=0), color="#21618c", lw=1.3, label="Media del generador")
        ax.plot(local, actual[:, j], color="#932c48", lw=1.4, label="Discrepancia observada − WRF")
        ax.axhline(0, color="#555555", lw=.8, ls="--")
        ax.set_ylabel(names[j]); ax.grid(alpha=.2)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(ncol=1, loc="upper right", fontsize=8)
    axes[-1].xaxis.set_major_locator(mdates.DayLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d ene"))
    axes[-1].set_xlabel("Evaluación interna 2017 · hora local UTC−3 · registros a :49")
    fig.suptitle("Prueba del modelo conjunto de discrepancias\nBloques de 48 h, fijados antes de evaluar", fontsize=15)
    fig.savefig(REV / "Evaluacion_conjunta.png", dpi=165)
    fig.savefig(REV / "Evaluacion_conjunta.pdf")
    plt.close(fig)
    summary = table.loc[table.franja == "todas"].set_index(["modelo", "variable"])
    worse = (summary.loc[("BLOQUES_48h", "v_m_s"), "CRPS"] / summary.loc[("BASE", "v_m_s"), "CRPS"] - 1) * 100
    note = f"""# Decisión tras la evaluación meteorológica

Se completó la evaluación interna de las 168 horas del 24–30 de enero y su recepción numérica separada. El generador 1.0 permanece congelado: no se ajustaron parámetros ni se eligió longitud después de observar esta semana.

**El modelo conjunto aún no justifica una propagación calibrada a concentraciones.** Mejora el CRPS de temperatura y de la componente este-oeste respecto de BASE, pero empeora la componente norte-sur en {worse:.2f} %. El contraste de 24 h tampoco resuelve ese deterioro. No procede escoger únicamente las variables o realizaciones favorables y presentarlas como validación conjunta.

La discrepancia media norte-sur es +4,423 m/s en ajuste y −0,593 m/s en evaluación. El generador de 48 h produce una corrección media +3,568 m/s; al sumarla a WRF deja un sesgo predicho−observado de +4,161 m/s. Su intervalo central del 90 % cubre el 71,43 % de esta semana y tiene anchura media 12,964 m/s. Por tanto, aumentar dispersión por sí solo no resuelve el problema.

Esta diferencia entre períodos señala que transportar una distribución fija de errores puede no describir bien el régimen objetivo. No prueba por sí sola la causa: deben considerarse representatividad, cambios meteorológicos y la hipótesis horaria. No se cambiará el reloj para mejorar el ajuste. La selección de bloques completos también cambia la ponderación: media esperada de v≈3,603 frente a 4,423 m/s en las 737 ternas; se conserva el diagnóstico de ese efecto.

Los 1024 miembros permiten evaluar el generador en estación y no equivalen a 1024 observaciones ni a corridas AERMOD. Las bandas son meteorológicas, no intervalos de concentración. Los controles de finitud y rangos no acreditan termodinámica, perfil vertical ni transferencia espacial.

## Continuación acotada

1. Mantener como resultados de tesis las sensibilidades meteorológicas emparejadas, con fuentes fijas, junto con este diagnóstico del modelo de discrepancias.
2. Resolver el procesamiento común y documentar una transferencia superficial/perfil físicamente explícita. Preparar sólo el siguiente contraste meteorológico interpretable; no volver a refinar fuentes por defecto.
3. Revisar estabilidad del error y alternativas condicionadas al estado meteorológico usando ajuste. Esta semana ya está abierta y no podrá presentarse como evaluación reservada de una versión modificada; esa limitación no se elimina con otra semilla.
4. El lote de ocho realizaciones de concentración queda condicionado a esa revisión. Si se ejecuta sólo como sensibilidad exploratoria, debe conservar ese nombre y no convertirse en una estimación de incertidumbre total.

No se necesita repetir AERMAP ni aportar más WRF para estos pasos. Los resultados zonales previos se conservan con su limitación de resolución.
"""
    (REV / "Decision.md").write_text(note, encoding="utf-8")
    receipt = dict(estado="GENERADOR_Y_EVALUACION_RECIBIDOS", ternas_ajuste=737, horas_evaluacion=168,
                   realizaciones_por_longitud=1024, longitudes_h=[24, 48],
                   metodo_recepcion_CRPS="Integral CDF empírica por escalones, distinta a fórmula ordenada del generador",
                   error_CRPS_max=float(max(check_errors)), trazabilidad_conjunta_exacta=True,
                   cobertura_reconstruida=True, modelo_no_reajustado=True,
                   decision="NO_ADOPTAR_COMO_MODELO_CONJUNTO_CALIBRADO",
                   deterioro_CRPS_v_porcentaje=float(worse),
                   archivos=[{"path": str(p), "sha256": sha(p)} for p in sorted(REV.iterdir()) if p.is_file()])
    (REV / "Recepcion.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k != "archivos"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
