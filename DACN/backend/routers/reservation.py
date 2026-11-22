from datetime import datetime
from typing import Literal

from services.layout_service import check_vehicle_spot
from services.parking_service import now, expire_reservations, released_spot_status
from services.reservation_policy import (
    CHECKIN_WINDOW_MINUTES, LIVE_STATES, MAX_ADVANCE_MINUTES, arrival_status,
    booking_deadline, current_hold, overlaps_window, reservation_view, reservation_views,
    slot_follows_active_stay,
)
from services.reservation_slots import active_stays, free_spots, spot_accepts_slot

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.operations import ParkingSession
from models.parking_area import ParkingArea
from models.parking_lot import ParkingLot
from models.parking_spot import ParkingSpot
from models.reservation import Reservation
from models.user import User
from models.vehicle import Vehicle
from schemas.parking_spot import ParkingSpotResponse
from schemas.reservation import (
    ReservationCreate,
    ReservationPolicyResponse,
    ReservationResponse
)


router = APIRouter(
    prefix="/reservations",
    tags=["Reservations"]
)


@router.get('/policy', response_model=ReservationPolicyResponse)
def get_policy(current_user: User = Depends(get_current_user)):
    return ReservationPolicyResponse(
        max_advance_minutes=MAX_ADVANCE_MINUTES,
        checkin_window_minutes=CHECKIN_WINDOW_MINUTES,
        server_time=now(),
    )


@router.get('/available-spots', response_model=list[ParkingSpotResponse])
def scheduled_spots(
    parking_lot_id: int, vehicle_type: Literal['CAR', 'MOTORBIKE'],
    energy_type: Literal['GASOLINE', 'ELECTRIC'], start_time: datetime, end_time: datetime,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    at = now()
    booking_deadline(start_time, None, at, end_time=end_time)
    lot = db.get(ParkingLot, parking_lot_id)
    if not lot or not lot.is_active:
        raise HTTPException(404, 'Bãi xe không hoạt động hoặc không tồn tại.')
    return free_spots(db, lot.id, vehicle_type, energy_type, start_time, end_time, at)


# =========================================================
# DANH SÁCH ĐẶT CHỖ CỦA NGƯỜI DÙNG
# =========================================================
@router.get(
    "",
    response_model=list[ReservationResponse]
)
def get_reservations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Reservation)

    # ADMIN xem được toàn bộ
    if current_user.role != "ADMIN":
        query = query.filter(
            Reservation.user_id == current_user.id
        )

    return reservation_views(query.order_by(Reservation.created_at.desc()))


# =========================================================
# CHI TIẾT ĐẶT CHỖ
# =========================================================
@router.get(
    "/{reservation_id}",
    response_model=ReservationResponse
)
def get_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rows = reservation_views(db.query(Reservation).filter_by(id=reservation_id))
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy đặt chỗ"
        )

    reservation = rows[0]
    if (
        current_user.role != "ADMIN"
        and reservation.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem đặt chỗ này"
        )

    return reservation


# =========================================================
# TẠO ĐẶT CHỖ
# =========================================================
@router.post(
    "",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED
)
def create_reservation(
    data: ReservationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    requested_at = now()
    expiry_time = booking_deadline(data.start_time, data.expiry_time, requested_at, end_time=data.end_time)
    expire_reservations(db)

    # Kiểm tra xe
    vehicle = (
        db.query(Vehicle)
        .filter(Vehicle.id == data.vehicle_id)
        .populate_existing().with_for_update().first()
    )

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương tiện"
        )

    # User bình thường chỉ được dùng xe của mình
    if (
        current_user.role not in {"ADMIN","MANAGER","SECURITY"}
        and vehicle.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phương tiện không thuộc tài khoản của bạn"
        )

    # Kiểm tra ô đỗ
    parking_spot = (
        db.query(ParkingSpot)
        .filter(ParkingSpot.id == data.parking_spot_id)
        .populate_existing().with_for_update()
        .first()
    )

    if not parking_spot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy ô đỗ xe"
        )

    area = db.get(ParkingArea, parking_spot.parking_area_id)
    lot = db.query(ParkingLot).filter_by(id=area.parking_lot_id).with_for_update().first()
    if not lot or not lot.is_active:
        raise HTTPException(409, 'Bãi xe không hoạt động')
    scheduled = data.end_time is not None
    start, end = (data.start_time, data.end_time) if scheduled else (requested_at, expiry_time)
    conflicts = db.query(Reservation.parking_spot_id, Reservation.vehicle_id).filter(
        overlaps_window(start, end, requested_at),
        or_(Reservation.parking_spot_id == parking_spot.id, Reservation.vehicle_id == vehicle.id),
    ).all()
    if any(spot_id == parking_spot.id for spot_id, _ in conflicts):
        raise HTTPException(409, 'Ô đỗ đã có đặt chỗ trùng thời gian. Hãy chọn ô hoặc giờ khác.')
    if conflicts:
        raise HTTPException(409, 'Xe đã có đặt chỗ trùng thời gian.')

    stays = active_stays(db).filter(or_(
        ParkingSession.parking_spot_id == parking_spot.id, ParkingSession.vehicle_id == vehicle.id,
    )).all()
    departures = {spot_id: planned_exit for spot_id, _, planned_exit in stays}
    if scheduled:
        spot_available = spot_accepts_slot(parking_spot, departures, start, requested_at)
    else:
        spot_available = parking_spot.status == 'AVAILABLE' and parking_spot.id not in departures
    if not spot_available:
        raise HTTPException(409, 'Ô đỗ không khả dụng trong thời gian này. Hãy chọn ô khác.')
    if any(active_vehicle == vehicle.id and not (scheduled and slot_follows_active_stay(planned_exit, start, requested_at))
           for _, active_vehicle, planned_exit in stays):
        raise HTTPException(409, 'Xe đang có lượt gửi hoạt động chưa có giờ rời phù hợp.')
    check_vehicle_spot(vehicle, parking_spot, db, allow_in_use=scheduled and parking_spot.id in departures)

    reservation = Reservation(
        user_id=vehicle.user_id or current_user.id,
        vehicle_id=data.vehicle_id,
        parking_spot_id=data.parking_spot_id,
        start_time=data.start_time,
        expiry_time=expiry_time,
        end_time=data.end_time,
        status="CONFIRMED",
        created_at=requested_at
    )

    if not scheduled or start <= requested_at:
        parking_spot.status = 'RESERVED'

    db.add(reservation)
    db.commit()
    db.refresh(reservation)

    return reservation_view(reservation, now())


# =========================================================
# HỦY ĐẶT CHỖ
# =========================================================
@router.patch(
    "/{reservation_id}/cancel",
    response_model=ReservationResponse
)
def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    reservation = (
        db.query(Reservation)
        .filter(Reservation.id == reservation_id)
        .first()
    )

    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy đặt chỗ"
        )

    if (
        current_user.role != "ADMIN"
        and reservation.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền hủy đặt chỗ này"
        )

    parking_spot = db.query(ParkingSpot).filter_by(id=reservation.parking_spot_id).populate_existing().with_for_update().first()
    db.refresh(reservation, with_for_update=True)
    at = now()
    checked_in = db.query(ParkingSession.id).filter_by(reservation_id=reservation.id, status='ACTIVE').first() is not None
    phase = arrival_status(reservation, at, checked_in)
    if phase == 'CHECKED_IN':
        raise HTTPException(409, 'Xe đã được nhận. Hãy làm thủ tục trả xe.')
    if reservation.status not in LIVE_STATES:
        if phase == 'EXPIRED':
            raise HTTPException(409, 'Đặt chỗ đã hết hạn nhận xe.')
        raise HTTPException(409, 'Đặt chỗ này không còn có thể hủy.')
    reservation.status = 'EXPIRED' if phase == 'EXPIRED' else 'CANCELLED'
    if parking_spot and parking_spot.status == 'RESERVED' and (reservation.end_time is None or reservation.start_time <= at):
        another_hold = db.query(Reservation.id).filter(
            Reservation.parking_spot_id == reservation.parking_spot_id, Reservation.id != reservation.id, current_hold(at),
        ).first()
        if not another_hold:
            since = reservation.start_time if reservation.end_time is not None else reservation.created_at
            parking_spot.status = released_spot_status(db, parking_spot, since)
    db.commit()
    if phase == 'EXPIRED':
        raise HTTPException(409, 'Đặt chỗ đã hết hạn nhận xe.')
    db.refresh(reservation)
    return reservation_view(reservation, at)
