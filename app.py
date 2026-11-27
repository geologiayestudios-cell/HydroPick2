import hashlib,hmac,json,os,re
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from hydropick.geophysics import read_pqwt,analyze,depth_intervals
from hydropick.geology import query_geode,suggest_family,interpret,SOURCES,RULES,REGIONAL
from hydropick.ai import run_ai
from hydropick.scales import PROFILES,detect_mode,automatic_mapping,physical_mapping
from hydropick.visuals import PQWT_SCALE,dense_section
from hydropick.comparison import load_image,compare
from PIL import Image,ImageDraw

st.set_page_config(page_title='HydroPick | GeoAqua',layout='wide',page_icon='💧')

def secret(name,default=''):
    try: return st.secrets.get(name,os.environ.get(name,default))
    except Exception: return os.environ.get(name,default)

password=secret('APP_PASSWORD')
if password and not st.session_state.get('authenticated'):
    st.title('HydroPick · Acceso técnico')
    with st.form('login'):
        attempt=st.text_input('Contraseña',type='password'); submit=st.form_submit_button('Acceder')
    if submit:
        if hmac.compare_digest(attempt,password): st.session_state.authenticated=True; st.rerun()
        else: st.error('Credenciales incorrectas.')
    st.stop()

st.title('HydroPick V2.1 · España')
st.caption('GeoAqua | Interpretación geoeléctrica contextualizada · Piloto Ciudad Real · 2.1.0')
if not password: st.sidebar.warning('Modo sin autenticación. Configura APP_PASSWORD antes de publicar.')
else:
    if st.sidebar.button('Cerrar sesión'):
        st.session_state.clear(); st.rerun()

@st.cache_data(ttl=86400,show_spinner=False)
def lookup(lat,lon): return query_geode(lat,lon)

with st.sidebar:
    st.header('Proyecto')
    name=st.text_input('Nombre','Nuevo estudio')
    demo=st.checkbox('Usar CSV de ejemplo',False,help='Los ejemplos no se atribuyen a las coordenadas de Ciudad Real.')
    example=st.selectbox('Ejemplo',['150M_L67.csv','300M_L171.csv','150M_L1.csv','100M_L15.csv'],disabled=not demo)
    upload=st.file_uploader('CSV PQWT',type='csv',disabled=demo)
    model=st.text_input('Modelo y firmware PQWT','No documentado')
    known=st.checkbox('Conozco el espaciamiento real')
    spacing=st.number_input('Separación entre estaciones (m)',min_value=.1,max_value=100.,value=1.,step=.5,disabled=not known)
    resolution=st.number_input('Resolución mínima de amplitud',min_value=.000001,value=.001,format='%.6f',help='Parámetro experimental, no certificación del instrumento.')
    threshold=st.slider('Sensibilidad del detector (umbral robusto)',.5,3.,1.5,.1)
    st.caption('Menor umbral = más candidatos. No es probabilidad de éxito.')
    st.divider()
    georef=st.checkbox('Dispongo de coordenadas del estudio')
    lat=st.number_input('Latitud WGS84',value=38.9861,min_value=-90.,max_value=90.,format='%.6f',disabled=not georef)
    lon=st.number_input('Longitud WGS84',value=-3.9273,min_value=-180.,max_value=180.,format='%.6f',disabled=not georef)
    if demo: st.caption('No hay asociación demostrada entre el CSV de ejemplo y estas coordenadas.')

if demo: raw=(Path(__file__).parent/'examples'/example).read_bytes()
elif upload: raw=upload.getvalue()
else:
    st.info('Carga un CSV PQWT o activa un ejemplo. La consulta geológica se habilita con coordenadas confirmadas.')
    st.stop()
if len(raw)>20_000_000: st.error('Archivo demasiado grande (máximo 20 MB).');st.stop()
try:
    df,cols=read_pqwt(raw)
except Exception as e: st.error(f'CSV no válido: {e}');st.stop()
line=st.sidebar.selectbox('Línea del CSV',list(df.L.unique()))
file_id=hashlib.sha256(raw).hexdigest()[:12]
with st.sidebar:
    st.divider(); st.header('Escala de profundidad')
    detected=detect_mode(cols)
    st.caption(f'{len(cols)} canales en el CSV · '+(f'modo compatible: {detected} m' if detected else 'modo no reconocido automáticamente'))
    modes=[100,150,200,300,400,500,600]
    nominal=st.selectbox('Alcance nominal (m)',modes,index=modes.index(detected or 150),key=f'nominal_{file_id}')
    scale_method=st.radio('Método de asignación',['Nominal automática PQWT','Personalizada / calibrada','Física contextualizada','Solo canales'],key=f'scale_method_{file_id}')
    scale_file=None; scale_source=''; freq_file=None; rho=None; correction=None
    if scale_method=='Personalizada / calibrada':
        scale_file=st.file_uploader('CSV de escala',type='csv',help='Columnas canal,profundidad_m; todos los canales.')
        scale_source=st.text_input('Referencia de la escala')
    elif scale_method=='Física contextualizada':
        freq_file=st.file_uploader('CSV de frecuencias físicas documentadas',type='csv',help='Columnas canal,frecuencia_hz. No introducir números de canal como Hz.')
        scale_source=st.text_input('Referencia de frecuencias y resistividad')
        rho=st.number_input('Resistividad asumida (Ω·m)',min_value=0.01,value=100.,step=10.)
        correction=st.slider('Factor empírico k',0.3,0.5,0.4,0.01)
        st.caption('Escala de penetración teórica; no es inversión ni profundidad comprobada.')
try:
    result=analyze(df[df.L==line],cols,spacing if known else None,resolution,threshold)
except Exception as e: st.error(f'No se puede analizar: {e}');st.stop()
if not known:
    for a in result['anomalies']: a['distancia']=None
scale=None; scale_status='Sin escala aplicada'; scale_meta=None
try:
    mapping=None
    if scale_method=='Nominal automática PQWT':
        mapping,scale_status=automatic_mapping(cols,nominal)
        scale_source='Distribución lineal 0–Dmax, N−1 intervalos · reconstrucción experimental HydroPick'
    elif scale_method=='Personalizada / calibrada' and scale_file:
        if not scale_source.strip(): raise ValueError('Indica la referencia de la escala.')
        mapping=pd.read_csv(scale_file);scale_status='Aportada por el técnico; procedencia no verificada por HydroPick'
    elif scale_method=='Física contextualizada' and freq_file:
        if not scale_source.strip(): raise ValueError('Indica la referencia de las frecuencias y resistividad.')
        mapping=physical_mapping(cols,pd.read_csv(freq_file),rho,correction,nominal)
        scale_status='Penetración teórica condicionada a resistividad y factor asumidos'
    if mapping is not None:
        scale=depth_intervals(result['anomalies'],mapping,cols,nominal)
        scale_meta={'metodo':scale_method,'estado':scale_status,'referencia':scale_source,'canales':dict(zip(cols,scale.tolist())), 'resistividad_asumida_ohm_m':rho,'factor_k':correction}
        if scale_method=='Física contextualizada':
            scale_meta['frecuencias_hz']=pd.read_csv(freq_file).set_index('canal').frecuencia_hz.reindex(cols).astype(float).to_dict()
        st.sidebar.info(scale_status)
except Exception as e:
    scale=None; scale_meta=None; scale_status='Sin escala aplicada'
    for a in result['anomalies']: a.pop('intervalo_nominal_m',None)
    st.sidebar.error(str(e))
project_id=hashlib.sha256(raw).hexdigest()[:12]
coord_key=f'{lat:.6f},{lon:.6f}' if georef else 'none'
if st.session_state.get('geo_key')!=coord_key:
    st.session_state.geo_key=coord_key; st.session_state.geo=None
geo=st.session_state.get('geo')

c1,c2,c3,c4=st.columns(4)
c1.metric('Estaciones',len(result['stations']));c2.metric('Canales informativos',f"{sum(result['valid'])}/{len(cols)}")
c3.metric('Candidatos',len(result['anomalies']));c4.metric('Datos numéricos',f"{result['coverage']:.0%}")
if result['gaps']: st.warning('Hay saltos en estaciones o canales; se limita la conectividad de regiones.')
if scale is None: st.warning('Sin escala aplicada: las gráficas y objetivos se expresan en canales.')
else: st.caption(f'Escala: {scale_status}. No representa profundidad comprobada de acuífero.')
if not known: st.info('Sin espaciamiento: el eje horizontal representa el número de estación, no metros.')

geo_tab,gp_tab,int_tab,report_tab=st.tabs(['01 · Geología','02 · Geofísica','03 · Interpretación','04 · Exportar'])
with geo_tab:
    st.subheader('Consulta geológica del punto de referencia')
    if georef:
        st.map(pd.DataFrame({'lat':[lat],'lon':[lon]}),zoom=10)
        if not (27<=lat<=44.5 and -19<=lon<=5): st.warning('Coordenadas fuera del ámbito aproximado español. GEODE puede no cubrir el punto.')
        if st.button('Consultar IGME · GEODE 1:50.000',type='primary'):
            with st.spinner('Consultando recintos geológicos oficiales…'):
                st.session_state.geo=lookup(lat,lon); geo=st.session_state.geo
    else: st.info('Activa e introduce las coordenadas reales para consultar el IGME.')
    if geo:
        st.write('Estado de consulta:',geo['estado'])
        for err in geo['errores']: st.warning(err)
        if not geo['registros']: st.warning('No se obtuvo una unidad local. Utiliza fuentes manuales; no se asignará una litología automática.')
        for rec in geo['registros']:
            st.markdown(f"**Capa {rec['capa']}** · {rec['escala']}")
            st.json(rec['atributos'],expanded=False)
        st.caption('Cartografía superficial; no demuestra la columna litológica ni la unidad a profundidad.')
    suggestion=suggest_family(geo['registros']) if geo else 'Desconocido'
    st.write('Familia sugerida por palabras clave:',suggestion)
    family=st.selectbox('Modelo geológico conceptual (selección del técnico)',list(RULES),key=f'family_{coord_key}_{project_id}_{suggestion}',index=list(RULES).index(suggestion))
    notes=st.text_area('Evidencia adicional: formación, pozos, niveles, litología, fuente y observaciones de campo',key=f'notes_{coord_key}_{project_id}')
    confirmed=st.checkbox('He revisado la evidencia y confirmo este modelo conceptual',key=f'confirm_{coord_key}_{project_id}_{family}_{suggestion}',disabled=family=='Desconocido')
    with st.expander('Contextos regionales de Ciudad Real (orientativos, no asignados automáticamente)'):
        for region,text in REGIONAL.items(): st.markdown(f'**{region}.** {text}')
    with st.expander('Fuentes españolas para contraste documental'):
        for label,url in SOURCES.items(): st.markdown(f'[{label}]({url})')
        st.caption('Comprobar demarcación hidrográfica y régimen de captación aplicable; la app no verifica permisos.')

x=result['x'] if known else result['stations']; y=scale if scale is not None else np.array([int(re.search(r'\d+',c).group()) for c in cols]); xlabel='Distancia (m)' if known else 'Estación N'; ylabel=('Escala teórica de penetración (m)' if scale_method=='Física contextualizada' else 'Profundidad nominal estimada (m)') if scale is not None else 'Canal PQWT'
channel_ids=np.array([int(re.search(r'\d+',c).group()) for c in cols])
representations={
    '01 · Original':('raw',PQWT_SCALE,False,'Amplitud exportada'),
    '02 · Procesada experimental':('log',PQWT_SCALE,False,'log₁₀(1 + |V|) con signo'),
    '03 · Contraste relativo':('z','RdBu_r',True,'Desviación robusta por canal'),
    '04 · Anomalías locales':('local','RdBu_r',True,'Residual local / escala robusta'),
    'Residual de tendencia':('trend','RdBu_r',True,'Residual robusto'),
    'Contraste fraccional':('relative','RdBu_r',True,'(V − mediana)/|mediana|'),
    'Consenso de detección':('votes','Blues',False,'Familias coincidentes (0–3)')}

def heat(matrix,title,colors=PQWT_SCALE,div=False,overlay=False,smooth=False,unit='Valor',grid=False):
    if smooth:
        xx,yy,zz=dense_section(x,y,matrix,result['stations'],channel_ids)
        trace=go.Heatmap(x=xx,y=yy,z=zz,colorscale=colors,zmid=0 if div else None,colorbar={'title':unit},hovertemplate='X %{x:.2f}<br>Y %{y:.2f}<br>Interpolado %{z:.4f}<extra></extra>',connectgaps=False)
    else:
        trace=go.Heatmap(x=x,y=y,z=matrix.T,colorscale=colors,zmid=0 if div else None,customdata=np.tile(np.array(cols)[:,None],(1,len(x))),hovertemplate='Posición %{x}<br>Canal %{customdata}<br>Valor %{z:.4f}<extra></extra>',colorbar={'title':unit},connectgaps=False)
    if overlay and title=='Consenso de detección': trace.update(zmin=0,zmax=3)
    elif not div and np.isfinite(matrix).any() and np.nanmin(matrix)>=0: trace.update(zmin=0)
    fig=go.Figure(trace)
    if smooth and grid:
        for v in x: fig.add_vline(x=v,line_width=.5,line_color='rgba(30,30,30,.35)')
        for v in y: fig.add_hline(y=v,line_width=.5,line_color='rgba(30,30,30,.35)')
        if np.isfinite(zz).any() and np.nanmax(zz)>np.nanmin(zz):
            fig.add_trace(go.Contour(x=xx,y=yy,z=zz,ncontours=17,contours={'coloring':'none'},line={'width':.5,'color':'rgba(25,25,25,.55)'},showscale=False,hoverinfo='skip',connectgaps=False))
    if overlay:
        for a in result['anomalies']:
            points=a['celdas']; fig.add_trace(go.Scatter(x=[x[i] for i,j in points],y=[y[j] for i,j in points],mode='markers',marker={'symbol':'square-open','size':7,'color':'white','line':{'width':1.2}},name=a['id'],hovertemplate=a['id']+'<extra></extra>'))
    fig.update_layout(title=title,xaxis_title=xlabel,yaxis_title=ylabel,height=425,margin=dict(l=10,r=10,t=50,b=20)); fig.update_yaxes(autorange='reversed',range=[float(max(y)),float(min(y))] if smooth else None);return fig

comparison_results={}
with gp_tab:
    st.subheader('Control de calidad y anomalías')
    with st.expander('QA/QC por canal',expanded=False): st.dataframe(pd.DataFrame(result['qc']),hide_index=True,use_container_width=True)
    compression=st.selectbox('Transformación de la pseudosección procesada',['Log₁₀(1+|V|) con signo','Log₁₀(V), solo positivos','Raíz cuadrada con signo'],help='Cambia solo la representación visual; el detector conserva su compresión logarítmica con signo.')
    if compression=='Log₁₀(V), solo positivos':
        result['display_log']=np.log10(np.where(result['raw']>0,result['raw'],np.nan))
        if np.any(result['raw']<=0): st.info('Log₁₀(V): valores cero y negativos quedan sin representación en esta vista.')
    elif compression=='Raíz cuadrada con signo': result['display_log']=np.sign(result['raw'])*np.sqrt(np.abs(result['raw']))
    else: result['display_log']=result['log']
    representations['02 · Procesada experimental']=('display_log',PQWT_SCALE,False,compression)
    view=st.radio('Visualización',['Comparar cuatro pseudosecciones','Vista individual'],horizontal=True)
    smooth=st.checkbox('Interpolación lineal para visualización',True,help='No se usa para detectar anomalías; no rellena huecos ni extrapola.')
    grid=st.checkbox('Malla y contornos estilo PQWT',False,disabled=not smooth)
    overlay=st.checkbox('Mostrar celdas de candidatos',False)
    if view=='Comparar cuatro pseudosecciones':
        selected=list(representations)[:4]
        for start in (0,2):
            panels=st.columns(2)
            for panel,label in zip(panels,selected[start:start+2]):
                mat,color,div,unit=representations[label]
                panel.plotly_chart(heat(result[mat],label,color,div,overlay,smooth,unit,grid),use_container_width=True,key='multi_'+mat)
    else:
        label=st.selectbox('Representación',list(representations)); mat,color,div,unit=representations[label]
        st.plotly_chart(heat(result[mat],label,color,div,overlay or mat=='votes',smooth and mat!='votes',unit,grid),use_container_width=True,key='single_'+mat)
    st.caption('Procesada experimental: transformación seleccionada, no algoritmo oficial. Azul = amplitud baja o residual negativo, no agua confirmada. El detector trabaja sobre datos medidos; las superficies interpoladas son visuales.')
    fig=go.Figure()
    for j,c in enumerate(cols):
        if result['valid'][j]: fig.add_trace(go.Scatter(x=x,y=result['raw'][:,j],mode='lines+markers',name=c))
    fig.update_layout(title='Curvas originales de canales informativos',xaxis_title=xlabel,yaxis_title='Amplitud exportada (unidad por confirmar)',height=380)
    st.plotly_chart(fig,use_container_width=True)
    station=st.selectbox('Estación para perfil individual',result['stations'].tolist()); i=list(result['stations']).index(station)
    p=go.Figure(go.Scatter(x=result['raw'][i],y=y,mode='lines+markers',customdata=cols,hovertemplate='%{customdata}: %{x}<extra></extra>'));p.update_yaxes(autorange='reversed');p.update_layout(title=f'Perfil N{station}',xaxis_title='Amplitud exportada',yaxis_title=ylabel,height=400);st.plotly_chart(p,use_container_width=True)
    st.subheader('Consenso y estabilidad')
    st.caption('Se exigen 2 de 3 familias por celda: contraste global (original/log agrupados), residual de tendencia y contraste local. Se requieren al menos 3 canales por región. La persistencia entre umbrales es sensibilidad algorítmica, no probabilidad ni repetibilidad de campo.')
    if not result['anomalies']:st.info('No hay candidatos que superen los criterios actuales. No se fuerza una selección.')
    else:
        st.dataframe(pd.DataFrame([{k:v for k,v in a.items() if k not in ('celdas','canales_detectados','consenso_por_metodo_pct')} for a in result['anomalies']]),hide_index=True,use_container_width=True)
        st.markdown('**Cobertura de cada método dentro de la región candidata (%)**')
        st.dataframe(pd.DataFrame([{'Objetivo':a['id'],'Estación':a['estacion'],**a['consenso_por_metodo_pct'],'Persistencia umbral':a['persistencia_umbral_pct']} for a in result['anomalies']]),hide_index=True,use_container_width=True)
    with st.expander('Comparar con gráficas PQWT del fabricante (experimental)'):
        st.caption('Carga imágenes de la misma línea. Ajusta manualmente el rectángulo de la pseudosección y la barra cromática vertical. No se envían las imágenes a la IA; solo métricas derivadas si autorizas el envío.')
        use_examples=st.checkbox('Usar las dos imágenes de ejemplo L171',disabled=not (demo and example=='300M_L171.csv'),key=f'example_images_{file_id}')
        for kind,filename in [('Original','Grafica_original_L171.jpeg'),('Procesada','Grafica_procesada_L171.jpeg')]:
            pic=st.file_uploader(f'Gráfica {kind}',type=['png','jpg','jpeg'],key=f'image_{file_id}_{line}_{kind}',disabled=use_examples and demo and example=='300M_L171.csv')
            if use_examples and demo and example=='300M_L171.csv': image_bytes=(Path(__file__).parent/'examples'/filename).read_bytes()
            elif pic: image_bytes=pic.getvalue()
            else: continue
            try:
                image=load_image(image_bytes); h,w=image.shape[:2]; k=f'{file_id}_{line}_{kind}_{hashlib.sha256(image_bytes).hexdigest()[:12]}'
                st.markdown(f'**Gráfica {kind} — {w} × {h} px**')
                a,b,c,d=st.columns(4)
                left=a.number_input('Izquierda px',0,w-1,int(w*.057),key=k+'l');right=b.number_input('Derecha px',0,w-1,int(w*.914),key=k+'r')
                top=c.number_input('Arriba px',0,h-1,int(h*.043),key=k+'t');bottom=d.number_input('Abajo px',0,h-1,int(h*.917),key=k+'b')
                a,b,c,d=st.columns(4)
                legend_x=a.number_input('Leyenda X px',0,w-1,int(w*.953),key=k+'lx');legend_top=b.number_input('Leyenda inicio px',0,h-1,int(h*.043),key=k+'lt');legend_bottom=c.number_input('Leyenda fin px',0,h-1,int(h*.78),key=k+'lb');bins=d.number_input('Clases de color',5,50,17,key=k+'bins')
                preview=Image.fromarray(image);draw=ImageDraw.Draw(preview)
                if left<right and top<bottom: draw.rectangle((left,top,right,bottom),outline='#ff00ff',width=2)
                if legend_top<legend_bottom: draw.line((legend_x,legend_top,legend_x,legend_bottom),fill='#ff00ff',width=2)
                st.image(preview,caption='Comprueba el rectángulo y la línea rosa sobre la leyenda (alto arriba, bajo abajo).',width=min(w,700))
                if st.checkbox(f'Comparar {kind} con las representaciones de HydroPick',key=k+'run'):
                    if scale is None: st.warning('Aplica una escala de profundidad para comparar con imágenes en metros.');continue
                    if scale_method=='Física contextualizada' or not np.isclose(min(y),0) or not np.isclose(max(y),nominal): st.warning('La comparación requiere una escala que cubra de 0 al alcance nominal de la imagen.');continue
                    mats={'Original':result['raw'],'Log₁₀(1+|V|) con signo':result['log'],'Log₁₀(V), solo si V>0':np.log10(np.where(result['raw']>0,result['raw'],np.nan)),'Raíz cuadrada con signo':np.sign(result['raw'])*np.sqrt(np.abs(result['raw'])),'Contraste relativo':result['z'],'Anomalías locales':result['local']}
                    rows,palette,_,_=compare(image,(left,top,right,bottom),(legend_x,legend_top,legend_bottom),bins,x,y,mats,result['stations'],channel_ids)
                    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
                    swatch=np.repeat(palette[None,:,:],24,axis=0).astype(np.uint8);swatch=np.repeat(swatch,24,axis=1);st.image(swatch,caption='Paleta muestreada: alto → bajo',width=min(600,bins*24))
                    comparison_results[kind]={'sha256':hashlib.sha256(image_bytes).hexdigest(),'recorte_px':[left,top,right,bottom],'leyenda_px':[legend_x,legend_top,legend_bottom],'clases':bins,'metricas':rows}
                    st.caption('Correlación aproximada con clases cromáticas, no con valores físicos; depende del recorte, leyenda, interpolación y coincidencia de línea. No modifica el detector.')
            except Exception as e: st.warning(f'No se pudo comparar la gráfica {kind}: {e}')

interpretation=interpret(result['anomalies'],family,confirmed,geo)
payload={'version':'2.1.0','proyecto':name,'hash_csv':project_id,'linea':str(line),'modelo_equipo':model,'alcance_nominal_m':nominal,'espaciado_m':spacing if known else None,'coordenadas_referencia':{'lat':lat,'lon':lon} if georef else None,'escala_fuente':scale_source if scale is not None else None,'escala':scale_meta,'comparacion_imagenes':comparison_results,'procesamiento':{'compresion_detector':'sign(V)*log10(1+abs(V))','compresion_visual':compression,'consenso':'2 de 3 familias, mínimo 3 canales por región','interpolacion':'solo visual'},'demo_csv':demo,'geologia_consulta':geo,'modelo_conceptual':family,'modelo_confirmado':confirmed,'notas_tecnico':notes,'qc':result['qc'],'parametros':{'umbral':threshold,'resolucion':resolution},'anomalias':result['anomalies'],'interpretacion_reglas':interpretation,'limitacion':'Análisis cualitativo; índice geofísico experimental, no probabilidad; escala de representación condicionada, no profundidad verificada; no hay coordenadas de estaciones ni inversión de resistividad.'}
fingerprint=hashlib.sha256(json.dumps(payload,default=str,sort_keys=True).encode()).hexdigest()
if st.session_state.get('ai_fingerprint')!=fingerprint: st.session_state.ai_result=None;st.session_state.ai_fingerprint=fingerprint
with int_tab:
    st.subheader('Interpretación contextual mediante reglas')
    if not confirmed:st.warning('Modelo no validado por el técnico. Las hipótesis son condicionales.')
    if demo:st.warning('CSV de ejemplo: no utilizar para recomendar perforación en las coordenadas introducidas.')
    for a in interpretation:
        with st.container(border=True):
            st.markdown(f"### {a['id']} · N{a['estacion']} | índice geofísico {a['indice_geofisico']}/100")
            st.write('**Prioridad contextual:**',a['prioridad_contextual']);st.write('**Hipótesis:**',a['hipotesis']);st.write('**Alternativa / riesgo:**',a['alternativa_riesgo']);st.write('**Acción:**',a['accion'])
            st.write('**Intervalo según escala de representación:**',a['profundidad_nominal_m'] if a['profundidad_nominal_m'] is not None else 'No determinado')
    st.divider();st.subheader('Asistencia de IA (opcional)')
    api_key=secret('OPENAI_API_KEY') or st.text_input('Clave API de OpenAI',type='password',key='key')
    ai_model=st.text_input('Modelo API',value=secret('OPENAI_MODEL','gpt-6.2-astra'))
    web=st.checkbox('Permitir investigación documental web',value=True)
    consent=st.checkbox('Autorizo enviar coordenadas, metadatos, notas y resultados derivados a OpenAI; puede generar costes.')
    if st.button('Generar interpretación asistida',disabled=not(api_key and consent)):
        with st.spinner('Consultando el modelo…'):
            try: st.session_state.ai_result=run_ai(api_key,ai_model,payload,web)
            except Exception as e: st.error(f'No se pudo generar la interpretación: {str(e)[:450]}')
    ai=st.session_state.get('ai_result')
    if ai:
        st.caption(f"Modelo: {ai['modelo']} · Estado: {ai['estado']} · Borrador sujeto a revisión")
        st.markdown(ai['texto']);
        if ai['referencias']:
            with st.expander('Referencias devueltas por la API'):
                for ref in ai['referencias']:st.write(ref.get('title','Fuente'),ref.get('url',''))
with report_tab:
    st.subheader('Exportación técnica')
    report=dict(payload,ia=st.session_state.get('ai_result'))
    st.download_button('Descargar paquete JSON',json.dumps(report,ensure_ascii=False,indent=2,default=str),f'HydroPick_{project_id}_L{line}.json','application/json')
    st.download_button('Descargar candidatos CSV',pd.DataFrame([{**a,**{k:v for k,v in b.items() if k not in ('celdas','canales_detectados')}} for a,b in zip(interpretation,result['anomalies'])]).to_csv(index=False).encode('utf-8-sig'),f'HydroPick_{project_id}_L{line}_objetivos.csv','text/csv')
    if scale is not None: st.download_button('Descargar escala aplicada CSV',pd.DataFrame({'canal':cols,'profundidad_m':scale}).to_csv(index=False).encode('utf-8'),f'HydroPick_{project_id}_escala.csv','text/csv')
    md=f'# HydroPick V2.1 · {name}\n\nLínea: {line}\n\nModelo conceptual: {family} (validado por técnico: {confirmed})\n\n{payload["limitacion"]}\n\n'
    md+=f'Escala: {scale_status}. Referencia: {scale_source if scale is not None else "No aplica"}\n\n'
    if demo:md+='**CSV de demostración no asociado al emplazamiento.**\n\n'
    for a in interpretation:md+=f'## {a["id"]} — N{a["estacion"]}\n\nHipótesis: {a["hipotesis"]}\n\nRiesgo: {a["alternativa_riesgo"]}\n\nAcción: {a["accion"]}\n\nIntervalo nominal: {a["profundidad_nominal_m"] or "No determinado"}\n\n'
    if st.session_state.get('ai_result'):md+='## Borrador IA\n\n'+st.session_state.ai_result['texto']+'\n\nReferencias API:\n'+json.dumps(st.session_state.ai_result['referencias'],ensure_ascii=False)
    md+='\n\n## Fuentes de referencia (no todas consultadas)\n'+'\n'.join(f'- {k}: {v}' for k,v in SOURCES.items())
    st.download_button('Descargar nota técnica Markdown',md.encode('utf-8'),f'HydroPick_{project_id}_L{line}.md','text/markdown')
    st.caption('No se almacena información permanentemente en esta versión. Descarga los resultados antes de cerrar la sesión.')
