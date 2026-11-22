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
from services.alert_service import reconcile_alerts

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
    device = IotDevice(**data.model_dump(), key_hash=hash_key(key), monitoring_since=now())
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
    device, spot = locked_device(db, code)
    device.enabled = data.enabled
    # Enabling again requires new measurements, rather than trusting pre-disable data.
    device.last_seen_at = None; device.last_telemetry_at = None
    device.monitoring_since = now()
    reconcile_alerts(db, device, spot)
    result = device_view(device); db.commit()
    return result

@router.post('/devices/{code}/rotate-key')
def rotate_key(code: str, db: Session=Depends(get_db), user=Depends(get_current_user)):
    management(user)
    device, _ = locked_device(db, code)
    key = secrets.token_urlsafe(32); device.key_hash = hash_key(key)
    device.last_seen_at = None; device.last_telemetry_at = None
    device.monitoring_since = now()
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
    from services.iot_service import apply_device_telemetry
    result=apply_device_telemetry(db,device,spot,data)
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
