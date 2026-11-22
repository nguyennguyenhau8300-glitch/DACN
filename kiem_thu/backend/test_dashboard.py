from test_backend import setup
from main import app
from dependencies import get_current_user
from models.parking_lot import ParkingLot
from models.parking_area import ParkingArea
from models.parking_spot import ParkingSpot
from models.operations import ParkingSession,Payment
from services.parking_service import now

def test_dashboard_staff_read_and_customer_isolation(setup):
    c,db,a,u,s,v=setup
    assert c.get('/dashboard-data/vehicles').json()[0]['license_plate']==v.license_plate
    assert c.get('/dashboard-data/reservations').status_code==200
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.get('/dashboard-data/vehicles').status_code==403
    assert c.get('/dashboard-data/reservations').status_code==403
    assert c.get('/vehicles').json()[0]['id']==v.id
    assert c.get('/users').status_code==403


def test_dashboard_reports_sessions_payments_filter_by_lot(setup):
    c,db,a,u,s,v=setup
    lot=ParkingLot(name='Second',address='Second');db.add(lot);db.flush()
    area=ParkingArea(parking_lot_id=lot.id,name='B');db.add(area);db.flush()
    other=ParkingSpot(parking_area_id=area.id,spot_code='B01',spot_type='MOTORBIKE',status='AVAILABLE');db.add(other);db.flush()
    session=ParkingSession(vehicle_id=v.id,parking_spot_id=other.id,entry_time=now(),exit_time=now(),status='COMPLETED',total_amount=7000);db.add(session);db.flush()
    db.add(Payment(parking_session_id=session.id,amount=7000,payment_method='CASH',status='SUCCESS',paid_at=now()));db.commit()
    q={'parking_lot_id':1}
    assert c.get('/parking-sessions',params=q).json()==[]
    assert c.get('/payments',params=q).json()==[]
    report=c.get('/reports/summary',params=q).json()
    assert float(report['revenue'])==0 and report['completed_sessions']==0 and report['spots']['AVAILABLE']==1
    q={'parking_lot_id':lot.id}
    assert len(c.get('/parking-sessions',params=q).json())==1
    assert len(c.get('/payments',params=q).json())==1
    assert float(c.get('/reports/summary',params=q).json()['revenue'])==7000
    app.dependency_overrides[get_current_user]=lambda:u
    assert len(c.get('/parking-sessions',params=q).json())==1
    assert len(c.get('/payments',params=q).json())==1


def test_spot_availability_includes_telemetry_and_lot_state(setup):
    c,db,a,u,s,v=setup
    assert c.get('/parking-spots').json()[0]['available_for_booking'] is True
    d=c.post('/iot/devices',json={'device_code':'FRONTEND','parking_spot_id':s.id,'kind':'SENSOR'}).json()
    assert c.get('/parking-spots').json()[0]['available_for_booking'] is False
    c.post('/iot/devices/FRONTEND/telemetry',headers={'X-API-Key':d['api_key']},json={'sequence':1,'sensor_status':'AVAILABLE'})
    assert c.get('/parking-spots').json()[0]['available_for_booking'] is True
    lot=db.get(ParkingLot,1);lot.is_active=False;db.commit()
    assert c.get('/parking-spots').json()[0]['available_for_booking'] is False


import pytest
from datetime import timedelta
from models.vehicle import Vehicle

@pytest.mark.parametrize('role',['ADMIN','MANAGER','SECURITY'])
def test_staff_registers_guest_or_customer_vehicle_without_claiming_ownership(setup,role):
    c,db,a,u,s,v=setup;a.role=role;db.commit()
    body={'license_plate':'59A1-88888','vehicle_type':'MOTORBIKE','energy_type':'GASOLINE'}
    guest=c.post('/dashboard-data/vehicles',json=body)
    assert guest.status_code==201,guest.text
    assert guest.json()['user_id'] is None
    customer=c.post('/dashboard-data/vehicles',json={**body,'license_plate':'59A1-77777','customer_email':u.email})
    assert customer.status_code==201,customer.text
    assert customer.json()['user_id']==u.id
    start=now()+timedelta(minutes=5)
    booking=c.post('/reservations',json={'vehicle_id':customer.json()['id'],'parking_spot_id':s.id,'start_time':start.isoformat(),'expiry_time':(start+timedelta(hours=2)).isoformat()})
    assert booking.status_code==201,booking.text
    assert booking.json()['user_id']==u.id
    app.dependency_overrides[get_current_user]=lambda:u
    assert customer.json()['id'] in [row['id'] for row in c.get('/vehicles').json()]
    assert guest.json()['id'] not in [row['id'] for row in c.get('/vehicles').json()]
    assert booking.json()['id'] in [row['id'] for row in c.get('/reservations').json()]


def test_customer_registration_api_rejects_invalid_owners_duplicates_and_customer_role(setup):
    c,db,a,u,s,v=setup
    body={'license_plate':'59A1-88888','vehicle_type':'MOTORBIKE','energy_type':'GASOLINE'}
    assert c.post('/dashboard-data/vehicles',json={**body,'customer_email':'missing@example.com'}).status_code==404
    assert c.post('/dashboard-data/vehicles',json={**body,'customer_email':a.email}).status_code==404
    u.is_active=False;db.commit()
    assert c.post('/dashboard-data/vehicles',json={**body,'customer_email':u.email}).status_code==404
    u.is_active=True;db.commit()
    assert c.post('/dashboard-data/vehicles',json={**body,'license_plate':'59a1 12345'}).status_code==409
    assert c.post('/dashboard-data/vehicles',json={**body,'user_id':u.id}).status_code==422
    assert db.query(Vehicle).count()==1
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.post('/dashboard-data/vehicles',json=body).status_code==403
