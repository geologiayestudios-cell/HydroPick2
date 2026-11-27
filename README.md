# HydroPick V2.1 — España · Piloto Ciudad Real

Versión 2.1.0 de GeoAqua. Conserva el conector GEODE `Identify` que funcionó en V2.0.1. Incorpora escalas automáticas, cuatro pseudosecciones, detección por consenso y comparación experimental con las imágenes del fabricante. No es una inversión geoeléctrica ni un predictor calibrado de productividad.

## Actualizar la aplicación que ya está publicada

1. Haz una copia de la rama existente o crea una rama `v2.1` en GitHub para probar antes de actualizar producción.
2. Descomprime el ZIP. Copia **el contenido** de `HydroPick_V2_1_ES/` en la raíz del repositorio (no anides esa carpeta dentro del repositorio). Reemplaza `app.py`, `requirements.txt`, `README.md` y los archivos de `hydropick/`. Añade `examples/` y `tests/`. La versión de `hydropick/geology.py` incluida es exactamente el parche IGME anterior.
3. Mantén tus Secrets de Streamlit y la configuración de acceso existente. No subas `.streamlit/secrets.toml`, claves ni `config.yaml` de V1. Las carpetas ocultas incluidas solo contienen configuración pública y una plantilla.
4. Confirma los cambios. Streamlit normalmente redespliega automáticamente; si es necesario usa **Manage app → Reboot app**. El archivo principal sigue siendo `app.py`. Python 3.11/3.12 recomendado. Se añade Pillow en `requirements.txt` para tratar imágenes.
5. Comprueba la consulta IGME con las mismas coordenadas que ya funcionaron. Luego prueba el ejemplo L171 y sus imágenes.

No se requiere una nueva API key para IGME ni para las mejoras del motor numérico. La IA opcional conserva la configuración previa (`APP_PASSWORD`, `OPENAI_API_KEY`, `OPENAI_MODEL`); su facturación es independiente de ChatGPT. El acceso por contraseña del prototipo no sustituye controles de acceso robustos ni limita intentos. Usa un repositorio privado y evita publicar información de clientes sin autorización.

## Escala de profundidad

El selector detecta el modo compatible por número y secuencia de canales. La escala automática utiliza `z=(i−1)*D/(N−1)`, de cero al alcance nominal. No se renumeran canales omitidos ni se inventan frecuencias.

| Modo | Canales | Intervalo nominal | Estado |
|---|---:|---:|---|
| 100 m | 20 | 5.263 m | Provisional |
| 150 m | 36 | 4.286 m | Provisional |
| 300 m | 40 | 7.692 m | Contrastada gráficamente en L171 |
| 500 m | 49 | 10.417 m | Extrapolada, sin gráfica de referencia |

Si el CSV no coincide con el modo, la escala automática se rechaza y las salidas quedan en canales. El selector también permite:
- **Personalizada / calibrada:** CSV `canal,profundidad_m`, todos los canales, referencia obligatoria. Monótona, dentro del alcance seleccionado.
- **Física contextualizada:** CSV `canal,frecuencia_hz` documentado, resistividad asumida y factor k (0.3–0.5). Calcula `k*503.3*sqrt(rho/f)`. Si excede el alcance, no lo recorta ni reescala; el usuario debe revisar supuestos. Es una escala de penetración teórica, no profundidad del cuerpo.
- **Solo canales:** análisis sin convertir el eje vertical.

La escala aplicada puede descargarse en la pestaña Exportar. Los canales constantes se excluyen del detector pero no se eliminan de la escala original. Las profundidades son nominales o teóricas, no intervalos verificados por perforación.

## Pseudosecciones y consenso

En Geofísica, la vista predeterminada muestra simultáneamente cuatro representaciones:
1. Original: amplitudes exportadas, paleta aproximada PQWT.
2. Procesada experimental: por defecto `sign(V)*log10(1+abs(V))`; opciones `log10(V)` (solo valores positivos) y raíz cuadrada con signo. No se afirma reproducir exactamente el algoritmo propietario PQWT.
3. Contraste relativo: puntuación robusta por canal (mediana/MAD y límite mínimo de resolución).
4. Anomalías locales: residual respecto a vecinos inmediatos, normalizado por la dispersión robusta del canal.

La vista individual incluye también residual de tendencia, contraste fraccional y mapa de consenso. La interpolación lineal y los contornos son opcionales y se emplean únicamente para visualizar; no extrapolan ni rellenan huecos entre estaciones/canales faltantes. Curvas originales, perfiles verticales y QA/QC se conservan.

El detector trabaja en la matriz medida, no en píxeles. Exige coincidencia de dos de tres familias por celda: contraste global (original y log agrupados para evitar duplicar evidencias), residual de tendencia, contraste local. Exige al menos tres canales por región conectada. El índice de contraste y persistencia es experimental; puede cambiar la jerarquización respecto a V2.0 y puede no identificar candidatos. Se penalizan bordes abiertos. La estabilidad se evalúa con umbrales 0.8×, 1× y 1.2×. Todas las transformaciones derivan de la misma adquisición; no representan corroboración de campo independiente.

## Comparación con gráficas del fabricante

En Geofísica, abrir **Comparar con gráficas PQWT del fabricante (experimental)**. Subir una o ambas imágenes PNG/JPEG de la misma línea y alcance. Ajustar los límites en píxeles del área de datos (sin ejes o leyenda) y la posición de la barra cromática vertical (alto arriba/bajo abajo), junto con el número de clases. La previsualización marca los límites. Seleccionar la casilla de comparación de cada imagen.

Para probar sin subir archivos: activar ejemplo `300M_L171.csv`, mantener escala automática de 300 m y activar **Usar las dos imágenes de ejemplo L171**. Los recortes iniciales están ajustados aproximadamente a estas imágenes; en otras imágenes se deben revisar. La comparación necesita un eje que cubra 0 a D y presupone un eje horizontal lineal con el mismo orden de estaciones. Se realiza interpolación lineal visual, muestreo de leyenda y asignación aproximada de clases cromáticas; se excluyen píxeles alejados de la paleta. Se calculan Pearson, Spearman y cobertura por método. Los métodos pueden tener distinta cobertura; comparar con cautela. No son amplitudes físicas recuperadas, una inversión ni una prueba del algoritmo propietario. Los resultados no alteran el detector. Las imágenes no se envían a la IA; las métricas se incorporan al paquete que puede enviarse con consentimiento.

## Geología y exportación

GEODE IGME-CSIC: https://mapas.igme.es/gis/rest/services/Cartografia_Geologica/IGME_Geode_50/MapServer — `Identify`, capas 8 y 6, escala peninsular 1:50.000. La aplicación conserva consulta, atributos, errores y validación manual del modelo geológico. Se mantienen las referencias MAGNA, CH Guadiana e IGME, las reglas expertas, los contextos regionales de Ciudad Real y la IA opcional. La cartografía superficial no determina la litología a profundidad. Revisar condiciones del servicio antes de uso comercial. Los ejemplos no corresponden automáticamente a las coordenadas del proyecto.

Exportar JSON (incluye escala, parámetros, comparación y métricas), CSV de candidatos, CSV de escala y nota Markdown. No existe almacenamiento persistente en esta versión; descargar los resultados antes de cerrar la sesión.

## Ejecutar localmente y verificar

```sh
python -m venv .venv
# Activa .venv según tu sistema
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
python -m compileall -q app.py hydropick
streamlit run app.py
```

15 pruebas automatizadas superadas en el entorno de desarrollo: importación de los cuatro CSV reales; canales constantes; anomalía sintética; cuatro escalas; modelo físico; respeto de huecos y orientación descendente; comparación con las dos imágenes reales de L171; consulta Identify simulada. La compilación Python pasó. No se ha ejecutado la interfaz real de Streamlit (dependencia no instalada en el entorno de desarrollo), ni se ha realizado una nueva consulta en vivo a IGME ni a OpenAI. El conector se conserva idéntico al parche que el usuario confirmó que funcionaba.

Con resolución 0.001 y umbral 1.5: L67 genera 5 regiones, L171 1, L1 1 y L15 ninguna. No equivale a éxito/fracaso de perforación. Con la configuración inicial de recorte cromático L171, Pearson es aproximadamente 0.975 para original vs datos brutos y 0.969 para procesada vs log10 positivo, frente a 0.787 para procesada vs datos brutos. Son cifras dependientes del procedimiento de comparación.

## Archivos

`app.py` interfaz; `hydropick/geophysics.py` análisis y consenso; `hydropick/scales.py` escalas; `hydropick/visuals.py` interpolación; `hydropick/comparison.py` comparación cromática; `hydropick/geology.py` conector IGME y reglas; `hydropick/ai.py` integración opcional; `examples/` cuatro CSV y dos imágenes L171; `tests/` pruebas. No incluye contraseñas ni claves reales.
