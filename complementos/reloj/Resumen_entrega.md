# Cierre de la reproducción portable

19 de noviembre de 2026.

Se eliminó la dependencia de rutas privadas para reproducir el diagnóstico del horario y las ternas. El paquete incluye los ocho insumos de datos/diseños, los cuatro módulos necesarios y las tablas de referencia. Las rutas históricas permanecen en el protocolo como procedencia, pero no se utilizan para cargar los datos.

La prueba se realizó desde una copia ubicada en una carpeta con espacios y con un directorio actual distinto. Un control de acceso bloqueó los archivos científicos originales; el cálculo terminó sin intentos de consultarlos. Se conservaron los cuerpos del cálculo, del control escalar y de los gráficos. Las dependencias Python existentes se reutilizaron; no se ensayó una instalación nueva ni otro sistema operativo.

Resultados de la prueba:

- Siete tablas reproducidas con igualdad de bytes.
- 48.890 celdas numéricas y 59.655 textuales comparadas; diferencia numérica máxima igual a cero en este entorno.
- 45.440 residuos comprobados por el verificador escalar independiente.
- Tres gráficos PNG reproducidos con igualdad de píxeles; también se generaron sus SVG.
- Rechazo de un insumo alterado antes del cálculo y rechazo de una carpeta de salida existente sin modificar sus archivos.

El archivo ZIP contiene `paquete/`, con el README y el comando de reproducción, y los registros de esta prueba. Los resultados científicos, el manuscrito y el repositorio público no se modificaron. No se ejecutaron simulaciones de dispersión.

## Alcance pendiente

Quedó resuelta la reproducción local portable de este diagnóstico, no la reproducción integral de todas las etapas de la tesis. La versión pública del repositorio citada en el manuscrito sigue siendo anterior a este complemento.

La confirmación instrumental de reloj, intervalo y altura de sensores sigue requiriendo antecedentes externos. La validación de la transferencia estación-columna-perfil, la procedencia vertical del DEM, la equivalencia integral con el titular y la trazabilidad volumétrica MP10 continúan separadas. Una repetición computacional exacta no resuelve esas cuestiones.
