"""Escalas de representación nominal; ninguna constituye calibración hidráulica."""
import re
import numpy as np
import pandas as pd

PROFILES={100:20,150:36,300:40,500:49}

def detect_mode(cols):
    ids=[int(re.search(r'\d+',c).group()) for c in cols]
    return next((d for d,n in PROFILES.items() if ids==list(range(1,n+1))),None)

def automatic_mapping(cols, nominal):
    if nominal not in PROFILES or detect_mode(cols)!=nominal:
        raise ValueError(f'El modo {nominal} m requiere {PROFILES.get(nominal,"un número documentado de")} canales consecutivos desde freq01. Usa una escala personalizada o analiza en canales.')
    n=len(cols)
    status='Contrastada gráficamente en L171 (no calibración instrumental)' if nominal==300 else ('Extrapolada: 49 canales comunicados por el usuario, sin gráfica de 500 m' if nominal==500 else 'Provisional: distribución lineal basada en los ejemplos aportados')
    return pd.DataFrame({'canal':cols,'profundidad_m':np.linspace(0,nominal,n)}),status

def physical_mapping(cols, table, rho, k, nominal):
    if not {'canal','frecuencia_hz'}<=set(table): raise ValueError('Se requieren canal,frecuencia_hz.')
    if table.canal.duplicated().any(): raise ValueError('Canales duplicados en tabla de frecuencias.')
    f=pd.to_numeric(table.set_index('canal').frecuencia_hz.reindex(cols),errors='raise').to_numpy(float)
    if not np.isfinite(f).all() or np.any(f<=0) or rho<=0 or not .3<=k<=.5: raise ValueError('Frecuencias positivas completas, resistividad positiva y factor 0.3–0.5 requeridos.')
    z=k*503.3*np.sqrt(rho/f)
    if not (np.all(np.diff(z)>0) or np.all(np.diff(z)<0)): raise ValueError('Escala física no monótona.')
    if z.max()>nominal: raise ValueError('La escala física excede el alcance seleccionado. No se recorta ni reescala artificialmente; modifica los supuestos o usa otra escala.')
    return pd.DataFrame({'canal':cols,'profundidad_m':z})
