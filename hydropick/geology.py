"""Conector oficial español. Los datos de afloramiento no son un sondeo."""
import requests
from datetime import datetime,timezone
import unicodedata

GEODE='https://mapas.igme.es/gis/rest/services/Cartografia_Geologica/IGME_Geode_50/MapServer'
SOURCES={
 'GEODE IGME-CSIC':GEODE,
 'MAGNA: hoja 784 Ciudad Real (solo si corresponde al sitio)':'https://datos.gob.es/es/catalogo/ea0010987-mapa-geologico-de-espana-e-1-50-000-hoja-784-ciudad-real2',
 'CH Guadiana: piezometría':'https://www.chguadiana.es/cuenca-hidrografica/hidrologia/aguas-subterraneas/piezometria',
 'CH Guadiana: masas en riesgo':'https://www.chguadiana.es/servicio-al-ciudadano/comunidades-de-usuarios/mas-en-riesgo',
 'IGME: hidrogeología regional de Daimiel (referencia histórica)':'https://aguas.igme.es/zonas_humedas/daimiel/medio_fisico/hidrogeologia.htm',
 'InfoIGME: servicios cartográficos':'https://mapas.igme.es/' }
RULES={
 'Desconocido':('Contraste eléctrico de origen indeterminado','No hay contexto validado; no priorizar perforación.'),
 'Carbonatado / kárstico':('Fractura, disolución, contacto o relleno conductor','Arcilla de relleno, conductos secos o desconectados.'),
 'Paleozoico cuarcita-pizarra':('Fractura, contacto cuarcita-pizarra o alteración','Pizarra conductora o fractura sellada; baja permeabilidad de matriz.'),
 'Volcánico / Campo de Calatrava':('Contacto volcánico-sedimentario, fractura, brecha o alteración','Toba alterada, arcillas, discontinuidad sin conectividad; posible mineralización.'),
 'Detrítico granular':('Nivel granular saturado o cambio de granulometría','Arcillas, matriz fina o cementación; verificar continuidad.'),
 'Arcilloso / margoso':('Cambio de arcilla, humedad o intercalación permeable','Conducción por arcilla sin caudal aprovechable.'),
 'Granítico / cristalino':('Fracturación o meteorización localizada','Alteración arcillosa, fractura sellada o escaso almacenamiento.'),
 'Mixto':('Contacto, cambio litológico o zona alterada/fracturada','Varias explicaciones plausibles; validar estratigrafía.')}
REGIONAL={'Montes de Toledo / Valle de Alcudia':'Paleozoico: cuarcitas y pizarras; objetivos en discontinuidades, no asumir productividad de matriz.', 'Campo de Calatrava':'Entorno heterogéneo con volcanismo, sustrato paleozoico y depósitos sedimentarios; contactos y alteración pueden generar contrastes.', 'Mancha Occidental':'Sistemas carbonatados y detríticos; verificar masa de agua, niveles, continuidad y situación administrativa.', 'Campo de Montiel':'Contexto carbonatado; evaluar disolución, fracturación y conectividad.'}

def query_geode(lat,lon):
    """Identifica polígonos en el punto mediante la operación publicada por GEODE."""
    if not (-90<=lat<=90 and -180<=lon<=180):
        raise ValueError('Coordenadas inválidas.')
    url=f'{GEODE}/identify'
    # Extensión de contexto para la escala del mapa; no es un radio de búsqueda.
    d=0.01
    params={'f':'json','geometry':f'{lon},{lat}',
            'geometryType':'esriGeometryPoint','sr':4326,
            'layers':'all:8,6','tolerance':0,
            'mapExtent':f'{lon-d},{lat-d},{lon+d},{lat+d}',
            'imageDisplay':'1000,1000,96','returnGeometry':'false',
            'returnFieldName':'true'}
    results=[]; errors=[]
    try:
        r=requests.get(url,params=params,timeout=25)
        r.raise_for_status(); data=r.json()
        if 'error' in data: raise ValueError(str(data['error']))
        if not isinstance(data.get('results'),list):
            raise ValueError('Respuesta sin lista results de Identify.')
        for item in data['results']:
            layer=item.get('layerId')
            if layer not in (8,6): continue
            attrs=dict(item.get('attributes') or {})
            aliases={'Descripción Unidad Geológica':'DESC_UNIT',
                     'Código de Unidad Geológica':'CODE_UNIO',
                     'Edad Superior':'NAME_EDA2','Edad Inferior':'NAME_EDA1'}
            for alias,key in aliases.items():
                if key not in attrs and alias in attrs: attrs[key]=attrs[alias]
            if not attrs.get('DESC_UNIT') and item.get('displayFieldName') in ('DESC_UNIT','Descripción Unidad Geológica'):
                attrs['DESC_UNIT']=item.get('value')
            results.append({'capa':layer,'atributos':attrs,'fuente':url,'escala':'1:50.000 peninsular'})
    except (requests.RequestException,ValueError) as e:
        errors.append(f'GEODE Identify: {str(e)[:350]}')
    return {'lat':lat,'lon':lon,'fecha_utc':datetime.now(timezone.utc).isoformat(),
            'registros':results,'errores':errors,'estado':'parcial' if results and errors else ('documentado' if results else ('error' if errors else 'sin coincidencias'))}

def suggest_family(records):
    text=' '.join(str(r.get('atributos',{}).get('DESC_UNIT','')) for r in records).lower(); text=''.join(c for c in unicodedata.normalize('NFD',text) if unicodedata.category(c)!='Mn')
    terms={'Carbonatado / kárstico':['caliza','dolomia'], 'Paleozoico cuarcita-pizarra':['cuarcita','pizarra'], 'Volcánico / Campo de Calatrava':['basalto','volcan','piroclast','toba'], 'Detrítico granular':['arena','grava','conglomerado','aluvial'], 'Arcilloso / margoso':['arcilla','marga'], 'Granítico / cristalino':['granito','granodiorita','gneis']}
    hits=[k for k,v in terms.items() if any(t in text for t in v)]
    return hits[0] if len(hits)==1 else ('Mixto' if hits else 'Desconocido')

def interpret(anomalies,family,confirmed,geology=None):
    hyp,risk=RULES[family]; out=[]
    for a in anomalies:
        action='Ampliar línea: anomalía de borde.' if a['borde'] else ('Validar contexto geológico antes de priorizar.' if not confirmed or family=='Desconocido' else 'Objetivo preliminar para contraste de campo; no autorización de perforación.')
        if family=='Arcilloso / margoso' and not a['borde']: action='Buscar evidencia independiente de intercalación permeable.'
        priority='Pendiente de contexto' if not confirmed or family=='Desconocido' else ('Verificación especial' if family in ('Arcilloso / margoso','Mixto') else 'Contraste de campo')
        if a['borde']: priority='Ampliación de perfil'
        out.append({'prioridad_contextual':priority,'id':a['id'],'estacion':a['estacion'],'indice_geofisico':a['indice_geofisico'],'hipotesis':hyp,'alternativa_riesgo':risk,'accion':action,'profundidad_nominal_m':a.get('intervalo_nominal_m')})
    return out
