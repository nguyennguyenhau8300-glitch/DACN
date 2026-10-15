from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import ceil
from fastapi import HTTPException
from models.reservation import Reservation
from models.parking_spot import ParkingSpot
from models.operations import ParkingSession, PricingRule
from models.parking_area import ParkingArea
from models.parking_lot import ParkingLot

def now():
    # Existing PostgreSQL schema stores local Vietnam wall time without a timezone.
    return datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None)

def staff(user):
    if user.role not in {'ADMIN','MANAGER','SECURITY'}:
        raise HTTPException(403, 'Chỉ nhân viên bãi xe được thực hiện')

def management(user):
    if user.role not in {'ADMIN','MANAGER'}:
        raise HTTPException(403, 'Chỉ ADMIN hoặc MANAGER được thực hiện')

def expire_reservations(db):
    ids = [r[0] for r in db.query(Reservation.parking_spot_id).filter(
        Reservation.status.in_(['PENDING','CONFIRMED']), Reservation.expiry_time <= now()).distinct()]
    count = 0
    for spot_id in sorted(ids):
        spot = db.query(ParkingSpot).filter_by(id=spot_id).with_for_update().first()
        rows = db.query(Reservation).filter(Reservation.parking_spot_id == spot_id,
            Reservation.status.in_(['PENDING','CONFIRMED']), Reservation.expiry_time <= now()).with_for_update().all()
        for row in rows:
            if not db.query(ParkingSession).filter_by(reservation_id=row.id, status='ACTIVE').first():
                row.status = 'EXPIRED'
                count += 1
        db.flush()
        if spot and spot.status == 'RESERVED' and not db.query(Reservation).filter(
            Reservation.parking_spot_id == spot_id, Reservation.status.in_(['PENDING','CONFIRMED'])).first():
            spot.status = released_spot_status(db, spot, min((r.created_at for r in rows), default=None))
    db.commit()
    return count

def price_for(db, spot, vehicle, require_active=True):
    area = db.get(ParkingArea, spot.parking_area_id)
    lot = db.query(ParkingLot).filter_by(id=area.parking_lot_id).with_for_update().first() if area else None
    if not lot or (require_active and not lot.is_active):
        raise HTTPException(409, 'Bãi xe không hoạt động')
    rule = db.query(PricingRule).filter_by(parking_lot_id=lot.id, vehicle_type=vehicle.vehicle_type, energy_type=vehicle.energy_type, is_active=True).first()
    if not rule:
        raise HTTPException(409, 'Chưa có bảng giá hoạt động cho loại xe này')
    return rule

def calculate_fee(entry, exit, rule):
    if exit < entry:
        raise HTTPException(409, 'Giờ ra không được trước giờ vào')
    hours = max(1, ceil((exit-entry).total_seconds()/3600))
    amount=(Decimal(rule.first_hour_price) + (hours-1)*Decimal(rule.additional_hour_price)).quantize(Decimal('0.01'))
    if amount > Decimal('9999999999.99'):
        raise HTTPException(409, 'Tổng phí vượt giới hạn lưu trữ; cần kiểm tra bảng giá')
    return amount


def released_spot_status(db, spot, since=None):
    from models.sensor_log import SensorLog
    query = db.query(SensorLog).filter_by(parking_spot_id=spot.id)
    if since is not None: query=query.filter(SensorLog.recorded_at>=since)
    latest=query.order_by(SensorLog.id.desc()).first()
    return latest.sensor_status if latest else 'AVAILABLE'
