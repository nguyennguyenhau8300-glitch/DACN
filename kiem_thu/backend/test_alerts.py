from datetime import timedelta
import pytest
from test_backend import setup
from test_iot import register, send, electric
from main import app
from dependencies import get_current_user
from models.incident import Incident
from models.iot_device import IotDevice, IotEvent
from models.operations import ParkingSession
from models.parking_area import ParkingArea
from services.alert_service import sweep_connections
from services.parking_service import now


def journal(c, **params):
    response = c.get('/alerts', params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_heat_hysteresis_acknowledgement_replay_and_recurrence(setup):
    c, db, a, u, s, v = setup
    lot_id = db.get(ParkingArea, s.parking_area_id).parking_lot_id
    electric(db, s);s.charger_status='READY';db.commit()
    d = register(c, s, 'CHARGER')
    hot = {'charger_status':'READY', 'temperature_c':75}
    assert send(c,d,1,**hot).status_code == 200
    rows = journal(c);assert rows['open_count']==1
    incident = rows['items'][0]
    assert incident['kind']=='OVERHEAT' and incident['severity']=='CRITICAL'
    assert not c.get('/parking-spots').json()[0]['available_for_booking']
    assert send(c,d,1,**hot).json()['duplicate'] is True
    assert send(c,d,2,**hot).status_code == 200
    assert db.query(Incident).count()==1
    ack=c.patch(f"/alerts/{incident['id']}/acknowledge")
    assert ack.status_code==200 and ack.json()['acknowledged_by']==a.id
    assert journal(c)['unacknowledged_count']==0
    assert send(c,d,3,charger_status='READY',temperature_c=58).status_code==200
    assert not c.get('/parking-spots').json()[0]['available_for_booking']
    assert send(c,d,4,charger_status='READY').status_code==200
    assert journal(c)['open_count']==1  # Missing temperature is not proof of cooling.
    snapshot = c.get(f'/parking-lots/{lot_id}/snapshot').json()
    assert snapshot['spots'] == c.get('/parking-spots', params={'parking_lot_id': lot_id}).json()
    assert snapshot['capacity'] == c.get(f'/parking-lots/{lot_id}/capacity').json()
    assert not snapshot['spots'][0]['available_for_booking']
    assert send(c,d,5,charger_status='READY',temperature_c=55).status_code==200
    assert journal(c)['open_count']==1
    assert send(c,d,6,charger_status='READY',temperature_c=54.9).status_code==200
    assert c.get('/parking-spots').json()[0]['available_for_booking']
    assert c.get(f'/parking-lots/{lot_id}/snapshot').json()['spots'][0]['available_for_booking']
    resolved=journal(c,status='RESOLVED')['items'][0]
    assert resolved['resolved_at'] and resolved['acknowledged_at'] and resolved['resolution']
    assert c.patch(f"/alerts/{incident['id']}/acknowledge").status_code==409
    assert send(c,d,7,**hot).status_code==200
    assert journal(c)['open_count']==1 and db.query(Incident).count()==2


def test_fault_resolves_on_measurement_and_disable_does_not_claim_a_repair(setup):
    c, db, a, u, s, v = setup;electric(db,s);d=register(c,s,'CHARGER')
    assert send(c,d,charger_status='FAULT',temperature_c=70).status_code==200
    assert journal(c)['open_count']==2
    assert c.patch('/iot/devices/'+d['device_code']+'/access',json={'enabled':False}).status_code==200
    assert journal(c)['open_count']==2
    c.patch('/iot/devices/'+d['device_code']+'/access',json={'enabled':True})
    assert send(c,d,2,charger_status='READY',temperature_c=30).status_code==200
    assert journal(c)['open_count']==0 and len(journal(c,status='RESOLVED')['items'])==2


@pytest.mark.parametrize('spot_type,spot_energy,observed_type,observed_energy',[
    ('CAR','ELECTRIC','CAR','GASOLINE'),
    ('CAR','GASOLINE','MOTORBIKE','GASOLINE'),
    ('MOTORBIKE','ELECTRIC','CAR','ELECTRIC'),
])
def test_wrong_parking_requires_observation_and_recovers_on_correct_or_empty(setup,spot_type,spot_energy,observed_type,observed_energy):
    c,db,a,u,s,v=setup
    if spot_energy=='ELECTRIC':electric(db,s)
    s.spot_type=spot_type
    if spot_type=='CAR' and spot_energy=='ELECTRIC':s.charger_type='EV_CHARGER'
    db.commit();d=register(c,s)
    assert send(c,d,sensor_status='OCCUPIED').status_code==200
    assert journal(c)['open_count']==0
    wrong={'sensor_status':'OCCUPIED','observed_vehicle_type':observed_type,'observed_energy_type':observed_energy}
    assert send(c,d,2,**wrong).status_code==200
    row=journal(c)['items'][0]
    assert row['kind']=='WRONG_PARKING' and row['spot_code']==s.spot_code
    assert row['details']['expected_vehicle_type']==spot_type
    assert db.query(ParkingSession).count()==0
    assert send(c,d,3,sensor_status='OCCUPIED').status_code==200
    assert journal(c)['open_count']==1
    assert send(c,d,4,sensor_status='OCCUPIED',observed_vehicle_type=spot_type,observed_energy_type=spot_energy).status_code==200
    assert journal(c)['open_count']==0
    send(c,d,5,**wrong);send(c,d,6,sensor_status='AVAILABLE')
    assert len(journal(c,status='RESOLVED')['items'])==2


def test_offline_monitor_never_seen_heartbeat_and_recovery(setup):
    c,db,a,u,s,v=setup;d=register(c,s)
    device=db.get(IotDevice,d['id'])
    sweep_connections(db);assert journal(c)['open_count']==0
    device.monitoring_since=now()-timedelta(seconds=11);db.commit()
    sweep_connections(db);sweep_connections(db)
    assert journal(c)['open_count']==1 and db.query(Incident).count()==1
    assert journal(c)['items'][0]['kind']=='CONNECTION_LOST'
    assert c.post('/iot/devices/'+d['device_code']+'/heartbeat',headers={'X-API-Key':d['api_key']}).status_code==200
    assert journal(c)['open_count']==1
    assert send(c,d,sensor_status='AVAILABLE').status_code==200
    assert journal(c)['open_count']==0
    device.last_telemetry_at=now()-timedelta(seconds=11);db.commit();sweep_connections(db)
    assert journal(c)['open_count']==1 and db.query(Incident).count()==2
    c.patch('/iot/devices/'+d['device_code']+'/access',json={'enabled':False})
    assert journal(c)['open_count']==0
    sweep_connections(db);assert journal(c)['open_count']==0


def test_journal_scoping_pagination_and_permissions(setup):
    from models.parking_lot import ParkingLot
    c,db,a,u,s,v=setup;d=register(c,s)
    send(c,d,sensor_status='OCCUPIED',observed_vehicle_type='CAR',observed_energy_type='GASOLINE')
    send(c,d,2,sensor_status='AVAILABLE')
    send(c,d,3,sensor_status='OCCUPIED',observed_vehicle_type='CAR',observed_energy_type='GASOLINE')
    rows=journal(c,status='ALL',limit=1)
    assert rows['total']==2 and rows['open_count']==1 and len(rows['items'])==1
    assert rows['items'][0]['status']=='OPEN'
    assert journal(c,offset=1,limit=1)['items'][0]['status']=='RESOLVED'
    other=ParkingLot(name='Other',address='Other');db.add(other);db.commit()
    assert journal(c,parking_lot_id=other.id)['total']==0
    iid=rows['items'][0]['id']
    a.role='SECURITY';db.commit();assert c.patch(f'/alerts/{iid}/acknowledge').status_code==200
    ack=journal(c,status='ACKNOWLEDGED')['items'][0]['acknowledged_at']
    assert c.patch(f'/alerts/{iid}/acknowledge').json()['acknowledged_at']==ack
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.get('/alerts').status_code==403
    assert c.patch(f'/alerts/{iid}/acknowledge').status_code==403
    assert db.query(Incident).count()==2


@pytest.mark.parametrize('payload',[
    {'charger_status':'READY','temperature_c':'NaN'},
    {'charger_status':'READY','temperature_c':201},
    {'sensor_status':'AVAILABLE','observed_vehicle_type':'CAR','observed_energy_type':'GASOLINE'},
    {'sensor_status':'OCCUPIED','observed_vehicle_type':'CAR'},
    {'sensor_status':'OCCUPIED','temperature_c':60},
    {'charger_status':'READY','observed_vehicle_type':'CAR','observed_energy_type':'ELECTRIC'},
])
def test_invalid_alert_telemetry_never_creates_events(setup,payload):
    c,db,a,u,s,v=setup;d=register(c,s)
    assert send(c,d,**payload).status_code==422
    assert db.query(IotEvent).count()==0 and db.query(Incident).count()==0


@pytest.mark.parametrize('scenario,expected',[
    ('idle',set()), ('overheat',{'OVERHEAT'}), ('charger-fault',{'CHARGER_FAULT'}),
    ('wrong-energy',{'WRONG_PARKING'}), ('wrong-vehicle-type',{'WRONG_PARKING'}),
])
def test_simulator_scenarios_reach_real_alert_pipeline(setup,tmp_path,scenario,expected):
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'DACN'/'backend'/'iot'))
    from simulator import configure,run_round
    c,db,a,u,s,v=setup;electric(db,s);s.charger_status='READY';db.commit()
    path=tmp_path/'devices.json';config=configure(c,'test',1,path)
    assert run_round(c,config,path,scenario,0)['sent']==2
    assert {r['kind'] for r in journal(c,status='OPEN')['items']}==expected
    run_round(c,config,path,'idle',1)
    assert journal(c)['open_count']==0
    assert run_round(c,config,path,'connection-loss',2)['sent']==0


def test_overheated_charger_does_not_block_existing_vehicle_checkout(setup):
    from models.operations import PricingRule
    c,db,a,u,s,v=setup;electric(db,s);s.charger_status='READY';v.energy_type='ELECTRIC'
    db.query(PricingRule).first().energy_type='ELECTRIC';db.commit()
    d=register(c,s,'CHARGER');send(c,d,charger_status='READY',temperature_c=30)
    entry=c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id})
    assert entry.status_code==201,entry.text
    send(c,d,2,charger_status='FAULT',temperature_c=75)
    assert journal(c)['open_count']==2
    response=c.post(f"/parking-sessions/{entry.json()['id']}/check-out",json={})
    assert response.status_code==200,response.text
    assert response.json()['status']=='COMPLETED'
