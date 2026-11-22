from datetime import timedelta
import pytest
from test_backend import setup
from main import app
from dependencies import get_current_user
from models.user import User
from models.vehicle import Vehicle
from services.parking_service import now


def registration(**changes):
    return {'full_name': '  Nguyễn Minh Anh  ', 'email': 'profile@example.com',
            'password': 'TestProfile123!', 'date_of_birth': '2002-04-23',
            'hometown': '  Đà Nẵng  ', 'vehicle': {'license_plate': '29-B1 555.55',
            'vehicle_type': 'MOTORBIKE', 'energy_type': 'GASOLINE'}, **changes}


@pytest.mark.parametrize('vehicle_type,energy_type', [
    ('CAR', 'GASOLINE'), ('CAR', 'ELECTRIC'),
    ('MOTORBIKE', 'GASOLINE'), ('MOTORBIKE', 'ELECTRIC')])
def test_register_profile_and_owned_vehicle(setup, vehicle_type, energy_type):
    c, db, a, u, s, v = setup
    payload = registration(vehicle={'license_plate': '30f-222.22' if vehicle_type == 'CAR' else '29-b1 555.55',
                                   'vehicle_type': vehicle_type, 'energy_type': energy_type})
    response = c.post('/auth/register', json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['full_name'] == 'Nguyễn Minh Anh' and data['hometown'] == 'Đà Nẵng'
    assert data['date_of_birth'] == '2002-04-23' and data['role'] == 'CUSTOMER'
    app.dependency_overrides.pop(get_current_user)
    login = c.post('/auth/login', json={'email': payload['email'], 'password': payload['password']})
    headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
    assert c.get('/auth/me', headers=headers).json()['date_of_birth'] == '2002-04-23'
    vehicles = c.get('/vehicles', headers=headers).json()
    assert len(vehicles) == 1 and vehicles[0]['user_id'] == data['id']
    assert vehicles[0]['vehicle_type'] == vehicle_type and vehicles[0]['energy_type'] == energy_type
    assert vehicles[0]['license_plate'] == payload['vehicle']['license_plate'].upper()


def test_invalid_registration_does_not_leave_account_or_claim_vehicle(setup):
    c, db, a, u, s, v = setup
    payload = registration(vehicle={'license_plate': '59A1 123.45', 'vehicle_type': 'MOTORBIKE'})
    assert c.post('/auth/register', json=payload).status_code == 409
    assert db.query(User).filter_by(email=payload['email']).first() is None
    assert db.get(Vehicle, v.id).user_id == u.id
    invalid = [registration(date_of_birth=(now().date()+timedelta(days=1)).isoformat()),
               registration(date_of_birth='2001-02-29'), registration(full_name='  '),
               registration(hometown='  '), registration(vehicle={'license_plate':'??','vehicle_type':'CAR'}),
               registration(vehicle={'license_plate':'30F-33333','vehicle_type':'TRUCK'})]
    for payload in invalid:
        assert c.post('/auth/register', json=payload).status_code == 422
    assert db.query(User).filter_by(email='profile@example.com').first() is None


def test_profile_update_is_self_only_and_cannot_change_permissions(setup):
    c, db, a, u, s, v = setup
    app.dependency_overrides[get_current_user] = lambda: u
    profile = {'full_name': 'Khách hàng mới', 'date_of_birth': '2000-02-29', 'hometown': 'Huế'}
    assert c.patch('/auth/me', json={**profile, 'role': 'ADMIN'}).status_code == 422
    assert c.patch('/auth/me', json={**profile, 'user_id': a.id}).status_code == 422
    assert c.patch('/auth/me', json={**profile, 'date_of_birth': None}).status_code == 422
    response = c.patch('/auth/me', json=profile)
    assert response.status_code == 200 and response.json()['id'] == u.id
    assert response.json()['hometown'] == 'Huế' and response.json()['role'] == 'CUSTOMER'
    assert c.get('/auth/me').json()['date_of_birth'] == '2000-02-29'
    db.refresh(a)
    assert a.full_name == 'Admin' and a.hometown is None
