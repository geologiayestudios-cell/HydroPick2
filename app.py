import hashlib,hmac,json,os
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from hydropick.geophysics import read_pqwt,analyze,depth_intervals
from hydropick.geology import query_geode,suggest_family,interpret,SOURCES,RULES,REGIONAL
from hydropick.ai import run_ai

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

st.title('HydroPick V2 · España')
st.caption('GeoAqua | Interpretación geoeléctrica contextualizada · Piloto Ciudad Real · 2.0.0')
if not password: st.sidebar.warning('Modo sin autenticación. Configura APP_PASSWORD antes de publicar.')
else:
    if st.sidebar.button('Cerrar sesión'):
        st.session_state.clear(); st.rerun()

@st.cache_data(ttl=86400,show_spinner=False)
def lookup(lat,lon): return query_geode(lat,lon)

with st.sidebar:
    st.header('Proyecto')
    name=st.text_input('Nombre','Nuevo estudio')
    demo=st.checkbox('Usar CSV de ejemplo L67',False,help='El CSV de ejemplo no se atribuye a Ciudad Real.')
    upload=st.file_uploader('CSV PQWT',type='csv',disabled=demo)
    model=st.text_input('Modelo y firmware PQWT','No documentado')
    nominal=st.selectbox('Alcance nominal (m)',[100,150,200,300,400,500,600],index=1)
    known=st.checkbox('Conozco el espaciamiento real')
    spacing=st.number_input('Separación entre estaciones (m)',min_value=.1,max_value=100.,value=1.,step=.5,disabled=not known)
    resolution=st.number_input('Resolución mínima de amplitud',min_value=.000001,value=.001,format='%.6f',help='Parámetro experimental, no certificación del instrumento.')
    threshold=st.slider('Sensibilidad del detector (umbral robusto)',.5,3.,1.5,.1)
    st.caption('Menor umbral = más candidatos. No es probabilidad de éxito.')
    st.divider()
    georef=st.checkbox('Dispongo de coordenadas del estudio')
    lat=st.number_input('Latitud WGS84',value=38.9861,min_value=-90.,max_value=90.,format='%.6f',disabled=not georef)
    lon=st.number_input('Longitud WGS84',value=-3.9273,min_value=-180.,max_value=180.,format='%.6f',disabled=not georef)
    if demo: st.caption('No hay asociación demostrada entre L67 y estas coordenadas.')
    scale_file=st.file_uploader('Escala canal–profundidad documentada (opcional)',type='csv',help='Columnas canal,profundidad_m. No se genera una escala ficticia.')
    scale_source=st.text_input('Referencia de la escala',disabled=scale_file is None)

if demo: raw=(Path(__file__).parent/'examples'/'150M_L67.csv').read_bytes()
elif upload: raw=upload.getvalue()
else:
    st.info('Carga un CSV PQWT o activa el ejemplo L67. La consulta geológica se habilita con coordenadas confirmadas.')
    st.stop()
if len(raw)>20_000_000: st.error('Archivo demasiado grande (máximo 20 MB).');st.stop()
try:
    df,cols=read_pqwt(raw)
except Exception as e: st.error(f'CSV no válido: {e}');st.stop()
line=st.sidebar.selectbox('Línea del CSV',list(df.L.unique()))
try:
    result=analyze(df[df.L==line],cols,spacing if known else None,resolution,threshold)
except Exception as e: st.error(f'No se puede analizar: {e}');st.stop()
scale=None
if scale_file:
    try:
        if not scale_source.strip(): raise ValueError('Indica la referencia de la escala.')
        scale=depth_intervals(result['anomalies'],pd.read_csv(scale_file),cols,nominal)
    except Exception as e: st.sidebar.error(str(e))

project_id=hashlib.sha256(raw).hexdigest()[:12]
coord_key=f'{lat:.6f},{lon:.6f}' if georef else 'none'
if st.session_state.get('geo_key')!=coord_key:
    st.session_state.geo_key=coord_key; st.session_state.geo=None
geo=st.session_state.get('geo')

c1,c2,c3,c4=st.columns(4)
c1.metric('Estaciones',len(result['stations']));c2.metric('Canales informativos',f"{sum(result['valid'])}/{len(cols)}")
c3.metric('Candidatos',len(result['anomalies']));c4.metric('Datos numéricos',f"{result['coverage']:.0%}")
if result['gaps']: st.warning('Hay saltos en estaciones o canales; se limita la conectividad de regiones.')
if scale is None: st.warning('Sin escala de profundidad documentada: las gráficas y objetivos se expresan en canales. El alcance nominal no valida profundidades.')
if not known: st.info('Sin espaciamiento: el eje horizontal representa posición relativa en estaciones, no metros.')

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

x=result['x']; y=scale if scale is not None else np.arange(1,len(cols)+1); xlabel='Distancia (m)' if known else 'Estaciones desde el inicio'; ylabel='Profundidad nominal aportada (m)' if scale is not None else 'Canal (orden CSV)'

def heat(matrix,title,colors='Viridis',div=False,overlay=False):
    fig=go.Figure(go.Heatmap(x=x,y=y,z=matrix.T,colorscale=colors,zmid=0 if div else None,customdata=np.tile(np.array(cols)[:,None],(1,len(x))),hovertemplate='Posición %{x}<br>Canal %{customdata}<br>Valor %{z:.4f}<extra></extra>',colorbar={'title':'Valor'}))
    if overlay:
        for a in result['anomalies']:
            points=a['celdas']; fig.add_trace(go.Scatter(x=[x[i] for i,j in points],y=[y[j] for i,j in points],mode='markers',marker={'symbol':'square-open','size':8,'color':'white'},name=a['id'],hovertemplate=a['id']+'<extra></extra>'))
    fig.update_layout(title=title,xaxis_title=xlabel,yaxis_title=ylabel,height=460,margin=dict(l=10,r=10,t=50,b=20)); fig.update_yaxes(autorange='reversed');return fig

with gp_tab:
    st.subheader('Control de calidad y anomalías')
    with st.expander('QA/QC por canal',expanded=True): st.dataframe(pd.DataFrame(result['qc']),hide_index=True,use_container_width=True)
    graph_mode=st.radio('Representación',['Datos originales','Normalización robusta','Residual de tendencia','Contraste local','Consenso de detección'],horizontal=True)
    mats={'Datos originales':('raw','Viridis',False),'Normalización robusta':('z','RdBu_r',True),'Residual de tendencia':('trend','RdBu_r',True),'Contraste local':('local','RdBu_r',True),'Consenso de detección':('votes','Blues',False)}
    mat,color,div=mats[graph_mode]; st.plotly_chart(heat(result[mat],graph_mode,color,div,graph_mode=='Consenso de detección'),use_container_width=True)
    st.caption('Representación de celdas medidas, sin interpolación ni inversión. Las celdas blancas delinean detecciones.')
    fig=go.Figure()
    for j,c in enumerate(cols):
        if result['valid'][j]: fig.add_trace(go.Scatter(x=x,y=result['raw'][:,j],mode='lines+markers',name=c))
    fig.update_layout(title='Curvas originales de canales informativos',xaxis_title=xlabel,yaxis_title='Amplitud exportada (unidad por confirmar)',height=380)
    st.plotly_chart(fig,use_container_width=True)
    station=st.selectbox('Estación para perfil individual',result['stations'].tolist()); i=list(result['stations']).index(station)
    p=go.Figure(go.Scatter(x=result['raw'][i],y=y,mode='lines+markers',customdata=cols,hovertemplate='%{customdata}: %{x}<extra></extra>'));p.update_yaxes(autorange='reversed');p.update_layout(title=f'Perfil N{station}',xaxis_title='Amplitud exportada',yaxis_title=ylabel,height=400);st.plotly_chart(p,use_container_width=True)
    if not result['anomalies']:st.info('No hay candidatos que superen los criterios actuales. No se fuerza una selección.')
    else: st.dataframe(pd.DataFrame([{k:v for k,v in a.items() if k not in ('celdas','canales_detectados')} for a in result['anomalies']]),hide_index=True,use_container_width=True)

interpretation=interpret(result['anomalies'],family,confirmed,geo)
payload={'version':'2.0.0','proyecto':name,'hash_csv':project_id,'linea':str(line),'modelo_equipo':model,'alcance_nominal_m':nominal,'espaciado_m':spacing if known else None,'coordenadas_referencia':{'lat':lat,'lon':lon} if georef else None,'escala_fuente':scale_source if scale is not None else None,'demo_csv':demo,'geologia_consulta':geo,'modelo_conceptual':family,'modelo_confirmado':confirmed,'notas_tecnico':notes,'qc':result['qc'],'parametros':{'umbral':threshold,'resolucion':resolution},'anomalias':result['anomalies'],'interpretacion_reglas':interpretation,'limitacion':'Análisis cualitativo; índice geofísico experimental, no probabilidad; no hay coordenadas de estaciones ni inversión de resistividad.'}
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
            st.write('**Intervalo nominal:**',a['profundidad_nominal_m'] if a['profundidad_nominal_m'] is not None else 'No determinado')
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
    st.download_button('Descargar candidatos CSV',pd.DataFrame(interpretation).to_csv(index=False).encode('utf-8-sig'),f'HydroPick_{project_id}_L{line}_objetivos.csv','text/csv')
    md=f'# HydroPick V2 · {name}\n\nLínea: {line}\n\nModelo conceptual: {family} (validado por técnico: {confirmed})\n\n{payload["limitacion"]}\n\n'
    if demo:md+='**CSV de demostración no asociado al emplazamiento.**\n\n'
    for a in interpretation:md+=f'## {a["id"]} — N{a["estacion"]}\n\nHipótesis: {a["hipotesis"]}\n\nRiesgo: {a["alternativa_riesgo"]}\n\nAcción: {a["accion"]}\n\nIntervalo nominal: {a["profundidad_nominal_m"] or "No determinado"}\n\n'
    if st.session_state.get('ai_result'):md+='## Borrador IA\n\n'+st.session_state.ai_result['texto']+'\n\nReferencias API:\n'+json.dumps(st.session_state.ai_result['referencias'],ensure_ascii=False)
    md+='\n\n## Fuentes de referencia (no todas consultadas)\n'+'\n'.join(f'- {k}: {v}' for k,v in SOURCES.items())
    st.download_button('Descargar nota técnica Markdown',md.encode('utf-8'),f'HydroPick_{project_id}_L{line}.md','text/markdown')
    st.caption('No se almacena información permanentemente en esta versión. Descarga los resultados antes de cerrar la sesión.')
