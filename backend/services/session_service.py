from services.layout_service import check_vehicle_spot
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.operations import ParkingSession
from models.vehicle import Vehicle
from models.parking_spot import ParkingSpot
from models.reservation import Reservation
from schemas.operations import CheckIn, CheckOut, SessionResponse
from services.parking_service import staff, expire_reservations, price_for, now, calculate_fee
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
    staff(user); expire_reservations(db)
    vehicle = db.query(Vehicle).filter_by(id=data.vehicle_id).populate_existing().with_for_update().first()
    if not vehicle: raise HTTPException(404, 'Không tìm thấy xe')
    if recognized_plate and normalized_plate(vehicle.license_plate) != recognized_plate:
        raise HTTPException(409, 'Biển số đã thay đổi; hãy nhận diện lại')
    spot = db.query(ParkingSpot).filter_by(id=data.parking_spot_id).with_for_update().first()
    if not spot: raise HTTPException(404, 'Không tìm thấy ô đỗ')
    if db.query(ParkingSession).filter_by(vehicle_id=vehicle.id,status='ACTIVE').first():
        raise HTTPException(409, 'Xe đã có lượt gửi đang hoạt động')
    if db.query(ParkingSession).filter_by(parking_spot_id=spot.id,status='ACTIVE').first():
        raise HTTPException(409, 'Ô đỗ đã có xe')
    check_vehicle_spot(vehicle,spot,db)
    price_for(db,spot,vehicle)
    held = db.query(Reservation).filter(Reservation.vehicle_id==vehicle.id,
        Reservation.status.in_(['PENDING','CONFIRMED'])).first()
    if held and held.id != data.reservation_id:
        raise HTTPException(409, 'Xe đang giữ chỗ; hãy dùng reservation_id phù hợp hoặc hủy trước')
    reservation = None
    if data.reservation_id:
        reservation = db.query(Reservation).filter_by(id=data.reservation_id).with_for_update().first()
        if not reservation: raise HTTPException(404, 'Không tìm thấy đặt chỗ')
        if reservation.vehicle_id != vehicle.id or reservation.parking_spot_id != spot.id:
            raise HTTPException(400, 'Đặt chỗ không khớp xe hoặc ô đỗ')
        if reservation.status != 'CONFIRMED' or not reservation.start_time <= now() < reservation.expiry_time:
            raise HTTPException(409, 'Đặt chỗ chưa tới giờ, hết hạn hoặc không còn hiệu lực')
        if spot.status != 'RESERVED': raise HTTPException(409, 'Ô đỗ không còn được giữ')
    elif spot.status != 'AVAILABLE': raise HTTPException(409, 'Ô đỗ không khả dụng')
    spot.status='OCCUPIED'
    row=ParkingSession(**data.model_dump(),entry_time=now(),status='ACTIVE')
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
    vehicle=db.get(Vehicle,row.vehicle_id)
    row.exit_time=now(); row.total_amount=calculate_fee(row.entry_time,row.exit_time,price_for(db,spot,vehicle,require_active=False))
    row.status='COMPLETED'
    for k,v in data.model_dump().items(): setattr(row,k,v)
    if row.reservation_id:
        reservation=db.query(Reservation).filter_by(id=row.reservation_id).with_for_update().first()
        if reservation: reservation.status='COMPLETED'
    spot.status='AVAILABLE'
    return finish_session(db, row, commit)


def finish_session(db, row, commit):
    db.flush()
    # Validate before commit; no refresh after commit can invalidate/delete evidence.
    response = SessionResponse.model_validate(row)
    if commit:
        db.commit()
        return response
    return row
