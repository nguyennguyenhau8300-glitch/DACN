from datetime import timedelta
import json
from pathlib import Path
import sys
import pytest
from test_backend import setup
from main import app
from dependencies import get_current_user
from models.iot_device import IotDevice, IotEvent
from models.sensor_log import SensorLog
from models.parking_spot import ParkingSpot
from models.operations import ParkingSession, PricingRule
from services.parking_service import now
from services.iot_service import hash_key


def register(c, spot, kind='SENSOR', code=None):
    r=c.post('/iot/devices',json={'device_code':code or 'SIM-'+kind,'parking_spot_id':spot.id,'kind':kind,'offline_after_seconds':10})
    assert r.status_code==201,r.text
    return r.json()


def send(c,d,seq=1,**payload):
    return c.post('/iot/devices/'+d['device_code']+'/telemetry',headers={'X-API-Key':d['api_key']},json={'sequence':seq,**payload})


def electric(db,s):
    s.energy_type='ELECTRIC';s.charger_type='SOCKET';s.charger_status='PLANNED'
    s.charging_station_code='STATION';s.charging_port_code='01';db.commit()


def test_registry_auth_and_scope(setup):
    c,db,a,u,s,v=setup
    d=register(c,s)
    assert d['connection_status']=='NEVER_SEEN'
    assert db.get(IotDevice,d['id']).key_hash==hash_key(d['api_key'])
    listed=c.get('/iot/devices').json()
    assert 'api_key' not in listed[0] and 'key_hash' not in listed[0]
    other=ParkingSpot(parking_area_id=s.parking_area_id,spot_code='A02',spot_type='MOTORBIKE',status='AVAILABLE')
    db.add(other);db.commit();d2=register(c,other,code='SECOND')
    assert c.post('/iot/devices/SECOND/telemetry',headers={'X-API-Key':d['api_key']},json={'sequence':1,'sensor_status':'OCCUPIED'}).status_code==401
    assert c.post('/iot/devices/SIM-SENSOR/heartbeat').status_code==401
    assert c.post('/iot/sensor',headers={'X-API-Key':'test-device-key'},json={'sensor_code':s.sensor_code,'sensor_status':'AVAILABLE'}).status_code==409
    assert c.post('/iot/devices',json={'device_code':'DUP','parking_spot_id':s.id,'kind':'SENSOR'}).status_code==409
    assert c.post('/iot/devices',json={'device_code':'CH','parking_spot_id':s.id,'kind':'CHARGER'}).status_code==422
    app.dependency_overrides[get_current_user]=lambda:u
    for path in ['/iot/devices','/iot/events']:
        assert c.get(path).status_code==403
    assert c.post('/iot/devices',json={'device_code':'NO','parking_spot_id':other.id,'kind':'SENSOR'}).status_code==403
    assert c.post('/iot/devices/SIM-SENSOR/rotate-key').status_code==403


def test_sequences_retry_history_and_old_packet(setup):
    c,db,a,u,s,v=setup;d=register(c,s)
    assert send(c,d,1,sensor_status='OCCUPIED').json()['new_status']=='OCCUPIED'
    assert send(c,d,1,sensor_status='OCCUPIED').json()['duplicate'] is True
    assert db.query(SensorLog).count()==1 and db.query(IotEvent).count()==1
    assert send(c,d,1,sensor_status='AVAILABLE').status_code==409
    assert send(c,d,3,sensor_status='AVAILABLE').status_code==200
    assert send(c,d,2,sensor_status='OCCUPIED').status_code==409
    assert send(c,d,1,sensor_status='OCCUPIED').json()['duplicate'] is True
    db.refresh(s);assert s.status=='AVAILABLE'
    events=c.get('/iot/events',params={'device_code':d['device_code'],'limit':1}).json()
    assert events[0]['sequence']==3
    assert c.get('/iot/events',params={'before_id':events[0]['id']}).json()[0]['sequence']==1


def test_offline_heartbeat_does_not_refresh_measurement(setup):
    c,db,a,u,s,v=setup;d=register(c,s)
    payload={'vehicle_id':v.id,'parking_spot_id':s.id}
    assert c.post('/parking-sessions/check-in',json=payload).status_code==409
    assert send(c,d,sensor_status='AVAILABLE').status_code==200
    device=db.get(IotDevice,d['id']);device.last_seen_at=now()-timedelta(seconds=11);device.last_telemetry_at=device.last_seen_at;db.commit()
    row=c.get('/iot/devices').json()[0];assert row['connection_status']=='OFFLINE' and not row['telemetry_fresh']
    h={'X-API-Key':d['api_key']}
    row=c.post('/iot/devices/SIM-SENSOR/heartbeat',headers=h).json()
    assert row['connection_status']=='ONLINE' and not row['telemetry_fresh']
    assert send(c,d,sensor_status='AVAILABLE').json()['duplicate']
    assert c.post('/parking-sessions/check-in',json=payload).status_code==409
    capacity=c.get('/parking-lots/1/capacity').json()
    assert sum(g['available_for_booking'] for g in capacity['groups'])==0
    assert send(c,d,2,sensor_status='AVAILABLE').status_code==200
    assert c.post('/parking-sessions/check-in',json=payload).status_code==201
    assert send(c,d,3,sensor_status='AVAILABLE').json()['new_status']=='OCCUPIED'


def test_disable_rotate_and_reenable(setup):
    c,db,a,u,s,v=setup;d=register(c,s)
    assert send(c,d,sensor_status='AVAILABLE').status_code==200
    assert c.patch('/iot/devices/SIM-SENSOR/access',json={'enabled':False}).json()['connection_status']=='DISABLED'
    assert send(c,d,2,sensor_status='AVAILABLE').status_code==401
    assert c.patch('/iot/devices/SIM-SENSOR/access',json={'enabled':True}).json()['telemetry_fresh'] is False
    rotated=c.post('/iot/devices/SIM-SENSOR/rotate-key').json()
    assert send(c,d,2,sensor_status='AVAILABLE').status_code==401
    d['api_key']=rotated['api_key']
    assert send(c,d,2,sensor_status='AVAILABLE').status_code==200


def test_reservation_maintenance_and_physical_presence(setup):
    c,db,a,u,s,v=setup;d=register(c,s)
    send(c,d,sensor_status='AVAILABLE')
    start=now()+timedelta(minutes=5)
    r=c.post('/reservations',json={'vehicle_id':v.id,'parking_spot_id':s.id,'start_time':start.isoformat(),'expiry_time':(start+timedelta(hours=1)).isoformat()})
    assert r.status_code==201,r.text
    assert send(c,d,2,sensor_status='OCCUPIED').json()['new_status']=='RESERVED'
    assert c.patch('/reservations/'+str(r.json()['id'])+'/cancel').status_code==200
    db.refresh(s);assert s.status=='OCCUPIED'
    s.status='MAINTENANCE';db.commit()
    assert send(c,d,3,sensor_status='AVAILABLE').json()['new_status']=='MAINTENANCE'


def test_charger_commissioning_fault_and_checkout(setup):
    c,db,a,u,s,v=setup;electric(db,s);d=register(c,s,'CHARGER')
    v.energy_type='ELECTRIC';db.add(PricingRule(parking_lot_id=1,vehicle_type='MOTORBIKE',energy_type='ELECTRIC',first_hour_price=6000,additional_hour_price=3000));db.commit()
    assert send(c,d,charger_status='READY',power_kw=0,energy_kwh=0).status_code==200
    db.refresh(s);assert s.charger_status=='PLANNED'
    payload={'vehicle_id':v.id,'parking_spot_id':s.id}
    assert c.post('/parking-sessions/check-in',json=payload).status_code==409
    c.patch(f'/parking-spots/{s.id}/charging-status',json={'charger_status':'READY'})
    assert send(c,d,2,charger_status='FAULT',power_kw=0).status_code==200
    assert c.post('/parking-sessions/check-in',json=payload).status_code==409
    assert c.get('/parking-spots',params={'charging_ready':True}).json()==[]
    assert len(c.get('/parking-spots',params={'charging_ready':False}).json())==1
    assert send(c,d,3,charger_status='READY',power_kw=0).status_code==200
    r=c.post('/parking-sessions/check-in',json=payload);assert r.status_code==201,r.text
    assert send(c,d,4,charger_status='CHARGING',power_kw=0.5,energy_kwh=0.1).status_code==200
    assert send(c,d,5,charger_status='OFFLINE',power_kw=0).status_code==200
    assert c.post('/parking-sessions/'+str(r.json()['id'])+'/check-out',json={}).status_code==200
    db.refresh(s);assert s.status=='AVAILABLE'
    assert c.post('/parking-sessions/check-in',json=payload).status_code==409


@pytest.mark.parametrize('payload',[
    {'sequence':0,'sensor_status':'AVAILABLE'},
    {'sequence':True,'sensor_status':'AVAILABLE'},
    {'sequence':1,'sensor_status':'UNKNOWN'},
    {'sequence':1,'sensor_status':'AVAILABLE','charger_status':'READY'},
    {'sequence':1,'sensor_status':'AVAILABLE','power_kw':1},
    {'sequence':1,'charger_status':'READY','power_kw':1},
    {'sequence':1,'charger_status':'CHARGING','power_kw':-1},
    {'sequence':1,'charger_status':'CHARGING','energy_kwh':-1},
    {'sequence':1,'sensor_status':'AVAILABLE','parking_spot_id':999},
])
def test_payload_validation(setup,payload):
    c,db,a,u,s,v=setup;d=register(c,s)
    assert c.post('/iot/devices/SIM-SENSOR/telemetry',headers={'X-API-Key':d['api_key']},json=payload).status_code==422
    assert db.query(IotEvent).count()==0


def test_wrong_type_power_limit_and_configuration_change(setup):
    c,db,a,u,s,v=setup;electric(db,s);s.charging_power_kw=1;db.commit();d=register(c,s,'CHARGER')
    assert send(c,d,sensor_status='AVAILABLE').status_code==422
    assert send(c,d,charger_status='CHARGING',power_kw=2).status_code==422
    assert c.put(f'/parking-spots/{s.id}',json={'energy_type':'GASOLINE','charger_type':'NONE','charger_status':'NOT_APPLICABLE','charging_station_code':None,'charging_port_code':None,'charging_power_kw':None}).status_code==409


def test_simulator_configure_round_and_replay_restart(setup,tmp_path):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'iot'))
    from simulator import configure,run_round,save_json,make_payload
    c,db,a,u,s,v=setup
    config_path=tmp_path/'config.json'
    config=configure(c,'test',1,config_path)
    assert len(config['devices'])==1
    config=configure(c,'test',1,config_path)
    assert len(config['devices'])==1
    assert run_round(c,config,config_path,'cycle',0)=={'sent':1,'duplicates':0}
    device=config['devices'][0];device['pending']=make_payload(device,'cycle',1);save_json(config_path,config)
    r=c.post('/iot/devices/'+device['device_code']+'/telemetry',headers={'X-API-Key':device['api_key']},json=device['pending'])
    assert r.status_code==200
    restored=json.loads(config_path.read_text(encoding='utf-8'))
    assert run_round(c,restored,config_path,'cycle',2)=={'sent':1,'duplicates':1}
    assert db.query(IotEvent).count()==2
    assert run_round(c,restored,config_path,'cycle',2)=={'sent':1,'duplicates':0}
    db.refresh(s);assert s.status=='AVAILABLE'


def test_occupied_sensor_after_checkout_blocks_rebooking(setup):
    c,db,a,u,s,v=setup;d=register(c,s)
    send(c,d,sensor_status='AVAILABLE')
    payload={'vehicle_id':v.id,'parking_spot_id':s.id}
    r=c.post('/parking-sessions/check-in',json=payload);assert r.status_code==201
    send(c,d,2,sensor_status='OCCUPIED')
    assert c.post('/parking-sessions/'+str(r.json()['id'])+'/check-out',json={}).status_code==200
    assert c.post('/parking-sessions/check-in',json=payload).status_code==409
    groups=c.get('/parking-lots/1/capacity').json()['groups']
    assert sum(g['available_for_booking'] for g in groups)==0
    send(c,d,3,sensor_status='AVAILABLE')
    assert c.post('/parking-sessions/check-in',json=payload).status_code==201


def test_reserved_arrival_can_check_in_when_sensor_sees_car(setup):
    from models.reservation import Reservation
    c,db,a,u,s,v=setup;d=register(c,s)
    send(c,d,sensor_status='AVAILABLE')
    start=now()+timedelta(minutes=5)
    r=c.post('/reservations',json={'vehicle_id':v.id,'parking_spot_id':s.id,'start_time':start.isoformat(),'expiry_time':(start+timedelta(hours=1)).isoformat()})
    assert r.status_code==201
    reservation=db.get(Reservation,r.json()['id']);reservation.start_time=now()-timedelta(seconds=1);db.commit()
    send(c,d,2,sensor_status='OCCUPIED')
    assert c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id,'reservation_id':reservation.id}).status_code==201
