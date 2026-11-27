"""Presentación compartida de la interpretación. No modifica el motor de decisión."""
from collections import defaultdict
from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape
from threading import RLock

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle, Patch
import matplotlib.patheffects as pe
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, KeepTogether

from .decision import DRILL
from .visuals import PQWT_COLORS, dense_section

_RENDER_LOCK=RLock()
SCOPE='Profundidades orientativas de exploración, sujetas a comprobación durante la perforación. La recomendación no acredita caudal, calidad de agua ni autorización de captación.'
EMPTY='No se han seleccionado puntos de perforación.'
SECTION='B y C · Anomalías y profundidad de perforación'


def target_cards(ordered):
    """Una sola fuente de textos para pantalla y PDF, con prioridad idéntica."""
    cards=[]; priority=0
    for t in ordered:
        drill=t['estado']==DRILL
        if drill: priority+=1
        interval=t['intervalo_objetivo_m'] or t['intervalo_anomalia_m']
        cards.append(dict(title=f"Estación N{t['estacion']} · {t['id']}"+(f' · Prioridad {priority}' if drill else ''),
            interval=f'{interval[0]:.0f}–{interval[1]:.0f} m' if interval else 'Por determinar',
            depth=f"{t['profundidad_recomendada_m']} m" if t['profundidad_recomendada_m'] is not None else '—',
            distance=f"Distancia desde el inicio: {t['distancia_m']:.1f} m" if t['distancia_m'] is not None else '',
            state=t['estado'],reason=t['motivo'],hypothesis=t['hipotesis'] if drill else '',risk=t['riesgo'] if drill else ''))
    return cards


def _bounds(values, indices):
    """Bordes de las celdas medidas, sin extender fuera de la cobertura."""
    values=np.asarray(values,float)
    lo,hi=min(indices),max(indices)
    a=(values[lo-1]+values[lo])/2 if lo>0 else values[lo]
    b=(values[hi]+values[hi+1])/2 if hi<len(values)-1 else values[hi]
    return tuple(sorted((float(a),float(b))))


def annotations(result,y,ordered,depth_axis):
    """Estaciones y cajas de todas las regiones; profundidades solo de planes admitidos."""
    x=np.asarray(result['stations'],float); y=np.asarray(y,float)
    targets={t['id']:t for t in ordered}; boxes=[]; stations=set(); depths=defaultdict(set)
    for a in result['anomalies']:
        if not a['celdas']: continue
        ii,jj=zip(*a['celdas']); left,right=_bounds(x,ii); top,bottom=_bounds(y,jj)
        boxes.append(dict(id=a['id'],left=left,right=right,top=top,bottom=bottom))
        stations.add(float(a['estacion']))
        t=targets.get(a['id'])
        if t and t['estado']==DRILL and depth_axis and t['profundidad_recomendada_m'] is not None:
            d=float(t['profundidad_recomendada_m'])
            if min(y)<=d<=max(y): depths[d].add(float(t['estacion']))
    return boxes,sorted(stations),{d:sorted(s) for d,s in sorted(depths.items())}


def interpretation_png(result,y,channel_ids,ordered,*,depth_axis=True,ylabel='Profundidad nominal estimada (m)',compression='',smooth=True):
    """PNG de alta resolución usado sin cambios tanto en Streamlit como en PDF."""
    with _RENDER_LOCK:
        return _interpretation_png(result,y,channel_ids,ordered,depth_axis,ylabel,compression,smooth)


def _interpretation_png(result,y,channel_ids,ordered,depth_axis,ylabel,compression,smooth):
    x=np.asarray(result['stations'],float); y=np.asarray(y,float)
    matrix=np.asarray(result['display_log'],float)
    boxes,stations,depths=annotations(result,y,ordered,depth_axis)
    fig=Figure(figsize=(9.5,5.2),dpi=240,facecolor='white'); FigureCanvasAgg(fig)
    ax=fig.add_subplot(111); fig.subplots_adjust(left=.10,right=.88,top=.87,bottom=.25)
    cmap=LinearSegmentedColormap.from_list('pqwt_report',PQWT_COLORS); cmap.set_bad('#E5E7EB')
    finite=matrix[np.isfinite(matrix)]
    vmin=float(min(0,finite.min())) if finite.size else 0.; vmax=float(finite.max()) if finite.size else 1.
    if vmax<=vmin: vmax=vmin+1.
    if smooth:
        xx,yy,zz=dense_section(x,y,matrix,result['stations'],channel_ids)
    else: xx,yy,zz=x,y,matrix.T
    mesh=ax.pcolormesh(xx,yy,np.ma.masked_invalid(zz),shading='nearest',cmap=cmap,norm=Normalize(vmin,vmax),rasterized=True)
    cb=fig.colorbar(mesh,ax=ax,pad=.025,fraction=.045); cb.ax.tick_params(labelsize=10); cb.set_label('Amplitud transformada',fontsize=11)
    ax.set_xlim(x[0],x[-1]); ax.set_ylim(max(y),min(y)); ax.set_xlabel('Estación de medición (N)',fontsize=11); ax.set_ylabel(ylabel,fontsize=11)
    ticks=x if len(x)<=22 else np.unique(np.r_[x[::max(1,int(np.ceil(len(x)/15)))],x[-1],stations if len(stations)<=15 else []])
    ax.set_xticks(ticks); ax.set_xticklabels([f'N{v:g}' for v in ticks],rotation=45 if len(ticks)>16 else 0,fontsize=10 if len(ticks)<=22 else 8)
    ax.tick_params(axis='y',labelsize=10)
    for tick,v in zip(ax.get_xticklabels(),ticks):
        if v in stations: tick.set_fontweight('bold'); tick.set_color('#173B47')
    halo=[pe.Stroke(linewidth=4.3,foreground='white'),pe.Normal()]
    style=dict(linestyle=(0,(4,3)),linewidth=2.5,path_effects=halo,zorder=5)
    for s in stations: ax.axvline(s,color='#172B38',**style)
    for depth,ss in depths.items():
        ax.axhline(depth,color='#A31529',**style)
        # El punto de cruce identifica a qué estación corresponde cada profundidad.
        ax.scatter(ss,[depth]*len(ss),s=30,marker='o',color='#A31529',edgecolors='white',linewidths=1.1,zorder=8)
        if len(depths)<=8:
            ax.annotate(f'{depth:g} m',xy=(1,depth),xycoords=('axes fraction','data'),xytext=(-4,3),textcoords='offset points',ha='right',va='bottom',fontsize=9,fontweight='bold',color='#A31529',bbox=dict(boxstyle='round,pad=.17',fc='white',ec='none',alpha=.92),zorder=9)
    for box in boxes:
        rect=Rectangle((box['left'],box['top']),box['right']-box['left'],box['bottom']-box['top'],fill=False,edgecolor='#172B38',linestyle=(0,(3,2)),linewidth=2.8,path_effects=halo,zorder=7)
        ax.add_patch(rect)
        if len(boxes)<=12:
            ax.annotate(box['id'],(box['left'],box['top']),xytext=(3,3),textcoords='offset points',fontsize=8,fontweight='bold',color='#172B38',bbox=dict(boxstyle='round,pad=.15',fc='white',ec='none',alpha=.92),zorder=9,clip_on=True)
    ax.set_title('Perfil geoeléctrico procesado',loc='left',fontweight='bold',fontsize=14,pad=12,color='#173B47')
    handles=[]
    if stations: handles.append(Line2D([0],[0],color='#172B38',lw=2.5,ls='--',label='Estación de anomalía'))
    if depths: handles.append(Line2D([0],[0],color='#A31529',lw=2.5,ls='--',marker='o',label='Profundidad recomendada (cruce marcado)'))
    if boxes: handles.append(Patch(facecolor='none',edgecolor='#172B38',lw=2.5,ls='--',label='Área anómala'))
    if handles: fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.49,.068),ncol=min(3,len(handles)),frameon=False,fontsize=9)
    status='Sin profundidad de perforación asignada.' if not depths else 'Las profundidades corresponden a los cruces marcados.'
    if not boxes: status='No se identificaron áreas anómalas. '+status
    fig.text(.10,.035,f'{compression}  |  {status}',fontsize=9,color='#475569')
    buf=BytesIO(); fig.savefig(buf,format='png',dpi=240,facecolor='white'); fig.clear(); return buf.getvalue()


TEAL=colors.HexColor('#087E83'); INK=colors.HexColor('#183B48'); MUTED=colors.HexColor('#526371'); LINE=colors.HexColor('#D8E2E6'); LIGHT=colors.HexColor('#F0F5F6')


def make_report(name,line,decision,cards,png,*,demo=False,coords=None,scale_status='',report_date=None):
    """Un PDF A4 paginado con la misma gráfica y textos B/C de la interfaz."""
    buf=BytesIO(); day=report_date or date.today()
    doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=23*mm,bottomMargin=20*mm,title='HydroPick - Informe técnico',author='GeoAqua | HydroPick')
    styles={
        'title':ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=23,leading=27,textColor=INK,spaceAfter=7),
        'sub':ParagraphStyle('sub',fontName='Helvetica',fontSize=10,leading=14,textColor=MUTED,spaceAfter=6),
        'h':ParagraphStyle('h',fontName='Helvetica-Bold',fontSize=13,leading=17,textColor=TEAL,spaceBefore=10,spaceAfter=6,keepWithNext=True),
        'target':ParagraphStyle('target',fontName='Helvetica-Bold',fontSize=12,leading=16,textColor=INK,spaceBefore=5,spaceAfter=6,keepWithNext=True),
        'body':ParagraphStyle('body',fontName='Helvetica',fontSize=10,leading=14,textColor=INK,spaceAfter=5,alignment=TA_LEFT),
        'small':ParagraphStyle('small',fontName='Helvetica',fontSize=8.5,leading=11.5,textColor=MUTED,spaceAfter=5),
        'state':ParagraphStyle('state',fontName='Helvetica-Bold',fontSize=12,leading=16,textColor=INK,spaceAfter=5),
        'metric':ParagraphStyle('metric',fontName='Helvetica-Bold',fontSize=15,leading=18,textColor=INK),
    }
    def p(text,style='body'): return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
    def labeled(label,value,style='body'): return Paragraph(f'<b>{escape(label)}:</b> {escape(str(value))}',styles[style])
    def page(canvas,doc):
        w,h=A4; canvas.setFillColor(TEAL);canvas.rect(18*mm,h-16*mm,8*mm,2*mm,fill=1,stroke=0)
        canvas.setFont('Helvetica-Bold',10);canvas.setFillColor(INK);canvas.drawString(29*mm,h-15.7*mm,'GEOAQUA  /  HYDROPICK')
        canvas.setStrokeColor(LINE);canvas.line(18*mm,h-19*mm,w-18*mm,h-19*mm);canvas.line(18*mm,15*mm,w-18*mm,15*mm)
        canvas.setFont('Helvetica',8);canvas.setFillColor(MUTED);canvas.drawString(18*mm,10.5*mm,'HydroPick V2.3 · Interpretación hidrogeofísica');canvas.drawRightString(w-18*mm,10.5*mm,f'Página {doc.page}')
    story=[p('Informe técnico de interpretación','title'),p(f'Estudio: {name} | Línea: {line} | Fecha: {day:%d/%m/%Y}','sub')]
    if coords is not None: story.append(p(f'Coordenadas de referencia (WGS84): {coords[0]:.6f}, {coords[1]:.6f}','small'))
    if demo: story.append(p('Demostración sintética · sin emplazamiento real','state'))
    story.extend([p('Resultado del estudio','h'),p(decision['estado'],'state'),p(decision['motivo']),Spacer(1,4)])
    chart=Image(BytesIO(png)); chart.drawWidth=doc.width-12;chart.drawHeight=chart.drawWidth*chart.imageHeight/chart.imageWidth
    story.extend([chart,p('Figura 1. Perfil procesado HydroPick con estaciones, áreas anómalas y profundidades asignadas, cuando corresponda.','small')])
    if scale_status: story.append(p('Escala: '+scale_status,'small'))
    story.append(p(SECTION,'h'))
    if not cards: story.append(p(EMPTY))
    for c in cards:
        metrics=Table([[p('Intervalo de interés','small'),p('Profundidad recomendada','small')],[p(c['interval'],'metric'),p(c['depth'],'metric')]],colWidths=[(doc.width-12)/2]*2)
        metrics.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT),('BOX',(0,0),(-1,-1),.5,LINE),('LINEBEFORE',(1,0),(1,-1),.5,LINE),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('VALIGN',(0,0),(-1,-1),'TOP')]))
        block=[p(c['title'],'target'),metrics,Spacer(1,6)]
        if c['distance']: block.append(p(c['distance'],'small'))
        block.extend([labeled('Decisión',c['state']),p(c['reason'])])
        if c['hypothesis']: block.append(labeled('Interpretación',c['hypothesis']))
        if c['risk']: block.append(labeled('Factor a verificar',c['risk']))
        block.append(Spacer(1,5)); story.append(KeepTogether(block))
    story.extend([Spacer(1,5),p(SCOPE,'small')])
    doc.build(story,onFirstPage=page,onLaterPages=page); return buf.getvalue()
