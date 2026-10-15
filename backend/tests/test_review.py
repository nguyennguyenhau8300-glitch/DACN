from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from test_backend import setup
from test_ai import png,box
from dependencies import get_current_user
from main import app
from models.parking_lot import ParkingLot
from models.parking_spot import ParkingSpot
from models.operations import ParkingSession
from models.reservation import Reservation
from ai_engine.recognizer import recognize
from services.parking_service import now

def booking(v,s):
    start=now()+timedelta(minutes=5)
    return {'vehicle_id':v.id,'parking_spot_id':s.id,'start_time':start.isoformat(),'expiry_time':(start+timedelta(hours=1)).isoformat()}

def test_plate_format_duplicate(setup):
    c,db,a,u,s,v=setup
    r=c.post('/vehicles',json={'license_plate':'59A112345','vehicle_type':'MOTORBIKE'})
    assert r.status_code in {400,409},r.text

def test_inactive_lot_booking(setup):
    c,db,a,u,s,v=setup
    lot=db.query(ParkingLot).first();lot.is_active=False;db.commit()
    r=c.post('/reservations',json=booking(v,s))
    assert r.status_code==409,r.text

def test_vehicle_cannot_hold_two_spots(setup):
    c,db,a,u,s,v=setup
    s2=ParkingSpot(parking_area_id=s.parking_area_id,spot_code='A02',spot_type='MOTORBIKE',status='AVAILABLE');db.add(s2);db.commit()
    assert c.post('/reservations',json=booking(v,s)).status_code==201
    assert c.post('/reservations',json=booking(v,s2)).status_code==409

def test_walkin_cannot_bypass_other_reservation(setup):
    c,db,a,u,s,v=setup
    s2=ParkingSpot(parking_area_id=s.parking_area_id,spot_code='A02',spot_type='MOTORBIKE',status='AVAILABLE');db.add(s2);db.commit()
    assert c.post('/reservations',json=booking(v,s)).status_code==201
    assert c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s2.id}).status_code==409

@pytest.mark.parametrize('path,body',[('/parking-areas/1',{'name':None}),('/parking-lots/1',{'name':'   '}),('/parking-spots/1',{'spot_code':' '}),('/vehicles/1',{'license_plate':'     '})])
def test_required_input_fields(setup,path,body):
    c,db,a,u,s,v=setup
    if path.startswith('/vehicles'):app.dependency_overrides[get_current_user]=lambda:u
    assert c.put(path,json=body).status_code==422

def test_cancel_retains_physical_occupancy(setup):
    c,db,a,u,s,v=setup
    r=c.post('/reservations',json=booking(v,s));assert r.status_code==201
    assert c.post('/iot/sensor',headers={'X-API-Key':'test-device-key'},json={'sensor_code':s.sensor_code,'sensor_status':'OCCUPIED'}).status_code==200
    assert c.patch('/reservations/'+str(r.json()['id'])+'/cancel').status_code==200
    assert s.status=='OCCUPIED'

def test_ocr_threshold_uses_unrounded_score():
    output=SimpleNamespace(txts=['30A12345'],scores=[.84999],boxes=[box(0,0,100,40)])
    with patch('ai_engine.recognizer._get_engine',return_value=lambda _:output):r=recognize(png())
    assert r['needs_review'] and r['reason']=='low_confidence'

def test_too_many_ocr_regions_requires_review():
    output=SimpleNamespace(txts=['30A12345']+['noise']*80+['59A112345'],scores=[.99]*82,
        boxes=[box(0,i*40,100,30) for i in range(82)])
    with patch('ai_engine.recognizer._get_engine',return_value=lambda _:output):r=recognize(png())
    assert r['needs_review'] and r['reason']=='too_many_regions'


def test_admin_booking_visible_to_vehicle_owner(setup):
    c,db,a,u,s,v=setup
    r=c.post('/reservations',json=booking(v,s));assert r.status_code==201
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.get('/reservations/'+str(r.json()['id'])).status_code==200

def test_expiry_uses_recent_sensor_not_old_occupancy(setup):
    from models.sensor_log import SensorLog
    c,db,a,u,s,v=setup
    db.add(SensorLog(parking_spot_id=s.id,sensor_status='OCCUPIED',recorded_at=now()-timedelta(days=1)));db.commit()
    r=c.post('/reservations',json=booking(v,s));assert r.status_code==201
    row=db.get(Reservation,r.json()['id']);row.start_time=now()-timedelta(minutes=2);row.expiry_time=now()-timedelta(minutes=1);db.commit()
    assert c.post('/reservations/expire').json()['expired']==1
    assert s.status=='AVAILABLE'

def test_history_preserves_vehicle_identity(setup):
    c,db,a,u,s,v=setup
    r=c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id});sid=r.json()['id']
    assert c.post(f'/parking-sessions/{sid}/check-out',json={}).status_code==200
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.put('/vehicles/'+str(v.id),json={'license_plate':'30A99999'}).status_code==409
    assert c.put('/vehicles/'+str(v.id),json={'brand':'Honda'}).status_code==200

def test_fee_overflow_keeps_active_session(setup):
    from models.operations import PricingRule
    c,db,a,u,s,v=setup
    price=db.query(PricingRule).first();price.first_hour_price=price.additional_hour_price=9999999999;db.commit()
    r=c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id});sid=r.json()['id']
    row=db.get(ParkingSession,sid);row.entry_time=now()-timedelta(hours=2);db.commit()
    assert c.post(f'/parking-sessions/{sid}/check-out',json={}).status_code==409
    db.refresh(row);assert row.status=='ACTIVE' and row.exit_time is None

def test_sensor_logs_are_staff_only(setup):
    c,db,a,u,s,v=setup
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.get('/iot/sensor-logs').status_code==403

def test_health_ready_checks_db(setup):
    c,*_=setup
    assert c.get('/health/ready').json()['status']=='ready'

def test_ocr_does_not_strip_unknown_symbols():
    output=SimpleNamespace(txts=['30A12345雪'],scores=[.99],boxes=[box(0,0,100,40)])
    with patch('ai_engine.recognizer._get_engine',return_value=lambda _:output):r=recognize(png())
    assert r['needs_review'] and r['plate'] is None

def test_evidence_storage_failure_is_503(setup,monkeypatch,tmp_path):
    from services import ai_service
    from test_ai import accepted
    c,db,a,u,s,v=setup
    bad_folder=tmp_path/'not_a_folder';bad_folder.write_text('file')
    monkeypatch.setattr(ai_service,'image_dir',lambda:bad_folder)
    monkeypatch.setattr(ai_service,'recognize',lambda *args:accepted())
    r=c.post('/ai/check-in',files={'file':('p.png',png(),'image/png')},data={'parking_spot_id':s.id})
    assert r.status_code==503,r.text
    assert db.query(ParkingSession).count()==0

def test_ai_failed_database_commit_removes_image(setup,monkeypatch,tmp_path):
    from services import ai_service
    from test_ai import accepted
    from sqlalchemy.exc import OperationalError
    c,db,a,u,s,v=setup
    monkeypatch.setattr(ai_service,'image_dir',lambda:tmp_path)
    monkeypatch.setattr(ai_service,'recognize',lambda *args:accepted())
    real_commit=db.commit
    def fail_only_session_commit():
        if db.query(ParkingSession).first():
            raise OperationalError('commit',{},Exception('unavailable'))
        real_commit()
    monkeypatch.setattr(db,'commit',fail_only_session_commit)
    r=c.post('/ai/check-in',files={'file':('p.png',png(),'image/png')},data={'parking_spot_id':s.id})
    assert r.status_code==503,r.text
    assert list(tmp_path.iterdir())==[] and db.query(ParkingSession).count()==0
