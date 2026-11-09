"""Diagnóstico descriptivo con ajuste solamente; no modifica el generador 1.0."""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT=Path(__file__).resolve().parents[1]
FIT=ROOT/"outputs/Discrepancias_ajuste_2026-10-19"
OUT=ROOT/"outputs/Estabilidad_ajuste_2026-10-20"
sys.path.insert(0,str(ROOT/"outputs/Biblioteca_Tesis"))
from tesis.comun import sha256,guardar_json

FIELDS={"T":("Temperatura_aire_C","T2_C","residuo_T_C","°C"),
        "u":("u_obs_m_s","u_earth_m_s","residuo_u_m_s","m/s"),
        "v":("v_obs_m_s","v_earth_m_s","residuo_v_m_s","m/s")}
START,END=pd.Timestamp("2016-12-21"),pd.Timestamp("2017-01-21")


def summarize(frame, groups):
    result=[]
    for key,part in frame.groupby(groups,sort=True):
        key=key if isinstance(key,tuple) else (key,)
        for name,(obs,base,resid,unit) in FIELDS.items():
            valid=part[[obs,base,resid]].dropna()
            if len(valid)==0:
                continue
            r=valid[resid].to_numpy()
            row=dict(zip(groups,key))
            row.update(variable=name,n=len(r),media_observada=float(valid[obs].mean()),
                media_WRF=float(valid[base].mean()),media_residuo=float(r.mean()),
                mediana_residuo=float(np.median(r)),P25=float(np.quantile(r,.25)),
                P75=float(np.quantile(r,.75)),RMSE=float(np.sqrt(np.mean(r*r))),unidad=unit)
            np.testing.assert_allclose(row["media_observada"]-row["media_WRF"],row["media_residuo"],atol=1e-12,rtol=0)
            result.append(row)
    return pd.DataFrame(result)


def main():
    if OUT.exists():
        if {p.name for p in OUT.iterdir()} != {"Plan.json"}:
            raise FileExistsError("Diagnóstico existente; no sobrescribir")
        # Primer intento se detuvo al leer: el CSV conserva 744 posiciones,
        # no sólo las737 ternas. Preservar ese plan antes de corregir el lector.
        (OUT/"Plan_lectura_previa.json").write_bytes((OUT/"Plan.json").read_bytes())
    receipt=json.loads((FIT/"Recepcion_independiente.json").read_text(encoding="utf-8"))
    target=next(r for r in receipt["archivos"] if Path(r["path"]).name=="Residuos_ajuste.csv")
    assert sha256(target["path"])==target["sha256"]
    OUT.mkdir(exist_ok=True)
    # Reglas fijadas antes de calcular tablas. Descriptivo, sin selección de modelo.
    plan=dict(estado="DIAGNOSTICO_DESCRIPTIVO_SOLO_AJUSTE",inicio=str(START),fin_exclusivo=str(END),
        semanas="Bloques consecutivos de7 días desde21dic; último18–20ene parcial, informado aparte.",
        franjas="00–05,06–11,12–17,18–23 de hora local original, sin mover :49.",
        estado_WRF="Cuadrante hacia el que apunta (u,v) WRF: signos de componentes; no dirección de procedencia.",
        limites="Sin prueba formal de estacionariedad, p-valores ni bandas probabilísticas; horas correlacionadas.",
        modelo="No se ajusta ni selecciona un nuevo generador; el 1.0 y su evaluación permanecen congelados.",
        evaluacion="No se leen filas24–30ene. Ya fue abierta anteriormente; no es reserva de una versión nueva.",
        fuente=target,codigo_sha256=sha256(__file__))
    guardar_json(OUT/"Plan.json",plan)
    source=pd.read_csv(target["path"],parse_dates=["fecha_local"])
    assert len(source)==744 and source.fecha_local.is_unique
    fields=[c for obs,base,resid,_ in FIELDS.values() for c in (obs,base,resid)]
    valid=np.isfinite(source[fields].to_numpy(float)).all(axis=1)
    assert valid.sum()==737 and np.array_equal(valid,source.valido_conjunto.to_numpy(bool))
    data=source.loc[valid].copy()
    assert data.fecha_local.ge(START).all() and data.fecha_local.lt(END).all()
    assert data.hipotesis.eq("civil_santiago").all() and data.operador.eq("interpolacion_instantanea").all()
    for obs,base,resid,_ in FIELDS.values():
        np.testing.assert_allclose(data[obs]-data[base],data[resid],atol=1e-10,rtol=0)
    # Retener las siete posiciones ausentes; no unir extremos ni rellenar.
    expected=pd.date_range(START+pd.Timedelta(minutes=49),END,inclusive="left",freq="h")
    assert len(expected)==744 and data.fecha_local.isin(expected).all()
    d=data.set_index("fecha_local").reindex(expected).rename_axis("fecha_local").reset_index()
    d["dia"]=d.fecha_local.dt.strftime("%Y-%m-%d")
    d["semana"]=((d.fecha_local.dt.normalize()-START).dt.days//7+1).astype(int)
    d["franja"]=(d.fecha_local.dt.hour//6).map({0:"00–05",1:"06–11",2:"12–17",3:"18–23"})
    ok=d["residuo_v_m_s"].notna()
    d["estado_WRF"]="sin_par"
    d.loc[ok,"estado_WRF"]=np.char.add(
        np.where(d.loc[ok,"v_earth_m_s"]>=0,"N","S"),
        np.where(d.loc[ok,"u_earth_m_s"]>=0,"E","W"))
    d.loc[ok & d.u_earth_m_s.eq(0)&d.v_earth_m_s.eq(0),"estado_WRF"]="calma_exacta"
    tables={"Diario":summarize(d,["dia"]),"Semanal":summarize(d,["semana"]),
            "Semanal_por_franja":summarize(d,["semana","franja"]),
            "Estado_WRF":summarize(d[ok],["estado_WRF"]),
            "Semanal_por_estado_WRF":summarize(d[ok],["semana","estado_WRF"])}
    coverage=d.groupby("semana").agg(inicio=("fecha_local","min"),fin=("fecha_local","max"),
        esperadas=("fecha_local","size"),validas=("residuo_v_m_s","count")).reset_index()
    coverage["ausentes"]=coverage.esperadas-coverage.validas
    coverage["semana_completa"]=coverage.esperadas.eq(168)
    assert coverage.validas.sum()==737 and coverage.ausentes.sum()==7
    coverage.to_csv(OUT/"Cobertura.csv",index=False,encoding="utf-8-sig")
    d.loc[~ok,["fecha_local","semana","franja"]].to_csv(OUT/"Horas_ausentes.csv",index=False,encoding="utf-8-sig")
    for label,table in tables.items():
        table.to_csv(OUT/(label+".csv"),index=False,encoding="utf-8-sig")
        # Reconciliación: todas las particiones reconstruyen el mismo promedio.
        for variable,part in table.groupby("variable"):
            assert part.n.sum()==737
            mean=np.average(part.media_residuo,weights=part.n)
            np.testing.assert_allclose(mean,data[FIELDS[variable][2]].mean(),rtol=0,atol=1e-12)
    fig,axes=plt.subplots(3,1,figsize=(11,8),layout="constrained",sharex=True)
    for ax,(variable,(_,_,resid,unit)) in zip(axes,FIELDS.items()):
        sub=tables["Diario"][tables["Diario"].variable==variable]
        dates=pd.to_datetime(sub.dia)
        ax.fill_between(dates,sub.P25,sub.P75,alpha=.18,color="#197e8e",label="P25–P75 intradía")
        ax.plot(dates,sub.media_residuo,"o-",ms=3,color="#197e8e",label="Media diaria")
        ax.axhline(data[resid].mean(),color="#b9762c",ls="--",label="Media del ajuste")
        ax.axhline(0,color="#555555",lw=.7)
        ax.set_ylabel(f"r{variable} ({unit})")
        ax.grid(alpha=.18)
        ax.spines[["top","right"]].set_visible(False)
    axes[0].legend(ncol=3,fontsize=9)
    axes[-1].xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.WE,interval=1))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d-%m"))
    axes[-1].set_xlabel("Fecha local · discrepancia r = observado − WRF")
    fig.suptitle("Variabilidad dentro del conjunto de ajuste\n21 dic 2016–20 ene 2017 · sombreado descriptivo, no intervalo de confianza",fontsize=13)
    fig.savefig(OUT/"Discrepancias_diarias.png",dpi=170)
    fig.savefig(OUT/"Discrepancias_diarias.pdf")
    plt.close(fig)
    weekly=tables["Semanal"].pivot(index="semana",columns="variable",values="media_residuo")
    text=["# Estabilidad de las discrepancias dentro del ajuste","",
        "Diagnóstico descriptivo de las 737 ternas válidas del21dic2016–20ene2017, "
        "sobre744 posiciones previstas. Siete huecos se conservan. Se mantuvo la hipótesis H-CIVIL "
        "y la interpolación al instante :49. No se ajustó un generador nuevo ni se leyeron filas "
        "de separación/evaluación. La evaluación de24–30ene ya estaba abierta previamente; "
        "este diagnóstico no restaura una reserva independiente.","",
        "| Tramo | Válidas/esperadas | Media rT (°C) | Media ru (m/s) | Media rv (m/s) |",
        "|---|---:|---:|---:|---:|"]
    for c in coverage.itertuples():
        r=weekly.loc[c.semana]
        label=c.inicio.strftime("%d-%m")+" a "+c.fin.strftime("%d-%m")
        if not c.semana_completa: label+=" (3 días)"
        text.append(f"| {label} | {c.validas}/{c.esperadas} | {r['T']:+.3f} | {r['u']:+.3f} | {r['v']:+.3f} |")
    text += ["","Los cuatro primeros tramos contienen siete días; el último contiene sólo tres y "
        "no se equipara a una semana completa. Cobertura.csv y Horas_ausentes.csv conservan los denominadores.",
        "","Semanal_por_franja.csv permite revisar si las diferencias entre tramos persisten al comparar "
        "las mismas seis horas del día. Estado_WRF.csv y Semanal_por_estado_WRF.csv describen los signos "
        "del viento simulado (hacia NE/NW/SE/SW), con el número de pares de cada celda. "
        "No son regímenes físicos validados ni una dirección meteorológica de procedencia.",
        "","No se atribuye causalmente la discrepancia al estado WRF: el residuo contiene −WRF por definición "
        "y puede mostrar asociación matemática con el predictor. La cobertura desigual de estados y la "
        "dependencia temporal impiden interpretar los conteos horarios como réplicas independientes. "
        "Las distribuciones diarias y entre tramos son descriptivas; no se realizó una prueba formal de estacionariedad.",
        "","El siguiente paso es diseñar y congelar una comparación interna con bloques temporales "
        "dentro del ajuste, frente a BASE y al generador1.0, antes de modificar el modelo de discrepancias. "
        "Debe conservar dependencia conjunta T/u/v, separar sesgo y variación sin contarlos dos veces, "
        "y comprobar soporte de las condiciones meteorológicas. Una mejora interna no validaría "
        "automáticamente la transferencia espacial/vertical ni la incertidumbre de concentración. "
        "No se propagaron todavía las realizaciones fallidas como si fueran calibradas.",
        "","Este producto no necesita nuevas simulaciones ni datos del usuario. "
        "Las tablas reconcilian por ponderación el promedio global de ajuste; el código conserva "
        "separadamente observación, WRF y discrepancia, verificando observado−WRF registro por registro."]
    (OUT/"Resultados.md").write_text("\n".join(text)+"\n",encoding="utf-8")
    result=dict(estado="DIAGNOSTICO_AJUSTE_COMPLETO",ternas=737,posiciones=744,ausentes=7,
        modelo_modificado=False,evaluacion_reabierta=False,
        medias_semanales={str(i):{k:float(v) for k,v in row.items()} for i,row in weekly.to_dict("index").items()},
        conciliacion_medias=True,archivos=[dict(path=str(p),sha256=sha256(p)) for p in [
            Path(__file__),*sorted(OUT.iterdir())] if p.is_file()])
    guardar_json(OUT/"Verificacion.json",result)
    print(coverage.to_string(index=False))
    print(weekly.to_string())


if __name__=="__main__":
    main()
