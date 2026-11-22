from test_backend import setup
from dependencies import get_current_user
from main import app
from models.parking_area import ParkingArea
from models.user import User
from models.vehicle import Vehicle
from services.auth_service import hash_password


def signed_in_roles(setup):
    client, db, admin, customer, spot, vehicle = setup
    password = 'RoleMatrix123!'
    shared_hash = hash_password(password)
    manager = User(full_name='Test Manager', email='manager@example.com', role='MANAGER', password_hash=shared_hash)
    security = User(full_name='Test Security', email='security@example.com', role='SECURITY', password_hash=shared_hash)
    admin.password_hash = customer.password_hash = shared_hash
    db.add_all([manager, security])
    db.commit()
    app.dependency_overrides.pop(get_current_user)
    headers = {}
    for account in (admin, manager, security, customer):
        login = client.post('/auth/login', json={'email': account.email, 'password': password})
        assert login.status_code == 200, login.text
        headers[account.role] = {'Authorization': 'Bearer ' + login.json()['access_token']}
    return headers, manager


def test_four_role_api_matrix_and_customer_scope(setup):
    client, db, admin, customer, spot, vehicle = setup
    headers, _ = signed_in_roles(setup)
    lot = db.get(ParkingArea, spot.parking_area_id).parking_lot_id
    all_roles = {'ADMIN', 'MANAGER', 'SECURITY', 'CUSTOMER'}
    staff = {'ADMIN', 'MANAGER', 'SECURITY'}
    management = {'ADMIN', 'MANAGER'}
    checks = {
        '/auth/me': all_roles,
        f'/parking-lots/{lot}/map': all_roles,
        '/dashboard-data/vehicles': staff,
        '/dashboard-data/reservations': staff,
        '/ai/status': staff,
        '/alerts': staff,
        '/iot/devices': staff,
        '/reports/summary': management,
        f'/reports/daily/payments?parking_lot_id={lot}&payment_date=2026-11-20': management,
        f'/internal-simulation/state?parking_lot_id={lot}': management,
        '/users': {'ADMIN'},
    }
    for path, allowed in checks.items():
        for role in all_roles:
            response = client.get(path, headers=headers[role])
            assert response.status_code == (200 if role in allowed else 403), (role, path, response.text)

    update = {'name': 'Role matrix parking lot'}
    for role in ('CUSTOMER', 'SECURITY', 'MANAGER'):
        assert client.put(f'/parking-lots/{lot}', json=update, headers=headers[role]).status_code == 403
    assert client.put(f'/parking-lots/{lot}', json=update, headers=headers['ADMIN']).status_code == 200

    another_vehicle = Vehicle(user_id=admin.id, license_plate='59B1-12345', vehicle_type='MOTORBIKE')
    db.add(another_vehicle)
    db.commit()
    checkin = {'vehicle_id': another_vehicle.id, 'parking_spot_id': spot.id}
    assert client.post('/parking-sessions/check-in', json=checkin, headers=headers['CUSTOMER']).status_code == 403
    received = client.post('/parking-sessions/check-in', json=checkin, headers=headers['SECURITY'])
    assert received.status_code == 201, received.text
    session_id = received.json()['id']
    path = f'/parking-sessions/{session_id}'
    assert client.get(path, headers=headers['CUSTOMER']).status_code == 403
    assert client.get(f'{path}/ticket', headers=headers['CUSTOMER']).status_code == 403
    assert client.get('/parking-sessions', headers=headers['CUSTOMER']).json() == []
    assert client.get('/vehicles', headers=headers['CUSTOMER']).json()[0]['id'] == vehicle.id


def test_access_change_takes_effect_for_an_existing_token(setup):
    client, _, admin, customer, _, _ = setup
    headers, manager = signed_in_roles(setup)
    admin_headers = headers['ADMIN']
    manager_headers = headers['MANAGER']
    access = f'/users/{manager.id}/access'
    demote = {'role': 'CUSTOMER', 'is_active': True}
    assert client.get('/reports/summary', headers=manager_headers).status_code == 200
    assert client.patch(access, json=demote, headers=manager_headers).status_code == 403
    assert client.patch(access, json=demote, headers=admin_headers).status_code == 200
    assert client.get('/auth/me', headers=manager_headers).json()['role'] == 'CUSTOMER'
    assert client.get('/reports/summary', headers=manager_headers).status_code == 403
    assert client.get('/dashboard-data/vehicles', headers=manager_headers).status_code == 403
    assert client.patch(access, json={**demote, 'is_active': False}, headers=admin_headers).status_code == 200
    assert client.get('/auth/me', headers=manager_headers).status_code == 403
    assert client.get('/parking-lots', headers=manager_headers).status_code == 403
    own_profile = {'full_name': customer.full_name, 'date_of_birth': '2002-01-01', 'hometown': 'Huế', 'role': 'ADMIN'}
    assert client.patch('/auth/me', json=own_profile, headers=headers['CUSTOMER']).status_code == 422
    assert client.patch(f'/users/{admin.id}/access', json=demote, headers=admin_headers).status_code == 409
