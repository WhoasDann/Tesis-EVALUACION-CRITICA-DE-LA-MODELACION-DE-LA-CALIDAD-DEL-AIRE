# Complementos posteriores de la tesis

Actualización del 26 de noviembre de 2026. La campaña inicial de 3.314 casos permanece sin cambios. Esta carpeta incorpora controles y diagnósticos posteriores, con distintos niveles de reproducción.

| Complemento | Material incluido | Alcance de reproducción |
|---|---|---|
| [Campaña final de doce configuraciones](Reproduccion_doce/README.md) | Concentraciones horarias, código, manifiesto y tablas de referencia | Reproducción de los indicadores publicados para los cuatro receptores destacados |
| [Horario y ternas](reloj/paquete/README.md) | Insumos, código, protocolo, tablas, figuras y control independiente | Ejecución portable del diagnóstico meteorológico; siete tablas y tres gráficos comprobados |
| [Evaluación H1 y H2](evaluacion_h1_h2.zip) | Protocolos, matrices, controles numéricos, figuras y código histórico | Evidencia de 42 corridas adicionales; no incluye todos sus archivos nativos de entrada y salida |
| [Transferencia física](diagnostico_transferencia.zip) | Series WRF extraídas, perfiles, contrastes, figuras, trazabilidad y código histórico | Diagnóstico descriptivo; la repetición completa requiere NetCDF y otros insumos locales |
| [Unidades de concentración](auditoria_unidades.zip) | Auditoría, factores condicionales, informe, tablas y código histórico | Los factores no se aplican a las concentraciones; no se acredita equivalencia volumétrica MP10 |

## Reproducción del horario

Desde la raíz del repositorio, con Python 3.12 y las dependencias del complemento instaladas:

```sh
python complementos/reloj/paquete/reproducir.py --salida salida_reloj
```

El [README del paquete](reloj/paquete/README.md) detalla la instalación y los controles. La salida debe ser nueva. El [registro de portabilidad](reloj/Verificacion_portabilidad.json) acredita la prueba desde otra carpeta con bloqueo de los datos científicos originales; se reutilizaron las dependencias instaladas y no se ensayó un segundo sistema operativo.

## Interpretación de los controles

En cinco episodios de 24 horas, 14 aumentos de 40 contrastes H1 y ocho inversiones de 60 contrastes H2 superaron los márgenes empíricos retrospectivos de las representaciones ensayadas. La comprobación es diaria y no certifica convergencia de medias estacionales o máximos de toda la malla. Los diagnósticos de transferencia y horario conservan las condiciones físicas de la interpretación.

Los ZIP contienen un alcance propio y hashes de los archivos archivados. Los scripts históricos documentan los cálculos y sus dependencias; no deben confundirse con el programa portable de horario. Los estados fechados de los recibos conservan el contexto en que se generaron, incluido el hecho de que entonces no estaban publicados.

## Pendientes científicos

- Confirmación del reloj, intervalo de registro y altura de sensores de Piedra Carvajal.
- Evidencia independiente para admitir la transferencia estación-columna-perfil en cada episodio y receptor.
- Identificación y referencia vertical del relieve utilizado.
- Entradas y soportes equivalentes para comparar íntegramente con el titular, y trazabilidad de la base volumétrica de MP10.

La reproducción computacional y los controles de precisión no resuelven por sí solos esos antecedentes. Los resultados mantienen interpretación de sensibilidad prescrita, sin incertidumbre calibrada ni determinación de un peor caso físico o legal.
