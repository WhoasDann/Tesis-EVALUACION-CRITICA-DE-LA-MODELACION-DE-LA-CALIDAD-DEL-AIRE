"""Generador conjunto en estación: congelar ajuste antes de evaluar días reservados."""
from pathlib import Path
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/Generador_meteorologico_2026-10-20"
FIT = ROOT / "outputs/Discrepancias_ajuste_2026-10-19"
SOURCE = Path(r"/archivo/usuario\Documents\Codex\2026-10-10\ten\outputs\Piloto_meteorologico\pares_civil_interpolacion_exploratorios.csv")
COLS = ["residuo_T_C", "residuo_u_m_s", "residuo_v_m_s"]
OBS = ["Temperatura_aire_C", "u_obs_m_s", "v_obs_m_s"]
BASE = ["T2_C", "u_earth_m_s", "v_earth_m_s"]
LABELS = ["T_C", "u_m_s", "v_m_s"]
SEED = 20261020
MEMBERS = 1024


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def record(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


def verify(records):
    for entry in records:
        if sha(entry["path"]) != entry["sha256"]:
            raise ValueError("Archivo congelado modificado: " + entry["path"])


def correlation(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3 or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
        return float("nan")
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


def starts_complete(values, length):
    return np.array([i for i in range(0, len(values) - length + 1, 24)
                     if np.isfinite(values[i:i + length]).all()], dtype=int)


def sample_indices(starts, length, horizon, members, seed):
    if not len(starts) or horizon < 1:
        raise ValueError("No hay bloques completos o horizonte válido.")
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, length])))
    chosen = rng.choice(starts, size=(members, math.ceil(horizon / length)), replace=True)
    indices = (chosen[:, :, None] + np.arange(length)[None, None, :]).reshape(members, -1)[:, :horizon]
    return indices, chosen


def crps(samples, observations):
    """CRPS de distribución empírica, eje 0=miembros; unidades de la variable."""
    x = np.asarray(samples, float)
    y = np.asarray(observations, float)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("CRPS requiere una máscara común finita.")
    m = x.shape[0]
    weights = (2 * np.arange(1, m + 1) - m - 1).reshape((m,) + (1,) * (x.ndim - 1))
    return np.mean(abs(x - y), axis=0) - np.sum(weights * np.sort(x, axis=0), axis=0) / m**2


def self_test():
    # Contraste independiente con la definición de pares, no sólo la fórmula rápida.
    x = np.array([[0., 3.], [2., 7.], [8., 5.]])
    y = np.array([1., 6.])
    brute = abs(x - y).mean(axis=0) - abs(x[:, None] - x[None, :]).mean(axis=(0, 1)) / 2
    np.testing.assert_allclose(crps(x, y), brute, rtol=0, atol=1e-14)
    np.testing.assert_allclose(crps(x[:1], y), abs(x[0] - y))
    a = np.ones((120, 3)); a[25] = np.nan
    assert list(starts_complete(a, 48)) == [48, 72]
    idx, draws = sample_indices(np.array([0, 48]), 48, 168, 8, SEED)
    assert np.array_equal(idx, sample_indices(np.array([0, 48]), 48, 168, 8, SEED)[0])
    assert (idx % 24 == np.arange(168) % 24).all()
    assert (np.diff(idx.reshape(8, 7, 24), axis=2) == 1).all()
    assert draws.shape == (8, 4)
    return {"CRPS_definicion_directa": True, "CRPS_determinista_MAE": True,
            "huecos_no_cruzados": True, "semilla_reproducible": True, "alineacion_diurna": True}


def prepare():
    if OUT.exists():
        raise FileExistsError("No sobrescribir el modelo congelado.")
    tests = self_test()
    receipt = json.loads((FIT / "Recepcion_independiente.json").read_text(encoding="utf-8"))
    verify(receipt["archivos"])
    d = pd.read_csv(FIT / "Residuos_ajuste.csv")
    t = pd.to_datetime(d.fecha_utc, utc=True)
    hour = pd.to_datetime(d.fecha_local).dt.hour
    assert len(d) == 744 and np.all(np.diff(t.astype("int64")) == 3600 * 10**9)
    x = d[COLS].to_numpy(float)
    valid = np.isfinite(x).all(axis=1)
    assert valid.sum() == 737 and (valid == d.valido_conjunto).all()
    partition = pd.read_csv(FIT / "Particion_preexistente.csv")
    eval_days = partition.loc[partition.rol.eq("evaluacion_interna")]
    start = pd.to_datetime(eval_days.inicio_utc.iloc[0], utc=True) + pd.Timedelta(minutes=49)
    end = pd.to_datetime(eval_days.fin_utc_exclusivo.iloc[-1], utc=True)
    target = pd.date_range(start, end, freq="h", inclusive="left")
    assert len(target) == 168 and target[0] > t.iloc[-1] + pd.Timedelta(hours=72)
    means = d.groupby(hour)[COLS].mean()
    centered = x - means.loc[hour].to_numpy()
    dep = []
    for kind, z in [("crudo", x), ("sin_media_horaria_ajuste", centered)]:
        for j, col in enumerate(COLS):
            for lag in (1, 3, 6, 12, 24, 36, 48, 60, 72, 96, 120, 144, 168):
                a, b = z[:-lag, j], z[lag:, j]
                dep.append(dict(tipo=kind, variable=col, lag_h=lag,
                                pares=int((np.isfinite(a) & np.isfinite(b)).sum()), correlacion=correlation(a, b)))
    OUT.mkdir()
    pd.DataFrame(dep).to_csv(OUT / "Dependencia_ajuste.csv", index=False, encoding="utf-8-sig")
    means.index.name = "hora_local"
    means.to_csv(OUT / "Ciclo_medio_ajuste.csv", encoding="utf-8-sig")
    pd.DataFrame({"fecha_utc": target, "fecha_local": target.tz_convert("Etc/GMT+3").tz_localize(None)}).to_csv(
        OUT / "Calendario_evaluacion.csv", index=False, encoding="utf-8-sig")
    support, pools, audit = [], [], []
    for length in (24, 48, 72):
        starts = starts_complete(x, length)
        nonoverlap, last_end = 0, -1
        for s in starts:
            if s >= last_end:
                nonoverlap += 1; last_end = s + length
        support.append(dict(longitud_h=length, candidatos=len(starts), no_solapados=nonoverlap, admisible=nonoverlap >= 10))
        if nonoverlap < 10:
            continue
        pool = np.stack([x[s:s + length] for s in starts])
        indices, chosen = sample_indices(starts, length, len(target), MEMBERS, SEED)
        r = x[indices]
        assert np.isfinite(r).all() and (indices % 24 == np.arange(len(target)) % 24).all()
        np.savez_compressed(OUT / f"Realizaciones_L{length}.npz", residuos=r, indices_ajuste=indices,
                            inicios_bloques=chosen, candidatos=starts)
        for j, col in enumerate(COLS):
            expected = pool.mean(axis=0)[np.arange(len(target)) % length, j].mean()
            pools.append(dict(longitud_h=length, variable=col, media_737=float(np.nanmean(x[:, j])),
                              media_pool=float(pool[:, :, j].mean()), media_esperada_168h=float(expected),
                              media_realizaciones=float(r[:, :, j].mean()),
                              delta_soporte=float(expected - np.nanmean(x[:, j]))))
        for member, row in enumerate(chosen, 1):
            for k, s in enumerate(row):
                n = min(length, len(target) - k * length)
                audit.append(dict(longitud_h=length, miembro=member, bloque=k + 1, inicio_indice_ajuste=int(s),
                                  origen_utc=str(t.iloc[s]), objetivo_utc=str(target[k * length]), horas_usadas=n))
    assert support[1]["no_solapados"] == 13 and not support[2]["admisible"]
    pd.DataFrame(support).to_csv(OUT / "Soporte.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(pools).to_csv(OUT / "Efecto_seleccion_bloques.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(audit).to_csv(OUT / "Trazabilidad_bloques.csv", index=False, encoding="utf-8-sig")
    dump(OUT / "Pruebas_preparacion.json", tests)
    config = dict(version="1.0", fecha_documental="2026-10-20", longitud_principal_h=48, alternativa_h=24,
                  criterio="Mayor longitud candidata con >=10 bloques no solapados; persistencia residual de v favorece 48 sobre 24.",
                  decision_antes_de_evaluar=True, n_miembros=MEMBERS, semilla=SEED, rng="PCG64 + SeedSequence([semilla,longitud])",
                  signo="r=observado-WRF; X*=Xbase+r*",
                  distribucion="Uniforme sobre bloques completos solapados; T/u/v se copian juntos, sin centrar ni sumar otro sesgo.",
                  ciclo="Alineación 00:49 local; UTC-3 sólo para este tramo estival.",
                  cortes="Bloques independientes entre sí; última pieza de48 usa sus primeras24h. No conserva toda dependencia entre bloques.",
                  sesgo="El sesgo está en los residuos crudos. El pool elegible puede diferir de737 filas; efecto cuantificado, no corregido ocultamente.",
                  truncamiento="Ninguno. No se rechazan miembros por amplitud ni por concentración.",
                  evaluacion="24-30ene2017 interna, exposición descriptiva previa; no validación independiente ni garantía nominal.",
                  comparaciones=["BASE", "BASE+sesgo_global_ajuste", "BASE+ciclo_medio_ajuste"],
                  metricas=["CRPS", "sesgo_predicho-menos-observado", "RMSE_media", "anchura_cobertura50_80_90", "persistencia", "correlacion"],
                  franjas="06-17 y18-05, horas locales; no equivalen a día/noche solar.",
                  regla_revision="Reportar deterioro CRPS frente a cada referencia, cobertura por franja, sesgo y dependencia; no elegir L con evaluación.",
                  alcance="Modelo aditivo en estación. Sin transferencia al dominio/perfil y sin concentraciones AERMOD.",
                  referencias=["https://doi.org/10.1111/ecog.02881", "https://acp.copernicus.org/articles/23/12477/2023/"])
    dump(OUT / "Modelo.json", config)
    (OUT / "Metodo_congelado.md").write_text(
        "# Generador conjunto de discrepancias en estación\n\n"
        "Se congela antes de calcular métricas del 24–30 de enero. Ajuste: 737 ternas válidas del 21dic–20ene; "
        "separación 21–23ene. H-CIVIL, instante :49 conservado. La exposición descriptiva previa permanece declarada.\n\n"
        "Principal: bloques48h (23 candidatos, 13 no solapados); contraste24h (26 candidatos). "
        "72h tiene8 no solapados, inferior al mínimo operativo10. Se elige la mayor longitud admisible para conservar "
        "más persistencia, no mediante resultados reservados. Al retirar la media por hora sólo para diagnóstico, "
        "la correlación a72h es aproximadamente −0,048/0,003/−0,055 para T/u/v. Esto no demuestra independencia. "
        "A48h v aún tiene correlación≈0,195, una limitación del corte de bloques.\n\n"
        "Se sortean1024 secuencias por opción y se copian las ternas de residuos crudos completas, con reemplazo "
        "y alineación diurna. Se usa X*=BASE+r*, sin agregar otro sesgo. Los bloques completos ponderan de modo "
        "distinto algunas fechas respecto de las737 ternas: Efecto_seleccion_bloques.csv lo cuantifica. "
        "Se conservan variaciones internas y asociación conjunta, pero no se garantiza dependencia entre bloques, "
        "estacionariedad ni relación del error con el régimen meteorológico objetivo. El último bloque48 se trunca a24h.\n\n"
        "1024 miembros reducen ruido computacional de la distribución empírica; no crean observaciones nuevas. "
        "Intervalos50/80/90 se examinarán con anchura y CRPS, por variable y franja horaria, contra BASE y "
        "dos correcciones deterministas obtenidas sólo en ajuste. No se escogerá el mejor bloque mirando evaluación. "
        "Se reportarán asimismo persistencia y correlaciones. No se habilita AERMOD por aprobar formatos.\n\n"
        "La separación temporal sigue el principio de evaluación de datos dependientes de "
        "[Roberts et al.](https://doi.org/10.1111/ecog.02881); las fechas y cantidades son decisiones del protocolo de esta tesis. "
        "La distinción entre dispersión y calibración se apoya conceptualmente en "
        "[Jones et al.](https://acp.copernicus.org/articles/23/12477/2023/), sin trasladar su validación a esta cadena.\n",
        encoding="utf-8")
    inputs = [FIT / "Residuos_ajuste.csv", FIT / "Particion_preexistente.csv", FIT / "Recepcion_independiente.json", Path(__file__)]
    frozen = dict(estado="GENERADOR_CONGELADO_ANTES_EVALUACION", fecha_utc=datetime.now(timezone.utc).isoformat(),
                  archivos=[record(p) for p in inputs + sorted(OUT.iterdir()) if p.is_file()])
    dump(OUT / "Congelacion.json", frozen)
    print(json.dumps({"estado": frozen["estado"], "soporte": support, "pruebas": tests}, ensure_ascii=False))


def evaluate():
    frozen = json.loads((OUT / "Congelacion.json").read_text(encoding="utf-8"))
    verify(frozen["archivos"])
    dest = OUT / "Evaluacion"
    if dest.exists():
        raise FileExistsError("Evaluación ya abierta; no sobrescribir ni reajustar silenciosamente.")
    # Registrar apertura antes de leer el archivo con observaciones reservadas.
    dest.mkdir()
    dump(dest / "Apertura.json", dict(fecha_utc=datetime.now(timezone.utc).isoformat(), modelo_sha256=sha(OUT / "Congelacion.json"),
                                    ajuste_cerrado=True, exposicion_previa=True, fuente=record(SOURCE)))
    fit = pd.read_csv(FIT / "Residuos_ajuste.csv")
    calendar = pd.read_csv(OUT / "Calendario_evaluacion.csv")
    target = pd.DatetimeIndex(pd.to_datetime(calendar.fecha_utc, utc=True))
    source = pd.read_csv(SOURCE)
    time = pd.to_datetime(source.fecha_objetivo_utc, utc=True)
    d = source.loc[time.isin(target)].copy()
    d.index = time.loc[time.isin(target)]
    assert d.index.is_unique and d.hipotesis.eq("civil_santiago").all() and d.operador.eq("interpolacion_instantanea").all()
    d = d.reindex(target)
    obs, base, resid = d[OBS].to_numpy(float), d[BASE].to_numpy(float), d[COLS].to_numpy(float)
    ok = np.isfinite(np.c_[obs, base, resid]).all(axis=1)
    flags = d.par_valido_Tuv.astype(str).str.lower().eq("true").to_numpy()
    assert np.array_equal(ok, flags)
    np.testing.assert_allclose(obs[ok] - base[ok], resid[ok], rtol=0, atol=1e-10)
    hour = pd.to_datetime(calendar.fecha_local).dt.hour.to_numpy()
    global_bias = fit[COLS].mean().to_numpy()
    hourly_bias = fit.groupby(pd.to_datetime(fit.fecha_local).dt.hour)[COLS].mean().loc[hour].to_numpy()
    refs = {"BASE": base, "BASE_sesgo_global": base + global_bias, "BASE_ciclo_horario": base + hourly_bias}
    d.index.name = "fecha_utc"
    d[[*OBS, *BASE, *COLS]].to_csv(dest / "Pares_evaluacion.csv", encoding="utf-8-sig")
    masks = {"todas": ok, "06_17": ok & (hour >= 6) & (hour < 18), "18_05": ok & ((hour < 6) | (hour >= 18))}
    for date in pd.to_datetime(calendar.fecha_local).dt.date.unique():
        masks[str(date)] = ok & (pd.to_datetime(calendar.fecha_local).dt.date == date).to_numpy()
    metrics, temporal, joint, physical, hourly = [], [], [], [], []
    for name, pred in refs.items():
        for group, mask in masks.items():
            if not mask.any(): continue
            for j, label in enumerate(LABELS):
                err = pred[mask, j] - obs[mask, j]
                metrics.append(dict(modelo=name, franja=group, variable=label, n=int(mask.sum()),
                                    sesgo=float(err.mean()), RMSE_media=float(np.sqrt((err**2).mean())),
                                    CRPS=float(abs(err).mean())))
    for length in (24, 48):
        data = np.load(OUT / f"Realizaciones_L{length}.npz")
        r, idx = data["residuos"], data["indices_ajuste"]
        # Reconstrucción exacta, independiente de RNG y sin separar variables.
        np.testing.assert_array_equal(r, fit[COLS].to_numpy()[idx])
        pred = base[None, :, :] + r
        mean = pred.mean(axis=0)
        label_model = f"BLOQUES_{length}h"
        values = crps(pred[:, ok], obs[ok])
        score = np.full(base.shape, np.nan); score[ok] = values
        intervals = {p: np.quantile(pred, [(1-p)/2, (1+p)/2], axis=0) for p in (.5, .8, .9)}
        for group, mask in masks.items():
            if not mask.any(): continue
            for j, label in enumerate(LABELS):
                err = mean[mask, j] - obs[mask, j]
                row = dict(modelo=label_model, franja=group, variable=label, n=int(mask.sum()),
                           sesgo=float(err.mean()), RMSE_media=float(np.sqrt((err**2).mean())),
                           CRPS=float(score[mask, j].mean()))
                for p, bounds in intervals.items():
                    low, high = bounds[:, mask, j]
                    row[f"cobertura_{int(p*100)}"] = float(((obs[mask, j] >= low) & (obs[mask, j] <= high)).mean())
                    row[f"anchura_{int(p*100)}"] = float((high - low).mean())
                metrics.append(row)
        for i in range(len(target)):
            for j, label in enumerate(LABELS):
                hourly.append(dict(modelo=label_model, fecha_utc=str(target[i]), variable=label, valido=bool(ok[i]),
                                   observado=obs[i, j], BASE=base[i, j], media=mean[i, j],
                                   p05=intervals[.9][0, i, j], p95=intervals[.9][1, i, j], CRPS=score[i, j]))
        # Mismas posiciones válidas para persistencia y asociación; huecos no se comprimen.
        observed_residuals = resid.copy(); observed_residuals[~ok] = np.nan
        synthetic = r.copy(); synthetic[:, ~ok, :] = np.nan
        for j, label in enumerate(LABELS):
            for lag in (1, 6, 24, 48):
                actual = correlation(observed_residuals[:-lag, j], observed_residuals[lag:, j])
                draws = [correlation(v[:-lag, j], v[lag:, j]) for v in synthetic]
                temporal.append(dict(modelo=label_model, variable=label, lag_h=lag, observada=actual,
                                     mediana=float(np.nanmedian(draws)), p05=float(np.nanquantile(draws, .05)),
                                     p95=float(np.nanquantile(draws, .95))))
        for j, k in ((0, 1), (0, 2), (1, 2)):
            draws = [correlation(v[:, j], v[:, k]) for v in synthetic]
            joint.append(dict(modelo=label_model, variables=LABELS[j] + "/" + LABELS[k],
                              observada=correlation(observed_residuals[:, j], observed_residuals[:, k]),
                              mediana=float(np.nanmedian(draws)), p05=float(np.nanquantile(draws, .05)),
                              p95=float(np.nanquantile(draws, .95))))
        physical.append(dict(modelo=label_model, valores_no_finitos_nuevos=int((~np.isfinite(pred[:, ok])).sum()),
                             temperatura_min_C=float(pred[:, ok, 0].min()), temperatura_max_C=float(pred[:, ok, 0].max()),
                             rapidez_max_m_s=float(np.hypot(pred[:, ok, 1], pred[:, ok, 2]).max()),
                             temperatura_bajo_cero_absoluto=int((pred[:, ok, 0] < -273.15).sum()),
                             recortes=0, transferido_WRF=False))
    table = pd.DataFrame(metrics)
    table.to_csv(dest / "Metricas.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(temporal).to_csv(dest / "Persistencia.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(joint).to_csv(dest / "Correlacion_conjunta.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(hourly).to_csv(dest / "Resumen_horario.csv", index=False, encoding="utf-8-sig")
    dump(dest / "Rangos_y_controles.json", physical)
    main = table.loc[(table.modelo == "BLOQUES_48h") & (table.franja == "todas")].set_index("variable")
    allrefs = table.loc[table.franja == "todas"].set_index(["modelo", "variable"])
    deterioration = {}
    for ref in refs:
        deterioration[ref] = [v for v in LABELS if main.loc[v, "CRPS"] > allrefs.loc[(ref, v), "CRPS"]]
    lines = ["# Evaluación interna del generador meteorológico", "",
             f"{int(ok.sum())}/168 horas con ternas válidas; cobertura de datos {ok.mean():.2%}. "
             "24–30ene2017, separado del ajuste actual, con exposición descriptiva previa. "
             "Los parámetros, semillas y realizaciones se congelaron antes de abrir esta evaluación.", "",
             "| Variable | CRPS BASE | CRPS sesgo global | CRPS ciclo horario | CRPS bloques48 | Cobertura central90 | Anchura90 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for v in LABELS:
        row = main.loc[v]
        lines.append(f"| {v} | {allrefs.loc[('BASE',v),'CRPS']:.3f} | {allrefs.loc[('BASE_sesgo_global',v),'CRPS']:.3f} | "
                     f"{allrefs.loc[('BASE_ciclo_horario',v),'CRPS']:.3f} | {row.CRPS:.3f} | "
                     f"{row.cobertura_90:.1%} | {row.anchura_90:.3f} |")
    lines += ["", "Menor CRPS es mejor; unidades °C o m/s. La referencia determinista tiene CRPS igual a MAE. "
              "La cobertura empírica se interpreta junto a la anchura y no acredita cobertura nominal futura.", "",
              "Deterioro de CRPS de bloques48 frente a referencias: " + json.dumps(deterioration, ensure_ascii=False) + ".", "",
              "Los resultados24h permanecen como contraste predefinido; no se elige ganador a partir de esta semana. "
              "Métricas diarias y franjas06–17/18–05 están en Metricas.csv; persistencia y correlación conjunta se informan por separado. "
              "Las franjas no representan día/noche astronómicos.", "",
              "**Alcance:** evaluación en estación; no se generaron nuevas concentraciones ni campos WRF. "
              "AERMOD sigue pendiente de una hipótesis física explícita de transferencia y procesamiento común. "
              "Los1024 miembros no aumentan el número de observaciones y no sustituyen días nuevos. "
              "Los rangos de temperatura/rapidez son controles numéricos, no prueba de plausibilidad del perfil o de humedad.", "",
              "Si se revisa el generador tras estos resultados, esta semana deja de ser evaluación reservada para esa revisión. "
              "Se conserva el modelo1.0 y su evaluación, sin reajuste oculto."]
    (dest / "Resultados.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    verify(frozen["archivos"])
    dump(dest / "Verificacion.json", dict(estado="EVALUACION_INTERNA_COMPLETA", horas_validas=int(ok.sum()),
         horas_esperadas=168, cobertura_datos=float(ok.mean()), modelo_congelado_intacto=True,
         realizaciones_reconstruidas=True, observaciones_no_usadas_ajuste=True, exposicion_descriptiva_previa=True,
         deterioro_CRPS=deterioration, AERMOD_habilitado=False,
         motivo="Revisión de desempeño y transferencia estación→MMIF/perfil con procesamiento común.",
         archivos=[record(p) for p in sorted(dest.iterdir()) if p.is_file()]))
    print(table.loc[table.franja == "todas", ["modelo", "variable", "n", "sesgo", "CRPS", "cobertura_90", "anchura_90"]].to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("etapa", choices=["preparar", "evaluar"])
    args = parser.parse_args()
    prepare() if args.etapa == "preparar" else evaluate()
