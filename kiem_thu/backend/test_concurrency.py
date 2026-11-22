"""PostgreSQL-only tests: separate transactions and real concurrent HTTP calls."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import sessionmaker
from test_backend import setup
from database import get_db
from dependencies import get_current_user
from main import app
from models.vehicle import Vehicle
from models.parking_spot import ParkingSpot
from models.operations import ParkingSession,Payment
from models.reservation import Reservation
from models.user import User
from services.auth_service import create_access_token
from services.parking_service import now

pytestmark=pytest.mark.skipif(not os.getenv('TEST_POSTGRES'),reason='Requires PostgreSQL row locks')

@pytest.fixture
def concurrent_setup(setup):
    _,db,a,u,s,v=setup
    ids=SimpleNamespace(admin=a.id,user=u.id,spot=s.id,vehicle=v.id)
    factory=sessionmaker(bind=db.get_bind(),expire_on_commit=False)
    db.commit()
    def request_db():
        with factory() as session:
            try: yield session
            except Exception:
                session.rollback();raise
    app.dependency_overrides[get_db]=request_db
    app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=ids.admin,role='ADMIN')
    return db,factory,ids

def race(path,body):
    gate=threading.Barrier(2)
    def request():
        gate.wait(timeout=5)
        return TestClient(app).post(path,json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:request(),range(2)))
    return results

def test_two_checkins_create_one_session(concurrent_setup):
    db,f,ids=concurrent_setup
    results=race('/parking-sessions/check-in',{'vehicle_id':ids.vehicle,'parking_spot_id':ids.spot})
    assert sorted(r.status_code for r in results)==[201,409],[r.text for r in results]
    with f() as s: assert s.query(ParkingSession).count()==1

def test_two_checkouts_and_payments(concurrent_setup):
    db,f,ids=concurrent_setup
    c=TestClient(app)
    r=c.post('/parking-sessions/check-in',json={'vehicle_id':ids.vehicle,'parking_spot_id':ids.spot})
    sid=r.json()['id']
    results=race(f'/parking-sessions/{sid}/check-out',{})
    assert sorted(r.status_code for r in results)==[200,409],[r.text for r in results]
    results=race('/payments',{'parking_session_id':sid})
    assert sorted(r.status_code for r in results)==[201,409],[r.text for r in results]
    with f() as s: assert s.query(Payment).count()==1

def test_same_car_cannot_book_two_spots_concurrently(concurrent_setup):
    db,f,ids=concurrent_setup
    with f() as s:
        spot=s.get(ParkingSpot,ids.spot)
        other=ParkingSpot(parking_area_id=spot.parking_area_id,spot_code='A02',spot_type='MOTORBIKE',status='AVAILABLE')
        s.add(other);s.commit();other_id=other.id
    gate=threading.Barrier(2);start=now()+timedelta(minutes=5)
    def request(spot_id):
        gate.wait(timeout=5)
        return TestClient(app).post('/reservations',json={'vehicle_id':ids.vehicle,'parking_spot_id':spot_id,
            'start_time':start.isoformat(),'expiry_time':(start+timedelta(hours=1)).isoformat()})
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(request,[ids.spot,other_id]))
    assert sorted(r.status_code for r in results)==[201,409],[r.text for r in results]


@pytest.mark.parametrize('scheduled', [False, True])
def test_two_customers_can_only_confirm_one_hold_on_the_same_spot(concurrent_setup, scheduled):
    _, factory, ids = concurrent_setup
    with factory() as db:
        first = db.get(User, ids.user)
        second = User(full_name='Other customer', email='second@example.com', role='CUSTOMER', password_hash='unused')
        db.add(second)
        db.flush()
        next_vehicle = Vehicle(user_id=second.id, license_plate='59B1-45678', vehicle_type='MOTORBIKE')
        db.add(next_vehicle)
        db.commit()
        actors = [(first, ids.vehicle), (second, next_vehicle.id)]
        requests = [({'Authorization':'Bearer '+create_access_token(user.id, user.email, user.role)}, vehicle)
                    for user,vehicle in actors]
    app.dependency_overrides.pop(get_current_user)
    start = now()+timedelta(minutes=180 if scheduled else 10)
    window = {'start_time': start.isoformat()}
    if scheduled:
        window['end_time'] = (start + timedelta(hours=1)).isoformat()
    gate = threading.Barrier(2)

    def place(args):
        headers, vehicle_id = args
        gate.wait(timeout=5)
        return TestClient(app).post('/reservations', headers=headers, json={
            'vehicle_id':vehicle_id, 'parking_spot_id':ids.spot, **window,
        })

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(place, requests))
    assert sorted(r.status_code for r in results) == [201,409], [r.text for r in results]
    with factory() as db:
        assert db.query(Reservation).filter_by(parking_spot_id=ids.spot, status='CONFIRMED').count() == 1
        assert db.get(ParkingSpot, ids.spot).status == ('AVAILABLE' if scheduled else 'RESERVED')

@pytest.mark.parametrize('target',['vehicle','spot'])
def test_edit_waits_for_inflight_checkin(concurrent_setup,target):
    db,f,ids=concurrent_setup
    actor=SimpleNamespace(id=ids.user if target=='vehicle' else ids.admin,role='CUSTOMER' if target=='vehicle' else 'ADMIN')
    app.dependency_overrides[get_current_user]=lambda:actor
    reached=threading.Event()
    table='vehicles' if target=='vehicle' else 'parking_spots'
    def about_to_select(conn,cursor,statement,parameters,context,executemany):
        if threading.current_thread().name!='MainThread' and table in statement and 'SELECT' in statement:
            reached.set()
    engine=db.get_bind();event.listen(engine,'before_cursor_execute',about_to_select)
    try:
        with f() as owner,ThreadPoolExecutor(max_workers=1) as pool:
            vehicle=owner.execute(select(Vehicle).where(Vehicle.id==ids.vehicle).with_for_update()).scalar_one()
            spot=owner.execute(select(ParkingSpot).where(ParkingSpot.id==ids.spot).with_for_update()).scalar_one()
            path=f'/vehicles/{ids.vehicle}' if target=='vehicle' else f'/parking-spots/{ids.spot}'
            body={'vehicle_type':'CAR'} if target=='vehicle' else {'status':'MAINTENANCE'}
            pending=pool.submit(lambda:TestClient(app).put(path,json=body))
            assert reached.wait(5),'Edit did not reach database'
            owner.add(ParkingSession(vehicle_id=vehicle.id,parking_spot_id=spot.id,entry_time=now(),status='ACTIVE'))
            spot.status='OCCUPIED';owner.commit()
            response=pending.result(timeout=10)
            assert response.status_code==409,response.text
        with f() as s:
            assert s.get(Vehicle,ids.vehicle).vehicle_type=='MOTORBIKE'
            assert s.get(ParkingSpot,ids.spot).status=='OCCUPIED'
    finally:event.remove(engine,'before_cursor_execute',about_to_select)


def test_last_category_slot_cannot_be_overallocated(concurrent_setup):
    from models.parking_lot import ParkingLot
    from models.parking_area import ParkingArea
    db,f,ids=concurrent_setup
    with f() as s:
        original=s.get(ParkingSpot,ids.spot);area_id=original.parking_area_id
        lot=s.get(ParkingLot,s.get(ParkingArea,area_id).parking_lot_id)
        limit=lot.motorbike_capacity-lot.electric_motorbike_capacity
        for index in range(limit-2):
            s.add(ParkingSpot(parking_area_id=area_id,spot_code=f'FILL{index}',spot_type='MOTORBIKE',energy_type='GASOLINE',status='AVAILABLE'))
        s.commit()
    gate=threading.Barrier(2)
    def request(index):
        gate.wait(timeout=5)
        return TestClient(app).post('/parking-spots',json={'parking_area_id':area_id,'spot_code':f'LAST{index}','spot_type':'MOTORBIKE','energy_type':'GASOLINE'})
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(request,[1,2]))
    assert sorted(r.status_code for r in results)==[201,409],[r.text for r in results]
    with f() as s:assert s.query(ParkingSpot).count()==limit


def test_iot_duplicate_event_is_applied_once(concurrent_setup):
    from models.iot_device import IotEvent
    from models.sensor_log import SensorLog
    db,f,ids=concurrent_setup
    c=TestClient(app)
    device=c.post('/iot/devices',json={'device_code':'CONCURRENT','parking_spot_id':ids.spot,'kind':'SENSOR'}).json()
    gate=threading.Barrier(2)
    def request():
        gate.wait(timeout=5)
        return TestClient(app).post('/iot/devices/CONCURRENT/telemetry',headers={'X-API-Key':device['api_key']},json={'sequence':1,'sensor_status':'OCCUPIED','observed_vehicle_type':'CAR','observed_energy_type':'GASOLINE'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:request(),range(2)))
    assert [r.status_code for r in results]==[200,200],[r.text for r in results]
    assert sorted(r.json()['duplicate'] for r in results)==[False,True]
    with f() as session:
        assert session.query(IotEvent).count()==1
        assert session.query(SensorLog).count()==1
        assert session.get(ParkingSpot,ids.spot).status=='OCCUPIED'
        from models.incident import Incident
        assert session.query(Incident).count()==1


def test_two_connection_monitors_create_one_incident(concurrent_setup):
    from models.iot_device import IotDevice
    from models.incident import Incident
    from services.alert_service import sweep_connections
    db,f,ids=concurrent_setup
    c=TestClient(app)
    device=c.post('/iot/devices',json={'device_code':'STALE','parking_spot_id':ids.spot,'kind':'SENSOR','offline_after_seconds':10}).json()
    with f() as session:
        row=session.get(IotDevice,device['id']);row.monitoring_since=now()-timedelta(seconds=11);session.commit()
    gate=threading.Barrier(2)
    def monitor():
        with f() as session:
            gate.wait(timeout=5)
            sweep_connections(session)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:monitor(),range(2)))
    with f() as session:
        assert session.query(Incident).count()==1
