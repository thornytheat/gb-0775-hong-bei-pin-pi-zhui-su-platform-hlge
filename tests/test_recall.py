import pytest

from app.errors import RoastError
from app.modules.recall.scope import assess


@pytest.fixture
def archived(client):
    return client.post('/api/runs',json={'sample':'dirty'}).json['id']


def register(client, run, **extra):
    return client.post('/api/recalls',json={'run':run,'origin':'BR-08','reference':'RC-2026-01',**extra})


def test_confirmed_pending_released(dirty):
    scope=assess(dirty,'BR-08')
    buckets={key:row['status'] for key,row in scope['packages'].items()}
    assert {key for key,status in buckets.items() if status=='confirmed'}=={'PK-A','PK-B','PK-C'}
    assert {key for key,status in buckets.items() if status=='pending'}=={'PK-G'}
    assert {key for key,status in buckets.items() if status=='released'}=={'PK-D','PK-E','PK-F'}
    assert scope['packages']['PK-C']['origin_g']=='9273/50'


def test_pending_roll_does_not_hold_unrelated(dirty):
    scope=assess(dirty,'CO-04')
    pending={key for key,row in scope['packages'].items() if row['status']=='pending'}
    assert pending=={'PK-G'}
    assert scope['packages']['PK-E']['status']=='released'
    assert scope['jobs']['BA-05']['status']=='released'


def test_multi_level_return_reaches_package(dirty):
    scope=assess(dirty,'ET-01')
    assert scope['packages']['PK-C']['status']=='confirmed'
    assert scope['packages']['PK-C']['origin_g']=='3597/50'
    assert scope['packages']['PK-E']['status']=='pending'


def test_drawn_return_not_remaining_stock(dirty):
    scope=assess(dirty,'ET-01')
    roll=scope['returns']['RT-A']
    assert (roll['status'],roll['stock_g'],roll['drawn_g'])==('drawn','0','300')
    kept=scope['returns']['RT-D']
    assert (kept['status'],kept['stock_g'],kept['origin_g'])==('confirmed','100','100')


def test_detained_stock_reconciles(dirty):
    for origin in ('ET-01','BR-08','CO-04'):
        recon=assess(dirty,origin)['reconcile']
        assert recon['balanced'] and recon['stock_delta_g']=='0' and recon['flow_delta_g']=='0'
    assert assess(dirty,'BR-08')['reconcile']['detained_stock_origin_g']=='4366/125'


def test_unknown_origin_rejected(dirty):
    with pytest.raises(RoastError) as error:
        assess(dirty,'XX-00')
    assert error.value.code=='NO_ORIGIN'


def test_register_and_rerun_no_double_detain(client,archived):
    first=register(client,archived)
    assert first.status_code==201 and not first.json['reused']
    again=register(client,archived)
    assert again.status_code==200 and again.json['reused']
    record=client.get(f"/api/recalls/{first.json['id']}").json
    assert len(record['assessments'])==1
    assert record['assessments'][0]['scope']['totals']==again.json['recall']['assessments'][0]['scope']['totals']


def test_reassess_after_provenance_supplemented(client,files,archived):
    first=register(client,archived).json['recall']
    pending={key for key,row in first['assessments'][0]['scope']['jobs'].items() if row['status']=='pending'}
    assert 'BA-08' in pending
    files['inputs']='\n'.join(['ticket,work,source_kind,source,quantity,unit',
        'IN-01,BA-01,origin,ET-01,0.6,kg','IN-02,BA-01,origin,BR-08,400,g',
        'IN-03,BA-02,return,RT-A,180,g','IN-04,BA-02,origin,CO-04,320000,mg',
        'IN-05,BA-03,return,RT-A,120,g','IN-06,BA-03,return,RT-B,30,g',
        'IN-07,BA-03,origin,BR-08,150,g','IN-08,BA-04,origin,ET-01,200,g',
        'IN-09,BA-05,return,RT-D,60,g','IN-10,BA-06,return,RT-D,60,g',
        'IN-11,BA-07,origin,CO-04,100,g','IN-12,BA-08,origin,BR-08,70,g',
        'IN-13,BA-09,return,RT-J,50,g','IN-14,BA-10,return,RT-I,50,g'])
    files['outputs']=files['outputs'].replace('PK-H,BA-08,pack,4,8,g','PK-H,BA-08,pack,70,2,g')
    new_run=client.post('/api/runs',json={'files':files}).json['id']
    assert new_run!=archived
    again=register(client,new_run)
    assert again.status_code==200 and not again.json['reused']
    record=again.json['recall']
    assert len(record['assessments'])==2
    latest=record['assessments'][-1]['scope']
    assert latest['jobs']['BA-08']['status']=='confirmed' and latest['jobs']['BA-08']['origin_g']=='2'
    assert latest['packages']['PK-H']['status']=='confirmed' and latest['packages']['PK-H']['origin_g']=='68'
    repeat=register(client,new_run)
    assert repeat.json['reused'] and len(repeat.json['recall']['assessments'])==2


def test_recall_listing(client,archived):
    register(client,archived)
    listed=client.get('/api/recalls').json['recalls']
    assert len(listed)==1 and listed[0]['origin']=='BR-08' and listed[0]['assessments']==1


def test_recall_requires_known_run(client):
    response=client.post('/api/recalls',json={'run':'0'*64,'origin':'BR-08'})
    assert (response.status_code,response.json['code'])==(404,'NO_RUN')


def test_recall_requires_known_origin(client,archived):
    response=client.post('/api/recalls',json={'run':archived,'origin':'XX-00'})
    assert (response.status_code,response.json['code'])==(404,'NO_ORIGIN')


def test_recall_page(client):
    page=client.get('/ledger/recall?origin=BR-08').get_data(as_text=True)
    assert '产地批召回联' in page and '确认涉及' in page and '尚待排除' in page and '可放行' in page
    assert 'PK-G' in page


def test_recall_page_after_register(client,archived):
    recall_id=register(client,archived).json['id']
    page=client.get(f'/ledger/recall?run={archived}&recall={recall_id}').get_data(as_text=True)
    assert 'RC-2026-01' in page and '重跑召回记录' in page
