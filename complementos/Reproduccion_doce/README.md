# Complemento del diseño final de doce configuraciones

Este paquete reproduce los indicadores de la campaña final de 4368 casos a partir de las concentraciones horarias comunes archivadas para un panel de 40 receptores. El programa comprueba los resultados de Los Bronces, Piedra Carvajal, Sulfatos y La Paloma. La carpeta reúne los datos horarios, el código, las dependencias y las tablas de referencia.

## Ejecución

Las dependencias fijadas requieren Python 3.11 o posterior. La ejecución se comprobó con Python 3.13.9; las versiones efectivamente ensayadas se registran en ENTORNO.json. Desde esta carpeta:

```sh
python -m pip install -r requirements.txt
python reproducir.py salida
```

La carpeta de salida debe ser nueva. El programa verifica SHA-256 de los insumos, reconstruye el calendario desde las marcas AERMOD (hora de término), convierte el invierno desde UTC−4 fijo al reloj civil de Santiago y admite solo días con 24 horas comunes. Compara 86 días de verano y 90 de invierno. Los archivos de entrada contienen 2150 y 2205 horas comunes por receptor, respectivamente. No se imputan horas.

Se reconstruyen 192 medias, 16 selecciones de mayor media y máximo diario, 96 contrastes de interacción y 264 comparaciones del orden de las medias. Los resultados se cotejan con las tablas de referencia después del cálculo. La tolerancia de 1e-9 µg/m³ se aplica al cotejo aritmético de las agregaciones.

## Escenarios y límites

T_MINUS/T_PLUS corresponden a BASE −/+ σ_T. WS_MINUS/WS_PLUS corresponden a BASE −/+ σ_WS. Los nombres combinados modifican ambos factores. El sufijo INV permite inversión de 180° cuando la resta firmada de rapidez atraviesa cero; sin INV se limita la rapidez a cero. Las amplitudes proceden de la desviación estándar muestral de observaciones horarias por temporada, no de discrepancias con WRF ni de medias diarias.

Este paquete permite reproducir indicadores desde salidas horarias ya generadas. No incluye los ejecutables, todos los insumos nativos ni una repetición completa de WRF–MMIF–AERMET–AERMOD. Los cuatro CSV horarios incorporan el calendario y la máscara común auditados; no sustituyen las salidas nativas conservadas en el archivo del proyecto. No asigna probabilidades, valida transferencia física ni acredita un peor caso regulatorio. Los resultados son aportes viales parciales y no concentración ambiental total.
