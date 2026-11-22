import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException

from test_backend import setup
from dependencies import get_current_user
from main import app
from models.operations import ParkingSession, Payment, PricingRule
from models.parking_area import ParkingArea
from models.parking_lot import ParkingLot
from models.parking_spot import ParkingSpot
from models.vehicle import Vehicle
from routers import checkout, operations
from services import internal_demo, iot_service, payment_gateway, session_service
from services.parking_service import calculate_fee_breakdown


def test_fee_report_cash_and_electric_checkout_across_midnight(setup, monkeypatch):
    client, db, admin, customer, gas_spot, gas_vehicle = setup
    lot_id = db.get(ParkingArea, gas_spot.parking_area_id).parking_lot_id
    charge_spot = ParkingSpot(parking_area_id=gas_spot.parking_area_id, spot_code='EV-01',
                              spot_type='CAR', energy_type='ELECTRIC', status='AVAILABLE',
                              charger_type='EV_CHARGER', charger_status='READY',
                              charging_station_code='TEST-A', charging_port_code='01', charging_power_kw=7)
    electric = Vehicle(user_id=customer.id, license_plate='30F-22222', vehicle_type='CAR', energy_type='ELECTRIC')
    unpaid_vehicle = Vehicle(user_id=customer.id, license_plate='29-B1 555.55', vehicle_type='MOTORBIKE')
    tariff = PricingRule(parking_lot_id=lot_id, vehicle_type='CAR', energy_type='ELECTRIC',
                         first_hour_price=10000, additional_hour_price=5000)
    db.add_all([charge_spot, electric, unpaid_vehicle, tariff])
    db.commit()
    bands = [
        {'start_minute': 0, 'end_minute': 420, 'hourly_price': '15000'},
        {'start_minute': 420, 'end_minute': 1140, 'hourly_price': '12000'},
        {'start_minute': 1140, 'end_minute': 1440, 'hourly_price': '15000'},
    ]
    assert client.put(f'/pricing-rules/{tariff.id}/schedule', json={'bands': bands}).status_code == 200

    clock = datetime(2026, 11, 19, 18, 40)
    for module in (session_service, operations, checkout, payment_gateway, internal_demo, iot_service):
        monkeypatch.setattr(module, 'now', lambda: clock)

    def arrive(vehicle, spot):
        response = client.post('/parking-sessions/check-in', json={'vehicle_id': vehicle.id, 'parking_spot_id': spot.id})
        assert response.status_code == 201, response.text
        assert response.json()['fee_breakdown'] is None
        return response.json()['id']

    def depart(session_id):
        response = client.post(f'/parking-sessions/{session_id}/check-out', json={})
        assert response.status_code == 200, response.text
        return response.json()['fee_breakdown']

    electric_id = arrive(electric, charge_spot)
    clock = datetime(2026, 11, 19, 18, 45)
    plugged = client.post('/api/v1/iot/simulate-charger', json={
        'parking_spot_id': charge_spot.id, 'scenario': 'CHARGING', 'power_kw': 7,
    })
    assert plugged.status_code == 200, plugged.text
    assert plugged.json()['result']['charger_status'] == 'CHARGING'
    clock = datetime(2026, 11, 19, 20, 10)
    ready = client.post('/api/v1/iot/simulate-charger', json={'parking_spot_id': charge_spot.id, 'scenario': 'READY'})
    assert ready.status_code == 200, ready.text
    electric_fee = depart(electric_id)
    assert electric_fee['pricing_rule_id'] == tariff.id
    assert electric_fee['energy_type'] == 'ELECTRIC'
    assert Decimal(electric_fee['elapsed_seconds']) == 5400
    assert electric_fee['billed_hours'] == 2
    assert [(r['start_minute'], r['hours'], Decimal(r['amount'])) for r in electric_fee['lines']] == [
        (420, 1, 12000), (1140, 1, 15000),
    ]
    assert Decimal(electric_fee['parking_fee']) == 27000
    assert Decimal(electric_fee['charging_fee']) == 0
    assert client.put(f'/pricing-rules/{tariff.id}/schedule', json={'bands': []}).status_code == 200

    clock = datetime(2026, 11, 19, 21, 25)
    gas_id = arrive(gas_vehicle, gas_spot)
    clock = datetime(2026, 11, 19, 23, 35)
    gas_fee = depart(gas_id)
    assert Decimal(gas_fee['elapsed_seconds']) == 7800
    assert gas_fee['billed_hours'] == 3
    assert [(r['kind'], r['hours'], Decimal(r['unit_price'])) for r in gas_fee['lines']] == [
        ('FIRST_HOUR', 1, 5000), ('ADDITIONAL_HOURS', 2, 2000),
    ]
    assert Decimal(gas_fee['parking_fee']) == 9000

    clock = datetime(2026, 11, 19, 23, 40)
    unpaid_id = arrive(unpaid_vehicle, gas_spot)
    clock = datetime(2026, 11, 19, 23, 59)
    assert Decimal(depart(unpaid_id)['parking_fee']) == 5000
    queries = {'parking_lot_id': lot_id, 'from_date': '2026-11-19', 'to_date': '2026-11-20'}
    before = client.get('/reports/daily', params=queries).json()
    assert Decimal(before['totals']['revenue']) == Decimal(before['totals']['sandbox_revenue']) == 0

    clock = datetime(2026, 11, 20, 0, 3)
    cash = client.post('/payments', json={'parking_session_id': gas_id})
    assert cash.status_code == 201, cash.text
    assert Decimal(cash.json()['amount']) == 9000
    assert client.post('/payments', json={'parking_session_id': gas_id}).status_code == 409

    clock = datetime(2026, 11, 20, 0, 4)
    order = client.post('/checkout/orders', json={'parking_session_id': electric_id})
    assert order.status_code == 201, order.text
    url = urlsplit(order.json()['checkout_url'])
    token = parse_qs(url.query)['token'][0]
    for _ in range(2):
        confirm = client.post(url.path, data={'token': token, 'result': 'success'})
        assert confirm.status_code == 200, confirm.text

    report = client.get('/reports/daily', params=queries).json()
    assert [(r['date'], r['exits'], Decimal(r['revenue']), Decimal(r['sandbox_revenue'])) for r in report['items']] == [
        ('2026-11-19', 3, 0, 0), ('2026-11-20', 0, 9000, 27000),
    ]
    assert Decimal(client.get('/reports/summary', params={'parking_lot_id': lot_id}).json()['revenue']) == 9000
    exported = client.get('/reports/daily', params={**queries, 'format': 'csv'})
    csv_rows = list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))))
    assert csv_rows[2][0:3] == ['2026-11-20', '0', '0']
    assert [Decimal(amount) for amount in csv_rows[2][3:]] == [9000, 27000]

    detail = {'parking_lot_id': lot_id, 'payment_date': '2026-11-20', 'limit': 1}
    latest = client.get('/reports/daily/payments', params=detail)
    assert latest.status_code == 200, latest.text
    assert latest.json()['has_more']
    sandbox = latest.json()['items'][0]
    assert sandbox['sandbox'] and sandbox['session']['id'] == electric_id
    assert sandbox['session']['fee_breakdown'] == electric_fee
    assert Decimal(sandbox['payment']['amount']) == Decimal(sandbox['session']['total_amount']) == 27000
    earlier = client.get('/reports/daily/payments', params={**detail, 'offset': 1}).json()
    assert not earlier['has_more']
    receipt = earlier['items'][0]
    assert not receipt['sandbox'] and receipt['session']['fee_breakdown'] == gas_fee
    assert receipt['payment']['id'] == cash.json()['id']
    assert client.get('/reports/daily/payments', params={**detail, 'payment_date': '2026-11-19'}).json()['items'] == []
    app.dependency_overrides[get_current_user] = lambda: customer
    assert client.get('/reports/daily/payments', params=detail).status_code == 403


def test_report_retains_legacy_totals_and_isolates_lots(setup):
    client, db, _, _, spot, vehicle = setup
    lot_id = db.get(ParkingArea, spot.parking_area_id).parking_lot_id
    other_lot = ParkingLot(name='Another parking lot', address='Test')
    db.add(other_lot)
    db.flush()
    other_area = ParkingArea(parking_lot_id=other_lot.id, name='B')
    db.add(other_area)
    db.flush()
    other_spot = ParkingSpot(parking_area_id=other_area.id, spot_code='B01', spot_type='MOTORBIKE')
    db.add(other_spot)
    db.flush()
    midnight = datetime(2026, 11, 20)
    final_tick = midnight - timedelta(microseconds=1)
    legacy = ParkingSession(vehicle_id=vehicle.id, parking_spot_id=spot.id, status='COMPLETED',
                            entry_time=midnight-timedelta(hours=2), exit_time=midnight, total_amount=6100)
    other = ParkingSession(vehicle_id=vehicle.id, parking_spot_id=other_spot.id, status='COMPLETED',
                           entry_time=legacy.entry_time, exit_time=midnight, total_amount=9999)
    db.add_all([legacy, other])
    db.flush()
    db.add_all([
        Payment(parking_session_id=legacy.id, amount=6000, payment_method='CASH', status='SUCCESS', paid_at=midnight),
        Payment(parking_session_id=legacy.id, amount=6100, payment_method='CASH', status='FAILED', paid_at=midnight),
        Payment(parking_session_id=legacy.id, amount=6100, payment_method='CASH', status='PENDING', paid_at=midnight),
        Payment(parking_session_id=other.id, amount=9999, payment_method='CASH', status='SUCCESS', paid_at=final_tick),
    ])
    db.commit()
    day = {'parking_lot_id': lot_id, 'payment_date': '2026-11-20'}
    data = client.get('/reports/daily/payments', params=day).json()
    assert len(data['items']) == 1
    receipt = data['items'][0]
    assert receipt['session']['fee_breakdown'] is None and not receipt['sandbox']
    assert Decimal(receipt['session']['total_amount']) == 6100
    assert Decimal(receipt['payment']['amount']) == 6000
    assert client.get('/reports/daily/payments', params={**day, 'parking_lot_id': other_lot.id}).json()['items'] == []
    previous = {**day, 'parking_lot_id': other_lot.id, 'payment_date': '2026-11-19'}
    assert Decimal(client.get('/reports/daily/payments', params=previous).json()['items'][0]['payment']['amount']) == 9999


def test_fee_breakdown_time_boundaries():
    rule = PricingRule(first_hour_price=Decimal('5000.01'), additional_hour_price=Decimal('2000.02'))
    start = datetime(2026, 11, 19, 18, 30)
    with pytest.raises(HTTPException) as backwards:
        calculate_fee_breakdown(start, start-timedelta(microseconds=1), rule)
    assert backwards.value.status_code == 409
    assert calculate_fee_breakdown(start, start, rule).billed_hours == 1
    elapsed = timedelta(hours=1, microseconds=1)
    fee = calculate_fee_breakdown(start, start+elapsed, rule)
    assert fee.elapsed_seconds == Decimal('3600.000001')
    assert fee.billed_hours == 2 and fee.parking_fee == Decimal('7000.03')
    bands = [
        {'start_minute': 0, 'end_minute': 420, 'hourly_price': '15'},
        {'start_minute': 420, 'end_minute': 1140, 'hourly_price': '12'},
        {'start_minute': 1140, 'end_minute': 1440, 'hourly_price': '15'},
    ]
    multi_day = calculate_fee_breakdown(start, start+timedelta(hours=48, minutes=1), rule, bands)
    assert multi_day.billed_hours == 49
    assert [line.hours for line in multi_day.lines] == [14, 25, 10]
    assert multi_day.parking_fee == 660

    max_rule = PricingRule(first_hour_price=Decimal('9999999999.99'), additional_hour_price=1)
    with pytest.raises(HTTPException) as overflow:
        calculate_fee_breakdown(start, start+elapsed, max_rule)
    assert overflow.value.status_code == 409
