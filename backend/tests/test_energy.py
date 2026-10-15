from datetime import timedelta
from decimal import Decimal
import pytest
from test_backend import setup
from models.parking_spot import ParkingSpot
from models.parking_lot import ParkingLot
from models.vehicle import Vehicle
from models.operations import ParkingSession,PricingRule
from main import app
from dependencies import get_current_user
from services.parking_service import now

def initialize(c):
    r=c.post('/parking-lots/1/initialize-layout');assert r.status_code==200,r.text
    return r.json()

def test_exact_capacity_and_idempotent_layout(setup):
    c,db,a,u,s,v=setup
    data=initialize(c)
    assert data['total_capacity']==170 and data['total_configured_spots']==170
    assert data['created_spots']==169
    assert {(g['vehicle_type'],g['energy_type']):g['configured_spots'] for g in data['groups']}=={
        ('CAR','GASOLINE'):30,('CAR','ELECTRIC'):20,('MOTORBIKE','GASOLINE'):70,('MOTORBIKE','ELECTRIC'):50}
    assert db.query(ParkingSpot).filter_by(charger_type='EV_CHARGER').count()==20
    assert db.query(ParkingSpot).filter_by(charger_type='SOCKET').count()==50
    assert initialize(c)['created_spots']==0
    assert db.query(ParkingSpot).count()==170

@pytest.mark.parametrize('vt',['CAR','MOTORBIKE'])
@pytest.mark.parametrize('energy',['GASOLINE','ELECTRIC'])
def test_register_four_categories(setup,vt,energy):
    c,db,a,u,s,v=setup
    r=c.post('/vehicles',json={'license_plate':'30A98765','vehicle_type':vt,'energy_type':energy})
    assert r.status_code==201,r.text
    assert r.json()['vehicle_type']==vt and r.json()['energy_type']==energy

def test_capacity_limit_and_invalid_plan(setup):
    c,db,a,u,s,v=setup
    initialize(c)
    r=c.post('/parking-spots',json={'parking_area_id':s.parking_area_id,'spot_code':'EXTRA','spot_type':'MOTORBIKE'})
    assert r.status_code==409,r.text
    assert c.put('/parking-lots/1',json={'car_capacity':30}).status_code==409
    assert c.put('/parking-lots/1',json={'electric_car_capacity':51}).status_code==422

def test_electric_point_requires_charging_details(setup):
    c,db,a,u,s,v=setup
    r=c.post('/parking-spots',json={'parking_area_id':s.parking_area_id,'spot_code':'E01','spot_type':'MOTORBIKE','energy_type':'ELECTRIC'})
    assert r.status_code==422,r.text

@pytest.mark.parametrize('vt',['CAR','MOTORBIKE'])
def test_electric_booking_checkin_pricing_and_fault(setup,vt):
    c,db,a,u,s,v=setup
    initialize(c)
    electric=db.query(ParkingSpot).filter_by(spot_type=vt,energy_type='ELECTRIC').first()
    gas=db.query(ParkingSpot).filter_by(spot_type=vt,energy_type='GASOLINE').first()
    vehicle=Vehicle(user_id=u.id,license_plate='30A98765',vehicle_type=vt,energy_type='ELECTRIC');db.add(vehicle);db.commit()
    start=now()+timedelta(minutes=5)
    data={'vehicle_id':vehicle.id,'parking_spot_id':electric.id,'start_time':start.isoformat(),'expiry_time':(start+timedelta(hours=1)).isoformat()}
    assert c.post('/reservations',json=data).status_code==409
    assert c.patch(f'/parking-spots/{electric.id}/charging-status',json={'charger_status':'READY'}).status_code==200
    assert c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':electric.id}).status_code==400
    assert c.post('/parking-sessions/check-in',json={'vehicle_id':vehicle.id,'parking_spot_id':gas.id}).status_code==400
    price={'parking_lot_id':1,'vehicle_type':vt,'energy_type':'ELECTRIC','first_hour_price':8000,'additional_hour_price':3000}
    assert c.post('/pricing-rules',json=price).status_code==201
    r=c.post('/parking-sessions/check-in',json={'vehicle_id':vehicle.id,'parking_spot_id':electric.id});assert r.status_code==201,r.text
    sid=r.json()['id']
    assert c.patch(f'/parking-spots/{electric.id}/charging-status',json={'charger_status':'OFFLINE'}).status_code==200
    r=c.post(f'/parking-sessions/{sid}/check-out',json={});assert r.status_code==200,r.text
    assert Decimal(r.json()['total_amount'])==8000
    assert c.post('/reservations',json=data).status_code==409

def test_pricing_categories_are_separate(setup):
    c,db,a,u,s,v=setup
    data={'parking_lot_id':1,'vehicle_type':'MOTORBIKE','energy_type':'ELECTRIC','first_hour_price':8000,'additional_hour_price':3000}
    assert c.post('/pricing-rules',json=data).status_code==201
    assert c.post('/pricing-rules',json=data).status_code==409
    assert db.query(PricingRule).filter_by(vehicle_type='MOTORBIKE',is_active=True).count()==2

def test_customer_cannot_commission_charging_point(setup):
    c,db,a,u,s,v=setup
    initialize(c);electric=db.query(ParkingSpot).filter_by(energy_type='ELECTRIC').first()
    app.dependency_overrides[get_current_user]=lambda:u
    assert c.patch(f'/parking-spots/{electric.id}/charging-status',json={'charger_status':'READY'}).status_code==403
    assert c.post('/parking-lots/1/initialize-layout').status_code==403


def test_electric_reservation_flow(setup):
    from models.reservation import Reservation
    c,db,a,u,s,v=setup
    initialize(c);v.energy_type='ELECTRIC';db.commit()
    e=db.query(ParkingSpot).filter_by(spot_type='MOTORBIKE',energy_type='ELECTRIC').first()
    c.patch(f'/parking-spots/{e.id}/charging-status',json={'charger_status':'READY'})
    c.post('/pricing-rules',json={'parking_lot_id':1,'vehicle_type':'MOTORBIKE','energy_type':'ELECTRIC','first_hour_price':9000,'additional_hour_price':3000})
    start=now()+timedelta(minutes=1)
    r=c.post('/reservations',json={'vehicle_id':v.id,'parking_spot_id':e.id,'start_time':start.isoformat(),'expiry_time':(start+timedelta(hours=1)).isoformat()})
    assert r.status_code==201,r.text
    reservation=db.get(Reservation,r.json()['id']);reservation.start_time=now()-timedelta(minutes=1);db.commit()
    r=c.post('/parking-sessions/check-in',json={'vehicle_id':v.id,'parking_spot_id':e.id,'reservation_id':reservation.id})
    assert r.status_code==201,r.text
    assert c.post('/parking-sessions/'+str(r.json()['id'])+'/check-out',json={}).status_code==200
    assert reservation.status=='COMPLETED'

def test_ai_uses_registered_energy_type(setup,monkeypatch,tmp_path):
    from services import ai_service
    from test_ai import accepted,png
    c,db,a,u,s,v=setup
    initialize(c);v.energy_type='ELECTRIC';db.commit()
    e=db.query(ParkingSpot).filter_by(spot_type='MOTORBIKE',energy_type='ELECTRIC').first()
    c.patch(f'/parking-spots/{e.id}/charging-status',json={'charger_status':'READY'})
    c.post('/pricing-rules',json={'parking_lot_id':1,'vehicle_type':'MOTORBIKE','energy_type':'ELECTRIC','first_hour_price':9000,'additional_hour_price':3000})
    monkeypatch.setattr(ai_service,'recognize',lambda *args:accepted())
    monkeypatch.setattr(ai_service,'image_dir',lambda:tmp_path)
    files={'file':('p.png',png(),'image/png')}
    assert c.post('/ai/check-in',files=files,data={'parking_spot_id':s.id}).status_code==400
    r=c.post('/ai/check-in',files=files,data={'parking_spot_id':e.id})
    assert r.status_code==201,r.text
    assert r.json()['vehicle_id']==v.id
