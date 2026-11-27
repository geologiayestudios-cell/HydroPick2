import hashlib,hmac,json,os,re
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from hydropick.geophysics import read_pqwt,analyze,depth_intervals
from hydropick.geology import query_geode,suggest_family,SOURCES,RULES,REGIONAL
from hydropick.ai import run_ai
from hydropick.decision import decide, DRILL, REPEAT, HOLD, NO
from hydropick.scales import PROFILES,detect_mode,automatic_mapping,physical_mapping
from hydropick.visuals import PQWT_SCALE,dense_section
from hydropick.comparison import load_image,compare
from PIL import Image,ImageDraw
from hydropick.reporting import interpretation_png,make_report,target_cards,SECTION,EMPTY,SCOPE

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

st.title('HydroPick · España')
st.caption('GeoAqua | Interpretación geofísica y selección de objetivos de perforación')
if password and st.sidebar.button('Cerrar sesión'):
    st.session_state.clear(); st.rerun()

@st.cache_data(ttl=86400,show_spinner=False,max_entries=256)
def lookup(lat,lon): return query_geode(lat,lon)

with st.sidebar:
    st.header('1 · Estudio')
    st.caption('Los CSV se procesan en el servidor; evita subir datos confidenciales sin autorización.')
    name=st.text_input('Nombre del estudio','Nuevo estudio')
    demo=st.checkbox('Explorar un ejemplo sintético',False)
    upload=st.file_uploader('Archivo PQWT (.csv)',type='csv',disabled=demo)
    st.header('2 · Ubicación')
    lat=st.number_input('Latitud WGS84',value=None,min_value=-90.,max_value=90.,format='%.6f',placeholder='38.980000',disabled=demo)
    lon=st.number_input('Longitud WGS84',value=None,min_value=-180.,max_value=180.,format='%.6f',placeholder='-3.930000',disabled=demo)
    georef=lat is not None and lon is not None and not demo
    if georef and not (27<=lat<=44.5 and -19<=lon<=5):
        georef=False; st.caption('Introduce coordenadas dentro del ámbito español.')
    spacing=st.number_input('Separación entre estaciones (m)',min_value=.1,max_value=100.,value=None,step=.5,placeholder='Opcional')
    known=spacing is not None
    advanced=st.toggle('Modo técnico',False)
    resolution=.001; threshold=1.5; model='No documentado'
    if advanced:
        with st.expander('Parámetros de adquisición y detector'):
            model=st.text_input('Modelo y firmware PQWT',model)
            resolution=st.number_input('Resolución mínima de amplitud',min_value=.000001,value=.001,format='%.6f')
            threshold=st.slider('Sensibilidad del detector',.5,3.,1.5,.1)

if demo:
    raw=(Path(__file__).parent/'examples'/'Demo_150m.csv').read_bytes()
    st.caption('Demostración sintética · sin emplazamiento real')
elif upload: raw=upload.getvalue()
else:
    st.markdown('### Comienza tu estudio')
    st.write('Carga el archivo CSV del equipo y añade las coordenadas del levantamiento. HydroPick identifica contrastes geoeléctricos, consulta la geología y propone objetivos de exploración.')
    st.stop()
if len(raw)>20_000_000: st.error('Archivo demasiado grande (máximo 20 MB).');st.stop()
try:
    df,cols=read_pqwt(raw)
    if len(df)>2000 or len(cols)>100: raise ValueError('Máximo 2.000 estaciones por archivo y 100 canales.')
except Exception as e: st.error(f'CSV no válido: {e}');st.stop()
line=st.sidebar.selectbox('Línea del CSV',list(df.L.unique()))
if len(df[df.L==line])<5:
    st.subheader('Repetir o ampliar mediciones')
    st.write('Registra al menos cinco estaciones para delimitar contrastes laterales.'); st.stop()
if len(df[df.L==line])>300:
    st.error('Analiza líneas de hasta 300 estaciones por separado.');st.stop()
file_id=hashlib.sha256(raw).hexdigest()[:12]
with st.sidebar:
    st.header('3 · Profundidad')
    detected=detect_mode(cols)
    modes=[100,150,200,300,400,500,600]
    nominal=st.selectbox('Alcance del equipo (m)',modes,index=modes.index(detected or 150),key=f'nominal_{file_id}')
    scale_method='Nominal automática PQWT'
    if advanced:
        scale_method=st.radio('Escala',['Nominal automática PQWT','Personalizada / calibrada','Física contextualizada','Solo canales'],key=f'scale_method_{file_id}')
    scale_file=None; scale_source=''; freq_file=None; rho=None; correction=None
    if scale_method=='Personalizada / calibrada':
        scale_file=st.file_uploader('CSV de escala',type='csv',help='Columnas canal,profundidad_m')
        scale_source=st.text_input('Referencia de la escala')
    elif scale_method=='Física contextualizada':
        freq_file=st.file_uploader('CSV de frecuencias físicas documentadas',type='csv',help='Columnas canal,frecuencia_hz')
        scale_source=st.text_input('Referencia de frecuencias y resistividad')
        rho=st.number_input('Resistividad asumida (Ω·m)',min_value=.01,value=100.,step=10.)
        correction=st.slider('Factor empírico k',.3,.5,.4,.01)
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

except Exception as e:
    scale=None; scale_meta=None; scale_status='Sin escala aplicada'
    for a in result['anomalies']: a.pop('intervalo_nominal_m',None)
    st.sidebar.caption("Escala pendiente: verifica el alcance o configura una escala en Modo técnico.")
project_id=hashlib.sha256(raw).hexdigest()[:12]
coord_key=f'{lat:.6f},{lon:.6f}' if georef else 'none'
if st.session_state.get('geo_key')!=coord_key:
    st.session_state.geo_key=coord_key; st.session_state.geo=None
geo=st.session_state.get('geo')

geo_tab,gp_tab,int_tab,report_tab=st.tabs(['01 · Contexto geológico','02 · Geofísica','03 · Interpretación','04 · Informe'])
with geo_tab:
    st.subheader('Geología del emplazamiento')
    if georef:
        st.map(pd.DataFrame({'lat':[lat],'lon':[lon]}),zoom=10)
        if st.button('Consultar geología IGME',type='primary'):
            with st.spinner('Consultando cartografía oficial…'):
                st.session_state.geo=lookup(lat,lon); geo=st.session_state.geo
    else: st.write('Introduce las coordenadas del levantamiento para consultar la cartografía.')
    records=geo['registros'] if geo else []
    descriptions=[]
    for r in records:
        attrs=r['atributos']; desc=str(attrs.get('DESC_UNIT') or '').strip()
        if not desc: continue
        ages=list(dict.fromkeys(str(attrs.get(k)).strip() for k in ('NAME_EDA1','NAME_EDA2') if attrs.get(k)))
        text=desc+(' · Edad: '+' – '.join(ages) if ages else '')
        if text not in descriptions: descriptions.append(text)
    if descriptions:
        for d in descriptions: st.write(d)
        st.caption('Fuente: IGME-CSIC · GEODE 1:50.000 · unidad cartografiada en superficie')
    elif geo: st.write('No se obtuvo una descripción geológica del punto. Reintenta o añade una fuente local.')
    suggestion=suggest_family(records)
    manual=st.checkbox('Ajustar el modelo con información geológica propia',value=False,key=f'manual_{coord_key}_{project_id}')
    family=suggestion; notes=''; confirmed=False
    if manual:
        family=st.selectbox('Modelo hidrogeológico',list(RULES),index=list(RULES).index(suggestion),key=f'family_{coord_key}_{project_id}_{suggestion}')
        notes=st.text_area('Fuente y evidencia local (cartografía, pozos, registros litológicos)',key=f'notes_{coord_key}_{project_id}')
        confirmed=st.checkbox('La evidencia indicada corresponde al emplazamiento',key=f'confirm_{coord_key}_{project_id}_{family}_{suggestion}',disabled=not notes.strip() or family=='Desconocido')
    elif suggestion!='Desconocido':
        st.markdown(f'**Modelo hidrogeológico interpretado:** {suggestion}')
    context_ok=bool((descriptions and suggestion==family and family!='Desconocido' and not manual) or (manual and confirmed and notes.strip()))
    horizon=None; horizon_source=''
    with st.expander('Antecedentes de pozos (opcional)'):
        has_horizon=st.checkbox('Dispongo de un intervalo productivo documentado y comparable',key=f'horizon_{coord_key}_{project_id}')
        if has_horizon:
            a,b=st.columns(2)
            lo=a.number_input('Inicio del intervalo (m)',min_value=0.,value=None,key=f'horizon_lo_{coord_key}_{project_id}')
            hi=b.number_input('Fin del intervalo (m)',min_value=0.,value=None,key=f'horizon_hi_{coord_key}_{project_id}')
            horizon_source=st.text_input('Referencia del pozo y evidencia de comparabilidad',key=f'horizon_source_{coord_key}_{project_id}')
            if lo is not None and hi is not None and hi>lo and horizon_source.strip(): horizon=(lo,hi)
            else: st.caption('Completa ambos límites y la fuente para incorporar el antecedente.')
    if advanced:
        with st.expander('Evidencia geológica y fuentes'):
            if geo: st.json(geo,expanded=False)
            for region,text in REGIONAL.items(): st.markdown(f'**{region}.** {text}')
            for label,url in SOURCES.items(): st.markdown(f'[{label}]({url})')
    st.caption('La cartografía caracteriza la superficie; el modelo en profundidad se interpreta a partir de los contrastes y antecedentes disponibles.')

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
    fig.update_layout(title=title,xaxis_title=xlabel,yaxis_title=ylabel,height=410,margin=dict(l=10,r=10,t=50,b=20)); fig.update_yaxes(autorange='reversed',range=[float(max(y)),float(min(y))] if smooth else None);return fig

comparison_results={}
with gp_tab:
    st.subheader('Perfil geoeléctrico')
    compression='Log₁₀(1+|V|) con signo'; smooth=True; grid=False; overlay=True
    if advanced:
        with st.expander('Ajustes de visualización'):
            compression=st.selectbox('Transformación de la sección procesada',['Log₁₀(1+|V|) con signo','Log₁₀(V), solo positivos','Raíz cuadrada con signo'])
            smooth=st.checkbox('Interpolación lineal',True)
            grid=st.checkbox('Malla y contornos',False,disabled=not smooth)
            overlay=st.checkbox('Marcar anomalías',True)
    if compression=='Log₁₀(V), solo positivos': result['display_log']=np.log10(np.where(result['raw']>0,result['raw'],np.nan))
    elif compression=='Raíz cuadrada con signo': result['display_log']=np.sign(result['raw'])*np.sqrt(np.abs(result['raw']))
    else: result['display_log']=result['log']
    representations['02 · Procesada experimental']=('display_log',PQWT_SCALE,False,compression)
    labels=['01 · Original','02 · Procesada experimental','03 · Contraste relativo','04 · Anomalías locales']
    view=st.radio('Representación',['Original y procesada','Cuatro pseudosecciones','Vista individual'],index=1,horizontal=True)
    if view=='Vista individual':
        selected=[st.selectbox('Sección',list(representations) if advanced else labels)]
    else: selected=labels[:2] if view=='Original y procesada' else labels
    for start in range(0,len(selected),2):
        panels=st.columns(len(selected[start:start+2]))
        for panel,label in zip(panels,selected[start:start+2]):
            mat,color,div,unit=representations[label]
            title=label.replace('Procesada experimental','Procesada HydroPick')
            panel.plotly_chart(heat(result[mat],title,color,div,overlay,smooth and mat!='votes',unit,grid),use_container_width=True,key='section_'+mat)
    st.caption('Escala vertical: '+('penetración teórica' if scale_method=='Física contextualizada' and scale is not None else 'profundidad nominal' if scale is not None else 'canales PQWT')+'. Sección procesada: compresión de amplitudes HydroPick.')
    with st.expander('Curvas y perfil por estación',expanded=True):
        fig=go.Figure()
        for j,c in enumerate(cols):
            if result['valid'][j]: fig.add_trace(go.Scatter(x=x,y=result['raw'][:,j],mode='lines+markers',name=c))
        fig.update_layout(title='Curvas originales',xaxis_title=xlabel,yaxis_title='Amplitud exportada',height=380)
        st.plotly_chart(fig,use_container_width=True)
        station=st.selectbox('Estación',result['stations'].tolist()); i=list(result['stations']).index(station)
        p=go.Figure(go.Scatter(x=result['raw'][i],y=y,mode='lines+markers'));p.update_yaxes(autorange='reversed');p.update_layout(title=f'Perfil N{station}',xaxis_title='Amplitud exportada',yaxis_title=ylabel,height=400);st.plotly_chart(p,use_container_width=True)
    if advanced:
        with st.expander('Diagnóstico técnico'):
            st.dataframe(pd.DataFrame(result['qc']),hide_index=True)
            st.dataframe(pd.DataFrame([{k:v for k,v in a.items() if k not in ('celdas','canales_detectados')} for a in result['anomalies']]),hide_index=True)
    if advanced:
        with st.expander('Comparar con gráficas PQWT del fabricante (experimental)'):
            st.caption('Carga imágenes de la misma línea. Ajusta manualmente el rectángulo de la pseudosección y la barra cromática vertical. No se envían las imágenes a la IA; solo métricas derivadas si autorizas el envío.')
            for kind,filename in [('Original','Grafica_original_L171.jpeg'),('Procesada','Grafica_procesada_L171.jpeg')]:
                pic=st.file_uploader(f'Gráfica {kind}',type=['png','jpg','jpeg'],key=f'image_{file_id}_{line}_{kind}')
                if pic: image_bytes=pic.getvalue()
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
                        if scale is None: st.caption('Aplica una escala de profundidad para comparar con imágenes en metros.');continue
                        if scale_method=='Física contextualizada' or not np.isclose(min(y),0) or not np.isclose(max(y),nominal): st.caption('La comparación requiere una escala que cubra de 0 al alcance nominal de la imagen.');continue
                        mats={'Original':result['raw'],'Log₁₀(1+|V|) con signo':result['log'],'Log₁₀(V), solo si V>0':np.log10(np.where(result['raw']>0,result['raw'],np.nan)),'Raíz cuadrada con signo':np.sign(result['raw'])*np.sqrt(np.abs(result['raw'])),'Contraste relativo':result['z'],'Anomalías locales':result['local']}
                        rows,palette,_,_=compare(image,(left,top,right,bottom),(legend_x,legend_top,legend_bottom),bins,x,y,mats,result['stations'],channel_ids)
                        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
                        swatch=np.repeat(palette[None,:,:],24,axis=0).astype(np.uint8);swatch=np.repeat(swatch,24,axis=1);st.image(swatch,caption='Paleta muestreada: alto → bajo',width=min(600,bins*24))
                        comparison_results[kind]={'sha256':hashlib.sha256(image_bytes).hexdigest(),'recorte_px':[left,top,right,bottom],'leyenda_px':[legend_x,legend_top,legend_bottom],'clases':bins,'metricas':rows}
                        st.caption('Correlación aproximada con clases cromáticas, no con valores físicos; depende del recorte, leyenda, interpolación y coincidencia de línea. No modifica el detector.')
                except Exception as e: st.caption(f'No se pudo comparar la gráfica {kind}: {e}')

decision=decide(result,scale,family,context_ok,georef,demo=demo,scale_method=scale_method,known_horizon=horizon)
# La evidencia y la recomendación se guardan juntas. No se envían a IA sin autorización.
payload={'version':'2.3.0','proyecto':name,'hash_csv':project_id,'linea':str(line),'modelo_equipo':model,'alcance_nominal_m':nominal,'espaciado_m':spacing if known else None,'coordenadas_referencia':{'lat':lat,'lon':lon} if georef else None,'escala':scale_meta,'comparacion_imagenes':comparison_results,'demo_csv':demo,'geologia_consulta':geo,'modelo_conceptual':family,'contexto_utilizable':context_ok,'notas_tecnico':notes,'intervalo_productivo_documentado':horizon,'fuente_intervalo':horizon_source,'qc':result['qc'],'calidad':{'cobertura':result['coverage'],'canales_informativos':result['informative'],'saltos':result['gaps']},'parametros':{'umbral':threshold,'resolucion':resolution,'compresion_visual':compression},'anomalias':result['anomalies'],'decision':decision,'alcance':'Recomendación de exploración basada en escala nominal o calibrada aportada; no confirma agua, caudal ni permisos. La ubicación es la estación del perfil, no una coordenada exacta. Los márgenes son reglas operativas no calibradas.'}
fp=hashlib.sha256(json.dumps(payload,default=str,sort_keys=True).encode()).hexdigest()
if st.session_state.get('ai_fingerprint')!=fp: st.session_state.ai_result=None;st.session_state.ai_fingerprint=fp
ordered=sorted(decision['objetivos'],key=lambda t:(t['estado']!=DRILL,-t['indice_geofisico']))
cards=target_cards(ordered)
# La misma imagen PNG se muestra en Interpretación y se incorpora al PDF.
annotated_png=interpretation_png(result,y,channel_ids,ordered,depth_axis=scale is not None and scale_method!='Física contextualizada',ylabel=ylabel,compression=compression,smooth=smooth)
with int_tab:
    st.subheader('Resultado del estudio')
    st.markdown(f"### {decision['estado']}")
    st.write(decision['motivo'])
    st.divider(); st.markdown('#### A · Contexto geológico')
    if descriptions:
        for d in descriptions: st.write(d)
        st.caption('IGME-CSIC · GEODE 1:50.000')
    if family!='Desconocido': st.write(f'**Modelo hidrogeológico:** {family}')
    if notes: st.write(notes)
    if not context_ok: st.write('Contexto pendiente de identificación o revisión.')
    st.divider(); st.markdown('#### '+SECTION)
    st.image(annotated_png,use_container_width=True)
    if not cards: st.write(EMPTY)
    for c in cards:
        with st.container(border=True):
            st.markdown('**'+c['title']+'**')
            a,b=st.columns(2)
            a.metric('Intervalo de interés',c['interval'])
            b.metric('Profundidad recomendada',c['depth'])
            if c['distance']: st.caption(c['distance'])
            st.write(f"**Decisión:** {c['state']}"); st.write(c['reason'])
            if c['hypothesis']: st.write(f"**Interpretación:** {c['hypothesis']}")
            if c['risk']: st.write(f"**Factor a verificar:** {c['risk']}")
    st.caption(SCOPE)
    if advanced:
        with st.expander('Análisis asistido por IA (opcional)'):
            # No usar una clave del propietario en una aplicación pública sin autenticación.
            api_key=(secret('OPENAI_API_KEY') if password else '') or st.text_input('Tu clave API de OpenAI',type='password',key='key')
            ai_model=st.text_input('Modelo API',value=secret('OPENAI_MODEL','gpt-5-mini'))
            web=st.checkbox('Investigación documental web',value=True)
            consent=st.checkbox('Autorizo enviar coordenadas, notas y resultados derivados a OpenAI (puede generar costes).')
            if st.button('Generar análisis complementario',disabled=not(api_key and consent)):
                with st.spinner('Consultando el modelo…'):
                    try: st.session_state.ai_result=run_ai(api_key,ai_model,payload,web)
                    except Exception: st.error('No se pudo generar el análisis. Comprueba la configuración de la API.')
            ai=st.session_state.get('ai_result')
            if ai:
                st.caption('Análisis complementario: no sustituye la decisión calculada.')
                st.markdown(ai['texto'])
                for ref in ai['referencias']: st.write(ref.get('title','Fuente'),ref.get('url',''))
with report_tab:
    st.subheader('Informe del estudio')
    st.write('Informe técnico PDF con el perfil geoeléctrico anotado y las conclusiones sobre puntos de interés y profundidad de perforación.')
    pdf=make_report(name,line,decision,cards,annotated_png,demo=demo,coords=(lat,lon) if georef else None,scale_status=scale_status)
    st.download_button('Descargar informe técnico (.pdf)',pdf,f'HydroPick_{project_id}_L{line}.pdf','application/pdf',type='primary')
