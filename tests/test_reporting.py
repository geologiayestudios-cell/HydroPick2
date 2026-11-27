from copy import deepcopy
from io import BytesIO
import numpy as np
from PIL import Image
from hydropick.reporting import annotations, target_cards, interpretation_png, make_report
from hydropick.decision import decide,DRILL,REPEAT
from test_decision import fixture,F


def example():
    r,z=fixture(); r['raw'][3,8:12]=.2; r['display_log']=np.log10(1+r['raw'])
    d=decide(r,z,F,True,True); return r,z,d


def test_markers_and_bounds():
    r,z,d=example(); boxes,stations,depths=annotations(r,z,d['objetivos'],True)
    assert stations==[4.] and depths=={65.:[4.]}
    assert boxes==[dict(id='A01',left=3.5,right=4.5,top=37.5,bottom=57.5)]
    assert annotations(r,z,d['objetivos'],False)[2]=={}


def test_multiple_and_rejected_targets():
    r,z,d=example(); a=deepcopy(r['anomalies'][0]);a.update(id='A02',estacion=6,celdas=[[5,j] for j in range(8,12)]);r['anomalies'].append(a)
    t=deepcopy(d['objetivos'][0]); t.update(id='A02',estacion=6,profundidad_recomendada_m=65);d['objetivos'].append(t)
    assert annotations(r,z,d['objetivos'],True)[2]=={65.:[4.,6.]}
    t.update(estado=REPEAT,profundidad_recomendada_m=None)
    boxes,stations,depths=annotations(r,z,d['objetivos'],True)
    assert len(boxes)==2 and stations==[4.,6.] and depths=={65.:[4.]}
    cards=target_cards(d['objetivos']); assert cards[0]['depth']=='65 m' and cards[1]['depth']=='—'


def test_render_and_pdf():
    r,z,d=example(); png=interpretation_png(r,z,np.arange(1,len(z)+1),d['objetivos'],compression='Log₁₀(1+|V|) con signo')
    with Image.open(BytesIO(png)) as im: assert im.width>2000 and im.height>1000
    pdf=make_report('Ejemplo <A> & B',1,d,target_cards(d['objetivos']),png,scale_status='Nominal');assert pdf.startswith(b'%PDF-') and b'%%EOF' in pdf[-100:]


def test_no_anomaly():
    r,z,d=example();r['anomalies']=[];d=decide(r,z,F,True,True)
    assert annotations(r,z,[],False)==([],[],{}) and target_cards([])==[]
    png=interpretation_png(r,np.arange(1,len(z)+1),np.arange(1,len(z)+1),[],depth_axis=False,ylabel='Canal PQWT',smooth=False)
    assert make_report('Sin objetivo',2,d,[],png).startswith(b'%PDF-')
