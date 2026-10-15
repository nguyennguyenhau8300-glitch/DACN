import secrets
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models.iot_device import IotDevice, IotEvent
from models.parking_spot import ParkingSpot
from models.parking_area import ParkingArea
from schemas.iot_device import DeviceCreate, DeviceAccess, Telemetry
from services.parking_service import management, staff, now
from services.iot_service import hash_key, check_key, locked_device, device_view, apply_sensor

router = APIRouter(prefix='/iot', tags=['IoT Devices'])

@router.post('/devices', status_code=201)
def register_device(data: DeviceCreate, db: Session=Depends(get_db), user=Depends(get_current_user)):
    management(user)
    spot = db.query(ParkingSpot).filter_by(id=data.parking_spot_id).populate_existing().with_for_update().first()
    if not spot:
        raise HTTPException(404, 'Không tìm thấy ô đỗ')
    if data.kind == 'CHARGER' and spot.energy_type != 'ELECTRIC':
        raise HTTPException(422, 'Chỉ ô xe điện mới có thiết bị sạc')
    if db.query(IotDevice).filter_by(parking_spot_id=spot.id, kind=data.kind).first():
        raise HTTPException(409, 'Ô đỗ đã có thiết bị loại này')
    key = secrets.token_urlsafe(32)
    device = IotDevice(**data.model_dump(), key_hash=hash_key(key))
    db.add(device); db.flush()
    result = {**device_view(device), 'api_key':key}
    db.commit()
    return result

@router.get('/devices')
def list_devices(parking_lot_id: int | None=None, db: Session=Depends(get_db), user=Depends(get_current_user)):
    staff(user)
    query = db.query(IotDevice)
    if parking_lot_id is not None:
        query = query.join(ParkingSpot).join(ParkingArea).filter(ParkingArea.parking_lot_id == parking_lot_id)
    return [device_view(d) for d in query.order_by(IotDevice.id).all()]

@router.patch('/devices/{code}/access')
def device_access(code: str, data: DeviceAccess, db: Session=Depends(get_db), user=Depends(get_current_user)):
    management(user)
    device, _ = locked_device(db, code)
    device.enabled = data.enabled
    # Enabling again requires new measurements, rather than trusting pre-disable data.
    device.last_seen_at = None; device.last_telemetry_at = None
    result = device_view(device); db.commit()
    return result

@router.post('/devices/{code}/rotate-key')
def rotate_key(code: str, db: Session=Depends(get_db), user=Depends(get_current_user)):
    management(user)
    device, _ = locked_device(db, code)
    key = secrets.token_urlsafe(32); device.key_hash = hash_key(key)
    device.last_seen_at = None; device.last_telemetry_at = None
    result = {**device_view(device), 'api_key':key}; db.commit()
    return result

@router.post('/devices/{code}/heartbeat')
def heartbeat(code: str, x_api_key: str | None=Header(default=None), db: Session=Depends(get_db)):
    device = db.query(IotDevice).filter_by(device_code=code).populate_existing().with_for_update().first()
    check_key(device, x_api_key)
    device.last_seen_at = now()
    result = device_view(device); db.commit()
    return result

@router.post('/devices/{code}/telemetry')
def telemetry(code: str, data: Telemetry, x_api_key: str | None=Header(default=None), db: Session=Depends(get_db)):
    device, spot = locked_device(db, code)
    check_key(device, x_api_key)
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
    db.add(IotEvent(device_id=device.id, sequence=data.sequence, payload=payload, result=result, received_at=timestamp))
    db.commit()
    return result

@router.get('/events')
def events(device_code: str | None=None, limit: int=Query(100, ge=1, le=500),
           before_id: int | None=Query(None, gt=0), db: Session=Depends(get_db), user=Depends(get_current_user)):
    staff(user)
    query = db.query(IotEvent, IotDevice.device_code).join(IotDevice)
    if device_code is not None: query = query.filter(IotDevice.device_code == device_code)
    if before_id is not None: query = query.filter(IotEvent.id < before_id)
    return [dict(id=e.id, device_code=code, sequence=e.sequence, payload=e.payload,
                 result=e.result, received_at=e.received_at) for e,code in query.order_by(IotEvent.id.desc()).limit(limit)]
