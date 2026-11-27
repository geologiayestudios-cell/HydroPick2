"""Pseudosecciones: interpolación exclusivamente visual, sin cubrir huecos."""
import numpy as np
from scipy.interpolate import RegularGridInterpolator

PQWT_COLORS=['#0000ff','#0066ff','#00baff','#58e2f2','#a4f5e6','#b5f5a4','#c9f56c','#e4f958','#ffff35','#ffe51f','#ffc822','#ffaf21','#ff9120','#ff741e','#ff4924','#ff1919','#ff0000']
PQWT_SCALE=[[i/(len(PQWT_COLORS)-1),c] for i,c in enumerate(PQWT_COLORS)]

def dense_section(x,y,matrix,stations,channel_ids,nx=250,ny=250):
    x=np.asarray(x,float); y=np.asarray(y,float); matrix=np.asarray(matrix,float)
    if y[0]>y[-1]: y=y[::-1]; matrix=matrix[:,::-1]; channel_ids=np.asarray(channel_ids)[::-1]
    xx=np.linspace(x[0],x[-1],nx); yy=np.linspace(y[0],y[-1],ny)
    X,Y=np.meshgrid(xx,yy)
    out=RegularGridInterpolator((x,y),matrix,method='linear',bounds_error=False,fill_value=np.nan)((X,Y))
    for a,b,gap in zip(x[:-1],x[1:],np.abs(np.diff(stations))):
        if gap!=1: out[:,(xx>a)&(xx<b)]=np.nan
    for a,b,gap in zip(y[:-1],y[1:],np.abs(np.diff(channel_ids))):
        if gap!=1: out[(yy>a)&(yy<b),:]=np.nan
    return xx,yy,out
