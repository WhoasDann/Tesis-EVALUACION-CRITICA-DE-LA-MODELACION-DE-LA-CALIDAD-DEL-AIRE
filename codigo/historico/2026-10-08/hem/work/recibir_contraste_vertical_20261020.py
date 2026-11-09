"""Recibe salidas nativas del contraste vertical; no repite simulaciones."""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"outputs/Contraste_vertical_2026-10-20"
OLD = ROOT/"outputs/Sensibilidad_meteorologica_puntos_2026-10-19"
WIND = ROOT/"outputs/Prueba_viento_NetCDF_2026-10-15"
DEST = OUT/"Recepcion"
sys.path.insert(0,str(ROOT/"outputs/Biblioteca_Tesis"))
from tesis.comun import sha256, guardar_json
from tesis.multidia import revisar_log_mmif, revisar_met
from tesis.validacion_dispersion import verificar_dispersion

LABELS = {"PCAR":"Piedra Carvajal","LBCEN":"Los Bronces, estación",
          "SULF":"Sulfatos","PALP":"La Paloma, punto"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify(entries):
    for entry in entries:
        assert sha256(entry["path"]) == entry["sha256"], entry["path"]


def main():
    assert not DEST.exists(), "Recepción existente; no sobrescribir"
    assert read(OUT/"Estado.json")["estado"] == "CONTRASTE_VERTICAL_COMPLETO"
    for manifest in ("Entrega.json","Estado.json","Preprocesamiento.json"):
        verify(read(OUT/manifest)["archivos"])
    oldmet = read(WIND/"Ejecuciones.json")
    for item in oldmet.values():
        verify(item["archivos"])
    met = OUT/"Meteorologia/PBL"
    vec = Path(oldmet["VEC"]["carpeta"])
    base = Path(oldmet["BASE"]["carpeta"])
    revisar_log_mmif((met/"mmif_4.1.1.exe.consola.log").read_text(errors="replace"),
                     "2016-12-21","2016-12-23")
    revisar_met(met/"met.SFC",met/"met.PFL","2016-12-21","2016-12-23")
    assert (vec/"met.SFC").read_bytes() == (met/"met.SFC").read_bytes()
    assert (base/"SURFACE.DAT").read_bytes() == (vec/"SURFACE.DAT").read_bytes() == (met/"SURFACE.DAT").read_bytes()
    p, v = np.loadtxt(met/"met.PFL"), np.loadtxt(vec/"met.PFL")
    assert p.shape == v.shape == (96*29,11)
    assert list(np.flatnonzero(np.any(p!=v,axis=0))) == [6,7]
    assert np.array_equal(p[:,6]==999,v[:,6]==999)
    assert np.array_equal(p[:,7]==99,v[:,7]==99)
    wind_valid = (p[:,6]!=999)&(p[:,7]!=99)
    profile = pd.DataFrame({
        "dia":p[wind_valid,2].astype(int),"hora":p[wind_valid,3].astype(int),
        "altura_m":p[wind_valid,4],
        "delta_rapidez_ms":p[wind_valid,7]-v[wind_valid,7],
        "delta_direccion_circular_grados":(p[wind_valid,6]-v[wind_valid,6]+180)%360-180})
    # Lee ONSITE por posiciones fijas y reconstruye componentes por trigonometría.
    expected = pd.read_csv(OUT/"Perfiles_esperados_MMIF.csv",dtype={"hora":str})
    lines = (met/"ONSITE.DAT").read_text(encoding="ascii").splitlines()
    reconstructed = []
    assert len(lines)==96*30
    for off in range(0,len(lines),30):
        for line in lines[off+2:off+30]:
            h, speed, direction = map(float,line.split()[:3])
            reconstructed.append(dict(hora=lines[off][:10],z_m=h,
                u=-speed*np.sin(np.deg2rad(direction)),v=-speed*np.cos(np.deg2rad(direction))))
    joined = expected.merge(pd.DataFrame(reconstructed),on=["hora","z_m"],validate="one_to_one")
    assert len(joined)==96*28
    error = max(float(abs(joined.u-joined.u_PBL).max()),float(abs(joined.v-joined.v_PBL).max()))
    assert error<.002
    new, old = read(OUT/"Corridas.json"), read(OLD/"Corridas.json")
    for item in list(new.values())+list(old.values()):
        verify(item["archivos"])
    jobs = {("PBL",pol):Path(info["carpeta"]) for pol,info in new.items()}
    jobs.update({(info["escenario"],info["contaminante"]):Path(info["carpeta"]) for info in old.values()})
    members = pd.read_csv(OLD/"Comunes/membresia.csv")
    raw_all, daily, checks = [], [], {}
    cols = ["x_m","y_m","C","elev","hill","flag","avg","group","date"]
    for (scenario,pol),folder in jobs.items():
        for name in ("fuentes_aermod.inc","receptores.inc",pol+".emi"):
            assert sha256(folder/name)==sha256(OLD/"Casos"/("BASE_"+pol)/name)
        qa,_,_ = verificar_dispersion(folder,12263,4,members,"2016-12-21","2016-12-23")
        checks[scenario+"_"+pol] = qa
        raw = pd.read_csv(folder/"receptor_horas.out",sep=r"\s+",comment="*",header=None,
                          names=cols,usecols=range(9),dtype={"date":str})
        raw = raw.merge(members[["x_m","y_m","grupo"]],on=["x_m","y_m"],validate="many_to_one")
        raw["dia"] = pd.to_datetime(raw.date.str[:6],format="%y%m%d").dt.strftime("%Y-%m-%d")
        raw["escenario"], raw["contaminante"] = scenario,pol
        raw_all.append(raw)
        agg = raw.groupby(["grupo","dia"]).C.agg(["count","mean"]).reset_index()
        assert len(agg)==8 and agg["count"].eq(24).all()
        agg["escenario"], agg["contaminante"] = scenario,pol
        daily.append(agg)
    for pol in ("MP10","MP25"):
        assert checks["PBL_"+pol]["advertencias"]==checks["BASE_"+pol]["advertencias"]
    raw = pd.concat(raw_all,ignore_index=True)
    assert len(raw)==1152
    d = pd.concat(daily,ignore_index=True)
    lookup = d.set_index(["escenario","contaminante","grupo","dia"])["mean"]
    comp = pd.read_csv(OUT/"Contrastes.csv")
    assert len(comp)==48 and not comp.duplicated(["contraste","contaminante","grupo","dia"]).any()
    for row in comp.itertuples():
        target, ref = row.contraste.split("-")
        a = lookup[(target,row.contaminante,row.grupo,row.dia)]
        b = lookup[(ref,row.contaminante,row.grupo,row.dia)]
        np.testing.assert_allclose([row.concentracion,row.referencia,row.delta],[a,b,a-b],atol=1e-12,rtol=0)
        if b>.0004:
            np.testing.assert_allclose(row.porcentaje,100*(a-b)/b,atol=1e-10,rtol=0)
        else:
            assert np.isnan(row.porcentaje)
    wide = raw.pivot(index=["contaminante","grupo","date","dia"],columns="escenario",values="C").reset_index()
    wide["PBL_menos_VEC"] = wide.PBL-wide.VEC
    hourly = []
    for (pol,group),sub in wide.groupby(["contaminante","grupo"]):
        largest = sub.loc[sub.PBL_menos_VEC.abs().idxmax()]
        hourly.append(dict(contaminante=pol,grupo=group,
            max_delta_absoluto_horario_ug_m3=float(abs(largest.PBL_menos_VEC)),
            hora_max_delta=str(largest.date),media_delta_absoluto_horario_ug_m3=float(sub.PBL_menos_VEC.abs().mean()),
            horas_con_delta_positivo=int((sub.PBL_menos_VEC>0).sum()),
            horas_con_delta_negativo=int((sub.PBL_menos_VEC<0).sum())))
    DEST.mkdir()
    d.to_csv(DEST/"Medias_reconstruidas.csv",index=False,encoding="utf-8-sig")
    wide.to_csv(DEST/"Contrastes_horarios.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(hourly).to_csv(DEST/"Resumen_diferencias_horarias.csv",index=False,encoding="utf-8-sig")
    profile.to_csv(DEST/"Cambios_perfil_PFL.csv",index=False,encoding="utf-8-sig")
    # Figura científica estática con diferencias relativas y absolutas por receptor.
    fig,axes=plt.subplots(2,1,figsize=(10,7),layout="constrained",sharex=True)
    x=np.arange(4); width=.35
    sub=comp[(comp.contaminante=="MP10")&(comp.contraste=="PBL-VEC")]
    for k,(day,color) in enumerate([("2016-12-21","#187f8d"),("2016-12-22","#b86c2e")]):
        values=sub[sub.dia==day].set_index("grupo").loc[list(LABELS)]
        for ax,col in zip(axes,["porcentaje","delta"]):
            bars=ax.bar(x+(k-.5)*width,values[col],width=width,color=color,label=day[8:10]+" dic")
            ax.bar_label(bars,labels=[f"{n:+.2f}" if col=="porcentaje" else f"{n:+.5f}" for n in values[col]],
                         padding=3,fontsize=8)
    axes[0].set(ylabel="Cambio respecto a VEC (%)",ylim=(-.65,6.2))
    axes[1].set(ylabel="Cambio de MP10 (µg/m³)",ylim=(-.123,.026))
    axes[1].set_xticks(x,["Piedra\nCarvajal","Los Bronces\nestación","Sulfatos","La Paloma\npunto"])
    for ax in axes:
        ax.axhline(0,color="#47535c",lw=.7)
        ax.grid(axis="y",alpha=.2); ax.set_axisbelow(True)
        ax.spines[["top","right"]].set_visible(False)
    axes[0].legend(ncol=2)
    fig.suptitle("Efecto de limitar en altura la perturbación del viento\nPBL menos uniforme (VEC) · medias diarias de MP10",fontsize=14)
    fig.savefig(DEST/"Efecto_vertical_por_receptor.png",dpi=180)
    fig.savefig(DEST/"Efecto_vertical_por_receptor.pdf")
    plt.close(fig)
    lines=[
        "# Recepción e interpretación del contraste vertical","",
        "Se verificaron seis corridas desde sus archivos nativos: 1152 concentraciones horarias, "
        "384 nuevas; 48 horas, cuatro receptores exactos y dos contaminantes. Se reconstruyeron "
        "48 medias diarias y 48 contrastes. Cero errores fatales, calmas o horas faltantes; "
        "las advertencias coinciden con BASE. Fuentes, masa horaria, terreno y receptores coinciden por hash.",
        "",
        "**Resultado que aísla el contraste:** SFC de PBL es idéntico byte por byte al de VEC en "
        "las 96 horas auxiliares. En PFL cambian únicamente dirección y rapidez del viento; "
        "calendario, niveles, temperaturas y restantes campos se mantienen iguales. Los perfiles "
        f"ONSITE reproducen la predicción previa con error máximo {error:.7f} m/s. "
        "No se perdió la perturbación ni se mezclaron características superficiales distintas.",
        "",
        "| Receptor | PBL−VEC, 21 dic (µg/m³) | Cambio (%) | PBL−VEC, 22 dic (µg/m³) | Cambio (%) |",
        "|---|---:|---:|---:|---:|"]
    for group,label in LABELS.items():
        a,b = [sub[(sub.grupo==group)&(sub.dia==day)].iloc[0] for day in ("2016-12-21","2016-12-22")]
        lines.append(f"| {label} | {a.delta:+.6f} | {a.porcentaje:+.3f} | {b.delta:+.6f} | {b.porcentaje:+.3f} |")
    lines += [
        "",
        "En Los Bronces, PBL conserva aumentos frente a BASE de 17,763 % y 10,462 %, próximos "
        "a los 17,872 % y 10,500 % del perfil uniforme. La diferencia entre transferencias es pequeña "
        "para ese receptor y estos dos días. No es igualmente pequeña en términos relativos en todos "
        "los puntos: Sulfatos alcanza 5,108 %, equivalente a 0,002040 µg/m³; La Paloma alcanza 1,309 %. "
        "Los resultados de MP2,5 están íntegros en Contrastes.csv; no se interpretan como evidencia independiente.",
        "",
        "Las medias diarias no sustituyen las respuestas horarias: la mayor diferencia absoluta "
        "horaria MP10 entre PBL y VEC es 0,369760 µg/m³ en Los Bronces. El detalle por punto, hora "
        "y contaminante queda en Contrastes_horarios.csv y Resumen_diferencias_horarias.csv.",
        "",
        "El ensayo demuestra que, para esta configuración, las dos hipótesis verticales producen "
        "respuestas próximas en Los Bronces y diferencias identificables en otros puntos. No valida "
        "la transferencia real del error observado, no establece un peor caso universal y no permite "
        "extrapolar al verano completo. No se selecciona PBL o VEC por producir mayor concentración. "
        "PBL sigue siendo una hipótesis de transferencia explícita y uniforme sigue siendo su contraste estructural.",
        "",
        "La altura de corte proviene de PBLH BASE en WRF; la altura de mezcla procesada por AERMET "
        "es otra variable y no debe confundirse con ese corte. La conservación de SFC PBL/VEC no "
        "significa que SFC sea igual a BASE: el cambio de viento superficial sí modifica diagnósticos "
        "entre BASE y ambos casos perturbados. La temperatura, los flujos y otros campos WRF se "
        "mantuvieron por diseño, sin reintegración dinámica.",
        "",
        "Texto utilizable en la tesis:",
        "",
        "«Para evaluar la dependencia de la respuesta respecto de la transferencia vertical, se "
        "comparó una perturbación vectorial uniforme de (+1; −0,5) m/s con otra de igual amplitud "
        "a 10 m, reducida mediante una función cúbica hasta cero en PBLH del WRF original. Se mantuvieron "
        "fijos emisiones, fuentes, receptores y procesamiento. En el receptor de la estación Los Bronces, "
        "las medias diarias de MP10 del 21 y 22 de diciembre de 2016 disminuyeron 0,092 % y 0,034 % "
        "respecto del caso uniforme; en Sulfatos, la diferencia alcanzó +5,108 % (+0,002040 µg/m³). "
        "El archivo superficial SFC fue idéntico entre ambas perturbaciones y sólo cambió el viento "
        "del perfil PFL. Estas diferencias cuantifican sensibilidad al supuesto vertical en el ensayo, "
        "sin constituir una validación de la transferencia ni intervalos probabilísticos de concentración.»",
        "",
        "La etapa queda cerrada, sin nuevas ejecuciones requeridas al usuario. El siguiente trabajo "
        "es revisar estabilidad temporal y por estado meteorológico de las discrepancias observadas "
        "en el conjunto de ajuste. Se conserva la evaluación fallida del generador 1.0; no se reutiliza "
        "como reserva para una versión modificada. No se abren refinamientos de fuentes ni se simulan "
        "los 1024 miembros como si fueran incertidumbre calibrada."]
    (DEST/"Lectura_resultados.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    receipt=dict(estado="CONTRASTE_VERTICAL_RECIBIDO",valores_recibidos=1152,valores_nuevos=384,
        casos=6,horas_por_caso=48,receptores=4,fuentes=12263,contrastes_verificados=48,
        SFC_PBL_VEC_identico_literal=True,PFL_solo_cambian_viento=True,
        error_ONSITE_max_ms=error,fuentes_emisiones_receptores_iguales=True,
        advertencias_nuevas=False,nativos=checks,
        archivos=[dict(path=str(p),sha256=sha256(p)) for p in [
            Path(__file__),OUT/"Entrega.json",OUT/"Estado.json",OUT/"Preprocesamiento.json",
            OUT/"Corridas.json",*sorted(DEST.iterdir())] if p.is_file()])
    guardar_json(DEST/"Verificacion_recepcion.json",receipt)
    print(json.dumps({k:receipt[k] for k in (
        "estado","valores_recibidos","valores_nuevos","contrastes_verificados",
        "SFC_PBL_VEC_identico_literal","PFL_solo_cambian_viento","error_ONSITE_max_ms")}))


if __name__=="__main__":
    main()
