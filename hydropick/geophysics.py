"""Detección reproducible en el dominio estación–canal, sin inversión."""
import re
from io import BytesIO
import numpy as np
import pandas as pd
from scipy.ndimage import label
from scipy.stats import theilslopes


def read_pqwt(raw):
    for encoding in ('utf-8-sig','cp1252'):
        try:
            df=pd.read_csv(BytesIO(raw),sep=None,engine='python',encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    df.columns=[str(c).strip() for c in df.columns]
    df=df.dropna(axis=1,how='all')
    if 'N' not in df: raise ValueError('Falta la columna N.')
    if 'L' not in df: df['L']='1'
    cols=sorted([c for c in df if re.fullmatch(r'freq\d+',c,re.I)],key=lambda c:int(re.search(r'\d+',c).group()))
    if len(cols)<2: raise ValueError('Se requieren dos o más canales freqNN.')
    if len(set(int(re.search(r'\d+',c).group()) for c in cols))!=len(cols): raise ValueError('Canales duplicados.')
    df['N']=pd.to_numeric(df.N,errors='raise')
    if not np.isfinite(df.N).all() or (df.N%1!=0).any(): raise ValueError('N debe ser entero y finito.')
    if df[['L','N']].duplicated().any(): raise ValueError('Estaciones duplicadas dentro de una línea.')
    if df.L.isna().any(): raise ValueError('Identificador L vacío.')
    for c in cols: df[c]=pd.to_numeric(df[c].astype(str).str.replace(',','.',regex=False),errors='coerce').replace([np.inf,-np.inf],np.nan)
    return df,cols


def longest_run(indices):
    return max(np.split(indices,np.where(np.diff(indices)!=1)[0]+1),key=len) if len(indices) else np.array([],dtype=int)


def analyze(df,cols,spacing=None,resolution=0.001,threshold=1.5):
    df=df.sort_values('N'); n=df.N.to_numpy(int); v=df[cols].to_numpy(float)
    if len(n)<5: raise ValueError('Se requieren al menos cinco estaciones para contraste local.')
    if resolution<=0 or threshold<=0: raise ValueError('Resolución y umbral deben ser positivos.')
    x=(n-n[0])*(spacing if spacing else 1.)
    valid=np.zeros(len(cols),bool); qc=[]; z=np.full_like(v,np.nan); local=z.copy(); trend=z.copy()
    for j,c in enumerate(cols):
        y=v[:,j]; ok=np.isfinite(y); a=y[ok]; status='válido'
        if len(a)==0: status='sin datos'
        elif np.all(a==0): status='cero constante'
        elif np.ptp(a)<resolution: status='constante / subresolución'
        elif ok.mean()<.7: status='cobertura insuficiente'
        else: valid[j]=True; status='válido con ausencias' if not ok.all() else 'válido'
        qc.append({'canal':c,'estado':status,'ceros':int(np.sum(y==0)),'ausentes':int((~ok).sum())})
        if not valid[j]: continue
        med=np.median(a); scale=max(1.4826*np.median(np.abs(a-med)),resolution)
        z[ok,j]=(a-med)/scale
        slope,intercept,*_=theilslopes(a,x[ok]); residual=a-(slope*x[ok]+intercept)
        ts=max(1.4826*np.median(np.abs(residual-np.median(residual))),resolution)
        trend[ok,j]=(residual-np.median(residual))/ts
        # Fondo local: interpolación entre vecinos válidos inmediatos, sin extrapolación.
        for i in range(1,len(n)-1):
            if ok[i-1:i+2].all() and n[i]-n[i-1]==1 and n[i+1]-n[i]==1:
                b=np.interp(x[i],x[[i-1,i+1]],y[[i-1,i+1]])
                local[i,j]=(y[i]-b)/scale
    # Malla de canales físicos numerados; no unir canales con identificadores discontinuos.
    ids=np.array([int(re.search(r'\d+',c).group()) for c in cols]); consecutive=np.all(np.diff(ids)==1)
    masks=[]
    for t in (threshold*.8,threshold,threshold*1.2):
        for base in (trend,z): masks.append(np.isfinite(base)&(base<=-t))
        # Contraste local más sensible; necesita apoyo multicanal posterior.
        masks.append(np.isfinite(local)&(local<=-t*.5))
    votes=np.sum(masks,axis=0); candidates=votes>=2
    # Evitar conexiones artificiales a través de estaciones/canales omitidos.
    if consecutive and np.all(np.diff(n)==1): regions,count=label(candidates)
    else:
        regions=np.zeros_like(v,dtype=int); count=0
        for i in range(len(n)):
            js=np.flatnonzero(candidates[i]); groups=np.split(js,np.where(np.diff(ids[js])!=1)[0]+1) if len(js) else []
            for group in groups:
                count+=1; regions[i,group]=count
    anomalies=[]
    for r in range(1,count+1):
        ii,jj=np.where(regions==r)
        if len(np.unique(jj))<3: continue
        strengths=np.maximum(0,-np.nan_to_num(trend[ii,jj],nan=0)); local_strength=np.maximum(0,-np.nan_to_num(local[ii,jj],nan=0)); raw_strength=np.maximum(0,-np.nan_to_num(z[ii,jj],nan=0))
        signal=np.maximum.reduce([strengths,local_strength,raw_strength]); station_scores={int(i):float(np.sum(signal[ii==i])) for i in np.unique(ii)}
        center=max(station_scores,key=station_scores.get); edge=bool(0 in ii or len(n)-1 in ii)
        support=float(np.mean(votes[ii,jj])/len(masks)); contrast=float(np.median(signal))
        # Índice experimental de contraste/soporte, no probabilidad; borde penalizado.
        score=100*(.50*min(contrast/3,1)+.30*support+.20*min(len(np.unique(jj))/8,1))*(.7 if edge else 1)
        anomalies.append({'estacion':int(n[center]),'estacion_inicio':int(n[ii.min()]),'estacion_fin':int(n[ii.max()]),'distancia':float(x[center]),'canal_inicio':cols[jj.min()],'canal_fin':cols[jj.max()],'canales_detectados':[cols[j] for j in sorted(set(jj))],'n_canales':int(len(np.unique(jj))),'n_estaciones':int(len(np.unique(ii))),'borde':edge,'contraste':round(contrast,2),'apoyo_metodos_pct':round(support*100,1),'indice_geofisico':round(score,1),'patron':'borde abierto' if edge else ('localizado' if len(np.unique(ii))<=2 else 'extenso'),'celdas':[[int(i),int(j)] for i,j in zip(ii,jj)]})
    anomalies.sort(key=lambda a:-a['indice_geofisico'])
    for i,a in enumerate(anomalies,1): a['id']=f'A{i:02d}'
    return {'stations':n,'x':x,'raw':v,'z':z,'trend':trend,'local':local,'votes':votes,'valid':valid,'qc':qc,'anomalies':anomalies,'coverage':float(np.isfinite(v).mean()),'informative':float(valid.mean()),'gaps':bool(np.any(np.diff(n)!=1) or not consecutive),'spacing_known':spacing is not None}


def depth_intervals(anomalies,mapping,cols,nominal):
    """El mapa debe ser aportado explícitamente por el técnico; no inventar escalas."""
    if not {'canal','profundidad_m'}<=set(mapping.columns): raise ValueError('Se requieren canal,profundidad_m.')
    if mapping.canal.duplicated().any(): raise ValueError('Canales duplicados en la escala.')
    d=dict(zip(mapping.canal,pd.to_numeric(mapping.profundidad_m,errors='raise')))
    if not set(cols)<=d.keys(): raise ValueError('La escala debe incluir todos los canales.')
    depths=np.array([d[c] for c in cols]); delta=np.diff(depths)
    if not np.isfinite(depths).all() or depths.min()<0 or depths.max()>nominal or not (np.all(delta>0) or np.all(delta<0)): raise ValueError('Escala no monótona o fuera del alcance nominal.')
    for a in anomalies:
        z=[float(d[c]) for c in a['canales_detectados']]; a['intervalo_nominal_m']=[min(z),max(z)]
    return depths
