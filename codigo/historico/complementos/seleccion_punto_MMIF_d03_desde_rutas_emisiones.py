# -*- coding: utf-8 -*-
"""
seleccion_punto_MMIF_d03_desde_rutas_emisiones.py
=================================================

Selecciona celdas candidatas de WRF d03 para POINT de MMIF usando la misma
geometría de caminos y la misma fórmula de emisiones del generador AERMOD.

Criterio principal:
    minimizar la distancia media desde el centro de una celda WRF a la
    distribución espacial de las fuentes LINE, ponderada por la masa total
    de MP10 emitida durante el período elegido.

La elevación se reporta como diagnóstico independiente y NO se mezcla en el
score para evitar una ponderación topográfica arbitraria.

Requiere:
    pip install netCDF4 numpy openpyxl shapely pyproj
"""
from __future__ import annotations

import csv
import math
import re
import shutil
import sys
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path

import numpy as np
import openpyxl
from netCDF4 import Dataset
from shapely.geometry import LineString, Polygon
from shapely.ops import transform as shapely_transform
from pyproj import Transformer


# =============================================================================
# 1. CONFIGURACIÓN
# =============================================================================

RUTA_EXCEL_ORIGEN = Path(
    r"/archivo/usuario\Codigos_VSC\Codigos_oficiales"
    r"\Transporte_cb_2017_MINA_MAS_400_CERCANOS_emisiones.xlsx"
)
RUTA_KMZ_ORIGEN = Path(
    r"/archivo/usuario\Codigos_VSC\Codigos_oficiales"
    r"\Transporte_cb_2017_MINA_MAS_400_CERCANOS.kmz"
)
RUTA_WRFOUT_D03 = Path(
    r"D:\Tesis_Dan\wrfoutERA5\wrfout_d03_2017-01-01_00_00_00"
)
CARPETA_SALIDA = Path(
    r"/archivo/usuario\Codigos_VSC\Codigos_oficiales"
    r"\SELECCION_PUNTO_MMIF_D03"
)

EPSG_ORIGEN = "EPSG:4326"
EPSG_UTM = "EPSG:32719"

HOJA_RUTAS = "Rutas_Seleccionadas"
HOJA_FLUJO = "Flujo_Diario"
HOJA_FE_MP10 = "FE_MP10"

# Igual que en tu generador AERMOD.
FACTOR_RESULTADO_A_GRAMOS = 1.0
LINESTRING_COMO_RECTA_UNICA = True

# Conviene usar todo 2017 aunque la primera prueba MMIF sea solo enero,
# para que el POINT no dependa del subconjunto temporal de prueba.
RANGO_PONDERACION = ("2017-01-01", "2017-12-31")

# Solo controla la resolución numérica con que se representa cada LINE.
# La masa total de cada ruta se conserva exactamente.
ESPACIADO_MUESTREO_M = 100.0

TOP_N_CANDIDATOS = 20
BLOQUE_CELDAS = 128
RADIO_VECINDAD_HGT = 1
GUARDAR_PUNTOS_MUESTREO = False


# =============================================================================
# 2. ESTRUCTURAS
# =============================================================================

@dataclass(frozen=True)
class FuenteLine:
    numero_ruta: int
    nombre_kmz: str
    linea_utm: LineString
    largo_m: float


@dataclass(frozen=True)
class PuntoEmision:
    numero_ruta: int
    x: float
    y: float
    peso_g: float


# =============================================================================
# 3. UTILIDADES
# =============================================================================

def mostrar(texto: str) -> None:
    print(texto, flush=True)


def extraer_numero_id(valor) -> int | None:
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        if math.isnan(valor):
            return None
        if valor.is_integer():
            return int(valor)
    m = re.search(r"(\d+)\s*$", str(valor).strip().upper())
    return int(m.group(1)) if m else None


def convertir_numero(valor) -> float | None:
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        if isinstance(valor, float) and math.isnan(valor):
            return None
        return float(valor)
    try:
        return float(str(valor).strip().replace(",", "."))
    except (ValueError, TypeError):
        return None


def numero_o_cero(valor) -> float:
    x = convertir_numero(valor)
    return 0.0 if x is None else x


def normalizar_fecha(valor) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
                "%d-%m-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            pass
    return None


def leer_coordenadas_kml(texto: str | None) -> list[tuple[float, float]]:
    out = []
    if not texto:
        return out
    for token in texto.strip().split():
        p = token.split(",")
        if len(p) >= 2:
            try:
                out.append((float(p[0]), float(p[1])))
            except ValueError:
                pass
    return out


# =============================================================================
# 4. KMZ: MISMA LÓGICA GEOMÉTRICA DEL GENERADOR AERMOD
# =============================================================================

def geometria_desde_placemark(placemark, ns):
    geometrias = []

    for pol in placemark.findall(".//kml:Polygon", ns):
        nodo = pol.find(
            ".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", ns
        )
        if nodo is None or not nodo.text:
            continue
        puntos = leer_coordenadas_kml(nodo.text)
        if len(puntos) < 3:
            continue
        try:
            g = Polygon(puntos)
            if not g.is_valid:
                g = g.buffer(0)
            if not g.is_empty:
                geometrias.append(g)
        except Exception:
            pass

    for lin in placemark.findall(".//kml:LineString", ns):
        nodo = lin.find("kml:coordinates", ns)
        if nodo is None or not nodo.text:
            continue
        puntos = leer_coordenadas_kml(nodo.text)
        if len(puntos) < 2:
            continue
        try:
            g = LineString(puntos)
            if not g.is_empty:
                geometrias.append(g)
        except Exception:
            pass

    return max(geometrias, key=lambda g: g.length) if geometrias else None


def obtener_poligono_principal(geom):
    if geom.geom_type == "Polygon":
        return geom
    if geom.geom_type == "MultiPolygon":
        return max(geom.geoms, key=lambda p: p.area)
    return None


def obtener_lineas_aermod_desde_geometria(geom_utm) -> list[LineString]:
    if geom_utm.geom_type == "LineString":
        coords = list(geom_utm.coords)
        if len(coords) < 2:
            return []
        if LINESTRING_COMO_RECTA_UNICA:
            linea = LineString([coords[0], coords[-1]])
            return [linea] if linea.length > 0 else []
        out = []
        for p1, p2 in zip(coords[:-1], coords[1:]):
            linea = LineString([p1, p2])
            if linea.length > 0:
                out.append(linea)
        return out

    pol = obtener_poligono_principal(geom_utm)
    if pol is None:
        return []

    try:
        rect = pol.minimum_rotated_rectangle
        coords = list(rect.exterior.coords)[:-1]
        if len(coords) != 4:
            return []
        medios = [
            ((coords[i][0] + coords[(i+1)%4][0]) / 2,
             (coords[i][1] + coords[(i+1)%4][1]) / 2)
            for i in range(4)
        ]
        if math.dist(medios[0], medios[2]) >= math.dist(medios[1], medios[3]):
            linea = LineString([medios[0], medios[2]])
        else:
            linea = LineString([medios[1], medios[3]])
        return [linea] if linea.length > 0 else []
    except Exception:
        return []


def cargar_geometrias_kmz(ruta_kmz: Path, ids_excel: set[int]):
    tmp = Path(tempfile.mkdtemp(prefix="mmif_kmz_"))
    incidencias = []
    try:
        with zipfile.ZipFile(ruta_kmz, "r") as zf:
            zf.extractall(tmp)
        kmls = list(tmp.rglob("*.kml"))
        if not kmls:
            raise FileNotFoundError("No se encontró .kml dentro del KMZ.")
        kml = next((p for p in kmls if p.name.lower() == "doc.kml"), kmls[0])

        root = ET.parse(kml).getroot()
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        tr = Transformer.from_crs(EPSG_ORIGEN, EPSG_UTM, always_xy=True)

        resultado: dict[int, list[LineString]] = {}
        for pm in root.findall(".//kml:Placemark", ns):
            nodo_nombre = pm.find("kml:name", ns)
            if nodo_nombre is None or not nodo_nombre.text:
                continue
            numero = extraer_numero_id(nodo_nombre.text.strip())
            if numero is None or numero not in ids_excel:
                continue

            geom_ll = geometria_desde_placemark(pm, ns)
            if geom_ll is None:
                incidencias.append(f"Ruta {numero}: geometría no válida.")
                continue
            try:
                geom_utm = shapely_transform(tr.transform, geom_ll)
            except Exception as exc:
                incidencias.append(f"Ruta {numero}: proyección falló ({exc}).")
                continue

            lineas = obtener_lineas_aermod_desde_geometria(geom_utm)
            if not lineas:
                incidencias.append(f"Ruta {numero}: no se obtuvo LINE válida.")
                continue
            resultado.setdefault(numero, []).extend(lineas)

        return resultado, incidencias, kml.name
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
# 5. EXCEL
# =============================================================================

def leer_hoja_rutas(ws) -> dict[int, dict]:
    filas = ws.iter_rows(values_only=True)
    encabezados = list(next(filas))
    indice = {
        str(n).strip(): i for i, n in enumerate(encabezados) if n is not None
    }

    def buscar(*nombres):
        for nombre in nombres:
            if nombre in indice:
                return indice[nombre]
        for titulo, pos in indice.items():
            for nombre in nombres:
                if nombre.lower() in titulo.lower():
                    return pos
        return None

    col_id = buscar("ID")
    col_nombre = buscar("Nombre KMZ")
    col_largo = buscar("LENGTH [unidad original]", "LENGTH [km]", "LENGTH")
    col_ab = buscar("Abatimiento [%]", "Abatimiento")
    if col_id is None or col_largo is None or col_ab is None:
        raise ValueError("No se identificaron ID, LENGTH y Abatimiento.")

    rutas = {}
    for fila in filas:
        if not fila:
            continue
        numero = extraer_numero_id(fila[col_id] if col_id < len(fila) else None)
        if numero is None:
            continue
        rutas[numero] = {
            "nombre_kmz": (
                fila[col_nombre] if col_nombre is not None and col_nombre < len(fila)
                else f"Ruta_{numero}"
            ),
            "largo_excel": convertir_numero(
                fila[col_largo] if col_largo < len(fila) else None
            ),
            "abatimiento_pct": convertir_numero(
                fila[col_ab] if col_ab < len(fila) else None
            ),
        }
    if not rutas:
        raise RuntimeError("No se encontraron rutas válidas.")
    return rutas


def leer_matriz_diaria(ws, ids_objetivo: set[int]):
    filas = ws.iter_rows(values_only=True)
    encabezados = list(next(filas))
    if len(encabezados) < 7:
        raise ValueError(f"{ws.title}: se esperaban fechas desde columna G.")

    fechas, posiciones = [], []
    for pos, valor in enumerate(encabezados[6:], start=6):
        f = normalizar_fecha(valor)
        if f is not None:
            fechas.append(f)
            posiciones.append(pos)

    datos = {}
    for fila in filas:
        if not fila:
            continue
        numero = extraer_numero_id(fila[0])
        if numero is None or numero not in ids_objetivo:
            continue
        datos[numero] = [
            convertir_numero(fila[p] if p < len(fila) else None) for p in posiciones
        ]
    return fechas, datos


def indices_periodo(fechas: list[date]) -> list[int]:
    ini = normalizar_fecha(RANGO_PONDERACION[0])
    fin = normalizar_fecha(RANGO_PONDERACION[1])
    if ini is None or fin is None or ini > fin:
        raise ValueError("RANGO_PONDERACION inválido.")
    idx = [i for i, f in enumerate(fechas) if ini <= f <= fin]
    if not idx:
        raise ValueError("RANGO_PONDERACION no intersecta el Excel.")
    return idx


def calcular_masa_total_por_ruta(rutas, flujo, fe, fechas) -> dict[int, float]:
    idx = indices_periodo(fechas)
    out = {}
    for numero, datos in rutas.items():
        q = flujo.get(numero)
        fef = fe.get(numero)
        if q is None or fef is None:
            continue
        if len(q) != len(fechas) or len(fef) != len(fechas):
            raise ValueError(f"Ruta {numero}: series de distinta longitud.")

        largo = numero_o_cero(datos["largo_excel"])
        abat = numero_o_cero(datos["abatimiento_pct"])
        residual = 1.0 - abat / 100.0

        masa = 0.0
        for i in idx:
            e = (
                numero_o_cero(q[i]) * numero_o_cero(fef[i]) * largo *
                residual * FACTOR_RESULTADO_A_GRAMOS
            )
            masa += max(0.0, e)
        out[numero] = masa
    return out


# =============================================================================
# 6. FUENTES LINE Y MUESTREO ESPACIAL DE LA MASA
# =============================================================================

def construir_fuentes_line(rutas, geometrias) -> list[FuenteLine]:
    out = []
    for numero in sorted(geometrias):
        if numero not in rutas:
            continue
        for linea in geometrias[numero]:
            if linea.length > 0:
                out.append(FuenteLine(
                    numero, str(rutas[numero]["nombre_kmz"]),
                    linea, float(linea.length)
                ))
    if not out:
        raise RuntimeError("No se generaron fuentes LINE.")
    return out


def muestrear_emision(fuentes, masa_ruta):
    por_ruta = {}
    for f in fuentes:
        por_ruta.setdefault(f.numero_ruta, []).append(f)

    puntos, diag = [], []
    for ruta, lineas in sorted(por_ruta.items()):
        masa = float(masa_ruta.get(ruta, 0.0))
        largo_total = sum(f.largo_m for f in lineas)
        if largo_total <= 0:
            continue

        masa_rec = 0.0
        n_total = 0
        for f in lineas:
            masa_linea = masa * f.largo_m / largo_total
            n = max(1, int(math.ceil(f.largo_m / ESPACIADO_MUESTREO_M)))
            peso = masa_linea / n

            for k in range(n):
                # Punto medio de cada subtramo.
                d = ((k + 0.5) / n) * f.largo_m
                p = f.linea_utm.interpolate(d)
                puntos.append(PuntoEmision(ruta, float(p.x), float(p.y), peso))
                masa_rec += peso
                n_total += 1

        diag.append({
            "id_ruta": ruta,
            "nombre_kmz": lineas[0].nombre_kmz,
            "masa_total_periodo_g": masa,
            "largo_LINE_total_m": largo_total,
            "n_puntos_muestreo": n_total,
            "masa_reconstruida_g": masa_rec,
        })

    peso_total = sum(p.peso_g for p in puntos)
    if peso_total <= 0:
        raise RuntimeError("La masa ponderadora total es cero.")
    return puntos, diag


def arrays_puntos(puntos):
    x = np.array([p.x for p in puntos], dtype=float)
    y = np.array([p.y for p in puntos], dtype=float)
    w = np.array([p.peso_g for p in puntos], dtype=float)
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(w) & (w > 0)
    x, y, w = x[mask], y[mask], w[mask]
    w /= w.sum()
    return x, y, w


# =============================================================================
# 7. MALLA WRF
# =============================================================================

def leer_malla_wrf(path: Path) -> dict:
    with Dataset(path, "r") as nc:
        for nombre in ("XLAT", "XLONG"):
            if nombre not in nc.variables:
                raise KeyError(f"Falta {nombre}.")

        def superficie(var):
            a = np.asarray(var[:], dtype=float)
            return a[0] if a.ndim == 3 else a

        lat = superficie(nc.variables["XLAT"])
        lon = superficie(nc.variables["XLONG"])

        if "HGT" in nc.variables:
            hgt = superficie(nc.variables["HGT"])
        elif "HGT_M" in nc.variables:
            hgt = superficie(nc.variables["HGT_M"])
        else:
            raise KeyError("Falta HGT/HGT_M.")

        if not (lat.shape == lon.shape == hgt.shape):
            raise ValueError("XLAT/XLONG/HGT tienen shapes incompatibles.")

        grid_id = getattr(nc, "GRID_ID", None)
        dx = getattr(nc, "DX", None)
        dy = getattr(nc, "DY", None)

    tr = Transformer.from_crs(EPSG_ORIGEN, EPSG_UTM, always_xy=True)
    x, y = tr.transform(lon, lat)

    return {
        "lat": lat, "lon": lon, "hgt": hgt,
        "x": np.asarray(x), "y": np.asarray(y),
        "grid_id": grid_id, "dx": dx, "dy": dy,
    }


# =============================================================================
# 8. SCORE DE REPRESENTATIVIDAD
# =============================================================================

def calcular_scores(malla, xs, ys, ws):
    xc = malla["x"].ravel()
    yc = malla["y"].ravel()
    mean = np.empty(xc.size)
    rms = np.empty(xc.size)

    for ini in range(0, xc.size, BLOQUE_CELDAS):
        fin = min(xc.size, ini + BLOQUE_CELDAS)
        dx = xc[ini:fin, None] - xs[None, :]
        dy = yc[ini:fin, None] - ys[None, :]
        d = np.sqrt(dx*dx + dy*dy)
        mean[ini:fin] = d @ ws
        rms[ini:fin] = np.sqrt((d*d) @ ws)

    return mean.reshape(malla["x"].shape), rms.reshape(malla["x"].shape)


def percentil_ponderado(v, w, q):
    idx = np.argsort(v)
    v = np.asarray(v)[idx]
    w = np.asarray(w)[idx]
    cw = np.cumsum(w)
    cw /= cw[-1]
    return float(np.interp(q, cw, v))


def diag_distancias(xc, yc, xs, ys, ws):
    d = np.sqrt((xs-xc)**2 + (ys-yc)**2)
    return {
        "dist_p50_pond_km": percentil_ponderado(d, ws, 0.50)/1000,
        "dist_p75_pond_km": percentil_ponderado(d, ws, 0.75)/1000,
        "dist_p90_pond_km": percentil_ponderado(d, ws, 0.90)/1000,
        "dist_p95_pond_km": percentil_ponderado(d, ws, 0.95)/1000,
        "dist_max_km": float(np.max(d))/1000,
    }


def diag_hgt(hgt, j, i):
    r = RADIO_VECINDAD_HGT
    j0, j1 = max(0, j-r), min(hgt.shape[0], j+r+1)
    i0, i1 = max(0, i-r), min(hgt.shape[1], i+r+1)
    z = hgt[j0:j1, i0:i1]
    return {
        "HGT_local_min_m": float(np.nanmin(z)),
        "HGT_local_max_m": float(np.nanmax(z)),
        "HGT_local_rango_m": float(np.nanmax(z)-np.nanmin(z)),
        "HGT_local_std_m": float(np.nanstd(z)),
    }


def construir_ranking(malla, mean, rms, xs, ys, ws):
    ny, nx = mean.shape
    orden = np.argsort(mean.ravel())[:TOP_N_CANDIDATOS]
    filas = []

    for rank, flat in enumerate(orden, 1):
        j, i = np.unravel_index(flat, mean.shape)
        fila = {
            "rank": rank,
            "j_south_north": int(j),
            "i_west_east": int(i),
            "lat_centro_celda": float(malla["lat"][j, i]),
            "lon_centro_celda": float(malla["lon"][j, i]),
            "x_utm19s_m": float(malla["x"][j, i]),
            "y_utm19s_m": float(malla["y"][j, i]),
            "HGT_celda_m": float(malla["hgt"][j, i]),
            "dist_media_ponderada_km": float(mean[j, i])/1000,
            "dist_rms_ponderada_km": float(rms[j, i])/1000,
            "distancia_borde_celdas": int(
                min(j, ny-1-j, i, nx-1-i)
            ),
        }
        fila.update(diag_distancias(
            malla["x"][j, i], malla["y"][j, i], xs, ys, ws
        ))
        fila.update(diag_hgt(malla["hgt"], j, i))
        filas.append(fila)
    return filas


def centroide_emision(malla, xs, ys, ws):
    x0 = float(np.sum(ws*xs))
    y0 = float(np.sum(ws*ys))
    d2 = (malla["x"]-x0)**2 + (malla["y"]-y0)**2
    j, i = np.unravel_index(np.argmin(d2), d2.shape)
    return {
        "x_centroide_utm_m": x0,
        "y_centroide_utm_m": y0,
        "j_celda_mas_cercana": int(j),
        "i_celda_mas_cercana": int(i),
        "lat_celda": float(malla["lat"][j, i]),
        "lon_celda": float(malla["lon"][j, i]),
        "HGT_celda_m": float(malla["hgt"][j, i]),
        "dist_centroide_celda_m": float(np.sqrt(d2[j, i])),
    }


# =============================================================================
# 9. SALIDAS
# =============================================================================

def escribir_csv(path: Path, filas: list[dict]):
    if not filas:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


def escribir_puntos(path, puntos, masa_total):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id_ruta", "x_utm19s_m", "y_utm19s_m",
                    "peso_g", "fraccion_emision_total"])
        for p in puntos:
            w.writerow([
                p.numero_ruta, f"{p.x:.3f}", f"{p.y:.3f}",
                f"{p.peso_g:.10E}", f"{p.peso_g/masa_total:.10E}",
            ])


def escribir_resumen(path, mejor, ranking, diag_rutas, incidencias,
                     centroide, malla, masa_total, n_puntos):
    top_rutas = sorted(
        diag_rutas, key=lambda x: x["masa_total_periodo_g"], reverse=True
    )

    with path.open("w", encoding="utf-8") as f:
        f.write("SELECCIÓN DE PUNTO MMIF - d03\n")
        f.write("="*78 + "\n\n")
        f.write("Criterio: distancia media a la distribución espacial de fuentes LINE,\n")
        f.write("ponderada por masa total de MP10 emitida.\n\n")

        f.write(f"Período de ponderación: {RANGO_PONDERACION[0]} a {RANGO_PONDERACION[1]}\n")
        f.write(f"GRID_ID: {malla['grid_id']}; DX={malla['dx']}; DY={malla['dy']}\n")
        f.write(f"Puntos de integración: {n_puntos:,}\n")
        f.write(f"Masa representada: {masa_total:.8E} g\n\n")

        f.write("CANDIDATO Nº1\n")
        f.write("-"*78 + "\n")
        for k, v in mejor.items():
            f.write(f"{k}: {v}\n")

        f.write("\nLÍNEA PARA MMIF\n")
        f.write("-"*78 + "\n")
        f.write(
            f"POINT LL {mejor['lat_centro_celda']:.8f} "
            f"{mejor['lon_centro_celda']:.8f}\n"
        )

        f.write("\nCENTROIDE DE EMISIÓN (solo diagnóstico)\n")
        f.write("-"*78 + "\n")
        for k, v in centroide.items():
            f.write(f"{k}: {v}\n")

        f.write("\n20 RUTAS DE MAYOR PESO\n")
        f.write("-"*78 + "\n")
        for row in top_rutas[:20]:
            frac = row["masa_total_periodo_g"]/masa_total
            f.write(
                f"Ruta {row['id_ruta']}: {row['masa_total_periodo_g']:.6E} g "
                f"({100*frac:.2f} %)\n"
            )

        f.write("\nINCIDENCIAS KMZ\n")
        f.write("-"*78 + "\n")
        if incidencias:
            for x in incidencias[:100]:
                f.write(f"- {x}\n")
        else:
            f.write("Sin incidencias reportadas.\n")

        f.write("\nNOTA METODOLÓGICA\n")
        f.write("-"*78 + "\n")
        f.write(
            "La elevación no forma parte del score principal. Se reporta HGT y la "
            "variabilidad topográfica 3x3 de cada candidato para revisar después "
            "la coherencia física sin imponer un peso arbitrario a la topografía.\n"
        )
        f.write(
            "Este ranking representa las fuentes viales. Para incorporar receptores "
            "sensibles a la selección final se requieren sus coordenadas y una regla "
            "explícita de ponderación; no se inventa esa ponderación aquí.\n"
        )


# =============================================================================
# 10. MAIN
# =============================================================================

def main():
    t0 = time.perf_counter()

    for p in (RUTA_EXCEL_ORIGEN, RUTA_KMZ_ORIGEN, RUTA_WRFOUT_D03):
        if not p.exists():
            raise FileNotFoundError(f"No existe: {p}")

    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

    mostrar("="*78)
    mostrar("SELECCIÓN DE CELDA MMIF REPRESENTATIVA - WRF d03")
    mostrar("="*78)

    mostrar("\n[1/5] Excel...")
    wb = openpyxl.load_workbook(
        RUTA_EXCEL_ORIGEN, read_only=True, data_only=True
    )
    try:
        for h in (HOJA_RUTAS, HOJA_FLUJO, HOJA_FE_MP10):
            if h not in wb.sheetnames:
                raise ValueError(f"Falta hoja {h}.")
        rutas = leer_hoja_rutas(wb[HOJA_RUTAS])
        ids = set(rutas)
        fechas_q, flujo = leer_matriz_diaria(wb[HOJA_FLUJO], ids)
        fechas_fe, fe = leer_matriz_diaria(wb[HOJA_FE_MP10], ids)
        if fechas_q != fechas_fe:
            raise ValueError("Flujo_Diario y FE_MP10 tienen fechas distintas.")
    finally:
        wb.close()

    masa_ruta = calcular_masa_total_por_ruta(rutas, flujo, fe, fechas_q)

    mostrar("\n[2/5] KMZ y fuentes LINE...")
    geometrias, incidencias, kml_usado = cargar_geometrias_kmz(
        RUTA_KMZ_ORIGEN, ids
    )
    fuentes = construir_fuentes_line(rutas, geometrias)
    puntos, diag_rutas = muestrear_emision(fuentes, masa_ruta)

    masa_total = sum(p.peso_g for p in puntos)
    masa_diag = sum(r["masa_total_periodo_g"] for r in diag_rutas)
    if not np.isclose(masa_total, masa_diag, rtol=1e-12, atol=1e-6):
        raise RuntimeError(
            f"No se conserva masa: puntos={masa_total}, rutas={masa_diag}"
        )

    for r in diag_rutas:
        r["fraccion_emision_total"] = r["masa_total_periodo_g"]/masa_total

    xs, ys, ws = arrays_puntos(puntos)
    mostrar(f"      KML: {kml_usado}")
    mostrar(f"      Fuentes LINE: {len(fuentes):,}")
    mostrar(f"      Puntos de integración: {len(puntos):,}")
    mostrar(f"      Masa ponderadora: {masa_total:.6E} g")

    mostrar("\n[3/5] Malla WRF...")
    malla = leer_malla_wrf(RUTA_WRFOUT_D03)
    mostrar(
        f"      GRID_ID={malla['grid_id']} "
        f"DX={malla['dx']} DY={malla['dy']} "
        f"shape={malla['lat'].shape}"
    )
    if malla["grid_id"] is not None and int(malla["grid_id"]) != 3:
        raise ValueError(
            f"GRID_ID={malla['grid_id']}; el archivo no parece d03."
        )

    mostrar("\n[4/5] Ranking de celdas...")
    score_mean, score_rms = calcular_scores(malla, xs, ys, ws)
    ranking = construir_ranking(malla, score_mean, score_rms, xs, ys, ws)
    centroide = centroide_emision(malla, xs, ys, ws)
    mejor = ranking[0]

    mostrar(
        f"      #1 j={mejor['j_south_north']} i={mejor['i_west_east']} "
        f"lat={mejor['lat_centro_celda']:.8f} "
        f"lon={mejor['lon_centro_celda']:.8f}"
    )
    mostrar(
        f"      HGT={mejor['HGT_celda_m']:.1f} m; "
        f"Dmean={mejor['dist_media_ponderada_km']:.3f} km"
    )

    mostrar("\n[5/5] Salidas...")
    escribir_csv(CARPETA_SALIDA/"ranking_celdas_mmif_d03.csv", ranking)
    escribir_csv(CARPETA_SALIDA/"diagnostico_pesos_rutas.csv", diag_rutas)

    with (CARPETA_SALIDA/"POINT_MMIF_sugerido.txt").open(
        "w", encoding="ascii", newline="\n"
    ) as f:
        f.write(
            f"POINT LL {mejor['lat_centro_celda']:.8f} "
            f"{mejor['lon_centro_celda']:.8f}\n"
        )

    escribir_resumen(
        CARPETA_SALIDA/"resumen_seleccion_punto_mmif.txt",
        mejor, ranking, diag_rutas, incidencias, centroide,
        malla, masa_total, len(puntos)
    )

    if GUARDAR_PUNTOS_MUESTREO:
        escribir_puntos(
            CARPETA_SALIDA/"puntos_emision_muestreados.csv",
            puntos, masa_total
        )

    mostrar("\nPOINT sugerido:")
    mostrar(
        f"POINT LL {mejor['lat_centro_celda']:.8f} "
        f"{mejor['lon_centro_celda']:.8f}"
    )
    mostrar(f"Tiempo: {time.perf_counter()-t0:.1f} s")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("\nERROR", file=sys.stderr)
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
