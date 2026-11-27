from pathlib import Path
import os
import numpy as np
import pandas as pd
import pytest
from hydropick.geophysics import read_pqwt,analyze,depth_intervals
from hydropick.scales import automatic_mapping,detect_mode,physical_mapping,PROFILES
from hydropick.visuals import dense_section
from hydropick.comparison import load_image,compare

EXAMPLES=Path(os.environ.get('HYDROPICK_PRIVATE_FIXTURES',Path(__file__).parents[1]/'examples'))
@pytest.mark.parametrize('mode,n',PROFILES.items())
def test_scale(mode,n):
    cols=[f'freq{i:02}' for i in range(1,n+1)]
    assert detect_mode(cols)==mode
    mapping,status=automatic_mapping(cols,mode)
    d=depth_intervals([],mapping,cols,mode)
    assert d[0]==0 and d[-1]==mode and np.allclose(np.diff(d),mode/(n-1))
    assert status
    with pytest.raises(ValueError): automatic_mapping(cols,mode+1)
    assert detect_mode(cols[:-1]) is None

def test_physical():
    cols=['freq01','freq02','freq03']
    tab=pd.DataFrame({'canal':cols,'frecuencia_hz':[1000,500,250]})
    m=physical_mapping(cols,tab,10,.4,150)
    assert np.allclose(m.profundidad_m,.4*503.3*np.sqrt(10/tab.frecuencia_hz))
    with pytest.raises(ValueError): physical_mapping(cols,tab,1000,.4,150)
    with pytest.raises(ValueError): physical_mapping(cols,tab.iloc[:-1],10,.4,150)

@pytest.mark.parametrize('file,mode',[('100M_L15.csv',100),('150M_L1.csv',150),('150M_L67.csv',150),('300M_L171.csv',300)])
def test_real_examples(file,mode):
    if not (EXAMPLES/file).exists(): pytest.skip('Fixture privada no distribuida')
    df,c=read_pqwt((EXAMPLES/file).read_bytes());a=analyze(df,c)
    assert detect_mode(c)==mode and np.array_equal(a['raw'],df.sort_values('N')[c].to_numpy(),equal_nan=True)
    assert np.allclose(a['log'],np.sign(a['raw'])*np.log10(1+np.abs(a['raw'])),equal_nan=True)
    assert a['votes'].min()>=0 and a['votes'].max()<=3
    assert np.all(a['votes'][:,~a['valid']]==0)
    for region in a['anomalies']:
        assert all(a['votes'][i,j]>=2 for i,j in region['celdas']) and region['n_canales']>=3
        assert 0<=region['persistencia_umbral_pct']<=100
    depth_intervals(a['anomalies'],automatic_mapping(c,mode)[0],c,mode)
    assert all(0<=r['intervalo_nominal_m'][0]<=r['intervalo_nominal_m'][1]<=mode for r in a['anomalies'])

def test_gaps_and_descending():
    x=[1,2,4,5];y=[0,1,3]; m=np.arange(12).reshape(4,3).astype(float)
    xx,yy,z=dense_section(x,y,m,x,[1,2,4],41,31)
    assert np.isnan(z[:,(xx>2)&(xx<4)]).all()
    assert np.isnan(z[(yy>1)&(yy<3),:]).all()
    _,_,z2=dense_section(x,y[::-1],m[:,::-1],x,[4,2,1],41,31)
    assert np.allclose(z,z2,equal_nan=True)

def test_images():
    if not (EXAMPLES/'300M_L171.csv').exists(): pytest.skip('Fixtures privadas no distribuidas')
    df,c=read_pqwt((EXAMPLES/'300M_L171.csv').read_bytes());a=analyze(df,c); y=automatic_mapping(c,300)[0].profundidad_m.to_numpy();x=a['stations']
    matrices={'raw':a['raw'],'log1p':a['log'],'log10':np.log10(a['raw'])}
    metrics=[]
    for kind in ('original','procesada'):
        im=load_image((EXAMPLES/f'Grafica_{kind}_L171.jpeg').read_bytes()); h,w=im.shape[:2]
        rows,*_=compare(im,(int(w*.057),int(h*.043),int(w*.914),int(h*.917)),(int(w*.953),int(h*.043),int(h*.78)),17,x,y,matrices,x,np.arange(1,41))
        metrics.append({r['representacion']:r['pearson'] for r in rows})
        assert min(r['pixeles_validos'] for r in rows)>1000
    assert metrics[0]['raw']>.9 and metrics[1]['log10']>metrics[1]['raw']
