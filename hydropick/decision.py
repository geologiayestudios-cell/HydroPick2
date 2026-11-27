"""Reglas operativas versionadas. No son un modelo de probabilidad ni un sondeo litológico."""
import math
import numpy as np
from .geology import RULES

VERSION='public-1.0'
DRILL='Perforación exploratoria recomendada'
REPEAT='Repetir o ampliar mediciones'
HOLD='Completar información'
NO='No recomendar perforación'
# Margen de exploración después del objetivo: mínimo (m), fracción de espesor aparente.
# Parámetros de ingeniería iniciales, no calibrados con perforaciones.
POLICY={
 'Carbonatado / kárstico':(10,.35),
 'Paleozoico cuarcita-pizarra':(10,.50),
 'Volcánico / Campo de Calatrava':(10,.50),
 'Detrítico granular':(5,.25),
 'Granítico / cristalino':(10,.50),
 'Arcilloso / margoso':(5,.25),
 'Mixto':(10,.50),
}
LIMITS={'cobertura_min':.80,'fraccion_canales_min':.35,'canales_min':3,'persistencia_min_pct':65,'indice_min':60,'canales_centro_min':3}

def _runs(indices):
    return [a for a in np.split(indices,np.flatnonzero(np.diff(indices)!=1)+1) if len(a)] if len(indices) else []

def decide(result,scale,family,context_ok,georef,*,demo=False,scale_method='',known_horizon=None):
    """known_horizon: intervalo (m) de evidencia independiente aportada, no de cartografía superficial."""
    a_list=result['anomalies']; targets=[]
    def global_result(state,reason):
        return {'estado':state,'motivo':reason,'objetivos':targets,'politica':VERSION,'limites':LIMITS.copy()}
    global_gate=None
    if result['coverage']<LIMITS['cobertura_min'] or result['informative']<LIMITS['fraccion_canales_min'] or sum(result['valid'])<LIMITS['canales_min']:
        global_gate=(REPEAT,'La cobertura o variabilidad de los canales no permite delimitar un objetivo.')
    elif result['gaps']:
        global_gate=(REPEAT,'Completar los saltos de estaciones o canales antes de seleccionar un punto.')
    if global_gate is None and not a_list:
        return global_result(NO,'No se identificaron contrastes con soporte suficiente. Evaluar otro perfil si se requiere continuar la exploración.')
    if global_gate is None and (not georef or not context_ok or family not in POLICY):
        global_gate=(HOLD,'Completar la ubicación y el contexto geológico del estudio.')
    if global_gate is None and (scale is None or scale_method=='Física contextualizada'):
        global_gate=(HOLD,'Seleccionar una escala nominal o calibrada para estimar una profundidad de perforación.')
    if known_horizon is not None:
        lo,hi=known_horizon
        if not (np.isfinite([lo,hi]).all() and 0<=lo<hi):
            raise ValueError('Intervalo independiente inválido.')
    for a in a_list:
        t={'id':a['id'],'estacion':a['estacion'],'distancia_m':a.get('distancia') if result['spacing_known'] else None,'intervalo_anomalia_m':a.get('intervalo_nominal_m'),'intervalo_objetivo_m':None,'profundidad_recomendada_m':None,'margen_m':None,'hipotesis':RULES.get(family,RULES['Desconocido'])[0],'riesgo':RULES.get(family,RULES['Desconocido'])[1],'indice_geofisico':a['indice_geofisico'],'estado':None,'motivo':None}
        targets.append(t)
        def reject(state,reason): t.update(estado=state,motivo=reason)
        if global_gate: reject(*global_gate); continue
        if a['borde']: reject(REPEAT,'El contraste queda abierto en el extremo del perfil. Extender la línea.'); continue
        if a['indice_geofisico']<LIMITS['indice_min'] or a['persistencia_umbral_pct']<LIMITS['persistencia_min_pct']:
            reject(REPEAT,'El contraste no alcanza los criterios de estabilidad y soporte. Repetir el perfil.');continue
        if family in ('Mixto','Arcilloso / margoso') and known_horizon is None:
            reject(NO,'Se necesita evidencia de una intercalación o estructura permeable para diferenciarla de materiales conductores de baja permeabilidad.');continue
        i=int(np.flatnonzero(result['stations']==a['estacion'])[0]); z=np.asarray(scale,float)
        js=np.array(sorted({j for ii,j in a['celdas'] if ii==i and result['valid'][j] and np.isfinite(result['raw'][i,j])}),int)
        runs=[r for r in _runs(js) if len(r)>=LIMITS['canales_centro_min']]
        if not runs: reject(REPEAT,'El centro del objetivo no tiene tres canales consecutivos de soporte.');continue
        # Seleccionar tramo más respaldado en la estación real, no la extensión de toda la región.
        run=max(runs,key=lambda r:(float(np.sum(result['votes'][i,r])),len(r),-float(np.min(z[r]))))
        lo,hi=float(min(z[run])),float(max(z[run]));t['intervalo_objetivo_m']=[round(lo,1),round(hi,1)]
        if known_horizon is not None:
            overlap=run[(z[run]>=known_horizon[0]) & (z[run]<=known_horizon[1])]
            if len(overlap)<2:
                reject(HOLD,'El contraste no tiene suficiente coincidencia con el intervalo productivo documentado; contrastar ambos antes de perforar.');continue
            # Acotar al soporte medido dentro del horizonte independiente, sin extender por inferencia.
            run=overlap; lo,hi=float(min(z[run])),float(max(z[run]));t['intervalo_objetivo_m']=[round(lo,1),round(hi,1)]
        # El antecedente no inventa una extensión vertical.
        order=np.argsort(z); deepest=int(np.flatnonzero(order==run[np.argmax(z[run])])[0]); deeper=order[deepest+1:]
        ok=result['valid'] & np.isfinite(result['raw'][i])
        follow=[]
        for j in deeper:
            if not ok[j]: break
            follow.append(j)
        if not follow: reject(REPEAT,'El objetivo alcanza el límite de los datos útiles en profundidad. Investigar un intervalo mayor.');continue
        step=float(z[follow[0]]-hi); base,frac=POLICY[family]
        margin=max(base,step,frac*(hi-lo)); proposed=math.ceil((hi+margin)/5-1e-10)*5
        if proposed>float(z[follow[-1]])+1e-9:
            reject(REPEAT,'No hay cobertura útil suficiente bajo el objetivo para definir la profundidad final.');continue
        t.update(estado=DRILL,motivo=('Contraste localizado y consistente, compatible con el modelo hidrogeológico seleccionado. '+('Coincide con el horizonte productivo aportado. ' if known_horizon is not None else '')+'Programar una parada técnica al alcanzar el intervalo objetivo.'),profundidad_recomendada_m=int(proposed),margen_m=round(proposed-hi,1))
    if global_gate: return global_result(*global_gate)
    # Un solo plan por estación: priorizar soporte y, en empate, menor profundidad.
    candidates=[t for t in targets if t['estado']==DRILL]
    for station in {t['estacion'] for t in candidates}:
        same=[t for t in candidates if t['estacion']==station]
        best=max(same,key=lambda t:(t['indice_geofisico'],-t['profundidad_recomendada_m']))
        for t in same:
            if t is not best:
                t.update(estado=HOLD,motivo='Horizonte alternativo en la misma estación; priorizar el plan con mayor soporte.',profundidad_recomendada_m=None,margen_m=None)
    if demo:
        for t in targets:
            if t['estado']==DRILL:
                t.update(estado=HOLD,motivo='Ejemplo didáctico sin localización real.',profundidad_recomendada_m=None,margen_m=None)
        return global_result(HOLD,'Caso de demostración; no asociado a un emplazamiento real.')
    if any(t['estado']==DRILL for t in targets): return global_result(DRILL,'Priorizar los objetivos seleccionados por el motor integrado.')
    if any(t['estado']==REPEAT for t in targets): return global_result(REPEAT,'Delimitar mejor los objetivos antes de invertir en perforación.')
    if any(t['estado']==HOLD for t in targets): return global_result(HOLD,'Resolver las condiciones pendientes de los objetivos identificados.')
    return global_result(NO,'Las anomalías identificadas no sustentan una recomendación de perforación con el contexto disponible.')
