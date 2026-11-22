import os
if not os.getenv('TEST_POSTGRES'): os.environ['DATABASE_URL']='sqlite://'
os.environ['JWT_SECRET_KEY']='test-secret-only'
os.environ['IOT_API_KEY']='test-device-key'
os.environ['AI_DETECTOR_MODE']='ocr'
os.environ['REDIS_URL']=''
os.environ['MQTT_ENABLED']='0'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'DACN'/'backend'))
from datetime import timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base,get_db
from dependencies import get_current_user
from main import app
from models.user import User
from models.vehicle import Vehicle
from models.parking_lot import ParkingLot
from models.parking_area import ParkingArea
from models.parking_spot import ParkingSpot
from models.operations import PricingRule,ParkingSession
from models.reservation import Reservation
from services.parking_service import now,calculate_fee

@pytest.fixture
def setup():
    schema = None
    if os.getenv('TEST_POSTGRES'):
        from uuid import uuid4
        from sqlalchemy import text
        from database import engine as original_engine
        schema = 'test_backend_' + uuid4().hex
        with original_engine.begin() as conn: conn.execute(text('CREATE SCHEMA '+schema))
        engine=create_engine(original_engine.url,connect_args={'options':'-csearch_path='+schema+' -clock_timeout=5000 -cstatement_timeout=10000'})
    else:
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    if schema:
        ddl=(Path(__file__).resolve().parents[2]/'DACN'/'backend'/'database'/'schema.sql').read_text(encoding='utf-8')
        with engine.begin() as conn: conn.exec_driver_sql(ddl)
    else:
        Base.metadata.create_all(engine)
    db=sessionmaker(bind=engine,expire_on_commit=False)()
    admin=User(full_name='Admin',email='admin@example.com',password_hash='unused',role='ADMIN')
    customer=User(full_name='Customer',email='customer@example.com',password_hash='unused',role='CUSTOMER')
    db.add_all([admin,customer]);db.flush()
    lot=ParkingLot(name='Test',address='Test');db.add(lot);db.flush()
    area=ParkingArea(parking_lot_id=lot.id,name='A');db.add(area);db.flush()
    spot=ParkingSpot(parking_area_id=area.id,spot_code='A01',spot_type='MOTORBIKE',status='AVAILABLE',sensor_code='SENSOR-A01')
    vehicle=Vehicle(user_id=customer.id,license_plate='59A1-12345',vehicle_type='MOTORBIKE')
    db.add_all([spot,vehicle,PricingRule(parking_lot_id=lot.id,vehicle_type='MOTORBIKE',first_hour_price=5000,additional_hour_price=2000)]);db.commit()
    def override_db():
        try:
            yield db
        except Exception:
            db.rollback()
            raise
    app.dependency_overrides[get_db]=override_db
    app.dependency_overrides[get_current_user]=lambda: admin
    client=TestClient(app)
    try:
        yield client,db,admin,customer,spot,vehicle
    finally:
        app.dependency_overrides.clear();db.close();engine.dispose()
        if schema:
            with original_engine.begin() as conn: conn.execute(text('DROP SCHEMA '+schema+' CASCADE'))

def test_full_walk_in_flow(setup):
    c,db,a,u,s,v=setup
    payload={'vehicle_id':v.id,'parking_spot_id':s.id}
    r=c.post('/parking-sessions/check-in',json=payload);assert r.status_code==201,r.text
    sid=r.json()['id'];assert s.status=='OCCUPIED'
    assert c.post('/parking-sessions/check-in',json=payload).status_code==409
    assert c.post('/payments',json={'parking_session_id':sid}).status_code==409
    assert c.post('/iot/sensor',headers={'X-API-Key':'test-device-key'},json={'sensor_code':'SENSOR-A01','sensor_status':'AVAILABLE'}).json()['new_status']=='OCCUPIED'
    row=db.get(ParkingSession,sid);row.entry_time=now()-timedelta(hours=2,minutes=1);db.commit()
    r=c.post(f'/parking-sessions/{sid}/check-out',json={});assert r.status_code==200,r.text
    assert Decimal(r.json()['total_amount'])==9000;assert s.status=='AVAILABLE'
    assert c.post(f'/parking-sessions/{sid}/check-out',json={}).status_code==409
    r=c.post('/payments',json={'parking_session_id':sid});assert r.status_code==201,r.text
    assert r.json()['status']=='SUCCESS'
    assert c.post('/payments',json={'parking_session_id':sid}).status_code==409
    assert c.get('/reports/summary').json()['revenue']=='9000.00'

def test_reservation_and_sensor(setup):
    c,db,a,u,s,v=setup
    future=now()+timedelta(minutes=5)
    r=c.post('/reservations',json={'vehicle_id':v.id,'parking_spot_id':s.id,'start_time':future.isoformat(),'expiry_time':(future+timedelta(hours=1)).isoformat()})
    assert r.status_code==201,r.text
    rid=r.json()['id'];assert s.status=='RESERVED'
    assert c.post('/iot/sensor',headers={'X-API-Key':'test-device-key'},json={'sensor_code':'SENSOR-A01','sensor_status':'AVAILABLE'}).json()['new_status']=='RESERVED'
    assert c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id,'reservation_id':rid}).status_code==409
    reservation=db.get(Reservation,rid);reservation.start_time=now()-timedelta(minutes=1);db.commit()
    r=c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id,'reservation_id':rid});assert r.status_code==201,r.text
    assert c.patch(f'/reservations/{rid}/cancel').status_code==409
    assert c.post('/parking-sessions/'+str(r.json()['id'])+'/check-out',json={}).status_code==200
    assert reservation.status=='COMPLETED'

def test_expiration_and_access(setup):
    c,db,a,u,s,v=setup
    r=Reservation(user_id=u.id,vehicle_id=v.id,parking_spot_id=s.id,start_time=now()-timedelta(hours=2),expiry_time=now()-timedelta(hours=1),status='CONFIRMED')
    s.status='RESERVED';db.add(r);db.commit()
    assert c.post('/reservations/expire').json()['expired']==1
    assert s.status=='AVAILABLE'
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id}).status_code==403
    assert c.get('/reports/summary').status_code==403
    assert c.post('/iot/sensor',json={'sensor_code':'SENSOR-A01','sensor_status':'AVAILABLE'}).status_code==401

def test_fee_boundaries():
    rule=PricingRule(first_hour_price=5000,additional_hour_price=2000)
    start=now()
    for seconds,expected in [(0,5000),(3600,5000),(3601,7000),(7200,7000),(7201,9000)]:
        assert calculate_fee(start,start+timedelta(seconds=seconds),rule)==expected

def test_input_validation(setup):
    c,*_=setup
    assert c.post('/auth/register',json={'full_name':'Test','email':'test@example.com','password':'ữ'*30}).status_code==422
    assert c.post('/payments',json={'parking_session_id':1,'payment_method':'MOMO'}).status_code==422

def test_customer_privacy(setup):
    c,db,a,u,s,v=setup
    row=c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id}).json()
    other=User(full_name='Other',email='other@example.com',password_hash='unused',role='CUSTOMER')
    db.add(other);db.commit()
    app.dependency_overrides[get_current_user]=lambda:other
    assert c.get('/parking-sessions').json()==[]
    assert c.get('/parking-sessions/'+str(row['id'])).status_code==403
    assert c.get('/users').status_code==403

def test_price_and_user_guards(setup):
    c,db,a,u,s,v=setup
    price=db.query(PricingRule).first()
    data={'parking_lot_id':price.parking_lot_id,'vehicle_type':'MOTORBIKE','first_hour_price':'6000','additional_hour_price':'2000'}
    assert c.post('/pricing-rules',json=data).status_code==409
    assert c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':s.id}).status_code==201
    assert c.put('/pricing-rules/'+str(price.id),json=data).status_code==409
    assert c.patch('/users/'+str(a.id)+'/access',json={'role':'CUSTOMER','is_active':True}).status_code==409

def test_real_auth(setup):
    c,db,*_=setup
    r=c.post('/auth/register',json={'full_name':'New User','email':'new@example.com','password':'password123'})
    assert r.status_code==201,r.text
    r=c.post('/auth/login',json={'email':'new@example.com','password':'password123'})
    assert r.status_code==200,r.text
    token=r.json()['access_token']
    app.dependency_overrides.pop(get_current_user)
    assert c.get('/auth/me',headers={'Authorization':'Bearer '+token}).status_code==200
    assert c.get('/auth/me',headers={'Authorization':'Bearer invalid'}).status_code==401
