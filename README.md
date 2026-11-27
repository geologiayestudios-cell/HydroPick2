# HydroPick · España — V2.2.0

Primera edición pública propuesta. Motor PQWT y contexto GEODE (IGME-CSIC). Especial interés en Ciudad Real. La aplicación calcula una recomendación de **perforación exploratoria**, no un rendimiento garantizado ni una autorización de captación.

## Despliegue

- Mantén una copia del repositorio y de tus Secrets anteriores.
- Copia los contenidos de esta carpeta a la raíz del repositorio GitHub (incluidas carpetas ocultas). `app.py` es el punto de entrada. Mantén `requirements.txt`.
- Si reutilizas el repositorio anterior, **elimina explícitamente** los CSV e imágenes reales de `examples/` y conserva solo `Demo_150m.csv`. Para una publicación abierta recomendamos un repositorio nuevo sin el historial privado ni credenciales anteriores. No publiques `config.yaml` de V1 ni `.streamlit/secrets.toml`. Revisa datos y permisos del repositorio.
- Para una app pública, elimina `APP_PASSWORD` de Secrets o establece `APP_PASSWORD = ""`. Si mantienes una contraseña, se conserva el acceso restringido. En modo público el código no usa la clave OpenAI del propietario; el usuario puede usar su propia clave en Modo técnico. `OPENAI_MODEL` es opcional y configurable.
- En Streamlit Community Cloud selecciona el repositorio, rama y `app.py`; Python 3.11/3.12. Reinicia. No se necesita API key del IGME. Antes de abrir el servicio al público comprueba condiciones de uso/atribución GEODE, privacidad y política de uso de la app; las condiciones de reutilización comercial no se han validado en esta entrega.

Local: `pip install -r requirements.txt` y `streamlit run app.py`.

## Flujo de uso

1. Carga CSV, introduce coordenadas WGS84 reales (sin valores por defecto), confirma alcance del equipo y, si lo conoces, espaciamiento entre estaciones. El número de estación se conserva tal como figura en el archivo.
2. Pulsa Consultar geología IGME. Se muestra la descripción de las unidades cartografiadas y se sugiere el modelo hidrogeológico por reglas léxicas. Si el contexto requiere ajuste, activa información propia, elige modelo y confirma una fuente local. La cartografía superficial no verifica la columna a profundidad.
3. Revisa la geofísica: original y procesada por defecto; cuatro secciones o vista individual disponibles. La transformación procesada es propia de HydroPick. La escala automática es lineal nominal de 0 a Dmax en N−1 intervalos, no una calibración física. La de 300 m se contrastó gráficamente con L171; 100/150/500 m siguen siendo provisionales. El modo técnico admite escalas personalizadas y físicas, aunque estas últimas no sustentan una profundidad de perforación por sí solas.
4. En Interpretación verás decisión, contexto, estaciones, intervalos y profundidades recomendadas. Si hay antecedentes productivos comparables, introduce su intervalo de profundidad y referencia. No introducir datos inventados o no comparables.
5. Descarga la nota técnica y los objetivos CSV. El Modo técnico añade diagnósticos, curvas, perfil, comparación con imágenes, escala y JSON trazable, así como análisis complementario opcional por IA.

El modo demostración solo contiene mediciones sintéticas, sin coordenadas ni recomendaciones reales. Los CSV no se envían a IGME ni OpenAI; IGME recibe las coordenadas al consultar. El modo IA envía el paquete de metadatos, notas, resultados derivados y coordenadas únicamente tras autorización; no se envían las imágenes. No hay almacenamiento persistente propio en la aplicación; el servicio de alojamiento puede tener sus propias políticas y registros. No subir información confidencial sin autorización. Las API y el alojamiento no han sido probados en vivo en esta entrega.

## Motor de decisión — política public-1.0

Módulo `hydropick/decision.py`. Reglas deterministas: el modelo de IA no puede modificar el resultado calculado de la app.

### Criterios de entrada

- Mínimo 5 estaciones; cobertura numérica ≥80%; proporción de canales informativos ≥35%, al menos 3 informativos. No se permiten saltos de estaciones/canales para recomendar perforación.
- Detector de V2.1: 2 de 3 familias de contraste, 3 canales por región. Umbral robusto inicial 1.5; resolución de amplitud 0.001.
- Para recomendar: anomalía interior, índice geofísico ≥60/100, persistencia ≥65%, y al menos 3 canales consecutivos respaldados en la estación seleccionada. Estos índices son heurísticos, no probabilidades.
- Ubicación real y modelo local identificable por GEODE o modelo aportado y confirmado por el usuario con fuente. En medios arcillosos/margosos o mixtos se exige antecedente productivo independiente comparable. Si se aporta intervalo, se exigen al menos dos canales de soporte dentro del mismo; la estimación se restringe a ese soporte.
- Escala nominal automática compatible o personalizada; sin escala, o escala de penetración teórica exclusivamente, no se emite profundidad de perforación.

### Cálculo de profundidad

1. Selecciona en la estación central el tramo consecutivo de canales con mayor suma de votos, después longitud y menor profundidad para desempatar. Obtiene techo y base z_sup y z_inf en la escala seleccionada.
2. Si hay horizonte productivo comparable documentado, restringe al tramo de soporte dentro de ese horizonte. No extrapola una unidad superficial ni inventa estratigrafía.
3. Margen exploratorio M = max(mínimo litológico, paso nominal hasta el canal útil siguiente, fracción × (z_inf − z_sup)). Los mínimos y fracciones son parámetros operativos iniciales no calibrados:

| Familia | Mínimo (m) | Fracción |
|---|---:|---:|
| Detrítico granular | 5 | 0.25 |
| Carbonatado/kárstico | 10 | 0.35 |
| Paleozoico cuarcita-pizarra | 10 | 0.50 |
| Volcánico | 10 | 0.50 |
| Granítico/cristalino | 10 | 0.50 |
| Arcilloso/margoso con antecedente | 5 | 0.25 |
| Mixto con antecedente | 10 | 0.50 |

4. D_rec = 5 × ceil((z_inf + M)/5). Redondeo ascendente a 5 m para planificación. El resultado se limita a la cobertura consecutiva de canales informativos medidos en esa estación **por debajo del objetivo**. Si no hay cobertura suficiente, se requiere ampliar el alcance; no se recorta el objetivo para emitir un número artificial.
5. Un plan de perforación por estación: mayor índice geofísico entre candidatos admisibles, en empate menor profundidad. Los horizontes secundarios permanecen en la salida. La prioridad entre estaciones admisibles utiliza el índice geofísico, tras los filtros geológicos y de calidad.

Estados: Perforación exploratoria recomendada; Repetir o ampliar mediciones; Completar información; No recomendar perforación. Un perfil sin candidatos suficientes no equivale a ausencia de agua. Se mantiene una parada técnica al alcanzar el horizonte y la verificación de calidad y caudal en campo. La app no evalúa concesiones, permisos, coste ni diseño definitivo. Para Ciudad Real deben comprobarse restricciones de la demarcación y masa de agua antes de ejecutar.

## Validación

`python -m pip install pytest` y `python -m pytest -q`.

La entrega excluye los ejemplos reales para no publicar datos aportados por el usuario. Las pruebas de regresión privadas se habilitan con `HYDROPICK_PRIVATE_FIXTURES` apuntando a la carpeta `examples/` de V2.1. Se probaron los cuatro CSV anteriores y ambas imágenes de L171; 27 pruebas pasaron con las fixtures originales, incluidas 12 pruebas adicionales de la política de decisión. Sin ellas se omiten seis pruebas de regresión privadas. El código compiló correctamente. No se ejecutó Streamlit ni una consulta externa en vivo en este entorno. La política aún requiere validación con pozos reales (incluidos improductivos).
