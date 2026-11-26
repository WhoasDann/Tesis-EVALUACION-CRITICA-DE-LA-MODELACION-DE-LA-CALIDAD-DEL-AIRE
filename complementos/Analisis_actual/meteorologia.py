from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

WORK = Path(__file__).resolve().parent
DATA = WORK / "datos"
IMAGES = None
HOURS = np.arange(24)
DIRECTION_BINS = np.arange(0, 361, 10)
SEASONS = ("verano", "invierno")
VARIABLES = (
    ("velocidad del viento", "m/s", "Velocidad_viento_m_s", "WS_wrf"),
    ("temperatura", "°C", "Temperatura_aire_C", "T2_C"),
    ("humedad relativa", "%", "Humedad_pct", "RH2_pct"),
)


def read_pairs(season):
    data = pd.read_csv(DATA / f"pares_{season}.csv.gz", index_col="fecha_utc")
    data.index = pd.to_datetime(data.index, utc=True).tz_convert("America/Santiago")
    return data


def daily_cycle(data):
    return data.groupby(data.index.hour).agg(
        media="mean", p05=lambda x: x.quantile(0.05), p95=lambda x: x.quantile(0.95),
    ).reindex(HOURS)


def plot_cycles(data, season):
    fig, axes = plt.subplots(3, 1, figsize=(8.6, 10.75), layout="constrained")
    for ax, (name, unit, obs, wrf) in zip(axes, VARIABLES, strict=True):
        pairs = data[[obs, wrf]].dropna()
        observed, simulated = daily_cycle(pairs[obs]), daily_cycle(pairs[wrf])
        for stats, source, color in [(observed, "OBS", "tab:blue"), (simulated, "WRF", "tab:orange")]:
            ax.fill_between(HOURS, stats.p05, stats.p95, color=color, alpha=.25,
                            label=f"{source} rango 90%")
        ax.plot(HOURS, observed.media, color="tab:blue", marker="o", linewidth=2,
                markersize=5, label="OBS media")
        ax.plot(HOURS, simulated.media, color="tab:orange", marker="o", linewidth=2,
                markersize=5, label="WRF media bilineal")
        ax.set(xticks=HOURS, xlim=(-.22, 23.22), xlabel="Hora local",
               ylabel=f"{name.capitalize()} [{unit}]",
               title=f"Ciclo diario de {name} - OBS y WRF bilineal d03")
        ax.grid(True, alpha=.3)
        ax.legend(fontsize=9.5)
        print(season, name, len(pairs))
    fig.savefig(IMAGES / f"ciclo_{season}.pdf")
    plt.close(fig)


def direction_frequencies(series):
    matrix = np.zeros((len(DIRECTION_BINS) - 1, len(HOURS)))
    for hour, values in series.groupby(series.index.hour):
        counts, _ = np.histogram(values.replace(360, 0), bins=DIRECTION_BINS)
        matrix[:, hour] = counts / counts.sum() * 100
    np.testing.assert_allclose(matrix.sum(axis=0), 100)
    return matrix


def plot_direction(matrices, season, vmax):
    fig, axes = plt.subplots(2, 1, figsize=(8.6, 7.1), sharex=True, layout="constrained")
    sources = ("observada", "simulada con WRF bilineal")
    for ax, values, source in zip(axes, matrices, sources, strict=True):
        image = ax.imshow(values, aspect="auto", origin="lower", cmap="jet",
                          extent=(-.5, 23.5, 0, 360), vmin=0, vmax=vmax,
                          interpolation="nearest")
        ax.set(title=f"Ciclo diario de la dirección del viento {source}",
               ylabel="Dirección del viento [°]", yticks=np.arange(0, 361, 60), xticks=HOURS)
        cbar = fig.colorbar(image, ax=ax, pad=.02, ticks=np.arange(0, vmax + 1, 10))
        cbar.set_label("Frecuencia (%)")
    axes[-1].set_xlabel("Hora local")
    name = "direccion_diaria.pdf" if season == "verano" else "direccion_diaria_invierno.pdf"
    fig.savefig(IMAGES / name)
    plt.close(fig)


if __name__ == "__main__":
    import argparse,json
    from integridad import verificar
    parser=argparse.ArgumentParser(description='Ciclos desde pares observación-WRF archivados.')
    parser.add_argument('salida',type=Path);args=parser.parse_args()
    verificar(WORK)
    IMAGES=args.salida.resolve();IMAGES.mkdir(parents=True,exist_ok=False)
    metrics=[]
    for season in SEASONS:
        frame=read_pairs(season)
        for name,unit,a,b in VARIABLES:
            pair=frame[[a,b]].dropna();error=pair[a]-pair[b]
            metrics.append(dict(temporada=season,variable=name,n=len(pair),BIAS=error.mean(),MAE=error.abs().mean(),RMSE=np.sqrt((error**2).mean()),r=pair[a].corr(pair[b])))
    pd.DataFrame(metrics).to_csv(IMAGES/'Metricas.csv',index=False)
    ref=json.loads((WORK/'referencia/pares_recuento.json').read_text())
    for season in SEASONS:
        frame=read_pairs(season)
        assert frame[['Temperatura_aire_C','T2_C','Velocidad_viento_m_s','WS_wrf']].dropna().shape[0]==ref[season.upper()]['T_y_WS']
        assert frame[['Humedad_pct','RH2_pct']].dropna().shape[0]==ref[season.upper()]['humedad']
        assert frame[['Direccion_viento_grados','WD_wrf']].dropna().shape[0]==ref[season.upper()]['direccion']
    (IMAGES/'Verificacion.json').write_text(json.dumps(dict(status='PASSED',alcance='Reproducción desde pares archivados; no reextracción de NetCDF.'),indent=2),encoding='utf-8')
    plt.rcParams.update({"pdf.fonttype": 42, "font.size": 11, "xtick.labelsize": 10.5})
    directions = {}
    for season in SEASONS:
        pairs = read_pairs(season)
        plot_cycles(pairs, season)
        direction = pairs[["Direccion_viento_grados", "WD_wrf"]].dropna()
        directions[season] = [direction_frequencies(direction[c]) for c in direction.columns]
        print(season, "dirección", len(direction))

    vmax = np.ceil(max(matrix.max() for panels in directions.values() for matrix in panels) / 10) * 10
    for season, matrices in directions.items():
        plot_direction(matrices, season, vmax)
