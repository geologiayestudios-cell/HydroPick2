# HydroPick · España — V2.2.0

## Flujo de uso

1. Carga CSV, introduce coordenadas WGS84 reales (sin valores por defecto), confirma alcance del equipo y, si lo conoces, espaciamiento entre estaciones. El número de estación se conserva tal como figura en el archivo.
2. Pulsa Consultar geología IGME. Se muestra la descripción de las unidades cartografiadas y se sugiere el modelo hidrogeológico por reglas léxicas. Si el contexto requiere ajuste, activa información propia, elige modelo y confirma una fuente local. La cartografía superficial no verifica la columna a profundidad.
3. Revisa la geofísica: original y procesada por defecto; cuatro secciones o vista individual disponibles. La transformación procesada es propia de HydroPick. La escala automática es lineal nominal de 0 a Dmax en N−1 intervalos, no una calibración física. La de 300 m se contrastó gráficamente con L171; 100/150/500 m siguen siendo provisionales. El modo técnico admite escalas personalizadas y físicas, aunque estas últimas no sustentan una profundidad de perforación por sí solas.
4. En Interpretación verás decisión, contexto, estaciones, intervalos y profundidades recomendadas. Si hay antecedentes productivos comparables, introduce su intervalo de profundidad y referencia. No introducir datos inventados o no comparables.
5. Descarga la nota técnica y los objetivos CSV. El Modo técnico añade diagnósticos, curvas, perfil, comparación con imágenes, escala y JSON trazable, así como análisis complementario opcional por IA.

El modo demostración solo contiene mediciones sintéticas, sin coordenadas ni recomendaciones reales. Los CSV no se envían a IGME ni OpenAI; IGME recibe las coordenadas al consultar. El modo IA envía el paquete de metadatos, notas, resultados derivados y coordenadas únicamente tras autorización; no se envían las imágenes. No hay almacenamiento persistente propio en la aplicación; el servicio de alojamiento puede tener sus propias políticas y registros. No subir información confidencial sin autorización. Las API y el alojamiento no han sido probados en vivo en esta entrega.
