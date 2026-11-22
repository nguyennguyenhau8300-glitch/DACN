from services.layout_service import check_vehicle_spot
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from models.operations import ParkingSession
from models.vehicle import Vehicle
from models.parking_spot import ParkingSpot
from models.reservation import Reservation
from schemas.operations import CheckIn, CheckOut, SessionResponse, FeeBreakdown
from services.parking_service import staff, expire_reservations, price_for, now, calculate_fee_breakdown
from services.reservation_policy import arrival_status, current_hold
from services.vehicle_service import normalized_plate

def visible_session(db, session_id, user, lock=False):
    q = db.query(ParkingSession).filter_by(id=session_id)
    row = (q.populate_existing().with_for_update() if lock else q).first()
    if not row:
        raise HTTPException(404, 'Không tìm thấy lượt gửi xe')
    vehicle = db.get(Vehicle, row.vehicle_id)
    if user.role not in {'ADMIN','MANAGER','SECURITY'} and vehicle.user_id != user.id:
        raise HTTPException(403, 'Không có quyền xem lượt gửi xe này')
    return row


def check_in(data: CheckIn, db: Session, user, *, commit=True, recognized_plate=None):
    staff(user)
    if commit:
        expire_reservations(db, spot_id=data.parking_spot_id)
    vehicle = db.query(Vehicle).filter_by(id=data.vehicle_id).populate_existing().with_for_update().first()
    if not vehicle: raise HTTPException(404, 'Không tìm thấy xe')
    if recognized_plate and normalized_plate(vehicle.license_plate) != recognized_plate:
        raise HTTPException(409, 'Biển số đã thay đổi; hãy nhận diện lại')
    if not commit:
        expire_reservations(db, commit=False, spot_id=data.parking_spot_id)
    spot = db.query(ParkingSpot).filter_by(id=data.parking_spot_id).populate_existing().with_for_update().first()
    if not spot: raise HTTPException(404, 'Không tìm thấy ô đỗ')
    if db.query(ParkingSession).filter_by(vehicle_id=vehicle.id,status='ACTIVE').first():
        raise HTTPException(409, 'Xe đã có lượt gửi đang hoạt động')
    if db.query(ParkingSession).filter_by(parking_spot_id=spot.id,status='ACTIVE').first():
        raise HTTPException(409, 'Ô đỗ đã có xe')
    if data.reservation_id:
        reservation = db.query(Reservation).filter_by(id=data.reservation_id).populate_existing().with_for_update().first()
        if not reservation: raise HTTPException(404, 'Không tìm thấy đặt chỗ')
        if reservation.vehicle_id != vehicle.id or reservation.parking_spot_id != spot.id:
            raise HTTPException(400, 'Đặt chỗ không khớp xe hoặc ô đỗ')
        entry = now()
        phase = arrival_status(reservation, entry)
        if phase == 'UPCOMING':
            start = reservation.start_time.strftime('%H:%M %d/%m/%Y')
            raise HTTPException(409, f'Chưa tới giờ nhận xe. Có thể nhận từ {start} (giờ Việt Nam).')
        if phase == 'EXPIRED':
            raise HTTPException(409, 'Đặt chỗ đã hết hạn nhận xe. Hãy chọn ô còn trống để đặt lại hoặc gửi xe trực tiếp.')
        if phase != 'READY': raise HTTPException(409, 'Đặt chỗ chưa được xác nhận hoặc đã kết thúc.')
        allowed = {'RESERVED'} if reservation.end_time is None else {'AVAILABLE', 'RESERVED'}
        if spot.status not in allowed:
            raise HTTPException(409, 'Ô đỗ chưa sẵn sàng. Kiểm tra xe trước hoặc chọn ô khác.')
    else:
        entry = now()
        held = db.query(Reservation.id).filter(
            or_(Reservation.vehicle_id == vehicle.id, Reservation.parking_spot_id == spot.id), current_hold(entry),
        ).first()
        if held:
            raise HTTPException(409, 'Xe hoặc ô đang giữ chỗ. Hãy nhận xe theo đúng đặt chỗ.')
        if spot.status != 'AVAILABLE': raise HTTPException(409, 'Ô đỗ không khả dụng')
    check_vehicle_spot(vehicle,spot,db)
    price_for(db,spot,vehicle)
    spot.status='OCCUPIED'
    row=ParkingSession(**data.model_dump(),entry_time=entry,status='ACTIVE')
    db.add(row)
    return finish_session(db, row, commit)


def check_out(session_id: int, data: CheckOut, db: Session, user, *, commit=True, recognized_plate=None):
    staff(user)
    row=visible_session(db,session_id,user,True)
    if row.status!='ACTIVE': raise HTTPException(409, 'Lượt gửi đã kết thúc')
    vehicle=db.query(Vehicle).filter_by(id=row.vehicle_id).populate_existing().with_for_update().first()
    if recognized_plate and normalized_plate(vehicle.license_plate) != recognized_plate:
        raise HTTPException(409, 'Biển số ảnh ra không khớp xe của lượt gửi')
    spot=db.query(ParkingSpot).filter_by(id=row.parking_spot_id).with_for_update().first()
    if not spot: raise HTTPException(409, 'Ô đỗ không còn tồn tại')
    rule=price_for(db,spot,vehicle,require_active=False)
    from models.extensions import TariffSchedule
    schedule=db.get(TariffSchedule,rule.id)
    row.exit_time = now()
    calculation = calculate_fee_breakdown(row.entry_time, row.exit_time, rule, schedule.bands if schedule else None)
    fee = FeeBreakdown(**calculation.model_dump(), pricing_rule_id=rule.id,
                       vehicle_type=rule.vehicle_type, energy_type=rule.energy_type)
    row.fee_breakdown = fee.model_dump(mode='json')
    row.total_amount = fee.parking_fee + fee.charging_fee
    row.status='COMPLETED'
    for k,v in data.model_dump().items(): setattr(row,k,v)
    if row.reservation_id:
        reservation=db.query(Reservation).filter_by(id=row.reservation_id).with_for_update().first()
        if reservation: reservation.status='COMPLETED'
    next_hold = db.query(Reservation.id).filter(
        Reservation.parking_spot_id == spot.id, Reservation.id != row.reservation_id, current_hold(row.exit_time),
    ).first()
    spot.status = 'RESERVED' if next_hold else 'AVAILABLE'
    return finish_session(db, row, commit)


def finish_session(db, row, commit):
    db.flush()
    from services.barrier_service import queue_command
    if row.status=='ACTIVE': queue_command(db,row,'ENTRY')
    elif row.total_amount==0: queue_command(db,row,'EXIT')
    db.flush()
    # Validate before commit; no refresh after commit can invalidate/delete evidence.
    response = SessionResponse.model_validate(row)
    if commit:
        db.commit()
        return response
    return row
