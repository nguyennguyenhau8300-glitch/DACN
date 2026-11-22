from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import and_, exists, or_
from models.reservation import Reservation
from models.parking_spot import ParkingSpot
from models.operations import ParkingSession, PricingRule
from models.parking_area import ParkingArea
from models.parking_lot import ParkingLot
from schemas.operations import FeeCalculation, FeeLine

def now():
    # Existing PostgreSQL schema stores local Vietnam wall time without a timezone.
    return datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None)

def staff(user):
    if user.role not in {'ADMIN','MANAGER','SECURITY'}:
        raise HTTPException(403, 'Chỉ nhân viên bãi xe được thực hiện')

def management(user):
    if user.role not in {'ADMIN','MANAGER'}:
        raise HTTPException(403, 'Chỉ ADMIN hoặc MANAGER được thực hiện')

def expire_reservations(db, *, commit=True, spot_id=None):
    from services.reservation_policy import LIVE_STATES, current_hold

    at = now()
    checked_in = exists().where(ParkingSession.reservation_id == Reservation.id, ParkingSession.status == 'ACTIVE')
    expired = and_(Reservation.status.in_(LIVE_STATES), Reservation.expiry_time <= at, ~checked_in)
    starts = and_(Reservation.end_time.is_not(None), current_hold(at), ParkingSpot.status == 'AVAILABLE')
    due = db.query(Reservation.parking_spot_id).join(ParkingSpot).filter(or_(expired, starts))
    if spot_id is not None:
        due = due.filter(Reservation.parking_spot_id == spot_id)
    ids = [row[0] for row in due.distinct()]
    count = 0
    for ident in sorted(ids):
        spot = db.query(ParkingSpot).filter_by(id=ident).populate_existing().with_for_update().first()
        if spot is None:
            continue
        rows = db.query(Reservation).filter(Reservation.parking_spot_id == ident, expired).with_for_update().all()
        for row in rows:
            row.status = 'EXPIRED'
        count += len(rows)
        db.flush()
        if spot.status in {'AVAILABLE', 'RESERVED'}:
            holds = db.query(Reservation.id).filter(Reservation.parking_spot_id == ident, current_hold(at)).first()
            if holds:
                spot.status = 'RESERVED'
            elif rows and spot.status == 'RESERVED':
                since = min(row.start_time if row.end_time is not None else row.created_at for row in rows)
                spot.status = released_spot_status(db, spot, since)
    if commit:
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

def calculate_fee(entry, exit, rule, bands=None):
    return calculate_fee_breakdown(entry, exit, rule, bands).parking_fee


def calculate_fee_breakdown(entry, exit, rule, bands=None):
    if exit < entry:
        raise HTTPException(409, 'Giờ ra không được trước giờ vào')
    elapsed = exit - entry
    full_hours, partial_hour = divmod(elapsed, timedelta(hours=1))
    hours = max(1, full_hours + bool(partial_hour))
    lines = []
    if bands:
        # Hourly anchors repeat every 24 hours, regardless of the length of the stay.
        days, remainder = divmod(hours, 24)
        band_hours = [0] * len(bands)
        for offset in range(min(hours, 24)):
            minute = ((entry.hour + offset) % 24) * 60 + entry.minute
            index = next(i for i, band in enumerate(bands)
                         if band['start_minute'] <= minute < band['end_minute'])
            band_hours[index] += days + (offset < remainder)
        for band, count in zip(bands, band_hours):
            if count:
                price = Decimal(band['hourly_price'])
                lines.append(FeeLine(kind='TIME_BAND', hours=count, unit_price=price, amount=price * count,
                                     start_minute=band['start_minute'], end_minute=band['end_minute']))
    else:
        first = Decimal(rule.first_hour_price)
        lines.append(FeeLine(kind='FIRST_HOUR', hours=1, unit_price=first, amount=first))
        if hours > 1:
            additional = Decimal(rule.additional_hour_price)
            lines.append(FeeLine(kind='ADDITIONAL_HOURS', hours=hours - 1, unit_price=additional,
                                 amount=additional * (hours - 1)))
    amount = sum(line.amount for line in lines).quantize(Decimal('0.01'))
    if amount > Decimal('9999999999.99'):
        raise HTTPException(409, 'Tổng phí vượt giới hạn lưu trữ; cần kiểm tra bảng giá')
    seconds = Decimal(elapsed // timedelta(microseconds=1)) / 1_000_000
    return FeeCalculation(elapsed_seconds=seconds, billed_hours=hours, lines=lines, parking_fee=amount)


def released_spot_status(db, spot, since=None):
    from models.sensor_log import SensorLog
    query = db.query(SensorLog).filter_by(parking_spot_id=spot.id)
    if since is not None: query=query.filter(SensorLog.recorded_at>=since)
    latest=query.order_by(SensorLog.id.desc()).first()
    return latest.sensor_status if latest else 'AVAILABLE'
