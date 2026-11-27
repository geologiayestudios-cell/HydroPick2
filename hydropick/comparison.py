"""Comparación cromática aproximada con gráficos del fabricante, no calibración."""
from io import BytesIO
import numpy as np
from PIL import Image
from scipy.stats import spearmanr
from .visuals import dense_section


def load_image(raw):
    if len(raw)>20_000_000: raise ValueError('Imagen superior a 20 MB.')
    with Image.open(BytesIO(raw)) as im:
        if im.width*im.height>12_000_000: raise ValueError('Imagen superior a 12 megapíxeles.')
        return np.asarray(im.convert('RGB')).copy()


def compare(image,box,legend,bins,x,y,matrices,stations,channel_ids):
    h,w=image.shape[:2]; l,t,r,b=box; lx,lt,lb=legend
    if not (0<=l<r<w and 0<=t<b<h and 0<=lx<w and 0<=lt<lb<h and 5<=bins<=50): raise ValueError('Ajusta los límites de la gráfica y la leyenda a la imagen.')
    # Centros de clases, de arriba (amplitud alta) a abajo (amplitud baja).
    ly=np.rint(lt+(np.arange(bins)+.5)*(lb-lt)/bins).astype(int)
    palette=np.array([np.median(image[max(0,p-1):p+2,max(0,lx-1):lx+2],axis=(0,1)) for p in ly],float)
    if np.unique(palette.astype(int),axis=0).shape[0]<bins*.65: raise ValueError('La leyenda no contiene suficientes colores distintos. Ajusta x, extremos o número de clases.')
    nx=min(250,r-l+1); ny=min(250,b-t+1)
    px=np.rint(np.linspace(l,r,nx)).astype(int); py=np.rint(np.linspace(t,b,ny)).astype(int)
    rgb=image[np.ix_(py,px)].astype(float); dist=np.sqrt(np.sum((rgb[:,:,None,:]-palette[None,None,:,:])**2,axis=-1))
    ranks=1-dist.argmin(axis=-1)/(bins-1)
    ok=(dist.min(axis=-1)<=38)&(rgb.max(axis=-1)-rgb.min(axis=-1)>=25)&(rgb.max(axis=-1)>=65)
    rows=[]
    for name,matrix in matrices.items():
        _,_,pred=dense_section(x,y,matrix,stations,channel_ids,nx,ny)
        valid=ok&np.isfinite(pred); n=int(valid.sum()); p=pred[valid]; q=ranks[valid]
        pearson=float(np.corrcoef(p,q)[0,1]) if n>=30 and np.ptp(p)>0 and np.ptp(q)>0 else None
        rank=float(spearmanr(p,q).statistic) if pearson is not None else None
        rows.append({'representacion':name,'pearson':pearson,'spearman':rank,'pixeles_validos':n,'cobertura_pct':round(100*n/(nx*ny),1)})
    return rows,palette.astype(int),ranks,ok
