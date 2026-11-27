from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest
from hydropick.geophysics import read_pqwt,analyze,depth_intervals
from hydropick.scales import automatic_mapping
from hydropick.decision import decide,DRILL,HOLD,REPEAT,NO

F='Carbonatado / kárstico'

def sample():
    d,c=read_pqwt((Path(__file__).parents[1]/'examples/Demo_150m.csv').read_bytes())
    r=analyze(d,c); z=depth_intervals(r['anomalies'],automatic_mapping(c,150)[0],c,150)
    return r,z

def fixture():
    z=np.arange(0,105,5,dtype=float); raw=np.ones((7,len(z))); votes=np.zeros_like(raw)
    cells=[[3,j] for j in range(8,12)];votes[3,8:12]=3
    a={'id':'A01','estacion':4,'distancia':6.,'borde':False,'indice_geofisico':85,'persistencia_umbral_pct':90,'celdas':cells,'intervalo_nominal_m':[40,55]}
    return {'anomalies':[a],'coverage':1.,'informative':1.,'valid':np.ones(len(z),bool),'gaps':False,'stations':np.arange(1,8),'raw':raw,'votes':votes,'spacing_known':True},z

def go(r,z,f=F,**kw):
    return decide(r,z,f,kw.pop('context_ok',True),kw.pop('georef',True),**kw)

def test_depth_family():
    r,z=fixture(); a=go(r,z)['objetivos'][0]; b=go(r,z,'Detrítico granular')['objetivos'][0]
    assert a['estado']==DRILL and a['profundidad_recomendada_m']==65 and b['profundidad_recomendada_m']==60
    assert a['intervalo_objetivo_m']==[40,55]

@pytest.mark.parametrize('key,value',[('coverage',.5),('informative',.1),('gaps',True)])
def test_quality(key,value):
    r,z=fixture();r[key]=value
    assert go(r,z)['estado']==REPEAT

@pytest.mark.parametrize('field,value',[('borde',True),('persistencia_umbral_pct',50),('indice_geofisico',45)])
def test_target_gate(field,value):
    r,z=fixture();r['anomalies'][0][field]=value
    assert go(r,z)['estado']==REPEAT and go(r,z)['objetivos'][0]['profundidad_recomendada_m'] is None

def test_no_context_and_scale():
    r,z=fixture()
    assert go(r,z,context_ok=False)['estado']==HOLD
    assert go(r,z,georef=False)['estado']==HOLD
    assert go(r,None)['estado']==HOLD
    assert go(r,z,scale_method='Física contextualizada')['estado']==HOLD
    assert go(r,z,demo=True)['objetivos'][0]['profundidad_recomendada_m'] is None

def test_no_target_clay_and_analogue():
    r,z=fixture()
    assert go(r,z,'Arcilloso / margoso')['estado']==NO
    assert go(r,z,known_horizon=(70,90))['estado']==HOLD
    a=go(r,z,'Arcilloso / margoso',known_horizon=(40,50))['objetivos'][0]
    assert a['estado']==DRILL and a['intervalo_objetivo_m']==[40,50] and a['profundidad_recomendada_m']==55
    r['anomalies']=[]; assert go(r,z)['estado']==NO

def test_bottom_and_gap_below():
    r,z=fixture(); r['valid'][12:]=False
    assert go(r,z)['estado']==REPEAT
    r,z=fixture(); r['anomalies'][0]['celdas']=[[3,j] for j in range(17,21)]
    assert go(r,z)['estado']==REPEAT

def test_duplicate_station():
    r,z=fixture(); a=deepcopy(r['anomalies'][0]);a['id']='A02';a['indice_geofisico']=70;r['anomalies'].append(a)
    assert sum(t['estado']==DRILL for t in go(r,z)['objetivos'])==1

def test_synthetic_demo():
    r,z=sample(); assert len(r['anomalies'])>0
    assert not any(t['estado']==DRILL for t in go(r,z,demo=True)['objetivos'])
