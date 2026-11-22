from datetime import timedelta,datetime
from decimal import Decimal
from urllib.parse import urlsplit,parse_qs
import pytest
from fastapi import HTTPException
from test_backend import setup
from main import app
from dependencies import get_current_user
from models.extensions import SandboxOrder,TariffSchedule,BarrierCommand
from models.operations import ParkingSession,Payment,PricingRule
from models.parking_area import ParkingArea
from models.parking_spot import ParkingSpot
from services.parking_service import now,calculate_fee
from services.navigation_service import shortest_paths
from services.payment_gateway import sign_vnpay

def complete(db,v,s):
    row=ParkingSession(vehicle_id=v.id,parking_spot_id=s.id,entry_time=now()-timedelta(hours=2),exit_time=now(),status='COMPLETED',total_amount=Decimal('7000.00'))
    db.add(row);db.commit();return row

def test_schematic_recommendation_respects_ownership_and_occupancy(setup):
    c,db,a,u,s,v=setup
    lot=db.get(ParkingArea,s.parking_area_id).parking_lot_id
    graph=c.get(f'/parking-lots/{lot}/map').json()
    assert graph['schematic'] and graph['revision']==0
    r=c.get(f'/parking-lots/{lot}/recommendation',params={'vehicle_id':v.id})
    assert r.status_code==200,r.text
    candidate=r.json()['candidates'][0]
    assert candidate['spot_id']==s.id and candidate['route'][0]=='gate' and candidate['walking_route'][-1]=='lift'
    s.status='RESERVED';db.commit()
    assert c.get(f'/parking-lots/{lot}/recommendation',params={'vehicle_id':v.id}).json()['candidates']==[]
    app.dependency_overrides[get_current_user]=lambda:u
    v.user_id=a.id;db.commit()
    assert c.get(f'/parking-lots/{lot}/recommendation',params={'vehicle_id':v.id}).status_code==403

def test_map_revision_validation_and_blocked_path(setup):
    c,db,a,u,s,v=setup
    lot=db.get(ParkingArea,s.parking_area_id).parking_lot_id
    route=f'/parking-lots/{lot}/map';graph=c.get(route).json()
    payload={k:graph[k] for k in ['name','units','nodes','edges','revision']}
    payload['edges'][0]['blocked']=True
    assert c.put(route,json=payload).status_code==200
    assert c.put(route,json=payload).status_code==409
    assert c.get(f'/parking-lots/{lot}/recommendation',params={'vehicle_id':v.id}).json()['candidates']==[]
    payload['revision']=1;payload['nodes'][0]['spot_id']=s.id
    assert c.put(route,json=payload).status_code==422
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.put(route,json=payload).status_code==403

def test_dijkstra_directed_and_reverse():
    graph={'nodes':[{'id':x} for x in 'ABCD'],'edges':[{'source':'A','target':'B','distance':2,'directed':True},{'source':'A','target':'C','distance':10},{'source':'B','target':'C','distance':1},{'source':'C','target':'D','distance':1,'blocked':True}]}
    dist,_=shortest_paths(graph,'A')
    assert dist['C']==3 and 'D' not in dist
    reverse,_=shortest_paths(graph,'C',True)
    assert reverse['A']==3


def test_recommendation_ranks_before_rounding_display_scores(setup):
    client, db, _, _, first, vehicle = setup
    lot = db.get(ParkingArea, first.parking_area_id).parking_lot_id
    second = ParkingSpot(parking_area_id=first.parking_area_id, spot_code='A02',
                         spot_type='MOTORBIKE', status='AVAILABLE')
    db.add(second)
    db.commit()

    def link(source, target, distance):
        return {'source':source, 'target':target, 'distance':distance, 'directed':True}

    graph = {
        'revision':0, 'units':'mét mô phỏng', 'name':'Kiểm tra chênh lệch điểm nhỏ',
        'nodes':[
            {'id':'gate', 'kind':'ENTRANCE', 'x':0, 'y':0},
            {'id':'lift', 'kind':'DESTINATION', 'x':2, 'y':0},
            {'id':'first', 'kind':'SPOT', 'x':1, 'y':1, 'spot_id':first.id},
            {'id':'second', 'kind':'SPOT', 'x':1, 'y':-1, 'spot_id':second.id},
        ],
        'edges':[
            link('gate','first',10.001), link('first','lift',12.003),
            link('gate','second',10.002), link('second','lift',12.0),
        ],
    }
    saved = client.put(f'/parking-lots/{lot}/map', json=graph)
    assert saved.status_code == 200, saved.text
    reply = client.get(f'/parking-lots/{lot}/recommendation', params={'vehicle_id':vehicle.id})
    assert reply.status_code == 200, reply.text
    candidates = reply.json()['candidates']
    assert [row['score'] for row in candidates] == [22.0, 22.0]
    assert [row['spot_id'] for row in candidates] == [second.id, first.id]


def test_internal_checkout_ownership_signature_idempotency_and_revenue(setup):
    c,db,a,u,s,v=setup
    row=complete(db,v,s)
    app.dependency_overrides[get_current_user]=lambda:u
    made=c.post('/checkout/orders',json={'parking_session_id':row.id})
    assert made.status_code==201,made.text
    data=made.json();assert data['sandbox']
    url=urlsplit(data['checkout_url']);token=parse_qs(url.query)['token'][0]
    assert c.get(url.path+'?token=wrong').status_code==403
    assert c.get(url.path+'?token='+token).status_code==200
    assert c.get(f"/checkout/internal/{data['id']}/qr?token={token}").headers['content-type']=='image/png'
    endpoint=f"/checkout/internal/{data['id']}"
    for _ in range(2): assert c.post(endpoint,data={'token':token,'result':'success'}).status_code==200
    assert db.query(Payment).filter_by(parking_session_id=row.id,status='SUCCESS').count()==1
    assert c.post(endpoint,data={'token':token,'result':'failed'}).status_code==409
    app.dependency_overrides[get_current_user]=lambda:a
    assert Decimal(c.get('/reports/summary').json()['revenue'])==0
    lot=db.get(ParkingArea,s.parking_area_id).parking_lot_id
    report=c.get('/reports/daily',params={'parking_lot_id':lot,'from_date':now().date().isoformat(),'to_date':now().date().isoformat()})
    assert report.status_code==200,report.text
    assert Decimal(report.json()['totals']['sandbox_revenue'])==7000
    assert Decimal(report.json()['totals']['revenue'])==0

@pytest.mark.parametrize('outcome',['failed','expired','cash_first'])
def test_checkout_terminal_states(setup,outcome):
    c,db,a,u,s,v=setup;row=complete(db,v,s)
    made=c.post('/checkout/orders',json={'parking_session_id':row.id}).json()
    url=urlsplit(made['checkout_url']);token=parse_qs(url.query)['token'][0]
    if outcome=='expired':
        # A new signature is necessary because expiry is part of the signed checkout.
        from services.payment_gateway import checkout_token
        order=db.get(SandboxOrder,made['id']);order.expires_at=now()-timedelta(seconds=1);db.commit();token=checkout_token(order)
    if outcome=='cash_first': assert c.post('/payments',json={'parking_session_id':row.id}).status_code==201
    result=c.post(url.path,data={'token':token,'result':'failed' if outcome=='failed' else 'success'})
    assert result.status_code==(200 if outcome=='failed' else 409)
    assert db.query(Payment).filter_by(parking_session_id=row.id,status='SUCCESS').count()==(1 if outcome=='cash_first' else 0)

def test_vnpay_signed_ipn_and_return_does_not_credit(setup,monkeypatch):
    c,db,a,u,s,v=setup;row=complete(db,v,s)
    for key,value in {'VNPAY_TMN_CODE':'TEST-TMN','VNPAY_HASH_SECRET':'unit-test-secret','VNPAY_RETURN_URL':'http://testserver/checkout/vnpay/return'}.items(): monkeypatch.setenv(key,value)
    made=c.post('/checkout/orders',json={'parking_session_id':row.id,'provider':'VNPAY'})
    assert made.status_code==201,made.text
    order=made.json()
    params={'vnp_TxnRef':order['id'],'vnp_TmnCode':'TEST-TMN','vnp_Amount':'700000','vnp_ResponseCode':'00','vnp_TransactionStatus':'00','vnp_TransactionNo':'1234567'}
    params['vnp_SecureHash']=sign_vnpay(params,'unit-test-secret')
    assert c.get('/checkout/vnpay/return',params=params).status_code==200
    assert db.query(Payment).count()==0
    bad={**params,'vnp_Amount':'1'}
    assert c.get('/checkout/vnpay/ipn',params=bad).json()['RspCode']=='97'
    bad['vnp_SecureHash']=sign_vnpay(bad,'unit-test-secret')
    assert c.get('/checkout/vnpay/ipn',params=bad).json()['RspCode']=='04'
    for _ in range(2): assert c.get('/checkout/vnpay/ipn',params=params).json()['RspCode']=='00'
    assert db.query(Payment).count()==1

def test_tariff_validation_midnight_and_freeze(setup):
    c,db,a,u,s,v=setup
    rule=db.query(PricingRule).first()
    bands=[{'start_minute':0,'end_minute':420,'hourly_price':'2000'},{'start_minute':420,'end_minute':1140,'hourly_price':'5000'},{'start_minute':1140,'end_minute':1440,'hourly_price':'2000'}]
    endpoint=f'/pricing-rules/{rule.id}/schedule'
    assert c.put(endpoint,json={'bands':bands[:2]}).status_code==422
    assert c.put(endpoint,json={'bands':bands}).status_code==200
    assert calculate_fee(datetime(2026,10,27,18,30),datetime(2026,10,27,20,31),rule,bands)==9000
    assert calculate_fee(datetime(2026,10,27,23,30),datetime(2026,10,28,1,30),rule,bands)==4000
    entered=c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id})
    assert entered.status_code==201,entered.text
    assert db.query(BarrierCommand).count()==1
    assert c.put(endpoint,json={'bands':[]}).status_code==409

def test_reports_dates_exports_and_access(setup):
    c,db,a,u,s,v=setup
    query={'parking_lot_id':1,'from_date':'2026-10-01','to_date':'2026-10-03'}
    assert len(c.get('/reports/daily',params=query).json()['items'])==3
    r=c.get('/reports/daily',params={**query,'format':'csv'})
    assert r.status_code==200 and r.content.startswith(b'\xef\xbb\xbf')
    assert c.get('/reports/daily',params={**query,'to_date':'2026-09-01'}).status_code==422
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.get('/reports/daily',params=query).status_code==403

def test_mqtt_validation_reuses_telemetry(setup,monkeypatch):
    import services.mqtt_bridge as bridge
    from contextlib import contextmanager
    import json
    c,db,a,u,s,v=setup
    registered=c.post('/iot/devices',json={'device_code':'MQTT-TEST','parking_spot_id':s.id,'kind':'SENSOR'}).json()
    @contextmanager
    def session(): yield db
    monkeypatch.setattr(bridge,'SessionLocal',session)
    envelope={'api_key':registered['api_key'],'telemetry':{'sequence':1,'sensor_status':'OCCUPIED'}}
    result=bridge.process_message('parkly/devices/MQTT-TEST/telemetry',json.dumps(envelope).encode())
    assert result['new_status']=='OCCUPIED'
    assert bridge.process_message('parkly/devices/MQTT-TEST/telemetry',json.dumps(envelope).encode())['duplicate']
    envelope['api_key']='wrong'
    with pytest.raises(HTTPException): bridge.process_message('parkly/devices/MQTT-TEST/telemetry',json.dumps(envelope).encode())

def test_virtual_barrier_waits_for_payment(setup):
    from services.barrier_service import advance
    c,db,a,u,s,v=setup
    entered=c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id}).json()
    advance(db)
    assert db.query(BarrierCommand).one().status=='SIMULATED_OPEN'
    command=db.query(BarrierCommand).one();command.opened_at=now()-timedelta(seconds=5);db.commit();advance(db)
    assert command.status=='SIMULATED_CLOSED'
    assert c.post(f"/parking-sessions/{entered['id']}/check-out",json={}).status_code==200
    assert db.query(BarrierCommand).count()==1
    assert c.post('/payments',json={'parking_session_id':entered['id']}).status_code==201
    assert db.query(BarrierCommand).filter_by(direction='EXIT').one().status=='QUEUED'

def test_websocket_authentication_and_origin(setup,monkeypatch):
    from starlette.websockets import WebSocketDisconnect
    import routers.realtime as sockets
    from contextlib import contextmanager
    from services.auth_service import create_access_token
    c,db,a,u,s,v=setup
    @contextmanager
    def session(): yield db
    monkeypatch.setattr(sockets,'SessionLocal',session)
    monkeypatch.setattr(sockets, 'HEARTBEAT_SECONDS', 0.05)
    token=create_access_token(a.id,a.email,a.role)
    with c.websocket_connect('/ws/events') as ws:
        from services import realtime

        ws.send_json({'token':token})
        ready = ws.receive_json()
        assert ready['type'] == 'ready' and ready['revision']
        realtime.invalidate()
        ping = ws.receive_json()
        assert ping['type'] == 'ping' and ping['revision'] != ready['revision']
    with c.websocket_connect('/ws/events') as ws:
        ws.send_json({'token':'bad'})
        with pytest.raises(WebSocketDisconnect): ws.receive_json()
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect('/ws/events',headers={'origin':'https://untrusted.example'}): pass


def test_realtime_notifies_only_after_a_successful_outer_commit(setup, monkeypatch):
    from contextlib import ExitStack, closing
    from select import select

    from psycopg2 import sql

    from services import realtime

    _, db, _, _, spot, _ = setup
    local = []
    monkeypatch.setattr(realtime, 'invalidate', lambda: local.append('invalidate'))

    with ExitStack() as resources:
        listener = None
        engine = db.get_bind()
        if engine.dialect.name == 'postgresql':
            connection = resources.enter_context(closing(engine.raw_connection()))
            listener = connection.driver_connection
            connection.detach()
            listener.autocommit = True
            with listener.cursor() as cursor:
                cursor.execute("SELECT 'parkly_events_' || md5(current_schema())")
                channel = sql.Identifier(cursor.fetchone()[0])
                cursor.execute(sql.SQL('LISTEN {}').format(channel))

        def received(expected):
            if listener is None:
                return
            if select([listener], [], [], 2 if expected else 0.1)[0]:
                listener.poll()
            assert len(listener.notifies) == expected
            listener.notifies.clear()

        with db.begin():
            with db.begin_nested():
                spot.status = 'OCCUPIED'
                db.flush()
                spot.sensor_code = 'REALTIME-001'
                db.flush()
            assert local == []
            received(0)
        assert local == ['invalidate']
        received(1)

        with db.begin():
            nested = db.begin_nested()
            spot.status = 'AVAILABLE'
            db.flush()
            nested.rollback()
        assert local == ['invalidate']
        received(0)

        with pytest.raises(RuntimeError, match='test rollback'):
            with db.begin():
                spot.status = 'AVAILABLE'
                db.flush()
                raise RuntimeError('test rollback')
        assert local == ['invalidate']
        received(0)


def test_pos_signed_ticket_is_lookup_only_and_staff_scoped(setup):
    c,db,a,u,s,v=setup;row=complete(db,v,s)
    ticket=c.get(f'/parking-sessions/{row.id}/ticket').json()
    assert c.post('/pos/scan',json={'code':ticket['code']}).json()['session']['id']==row.id
    assert c.post('/pos/scan',json={'code':ticket['code'][:-1]+('0' if ticket['code'][-1]!='0' else '1')}).status_code==400
    assert c.get('/pos/ticket/qr',params={'code':ticket['code']}).headers['content-type']=='image/png'
    assert db.query(Payment).count()==0 and db.query(BarrierCommand).count()==0
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.post('/pos/scan',json={'code':ticket['code']}).status_code==403
    assert c.get(f'/parking-sessions/{row.id}/ticket').status_code==200
    v.user_id=a.id;db.commit()
    assert c.get(f'/parking-sessions/{row.id}/ticket').status_code==403
