from contextlib import contextmanager
from datetime import timedelta
import io
import json
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi import WebSocketDisconnect
from PIL import Image
from test_backend import setup
from main import app
from dependencies import get_current_user
from models.simulation import SimulationSite, SimulationAction, CameraObservation
from models.parking_lot import ParkingLot
from models.parking_spot import ParkingSpot
from models.operations import ParkingSession
from models.extensions import BarrierCommand
from models.iot_device import IotDevice
from schemas.iot_device import Telemetry
from services import simulation_service as simulator, live_camera
from services.parking_service import now


def provision(c):
    response=c.post('/simulation/sites');assert response.status_code==201,response.text
    lot_id=response.json()['parking_lot_id']
    assert c.post(f'/simulation/{lot_id}/enabled',json={'enabled':True}).status_code==200
    return lot_id,c.get(f'/simulation/{lot_id}/state').json()


def transport_to_real_telemetry(db,monkeypatch):
    from routers.iot_devices import telemetry
    sent=[]
    def exchange(transport,code,key,payload,port):
        sent.append((transport,payload))
        return telemetry(code,Telemetry.model_validate(payload),key,db)
    monkeypatch.setattr(simulator,'exchange',exchange)
    return sent


def test_demo_site_is_isolated_and_idempotent(setup):
    c,db,a,u,s,v=setup
    lot_id,state=provision(c)
    assert lot_id!=1 and len(state['spots'])==4 and len(state['devices'])==6
    assert state['capacity']['total_capacity']==4
    assert db.get(ParkingLot,1).car_capacity==30 and db.get(ParkingSpot,s.id).status=='AVAILABLE'
    assert c.post('/simulation/sites').json()['parking_lot_id']==lot_id
    assert db.query(SimulationSite).count()==1
    assert 'api_key' not in json.dumps(state) and 'key_hash' not in json.dumps(state)
    assert c.post('/simulation/1/enabled',json={'enabled':True}).status_code==409


@pytest.mark.parametrize('transport',['HTTP','MQTT'])
def test_panel_uses_shared_receiver_and_idempotent_sequences(setup,monkeypatch,transport):
    c,db,a,u,s,v=setup;lot_id,state=provision(c);sent=transport_to_real_telemetry(db,monkeypatch)
    sensor=next(d for d in state['devices'] if d['kind']=='SENSOR')
    body={'request_id':str(uuid4()),'device_id':sensor['id'],'transport':transport,'scenario':'WRONG_VEHICLE'}
    response=c.post(f'/simulation/{lot_id}/actions',json=body);assert response.status_code==200,response.text
    assert response.json()['status']=='ACKNOWLEDGED' and sent[0][0]==transport
    assert c.post(f'/simulation/{lot_id}/actions',json=body).json()['status']=='ACKNOWLEDGED'
    assert len(sent)==1
    assert c.post(f'/simulation/{lot_id}/actions',json={**body,'scenario':'EMPTY'}).status_code==409
    alerts=c.get(f'/alerts?parking_lot_id={lot_id}&status=OPEN').json()['items']
    assert any(a['kind']=='WRONG_PARKING' for a in alerts)
    body.update(request_id=str(uuid4()),scenario='EMPTY')
    assert c.post(f'/simulation/{lot_id}/actions',json=body).json()['sequence']==2
    assert db.get(IotDevice,sensor['id']).last_payload=={'sensor_status':'AVAILABLE'}


def test_offline_waits_for_real_freshness_and_requires_resume(setup,monkeypatch):
    c,db,*_=setup;lot_id,state=provision(c);transport_to_real_telemetry(db,monkeypatch)
    sensor=state['devices'][0];body={'request_id':str(uuid4()),'device_id':sensor['id'],'scenario':'OCCUPIED'}
    assert c.post(f'/simulation/{lot_id}/actions',json=body).status_code==200
    timestamp=db.get(IotDevice,sensor['id']).last_telemetry_at
    assert c.post(f'/simulation/{lot_id}/actions',json={**body,'scenario':'OFFLINE'}).json()['status']=='PAUSED'
    assert db.get(IotDevice,sensor['id']).last_telemetry_at==timestamp
    assert c.post(f'/simulation/{lot_id}/actions',json={**body,'scenario':'EMPTY'}).status_code==409
    assert c.post(f'/simulation/{lot_id}/actions',json={**body,'scenario':'RESUME'}).json()['status']=='RESUMED'


def test_keepalive_cannot_revert_a_newer_panel_state(setup,monkeypatch):
    c,db,*_=setup;lot_id,state=provision(c);transport_to_real_telemetry(db,monkeypatch)
    sensor=state['devices'][0]
    body={'request_id':str(uuid4()),'device_id':sensor['id'],'scenario':'OCCUPIED'}
    assert c.post(f'/simulation/{lot_id}/actions',json=body).json()['status']=='ACKNOWLEDGED'
    # A background tick captured AVAILABLE before the operator changed the state.
    row=simulator.send_action(db,lot_id,sensor['id'],{'sensor_status':'AVAILABLE'},'MQTT',uuid4().hex,8001,'KEEPALIVE')
    assert row.payload=={'sensor_status':'OCCUPIED'}
    assert db.get(IotDevice,sensor['id']).last_payload=={'sensor_status':'OCCUPIED'}


def test_wokwi_export_is_admin_only_and_pauses_duplicate_publisher(setup):
    c,db,a,u,s,v=setup;lot_id,state=provision(c);sensor=state['devices'][0]
    r=c.post(f'/simulation/{lot_id}/wokwi-config',json={'device_id':sensor['id']})
    assert r.status_code==200 and '#define DEVICE_SEQUENCE_START 1000ULL' in r.text
    assert '#define DEVICE_API_KEY' in r.text and 'no-store' in r.headers['cache-control']
    assert sensor['id'] in db.get(SimulationSite,lot_id).paused_devices
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.post(f'/simulation/{lot_id}/wokwi-config',json={'device_id':sensor['id']}).status_code==403
    for endpoint in ['/simulation/sites',f'/simulation/{lot_id}/state','/simulation/observations?parking_lot_id=1']:
        assert c.get(endpoint).status_code==403
    assert c.get('/simulation/firmware/sensor').status_code==403


def test_stream_evidence_crops_and_links_the_actual_transaction(setup,monkeypatch,tmp_path):
    c,db,a,u,s,v=setup;lot_id,state=provision(c)
    monkeypatch.setattr(live_camera,'evidence_path',lambda ident:tmp_path/(ident+'.jpg'))
    from routers.iot_devices import telemetry
    for d in simulator.site_devices(db,lot_id):
        payload={'sensor_status':'AVAILABLE'} if d.kind=='SENSOR' else {'charger_status':'READY','temperature_c':30}
        telemetry(d.device_code,Telemetry(sequence=1,**payload),simulator.device_key(d.device_code),db)
    plate=json.loads((simulator.ROOT/'backend/ai_engine/assets/camera-demo.json').read_text())['plates'][0]
    result={'plate':plate,'confidence':.98,'needs_review':False,'detections':[{'box':[30,40,150,100],'confidence':.96}]}
    buffer=io.BytesIO();Image.new('RGB',(640,384),'white').save(buffer,format='JPEG');jpeg=buffer.getvalue()
    observed=now()-timedelta(milliseconds=150)
    row=live_camera.record_evidence(db,lot_id,a.id,result,jpeg,42,observed,'ENTRY')
    assert row.outcome=='CHECKED_IN' and row.parking_session_id
    session=db.get(ParkingSession,row.parking_session_id)
    assert session.entry_plate_image==f'/simulation/observations/{row.id}/image'
    assert Image.open(tmp_path/(row.id+'.jpg')).size==(120,60)
    assert row.captured_at==observed and row.frame_id==42
    assert c.get(f'/simulation/observations/{row.id}/image').status_code==200
    duplicate=live_camera.record_evidence(db,lot_id,a.id,result,jpeg,43,now(),'ENTRY')
    assert duplicate.outcome=='REJECTED' and db.query(ParkingSession).count()==1
    exit_row=live_camera.record_evidence(db,lot_id,a.id,result,jpeg,44,now(),'EXIT')
    assert exit_row.outcome=='CHECKED_OUT' and exit_row.parking_session_id==session.id
    assert db.query(BarrierCommand).filter_by(direction='EXIT').count()==0
    assert c.post('/payments',json={'parking_session_id':session.id}).status_code==201
    assert db.query(BarrierCommand).filter_by(direction='EXIT').count()==1
    assert len(c.get(f'/simulation/observations?parking_lot_id={lot_id}').json())==3
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.get(f'/simulation/observations/{row.id}/image').status_code==403


def test_stream_socket_rejects_customers_and_untrusted_origin(setup,monkeypatch):
    from routers import simulation
    c,db,a,u,s,v=setup
    monkeypatch.setattr(simulation,'socket_allowed',lambda token:token=='staff-token')
    with c.websocket_connect('/ws/live-camera') as ws:
        ws.send_json({'token':'staff-token','parking_lot_id':1})
        assert ws.receive_json()['state']=='STOPPED'
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect('/ws/live-camera') as ws:
            ws.send_json({'token':'customer-token','parking_lot_id':1});ws.receive_json()
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect('/ws/live-camera',headers={'origin':'https://untrusted.example'}) as ws:ws.receive_json()
