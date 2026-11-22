from datetime import datetime, timedelta

import pytest

from test_backend import setup
from dependencies import get_current_user
from main import app
from models.parking_spot import ParkingSpot
from models.reservation import Reservation
from models.sensor_log import SensorLog
from models.user import User
from models.vehicle import Vehicle
from routers import reservation
from services import barrier_service, parking_service, reservation_policy, session_service


@pytest.fixture
def clock(monkeypatch):
    value = [datetime(2026, 11, 20, 8)]
    for module in (reservation, reservation_policy, parking_service, session_service, barrier_service):
        monkeypatch.setattr(module, 'now', lambda: value[0])
    return value


def make_booking(client, spot, vehicle, start, **fields):
    return client.post('/reservations', json={
        'vehicle_id':vehicle.id, 'parking_spot_id':spot.id, 'start_time':start.isoformat(), **fields,
    })


def test_window_is_enforced_on_server_and_rolls_into_next_day(setup, clock):
    client, _, _, _, spot, vehicle = setup
    clock[0] = datetime(2026, 11, 20, 21, 30)
    policy = client.get('/reservations/policy').json()
    assert policy == {
        'max_advance_minutes':120, 'checkin_window_minutes':120,
        'server_time':'2026-11-20T21:30:00', 'timezone':'Asia/Ho_Chi_Minh',
    }
    start = clock[0]+timedelta(hours=2)
    assert make_booking(client, spot, vehicle, clock[0]-timedelta(minutes=1)).status_code == 400
    assert make_booking(client, spot, vehicle, start+timedelta(microseconds=1)).status_code == 422
    too_long = (start+timedelta(hours=2, seconds=1)).isoformat()
    assert make_booking(client, spot, vehicle, start, expiry_time=too_long).status_code == 422
    assert make_booking(client, spot, vehicle, start, expiry_time=start.isoformat()).status_code == 400
    booked = make_booking(client, spot, vehicle, start)
    assert booked.status_code == 201, booked.text
    assert booked.json()['expiry_time'] == '2026-11-21T01:30:00'
    assert booked.json()['arrival_status'] == 'UPCOMING'
    assert spot.status == 'RESERVED'


def test_arrival_phases_and_cancellation_after_checkin(setup, clock):
    client, _, _, _, spot, vehicle = setup
    start = clock[0]+timedelta(hours=1)
    booking = make_booking(client, spot, vehicle, start).json()
    key = booking['id']
    reservation_path = f'/reservations/{key}'
    payload = {'vehicle_id':vehicle.id, 'parking_spot_id':spot.id, 'reservation_id':key}
    clock[0] = start-timedelta(minutes=15)
    early = client.post('/parking-sessions/check-in', json=payload)
    assert early.status_code == 409 and 'Chưa tới giờ nhận xe' in early.json()['detail']
    assert '09:00 20/11/2026' in early.json()['detail']
    assert client.get(reservation_path).json()['arrival_status'] == 'UPCOMING'

    clock[0] = start
    assert client.get(reservation_path).json()['arrival_status'] == 'READY'
    entered = client.post('/parking-sessions/check-in', json=payload)
    assert entered.status_code == 201, entered.text
    assert entered.json()['entry_time'] == '2026-11-20T09:00:00'
    assert client.get(reservation_path).json()['arrival_status'] == 'CHECKED_IN'

    clock[0] = start+timedelta(hours=2)
    assert client.post('/reservations/expire').json()['expired'] == 0
    assert client.get('/dashboard-data/reservations').json()[0]['arrival_status'] == 'CHECKED_IN'
    refused = client.patch(reservation_path+'/cancel')
    assert refused.status_code == 409 and 'Xe đã được nhận' in refused.json()['detail']
    assert spot.status == 'OCCUPIED'
    assert client.post(f"/parking-sessions/{entered.json()['id']}/check-out", json={}).status_code == 200
    assert client.get(reservation_path).json()['arrival_status'] == 'COMPLETED'


def test_arrival_without_checkin_expires_at_exact_deadline(setup, clock):
    client, db, _, _, spot, vehicle = setup
    start = clock[0]+timedelta(hours=1)
    booking = make_booking(client, spot, vehicle, start).json()
    path = f"/reservations/{booking['id']}"
    deadline = start+timedelta(hours=2)
    clock[0] = deadline-timedelta(microseconds=1)
    assert client.get(path).json()['arrival_status'] == 'READY'

    clock[0] = deadline
    assert client.get(path).json()['arrival_status'] == 'EXPIRED'
    payload = {'vehicle_id':vehicle.id, 'parking_spot_id':spot.id}
    late = client.post('/parking-sessions/check-in', json={**payload, 'reservation_id':booking['id']})
    assert late.status_code == 409 and 'hết hạn nhận xe' in late.json()['detail']
    assert db.get(Reservation, booking['id']).status == 'EXPIRED'
    assert spot.status == 'AVAILABLE'
    assert client.post('/parking-sessions/check-in', json=payload).status_code == 201


def test_cancel_honors_ownership_and_current_sensor_state(setup, clock):
    client, db, _, owner, spot, vehicle = setup
    another = User(full_name='Another customer', email='another@example.com', password_hash='unused', role='CUSTOMER')
    db.add(another)
    db.commit()
    start = clock[0]+timedelta(hours=1)
    legacy_deadline = start+timedelta(hours=1)
    booked = make_booking(client, spot, vehicle, start, expiry_time=legacy_deadline.isoformat()).json()
    assert booked['expiry_time'] == legacy_deadline.isoformat()
    path = f"/reservations/{booked['id']}/cancel"
    app.dependency_overrides[get_current_user] = lambda: another
    assert client.patch(path).status_code == 403
    app.dependency_overrides[get_current_user] = lambda: owner
    db.add(SensorLog(parking_spot_id=spot.id, sensor_status='OCCUPIED', recorded_at=clock[0]+timedelta(seconds=5)))
    db.commit()
    clock[0] += timedelta(minutes=20)
    cancelled = client.patch(path)
    assert cancelled.status_code == 200 and cancelled.json()['arrival_status'] == 'CANCELLED'
    assert spot.status == 'OCCUPIED'
    assert client.patch(path).status_code == 409


def test_cancel_at_deadline_records_expiration_instead(setup, clock):
    client, db, _, _, spot, vehicle = setup
    start = clock[0]+timedelta(hours=1)
    booked = make_booking(client, spot, vehicle, start).json()
    clock[0] = start+timedelta(hours=2)
    response = client.patch(f"/reservations/{booked['id']}/cancel")
    assert response.status_code == 409 and 'hết hạn nhận xe' in response.json()['detail']
    assert db.get(Reservation, booked['id']).status == 'EXPIRED' and spot.status == 'AVAILABLE'


def test_slot_availability_and_overlaps_on_both_spot_and_vehicle(setup, clock):
    client, db, _, owner, spot, vehicle = setup
    other_spot = ParkingSpot(parking_area_id=spot.parking_area_id, spot_code='A02', spot_type=spot.spot_type)
    other_vehicle = Vehicle(user_id=owner.id, license_plate='59A1-45678', vehicle_type=vehicle.vehicle_type)
    db.add_all([other_spot, other_vehicle])
    db.commit()
    start = clock[0] + timedelta(days=1)
    end = start + timedelta(hours=1)
    booked = make_booking(client, spot, vehicle, start, end_time=end.isoformat())
    assert booked.status_code == 201, booked.text
    assert booked.json()['end_time'] == booked.json()['expiry_time'] == end.isoformat()
    assert spot.status == 'AVAILABLE'

    preview = client.get('/reservations/available-spots', params={
        'parking_lot_id': 1, 'vehicle_type': vehicle.vehicle_type, 'energy_type': vehicle.energy_type,
        'start_time': start.isoformat(), 'end_time': end.isoformat(),
    })
    assert preview.status_code == 200, preview.text
    assert [candidate['id'] for candidate in preview.json()] == [other_spot.id]
    halfway = start + timedelta(minutes=30)
    overlapping = make_booking(client, spot, other_vehicle, halfway, end_time=end.isoformat())
    assert overlapping.status_code == 409 and 'Ô đỗ' in overlapping.json()['detail']
    overlapping = make_booking(client, other_spot, vehicle, halfway, end_time=end.isoformat())
    assert overlapping.status_code == 409 and 'Xe' in overlapping.json()['detail']
    assert make_booking(client, spot, other_vehicle, end, end_time=end.isoformat()).status_code == 422

    following = make_booking(client, spot, vehicle, end, end_time=(end + timedelta(hours=3)).isoformat())
    assert following.status_code == 201, following.text
    assert following.json()['expiry_time'] == (end + timedelta(hours=2)).isoformat()
    clock[0] = start
    assert client.post('/reservations/expire').json()['expired'] == 0 and spot.status == 'RESERVED'
    clock[0] = end
    assert client.post('/reservations/expire').json()['expired'] == 1 and spot.status == 'RESERVED'
    assert client.patch(f"/reservations/{following.json()['id']}/cancel").status_code == 200
    assert spot.status == 'AVAILABLE'


def test_scheduled_checkin_respects_previous_car_until_it_leaves(setup, clock):
    client, db, _, owner, spot, first_vehicle = setup
    other_vehicle = Vehicle(user_id=owner.id, license_plate='59A1-45678', vehicle_type=first_vehicle.vehicle_type)
    db.add(other_vehicle)
    db.commit()
    start = clock[0] + timedelta(hours=1)
    boundary = start + timedelta(hours=1)
    booking = make_booking(client, spot, first_vehicle, start, end_time=boundary.isoformat()).json()
    payload = {'vehicle_id': first_vehicle.id, 'parking_spot_id': spot.id, 'reservation_id': booking['id']}
    early = client.post('/parking-sessions/check-in', json=payload)
    assert early.status_code == 409 and 'Chưa tới giờ' in early.json()['detail']
    assert spot.status == 'AVAILABLE'

    clock[0] = start
    entry = client.post('/parking-sessions/check-in', json=payload)
    assert entry.status_code == 201, entry.text
    following = make_booking(client, spot, other_vehicle, boundary, end_time=(boundary + timedelta(hours=1)).isoformat())
    assert following.status_code == 201, following.text
    next_payload = {**payload, 'vehicle_id': other_vehicle.id, 'reservation_id': following.json()['id']}

    clock[0] = boundary
    assert client.post('/parking-sessions/check-in', json=next_payload).status_code == 409
    assert spot.status == 'OCCUPIED'
    assert client.post(f"/parking-sessions/{entry.json()['id']}/check-out", json={}).status_code == 200
    assert spot.status == 'RESERVED'
    assert client.post('/parking-sessions/check-in', json=next_payload).status_code == 201
    assert spot.status == 'OCCUPIED'
