from pathlib import Path
import os,pytest
from unittest.mock import patch,Mock
import numpy as np
import pandas as pd
from hydropick.geophysics import read_pqwt,analyze,depth_intervals
from hydropick.geology import query_geode,suggest_family,interpret

def test_l67():
    p=Path(os.environ.get('HYDROPICK_PRIVATE_FIXTURES',Path(__file__).parents[1]/'examples'))/'150M_L67.csv'
    if not p.exists(): pytest.skip('Fixture privada no distribuida')
    df,cols=read_pqwt(p.read_bytes())
    a=analyze(df,cols)
    assert len(cols)==36 and len(df)==11 and (a['raw']==0).sum()==149
    assert not a['valid'][:12].any() and a['valid'][12:].all()
    assert all('intervalo_nominal_m' not in x for x in a['anomalies'])

def test_flat():
    df=pd.DataFrame({'N':range(1,12),**{f'freq{i:02}':np.ones(11) for i in range(1,7)}});cols=list(df.columns[1:]);a=analyze(df,cols)
    assert not a['anomalies'] and not a['valid'].any()

def test_synthetic():
    x=np.arange(11); df=pd.DataFrame({'N':x+1,**{f'freq{i:02}':1+.01*x-.4*(x==5) for i in range(1,9)}});cols=list(df.columns[1:]);a=analyze(df,cols,2.)
    assert any(x['estacion']==6 and not x['borde'] for x in a['anomalies'])
    depths=depth_intervals(a['anomalies'],pd.DataFrame({'canal':cols,'profundidad_m':np.arange(1,9)*10}),cols,150)
    assert depths[-1]==80 and all(x.get('intervalo_nominal_m') for x in a['anomalies'])

def test_query_mock():
    r=Mock();r.json.return_value={'results':[{'layerId':8,'attributes':{'DESC_UNIT':'Calizas'}},{'layerId':6,'attributes':{'DESC_UNIT':'Calizas'}}]}
    with patch('hydropick.geology.requests.get',return_value=r) as get:
        a=query_geode(39,-4);assert a['estado']=='documentado' and len(a['registros'])==2
        assert get.call_args.args[0].endswith('/identify') and get.call_args.kwargs['params']['layers']=='all:8,6'
    assert suggest_family(a['registros'])=='Carbonatado / kárstico'
    assert interpret([{'id':'A1','estacion':3,'indice_geofisico':90,'borde':True}],'Carbonatado / kárstico',True)[0]['accion'].startswith('Ampliar')
