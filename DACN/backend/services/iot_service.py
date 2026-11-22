import hashlib
import secrets
from fastapi import HTTPException
from sqlalchemy import exists
from sqlalchemy.orm import object_session
from models.incident import Incident
from models.iot_device import IotDevice
from models.parking_spot import ParkingSpot
from models.sensor_log import SensorLog
from models.operations import ParkingSession
from models.reservation import Reservation
from services.parking_service import now


def hash_key(key):
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def check_key(device, key):
    if not device or not device.enabled or not key or not secrets.compare_digest(device.key_hash, hash_key(key)):
        raise HTTPException(401, 'Khóa thiết bị không hợp lệ hoặc thiết bị bị tắt')


def locked_device(db, code):
    # All combined writes acquire the spot before the device, like booking/check-in.
    binding = db.query(IotDevice.parking_spot_id).filter_by(device_code=code).first()
    if not binding:
        raise HTTPException(404, 'Không tìm thấy thiết bị')
    spot = db.query(ParkingSpot).filter_by(id=binding[0]).populate_existing().with_for_update().first()
    device = db.query(IotDevice).filter_by(device_code=code).populate_existing().with_for_update().first()
    if not spot or not device:
        raise HTTPException(404, 'Không tìm thấy thiết bị')
    return device, spot


def is_fresh(device, field='last_telemetry_at', at=None):
    timestamp = getattr(device, field)
    return bool(device.enabled and timestamp and (getattr(device,'simulation_only',False) or 0 <= ((at or now())-timestamp).total_seconds() < device.offline_after_seconds))


def device_view(device):
    at = now()
    connection = ('DISABLED' if not device.enabled else 'NEVER_SEEN' if device.last_seen_at is None
                  else 'ONLINE' if is_fresh(device, 'last_seen_at', at) else 'OFFLINE')
    return dict(id=device.id, device_code=device.device_code, parking_spot_id=device.parking_spot_id,
                kind=device.kind, enabled=device.enabled, simulation_only=device.simulation_only, offline_after_seconds=device.offline_after_seconds,
                connection_status=connection, telemetry_fresh=is_fresh(device, at=at),
                last_seen_at=device.last_seen_at, last_telemetry_at=device.last_telemetry_at,
                last_sequence=device.last_sequence, last_payload=device.last_payload)


def devices_allow_entry(devices, *, allow_occupied_sensor=False, allow_busy_charger=False, at=None, overheated_ids=None):
    # Registered devices fail closed when stale/disabled; unregistered spots keep manual operation.
    at = at or now()
    charger_states = {'READY', 'PLUGGED', 'CHARGING'} if allow_busy_charger else {'READY'}
    for device in devices:
        if not is_fresh(device, at=at):
            return False
        if device.kind == 'SENSOR' and not allow_occupied_sensor and (device.last_payload or {}).get('sensor_status') != 'AVAILABLE':
            return False
        if device.kind == 'CHARGER' and (device.last_payload or {}).get('charger_status') not in charger_states:
            return False
        if device.kind == 'CHARGER':
            from services.alert_service import OVERHEAT_C, COOLED_C
            temperature = (device.last_payload or {}).get('temperature_c')
            if temperature is not None and temperature >= OVERHEAT_C:
                return False
            # Retain the safety block until a cool measurement resolves an overheat episode.
            if temperature is None or temperature >= COOLED_C:
                if overheated_ids is not None:
                    if device.id in overheated_ids:
                        return False
                else:
                    session = object_session(device)
                    if session and session.query(Incident.id).filter_by(device_id=device.id, kind='OVERHEAT').filter(Incident.status != 'RESOLVED').first():
                        return False
    return True


def load_devices_for_availability(db, spot_ids):
    by_spot = {}
    overheated_ids = set()
    if spot_ids:
        open_overheat = exists().where(
            Incident.device_id == IotDevice.id,
            Incident.kind == 'OVERHEAT',
            Incident.status != 'RESOLVED',
        )
        for device, overheated in db.query(IotDevice, open_overheat).filter(IotDevice.parking_spot_id.in_(spot_ids)):
            by_spot.setdefault(device.parking_spot_id, []).append(device)
            if overheated:
                overheated_ids.add(device.id)
    return by_spot, overheated_ids


def spot_devices(db, spot_id):
    return db.query(IotDevice).filter_by(parking_spot_id=spot_id).populate_existing().all()


def apply_sensor(db, spot, sensor_status):
    old_status = spot.status
    if spot.status != 'MAINTENANCE':
        from models.internal_demo import InternalDemoRun
        from services.reservation_policy import current_hold

        active_query = db.query(ParkingSession.id).filter_by(parking_spot_id=spot.id, status='ACTIVE')
        exit_query = db.query(InternalDemoRun.id).join(ParkingSession, InternalDemoRun.parking_session_id == ParkingSession.id).filter(
            InternalDemoRun.kind == 'EXIT', InternalDemoRun.status == 'AWAITING_PAYMENT', ParkingSession.parking_spot_id == spot.id,
        )
        reservation_query = db.query(Reservation.id).filter(
            Reservation.parking_spot_id == spot.id, current_hold(now()),
        )
        active, pending_exit, reserved = db.query(active_query.exists(), exit_query.exists(), reservation_query.exists()).one()
        if active or pending_exit:
            spot.status = 'OCCUPIED'
        elif reserved and (spot.status == 'RESERVED' or sensor_status == 'AVAILABLE'):
            spot.status = 'RESERVED'
        else:
            spot.status = sensor_status
    db.add(SensorLog(parking_spot_id=spot.id, sensor_status=sensor_status, recorded_at=now()))
    return dict(parking_spot_id=spot.id, spot_code=spot.spot_code, sensor_code=spot.sensor_code,
                old_status=old_status, new_status=spot.status)


def apply_device_telemetry(db,device,spot,data):
    from models.iot_device import IotEvent
    from services.alert_service import reconcile_alerts
    code=device.device_code
    if (device.kind == 'SENSOR') != (data.sensor_status is not None):
        raise HTTPException(422, 'Dữ liệu không đúng loại thiết bị')
    if device.kind == 'CHARGER' and spot.energy_type != 'ELECTRIC':
        raise HTTPException(409, 'Cấu hình ô đỗ không còn phù hợp thiết bị sạc')
    payload = data.model_dump(exclude={'sequence'}, exclude_none=True)
    previous = db.query(IotEvent).filter_by(device_id=device.id, sequence=data.sequence).first()
    if previous:
        if previous.payload != payload:
            raise HTTPException(409, 'Sequence đã được dùng cho dữ liệu khác')
        # Replay acknowledges the original event without refreshing measurement freshness.
        return {**previous.result, 'duplicate':True}
    if data.sequence <= device.last_sequence:
        raise HTTPException(409, 'Sequence cũ; cần lớn hơn last_sequence')
    if data.power_kw is not None and spot.charging_power_kw is not None and data.power_kw > float(spot.charging_power_kw):
        raise HTTPException(422, 'Công suất báo cáo vượt cấu hình điểm sạc')
    result = dict(device_code=code, parking_spot_id=spot.id, sequence=data.sequence, duplicate=False)
    if device.kind == 'SENSOR':
        result.update(apply_sensor(db, spot, data.sensor_status))
    else:
        # Administrative commissioning/maintenance remains separate from telemetry.
        result.update(charger_status=data.charger_status, configured_charger_status=spot.charger_status)
    timestamp = now()
    device.last_seen_at = timestamp; device.last_telemetry_at = timestamp
    device.last_sequence = data.sequence; device.last_payload = payload
    reconcile_alerts(db, device, spot, measurement=True, at=timestamp)
    db.add(IotEvent(device_id=device.id, sequence=data.sequence, payload=payload, result=result, received_at=timestamp))
    db.flush()
    return result
