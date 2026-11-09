"""Muestra las selecciones CDS equivalentes a los campos conservados en un GRIB."""
import argparse
import json
from pathlib import Path

DIRECTORIO = Path(__file__).resolve().parent
VARIABLES = {
    33: "snow_density", 34: "sea_surface_temperature",
    39: "volumetric_soil_water_layer_1", 40: "volumetric_soil_water_layer_2",
    41: "volumetric_soil_water_layer_3", 42: "volumetric_soil_water_layer_4",
    49: "10m_wind_gust_since_previous_post_processing", 129: "geopotential",
    130: "temperature", 131: "u_component_of_wind", 132: "v_component_of_wind",
    134: "surface_pressure", 135: "vertical_velocity", 139: "soil_temperature_level_1",
    141: "snow_depth", 151: "mean_sea_level_pressure", 155: "divergence",
    157: "relative_humidity", 165: "10m_u_component_of_wind",
    166: "10m_v_component_of_wind", 167: "2m_temperature",
    168: "2m_dewpoint_temperature", 170: "soil_temperature_level_2",
    172: "land_sea_mask", 182: "evaporation", 183: "soil_temperature_level_3",
    235: "skin_temperature", 236: "soil_temperature_level_4",
    140229: "significant_height_of_combined_wind_waves_and_swell",
    140230: "mean_wave_direction", 140232: "mean_wave_period",
    228003: "friction_velocity", 228023: "cloud_base_height",
    228029: "instantaneous_10m_wind_gust", 228131: "10m_u_component_of_neutral_wind",
    228132: "10m_v_component_of_neutral_wind", 228246: "100m_u_component_of_wind",
    228247: "100m_v_component_of_wind",
}

def consultas(archivo):
    for s in archivo["selecciones"]:
        niveles = s["pressure_level"]
        producto = "reanalysis-era5-pressure-levels" if niveles else "reanalysis-era5-single-levels"
        parametros = {
            "product_type": ["reanalysis"], "data_format": "grib", "download_format": "unarchived",
            "variable": [VARIABLES[i] for i in s["parameter_ids"]], "area": s["area"],
            "year": [str(s["year"])], "month": [f'{s["month"]:02d}'],
            "day": [f"{d:02d}" for d in s["day"]], "time": [f"{h:02d}:00" for h in s["time"]],
        }
        if niveles:
            parametros["pressure_level"] = [str(n) for n in niveles]
        yield producto, parametros

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archivo", nargs="?", help="Nombre exacto en el inventario, incluida la subcarpeta si corresponde")
    parser.add_argument("--descargar", metavar="CARPETA", type=Path, help="Envía las consultas y guarda un GRIB por grupo")
    args = parser.parse_args()
    archivos = {f["archivo"]: f for f in json.loads((DIRECTORIO/"inventario_grib.json").read_text(encoding="utf8"))}
    if args.archivo is None:
        print("\n".join(archivos))
        return
    if args.archivo not in archivos:
        parser.error("El archivo debe figurar en el inventario.")
    if args.descargar:
        import cdsapi
        cliente = cdsapi.Client()
        args.descargar.mkdir(exist_ok=True, parents=True)
    for i, (producto, parametros) in enumerate(consultas(archivos[args.archivo]),1):
        print(json.dumps({"dataset":producto, "request":parametros}, indent=2))
        if args.descargar:
            destino = args.descargar / f"{Path(args.archivo).stem}-{i:02d}.grib"
            if destino.exists():
                raise FileExistsError(destino)
            temporal = destino.with_suffix(".grib.part")
            cliente.retrieve(producto,parametros).download(str(temporal))
            temporal.rename(destino)

if __name__ == "__main__":
    main()
