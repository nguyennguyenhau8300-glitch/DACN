from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import json
import pytest
from test_backend import setup
from main import app
from dependencies import get_current_user
from models.iot_device import IotDevice,IotEvent
from models.internal_demo import InternalDemoRun
from models.operations import ParkingSession,Payment,PricingRule
from models.parking_spot import ParkingSpot
from models.extensions import BarrierCommand,SandboxOrder
from services import ai_service
from services.iot_service import is_fresh
from services.parking_service import now


def ready(c,db):
    assert c.post('/parking-lots/1/initialize-layout').status_code==200
    for spot in db.query(ParkingSpot).filter_by(energy_type='ELECTRIC'):spot.charger_status='READY'
    db.add(PricingRule(parking_lot_id=1,vehicle_type='CAR',energy_type='ELECTRIC',first_hour_price=10000,additional_hour_price=5000));db.commit()


def accepted(monkeypatch,tmp_path):
    from ai_engine import recognizer
    from services.internal_demo import sample
    item,_=sample('car_electric_clear')
    monkeypatch.setattr(recognizer,'recognize',lambda *args,**kwargs:{'plate':item['plate'],'confidence':.98,'needs_review':False,
        'detections':[{'box':[100,110,410,235],'confidence':.95}],'candidates':[]})
    monkeypatch.setattr(ai_service,'image_dir',lambda:tmp_path)


def test_internal_sensor_is_persistent_and_idempotent_without_transport(setup):
    c,db,a,u,s,v=setup;ident=str(uuid4());body={'request_id':ident,'parking_spot_id':s.id,'sensor_status':'OCCUPIED'}
    r=c.post('/api/v1/iot/simulate-sensor',json=body);assert r.status_code==200,r.text
    assert s.status=='OCCUPIED' and db.query(IotEvent).count()==1
    device=db.query(IotDevice).one();assert device.simulation_only
    device.last_seen_at=device.last_telemetry_at=now()-timedelta(days=1);db.commit();assert is_fresh(device)
    assert c.post('/api/v1/iot/simulate-sensor',json=body).status_code==200 and db.query(IotEvent).count()==1
    assert c.post('/api/v1/iot/simulate-sensor',json={**body,'sensor_status':'AVAILABLE'}).status_code==409
    body.update(request_id=str(uuid4()),sensor_status='AVAILABLE')
    assert c.post('/api/v1/iot/simulate-sensor',json=body).status_code==200 and s.status=='AVAILABLE'


def test_internal_sensor_does_not_release_an_active_session(setup):
    c,db,a,u,s,v=setup
    assert c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id}).status_code==201
    assert c.post('/api/v1/iot/simulate-sensor',json={'parking_spot_id':s.id,'sensor_status':'AVAILABLE'}).status_code==200
    assert s.status=='OCCUPIED'


def test_internal_controls_cannot_replace_protocol_devices(setup):
    c,db,a,u,s,v=setup
    d=c.post('/iot/devices',json={'device_code':'REAL-SENSOR','parking_spot_id':s.id,'kind':'SENSOR'});assert d.status_code==201
    assert c.post('/api/v1/iot/simulate-sensor',json={'parking_spot_id':s.id,'sensor_status':'OCCUPIED'}).status_code==409
    assert s.status=='AVAILABLE' and db.query(InternalDemoRun).count()==0


def test_internal_charger_records_heat_and_recovers(setup):
    c,db,a,u,s,v=setup;ready(c,db)
    spot=db.query(ParkingSpot).filter_by(energy_type='ELECTRIC',spot_type='CAR').first()
    r=c.post('/api/v1/iot/simulate-charger',json={'parking_spot_id':spot.id,'scenario':'OVERHEAT'});assert r.status_code==200,r.text
    assert db.query(IotDevice).filter_by(kind='CHARGER').one().last_payload['temperature_c']==70
    alerts=c.get('/alerts?parking_lot_id=1&status=OPEN').json()['items'];assert any(a['kind']=='OVERHEAT' for a in alerts)
    assert c.post('/api/v1/iot/simulate-charger',json={'parking_spot_id':spot.id,'scenario':'READY'}).status_code==200
    assert not c.get('/alerts?parking_lot_id=1&status=OPEN').json()['items']
    assert c.post('/api/v1/iot/simulate-charger',json={'parking_spot_id':s.id,'scenario':'CHARGING'}).status_code==422


def test_presets_real_business_qr_payment_and_gate(setup,monkeypatch,tmp_path):
    c,db,a,u,s,v=setup;ready(c,db);accepted(monkeypatch,tmp_path)
    body={'parking_lot_id':1,'request_id':str(uuid4())}
    entered=c.post('/internal-simulation/presets/entry',json=body);assert entered.status_code==200,entered.text
    entered=entered.json();assert entered['status']=='DONE',entered
    sid=entered['parking_session_id'];session=db.get(ParkingSession,sid);spot=db.get(ParkingSpot,session.parking_spot_id)
    assert spot.status=='OCCUPIED' and session.entry_plate_image
    assert c.get(entered['result']['crop_url']).status_code==200
    charger=db.query(IotDevice).filter_by(parking_spot_id=spot.id,kind='CHARGER').one()
    assert charger.last_payload['charger_status']=='CHARGING' and charger.last_payload['power_kw']==7
    assert c.post('/internal-simulation/presets/entry',json=body).json()['parking_session_id']==sid
    duplicate=c.post('/internal-simulation/presets/entry',json={**body,'request_id':str(uuid4())}).json()
    assert duplicate['status']=='FAILED' and db.query(ParkingSession).count()==1
    exited=c.post('/internal-simulation/presets/exit',json={'parking_lot_id':1,'parking_session_id':sid}).json()
    assert exited['status']=='AWAITING_PAYMENT' and session.status=='COMPLETED'
    assert spot.status=='OCCUPIED' and db.query(Payment).count()==0
    assert db.query(BarrierCommand).filter_by(direction='EXIT').count()==0
    assert c.get(exited['checkout']['qr_url']).headers['content-type']=='image/png'
    path='/internal-simulation/runs/'+exited['id']+'/confirm-payment'
    assert c.post(path).json()['status']=='DONE'
    assert c.post(path).json()['status']=='DONE'
    assert spot.status=='AVAILABLE' and db.query(Payment).count()==1
    assert db.query(BarrierCommand).filter_by(direction='EXIT').count()==1
    assert db.query(Payment).one().transaction_code.startswith('SANDBOX-INTERNAL-')
    assert Decimal(c.get('/reports/summary').json()['revenue'])==0


def test_failed_ai_does_not_create_sessions_or_signals(setup,monkeypatch):
    from ai_engine import recognizer
    c,db,*_=setup;ready(c,db)
    monkeypatch.setattr(recognizer,'recognize',lambda *args:{'plate':None,'needs_review':True,'confidence':0})
    r=c.post('/internal-simulation/presets/entry',json={'parking_lot_id':1})
    assert r.json()['status']=='FAILED' and db.query(ParkingSession).count()==0 and db.query(IotEvent).count()==0


def test_cash_payment_can_finish_an_internal_exit_without_leaving_an_active_qr(setup,monkeypatch,tmp_path):
    c,db,a,u,s,v=setup;ready(c,db);accepted(monkeypatch,tmp_path)
    entered=c.post('/internal-simulation/presets/entry',json={'parking_lot_id':1}).json()
    sid=entered['parking_session_id']
    exited=c.post('/internal-simulation/presets/exit',json={'parking_lot_id':1,'parking_session_id':sid}).json()
    assert c.post('/payments',json={'parking_session_id':sid}).status_code==201
    assert db.get(InternalDemoRun,exited['id']).status=='DONE'
    assert db.query(SandboxOrder).one().status=='CANCELLED'
    assert db.get(ParkingSpot,db.get(ParkingSession,sid).parking_spot_id).status=='AVAILABLE'


def test_internal_exit_cannot_end_normal_customer_sessions(setup):
    c,db,a,u,s,v=setup
    r=c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id});sid=r.json()['id']
    assert c.post('/internal-simulation/presets/exit',json={'parking_lot_id':1,'parking_session_id':sid}).status_code==409
    assert db.get(ParkingSession,sid).status=='ACTIVE'


def test_internal_panel_is_management_only_and_samples_staff_only(setup):
    c,db,a,u,s,v=setup
    samples=c.get('/ai/samples').json()
    kinds={row['id']:row['vehicle_type'] for row in samples}
    assert len(kinds)==len(samples)
    assert {'blank','car_electric_clear','motorbike_gas_clear'}<=kinds.keys()
    assert kinds['demo_car_scene']=='CAR'
    assert kinds['demo_motorbike_scene']=='MOTORBIKE'
    for ident in ('demo_car_scene','demo_motorbike_scene'):
        sample=c.get('/ai/samples/'+ident+'/image')
        assert sample.status_code==200 and sample.headers['content-type']=='image/jpeg'
    assert c.get('/ai/samples/unknown/image').status_code==404
    app.dependency_overrides[get_current_user]=lambda:u
    for path in ['/internal-simulation/state?parking_lot_id=1','/ai/samples']:
        assert c.get(path).status_code==403
    assert c.get('/ai/samples/demo_car_scene/image').status_code==403
    assert c.post('/internal-simulation/presets/entry',json={'parking_lot_id':1}).status_code==403
    assert c.post('/api/v1/iot/simulate-sensor',json={'parking_spot_id':s.id,'sensor_status':'OCCUPIED'}).status_code==403


def test_gate_opens_for_four_seconds_from_actual_open_time(setup):
    from services.barrier_service import advance
    c,db,a,u,s,v=setup
    assert c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id}).status_code==201
    gate=db.query(BarrierCommand).one();gate.created_at=now()-timedelta(minutes=1);db.commit()
    advance(db);assert gate.status=='SIMULATED_OPEN' and gate.opened_at
    advance(db);assert gate.status=='SIMULATED_OPEN'
    gate.opened_at=now()-timedelta(seconds=5);db.commit();advance(db);assert gate.status=='SIMULATED_CLOSED'
