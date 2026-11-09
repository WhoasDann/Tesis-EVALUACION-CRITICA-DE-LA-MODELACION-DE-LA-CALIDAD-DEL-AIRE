from pathlib import Path
import json,hashlib
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/Piloto_transferencia_2026-10-27'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    old=Path(r'/archivo/usuario\Documents\Codex\2026-10-08\hem')
    deps=[ROOT/'work/piloto_transferencia/receive_results.py',ROOT/'work/piloto_transferencia/prepare_transfer.py',old/'work/salidas_estacionales_20261021.py',old/'work/ejecutar_base_verano_20261021.py',old/'outputs/Biblioteca_Tesis/tesis/receptores.py',OUT/'Diseno.json',OUT/'Verificacion_meteorologia.json',OUT/'Referencias_BASE.json']
    (OUT/'Contrato_recepcion.json').write_text(json.dumps(dict(created_utc=datetime.now(timezone.utc).isoformat(),inputs=[dict(path=str(p),sha256=sha(p)) for p in deps]),indent=2))
    text='''# Piloto de transferencia del viento en el tercer PC

Este lote completa un contraste de sensibilidad que estaba pendiente: sumar el mismo vector horizontal al viento de toda la columna o limitarlo a la capa baja. No son miembros de incertidumbre calibrada. Los lotes BASE de Windows y Linux continúan por separado.

## Diseño fijado antes de las nuevas concentraciones

Se eligieron el 21 y 22 de diciembre de 2016, los mismos días del ensayo vectorial previo. Se conserva el inventario de 12.263 fuentes, las emisiones propias de MP10 y MP2,5, el terreno y la configuración estacional. Las alternativas se comparan con los resultados BASE de esos mismos días; no se repite su dispersión.

- **UNIFORM:** incremento de +1 m/s hacia el este y -0,5 m/s hacia el norte en todos los niveles con viento válido.
- **PBL:** mismo incremento hasta 10 m y reducción suave a cero al llegar a la altura de capa límite horaria de BASE. Por encima, el perfil permanece idéntico.

El adaptador actúa en los registros de viento del archivo ONSITE de la única columna MMIF, antes de AERMET. La altura utilizada es MHGT ya procesada por MMIF. Esta implementación es distinta de editar niveles instantáneos de WRF antes de la interpolación: no se afirma equivalencia entre ambos operadores. Tampoco reintegra la dinámica de WRF. Temperaturas, presión, humedad, flujos, altura de mezcla, sondeos y parámetros estacionales de superficie permanecen como en BASE.

La perturbación comprende 96 horas, con un día auxiliar antes y después de los dos días objetivo. AERMET procesa el calendario estacional completo para conservar el mismo contexto y las mismas características de superficie. Se conservan sus advertencias; no se convierten en datos válidos las horas faltantes.

## Verificación y costo limitado

La repetición de control de AERMET reprodujo exactamente todos los valores numéricos SFC/PFL del BASE estacional. Se verificaron 2.688 registros válidos de perfil por alternativa, con tolerancias fijadas por la precisión de sus archivos. En PBL, 1.098 registros superiores quedaron exactamente iguales. Las temperaturas y las horas fuera de la ventana también quedaron intactas.

Primero se ejecutan ocho casos diarios en cuatro puntos exactos: Piedra Carvajal, estación Los Bronces, Sulfatos y La Paloma. Son dos tratamientos por dos días por dos contaminantes; no ocho realizaciones aleatorias. Después de recibirlos correctamente se ejecutan cuatro casos PBL en la malla completa de 6.295 receptores. La recepción de estos casos comprobará además que los cuatro puntos comunes coinciden con sus corridas pequeñas.

La comparación de cuatro puntos sirve para el contraste inicial. No representa el máximo de la malla general ni de los glaciares. Los cuatro casos completos permitirán comparar la variante PBL con BASE en toda la malla existente. No se ha asignado una malla completa para UNIFORM ni un conjunto probabilístico estacional.

## Estado y operación

El estado verificable está en Estado_small.json y Estado_full.json. Los archivos *_remote_status.json son instantáneas fechadas del ejecutor. Solo los casos con recibo SCIENTIFIC_RECEPTION_PASSED se consideran recibidos. Estos resultados no se suman a los días BASE completados.

El plan limita el tercer equipo a dos procesos AERMOD simultáneos. La tarea Tesis_AERMOD_PC3_20261027 funciona bajo demanda, sin calendario y sin inicio al arrancar Windows. Sus procesos sobreviven al cierre de SSH. Las entradas y ejecutables se verifican por SHA256; el ejecutor conserva intentos y resultados y mantiene una reserva de disco de 6 GiB.

Directorio remoto: C:/Users/Daniel/Documents/Tesis_Calculo_20261027/jobs/transfer_20261027. Las carpetas small y full tienen planes distintos; sus lanzadores usan launch_small y launch_full. No repetir la tarea ni borrar candados para reiniciarla. STOP_AFTER_CURRENT en la carpeta del lote permite terminar los casos activos y no despachar los siguientes; una reanudación requiere revisar los recibos e intentos existentes.

El receptor local descarga y verifica resultados en esta entrega, sin modificar recibos BASE. Si se apaga el Windows principal, las corridas del tercer PC continúan mientras ese equipo permanezca encendido; la descarga espera a restablecer el receptor. Los estados fechados no sustituyen una comprobación de conexión actual.

## Límites y referencias

La transición cúbica y la amplitud son hipótesis explícitas de sensibilidad de esta tesis. No proceden de una covarianza espacial observada ni de una validación del error a distintas alturas. Que las corridas terminen no valida físicamente esa transferencia. El ensayo permite medir su influencia bajo condiciones fijas; no estima P95 estacional ni incertidumbre total.

La documentación de EPA describe el procesamiento de datos pronosticados mediante MMIF y AERMET; no prescribe ni valida la función de pesos elegida aquí: [guía MMIF](https://gaftp.epa.gov/aqmg/SCRAM/models/related/mmif/MMIF_Guidance.pdf), [manual AERMET](https://gaftp.epa.gov/Air/aqmg/SCRAM/models/met/aermet/aermet_userguide.pdf).
'''
    (OUT/'LEEME.md').write_text(text,encoding='utf-8')
if __name__=='__main__':main()