"""Reconciliación separada de semanas, cobertura y estados del ajuste."""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/Estabilidad_ajuste_2026-10-20"
sys.path.insert(0,str(ROOT/"outputs/Biblioteca_Tesis"))
from tesis.comun import sha256,guardar_json

if (OUT/"Recepcion.json").exists():
    raise FileExistsError("Recepción existente")
q=json.loads((OUT/"Verificacion.json").read_text(encoding="utf-8"))
for item in q["archivos"]:
    assert sha256(item["path"])==item["sha256"]
plan=json.loads((OUT/"Plan.json").read_text(encoding="utf-8"))
assert sha256(plan["fuente"]["path"])==plan["fuente"]["sha256"]
raw=pd.read_csv(plan["fuente"]["path"],parse_dates=["fecha_local"])
weekly=pd.read_csv(OUT/"Semanal.csv")
coverage=pd.read_csv(OUT/"Cobertura.csv")
assert len(raw)==744 and raw.valido_conjunto.sum()==737
for row in coverage.itertuples():
    start=pd.Timestamp("2016-12-21")+pd.Timedelta(days=7*(row.semana-1))
    end=min(start+pd.Timedelta(days=7),pd.Timestamp("2017-01-21"))
    part=raw[raw.fecha_local.ge(start)&raw.fecha_local.lt(end)]
    assert len(part)==row.esperadas and part.valido_conjunto.sum()==row.validas
    for variable,col in [("T","residuo_T_C"),("u","residuo_u_m_s"),("v","residuo_v_m_s")]:
        actual=part[col].dropna().to_numpy()
        record=weekly[(weekly.semana==row.semana)&(weekly.variable==variable)].iloc[0]
        np.testing.assert_allclose([record.media_residuo,record.mediana_residuo,record.P25,record.P75],
            [sum(actual)/len(actual),np.median(actual),np.percentile(actual,25),np.percentile(actual,75)],
            atol=1e-12,rtol=0)
conditions=pd.read_csv(OUT/"Semanal_por_estado_WRF.csv")
for row in conditions[conditions.variable=="v"].itertuples():
    start=pd.Timestamp("2016-12-21")+pd.Timedelta(days=7*(row.semana-1))
    end=min(start+pd.Timedelta(days=7),pd.Timestamp("2017-01-21"))
    part=raw[raw.fecha_local.ge(start)&raw.fecha_local.lt(end)&raw.valido_conjunto].copy()
    part=part[part.v_earth_m_s.ge(0) if row.estado_WRF[0]=="N" else part.v_earth_m_s.lt(0)]
    part=part[part.u_earth_m_s.ge(0) if row.estado_WRF[1]=="E" else part.u_earth_m_s.lt(0)]
    assert len(part)==row.n
    np.testing.assert_allclose((part.v_obs_m_s-part.v_earth_m_s).mean(),row.media_residuo,atol=1e-12,rtol=0)
guardar_json(OUT/"Recepcion.json",dict(estado="ESTABILIDAD_AJUSTE_RECIBIDA",semanas_completas=4,
    tramo_final_dias=3,pares_validos=737,huecos=7,modelo_modificado=False,
    tablas_semanales_y_condicionales_reconstruidas=True,
    archivos=[dict(path=str(p),sha256=sha256(p)) for p in [
        Path(__file__),OUT/"Verificacion.json",OUT/"Lectura_estabilidad.md"]]))
print("Recibidos cuatro tramos de7 días y un tramo de3 días; 737 ternas, siete huecos.")
