# HydroPick V2 — España / piloto Ciudad Real

Prototipo técnico 2.0.0 de GeoAqua. Analiza exportaciones PQWT y consulta la unidad geológica superficial en GEODE (IGME-CSIC). Mantiene separado el análisis de anomalías, la hipótesis geológica y la decisión técnica. No es una inversión de resistividad ni un predictor calibrado de caudal.

## Despliegue en Streamlit Community Cloud

1. Crear un repositorio **privado** nuevo en GitHub (por ejemplo, `hydropick-v2-es`). Descomprimir este ZIP y subir el contenido de `HydroPick_V2_ES`, incluidas las carpetas ocultas `.streamlit` y `.gitignore`. No copiar `config.yaml` ni credenciales de V1.
2. En https://share.streamlit.io/ crear una aplicación desde el nuevo repositorio. Rama `main`; archivo principal `app.py`. Python 3.11 o 3.12 recomendado.
3. En Advanced settings / Secrets, configurar al menos `APP_PASSWORD` con una contraseña larga propia. Preferir además los controles de acceso del alojamiento; el acceso por contraseña de este prototipo no es un sistema multiusuario robusto ni limita intentos. No publicar proyectos de clientes sin controles adecuados.
4. Para IA opcional, añadir `OPENAI_API_KEY` y `OPENAI_MODEL` (modelo predeterminado configurable: `gpt-6.2-astra`, sujeto a acceso de la cuenta). La API tiene facturación separada y el servicio necesita conexión a Internet. El modo de reglas funciona sin clave.
5. No subir `.streamlit/secrets.toml` al repositorio. El archivo `secrets.toml.example` contiene únicamente marcadores. Si la clave de cookies V1 estuvo expuesta, renovarla.

## Ejecución local

```sh
python -m venv .venv
# Activar entorno: Windows .venv\Scripts\activate | Linux/macOS source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

## Uso

- Cargar CSV con N, L opcional, y columnas freqNN. El ejemplo L67 sirve para probar el motor; no corresponde automáticamente a Ciudad Real ni debe usarse para recomendar allí.
- Indicar el modelo PQWT, modo nominal y separación real si se conoce. Los índices N deben ser enteros únicos por línea. Elegir la línea si el archivo contiene varias.
- Activar coordenadas reales WGS84 (latitud/longitud). Los valores precargados ilustran la ciudad de Ciudad Real; no representan un terreno investigado. Consultar IGME. Si el servicio falla, registrar evidencia manual y validar la familia conceptual.
- Revisar datos originales, normalizados, residual de tendencia, contraste local y regiones detectadas. El detector busca bajos relativos con soporte multicanal; no fuerza un candidato. Las anomalías abiertas tienen penalización provisional.
- Para usar metros de profundidad, aportar CSV `canal,profundidad_m` con la escala **documentada** de todos los canales y su referencia. No existe una tabla de frecuencias confirmada en la documentación aportada. Si no hay escala, la salida queda en canales. El rango nominal por sí solo no basta. No equivale a una inversión ni a profundidad de acuífero.
- Revisar interpretación de reglas y, si se desea, generar borrador IA con autorización de envío. La investigación web se habilita opcionalmente en la llamada Responses API. Las referencias y resultados requieren revisión humana. La IA no modifica el detector.
- Descargar JSON, CSV de candidatos y nota técnica Markdown; no existe persistencia de proyectos en servidor en esta versión.

## Fuentes y alcance

- GEODE: https://mapas.igme.es/gis/rest/services/Cartografia_Geologica/IGME_Geode_50/MapServer — consultas REST puntuales de capas 8 (Recintos geología) y 6 (Cuaternario), escala peninsular 1:50.000. Se conservan atributos, hora, enlace y errores. No se afirma la litología profunda ni se calcula distancia a contactos. La clasificación automática por palabras clave es sugerencia, no veredicto.
- MAGNA hoja 784: https://datos.gob.es/es/catalogo/ea0010987-mapa-geologico-de-espana-e-1-50-000-hoja-784-ciudad-real2 — referencia si las coordenadas pertenecen a esa hoja.
- CH Guadiana: https://www.chguadiana.es/cuenca-hidrografica/hidrologia/aguas-subterraneas/piezometria — enlace para consulta documental, no conexión automatizada en esta versión.
- IGME Daimiel: https://aguas.igme.es/zonas_humedas/daimiel/medio_fisico/hidrogeologia.htm — contexto histórico regional, no nivel freático actual.
- Condiciones GEODE: https://mapas.igme.es/gis/rest/services/Cartografia_Geologica/IGME_Geode_50/MapServer/info/iteminfo — revisar licencias y contactar con IGME antes de ofrecer un servicio de valor añadido no gratuito.

Biblioteca de reglas inicial: carbonatado/kárstico, cuarcita-pizarra paleozoica, volcánico, detrítico, arcilloso/margoso, granítico, mixto y desconocido. Las cuatro referencias regionales de Ciudad Real son orientativas, no polígonos de clasificación territorial.

## Verificación

```sh
python -m pip install pytest
python -m pytest -q
python -m compileall -q app.py hydropick
```

Pruebas locales ejecutadas: L67 (11 estaciones, 36 canales, 149 ceros, 24 canales informativos), perfil constante, anomalía sintética con escala explícita, consulta GEODE simulada. La compilación Python pasó. En el entorno de desarrollo no estaba instalada la dependencia Streamlit y no había acceso de red al IGME; no se ha ejecutado la interfaz ni probado la API en vivo. Probar en el despliegue antes de uso operativo. Con parámetros predeterminados L67 detecta 5 regiones, incluidas dos distintas en N4 y una de borde en N11. Esto no establece presencia de agua.

## Estructura y próximos pasos

`app.py`: interfaz. `hydropick/geophysics.py`: detector determinista. `hydropick/geology.py`: conector GEODE y reglas. `hydropick/ai.py`: integración opcional Responses API. `tests/`: pruebas. `examples/`: CSV del usuario.

Pendientes: tabla instrumental verificada, pruebas con levantamientos de Ciudad Real, extracción automática de MASb y pozos, topografía, georreferenciación de estaciones, correlación multilínea, parámetros GQI/GEQI/HPI/ICI calibrados, persistencia y exportación PDF. La priorización contextual es cualitativa en este MVP. No se ha incorporado la autenticación de V1, para no reutilizar secretos.
