"""Persistent incident episodes; caller locks spot then device before reconciling."""
from fastapi import HTTPException
from sqlalchemy import func, literal_column
from models.incident import Incident
from models.iot_device import IotDevice
from models.parking_area import ParkingArea
from services.parking_service import now

OVERHEAT_C = 60
COOLED_C = 55
KINDS = ('OVERHEAT', 'CHARGER_FAULT', 'CONNECTION_LOST', 'WRONG_PARKING')


def connection_expired(device, at):
    if getattr(device,'simulation_only',False):return False
    baseline = device.last_telemetry_at or device.monitoring_since
    return bool(device.enabled and baseline and
                (at-baseline).total_seconds() >= device.offline_after_seconds)


def reconcile_alerts(db, device, spot, *, measurement=False, at=None):
    at = at or now()
    active = {r.kind: r for r in db.query(Incident).filter(
        Incident.device_id == device.id, Incident.status != 'RESOLVED').with_for_update()}

    def condition(kind, present, message='', details=None, severity='WARNING', resolution='Thiết bị đã gửi dữ liệu bình thường'):
        row = active.get(kind)
        if present is None:  # No fresh evidence: retain the previous incident.
            return
        if present:
            if row is None:
                area = db.get(ParkingArea, spot.parking_area_id)
                row = Incident(device_id=device.id, parking_lot_id=area.parking_lot_id,
                               parking_spot_id=spot.id, device_code=device.device_code, spot_code=spot.spot_code,
                               kind=kind, severity=severity, status='OPEN', message=message,
                               details=details or {}, opened_at=at, last_seen_at=at)
                db.add(row)
            else:
                row.message = message
                row.details = details or {}
                row.last_seen_at = at
        elif row is not None:
            row.status = 'RESOLVED'
            row.resolved_at = at
            row.resolution = resolution

    if not device.enabled:
        condition('CONNECTION_LOST', False, resolution='Người quản lý tắt thiết bị và dừng giám sát kết nối')
        # Turning off monitoring is not evidence that heat/fault/wrong parking has recovered.
        return

    condition('CONNECTION_LOST', connection_expired(device, at),
              'Thiết bị mất kết nối hoặc không có số đo mới quá thời hạn',
              {'last_telemetry_at': device.last_telemetry_at.isoformat() if device.last_telemetry_at else None,
               'timeout_seconds': device.offline_after_seconds},
              resolution='Đã nhận bản tin đo mới từ thiết bị')
    if not measurement:
        return
    payload = device.last_payload or {}
    if device.kind == 'CHARGER':
        temperature = payload.get('temperature_c')
        condition('OVERHEAT', None if temperature is None else temperature >= (COOLED_C if 'OVERHEAT' in active else OVERHEAT_C),
                  'Điểm sạc quá nhiệt; cần kiểm tra thiết bị',
                  {'temperature_c': temperature, 'trigger_c': OVERHEAT_C, 'clear_below_c': COOLED_C},
                  severity='CRITICAL', resolution='Nhiệt độ đã giảm dưới ngưỡng khôi phục mô phỏng')
        condition('CHARGER_FAULT', payload.get('charger_status') in ('FAULT', 'OFFLINE'),
                  'Thiết bị sạc báo lỗi hoặc ngoại tuyến',
                  {'charger_status': payload.get('charger_status')})
    else:
        observed_type, observed_energy = payload.get('observed_vehicle_type'), payload.get('observed_energy_type')
        occupied = payload.get('sensor_status') == 'OCCUPIED'
        known = observed_type is not None and observed_energy is not None
        expected_type = 'CAR' if spot.spot_type == 'DISABLED' else spot.spot_type
        wrong = (observed_type, observed_energy) != (expected_type, spot.energy_type)
        condition('WRONG_PARKING', (wrong if known else None) if occupied else False,
                  'Xe quan sát được không phù hợp nhóm ô đỗ',
                  {'observed_vehicle_type': observed_type, 'observed_energy_type': observed_energy,
                   'expected_vehicle_type': expected_type, 'expected_energy_type': spot.energy_type,
                   'source': 'iot_observation'}, resolution='Ô đã trống hoặc dữ liệu quan sát mới cho thấy đúng nhóm xe')


def sweep_connections(db):
    """Also detects devices that have never reported; lock order matches telemetry."""
    from services.iot_service import locked_device
    at = now()
    query = db.query(IotDevice).filter(IotDevice.enabled.is_(True), IotDevice.simulation_only.is_(False))
    if db.get_bind().dialect.name == 'postgresql':
        baseline = func.coalesce(IotDevice.last_telemetry_at, IotDevice.monitoring_since)
        deadline = baseline + IotDevice.offline_after_seconds * literal_column("INTERVAL '1 second'")
        candidates = query.with_entities(IotDevice.parking_spot_id, IotDevice.device_code).filter(deadline <= at).all()
    else:
        candidates = [(d.parking_spot_id, d.device_code) for d in query if connection_expired(d, at)]
    for _, code in sorted(candidates):
        try:
            device, spot = locked_device(db, code)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            continue  # The device was removed after the candidate read.
        reconcile_alerts(db, device, spot, at=at)
    db.commit()
