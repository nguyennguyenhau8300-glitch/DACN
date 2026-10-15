import hashlib
import secrets
from fastapi import HTTPException
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
    return bool(device.enabled and timestamp and 0 <= ((at or now())-timestamp).total_seconds() < device.offline_after_seconds)


def device_view(device):
    at = now()
    connection = ('DISABLED' if not device.enabled else 'NEVER_SEEN' if device.last_seen_at is None
                  else 'ONLINE' if is_fresh(device, 'last_seen_at', at) else 'OFFLINE')
    return dict(id=device.id, device_code=device.device_code, parking_spot_id=device.parking_spot_id,
                kind=device.kind, enabled=device.enabled, offline_after_seconds=device.offline_after_seconds,
                connection_status=connection, telemetry_fresh=is_fresh(device, at=at),
                last_seen_at=device.last_seen_at, last_telemetry_at=device.last_telemetry_at,
                last_sequence=device.last_sequence, last_payload=device.last_payload)


def devices_allow_entry(devices, *, allow_occupied_sensor=False):
    # Registered devices fail closed when stale/disabled; unregistered spots keep manual operation.
    for device in devices:
        if not is_fresh(device):
            return False
        if device.kind == 'SENSOR' and not allow_occupied_sensor and (device.last_payload or {}).get('sensor_status') != 'AVAILABLE':
            return False
        if device.kind == 'CHARGER' and (device.last_payload or {}).get('charger_status') != 'READY':
            return False
    return True


def spot_devices(db, spot_id):
    return db.query(IotDevice).filter_by(parking_spot_id=spot_id).populate_existing().all()


def apply_sensor(db, spot, sensor_status):
    old_status = spot.status
    active = db.query(ParkingSession.id).filter_by(parking_spot_id=spot.id, status='ACTIVE').first()
    reserved = db.query(Reservation.id).filter(Reservation.parking_spot_id == spot.id,
                                            Reservation.status.in_(['PENDING','CONFIRMED'])).first()
    if spot.status != 'MAINTENANCE':
        spot.status = 'OCCUPIED' if active else 'RESERVED' if reserved else sensor_status
    db.add(SensorLog(parking_spot_id=spot.id, sensor_status=sensor_status, recorded_at=now()))
    return dict(parking_spot_id=spot.id, spot_code=spot.spot_code, sensor_code=spot.sensor_code,
                old_status=old_status, new_status=spot.status)
