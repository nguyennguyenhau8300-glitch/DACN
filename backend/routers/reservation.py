from services.layout_service import check_vehicle_spot
from services.parking_service import now, expire_reservations, released_spot_status

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.parking_spot import ParkingSpot
from models.reservation import Reservation
from models.user import User
from models.vehicle import Vehicle
from schemas.reservation import (
    ReservationCreate,
    ReservationResponse
)


router = APIRouter(
    prefix="/reservations",
    tags=["Reservations"]
)


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

    return (
        query
        .order_by(Reservation.created_at.desc())
        .all()
    )


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
    expire_reservations(db)
    if data.start_time.tzinfo or data.expiry_time.tzinfo:
        raise HTTPException(400, "Dùng giờ Việt Nam không kèm múi giờ")
    if data.expiry_time <= now() or data.start_time < now():
        raise HTTPException(400, "Thời gian đặt chỗ phải trong tương lai")
    # Kiểm tra thời gian
    if data.expiry_time <= data.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="expiry_time phải lớn hơn start_time"
        )

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
        .with_for_update()
        .first()
    )

    if not parking_spot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy ô đỗ xe"
        )

    # Chỉ cho đặt ô AVAILABLE
    if parking_spot.status != "AVAILABLE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ô đỗ hiện không khả dụng"
        )

    check_vehicle_spot(vehicle,parking_spot,db)

    from models.parking_area import ParkingArea
    from models.parking_lot import ParkingLot
    area = db.get(ParkingArea, parking_spot.parking_area_id)
    lot = db.query(ParkingLot).filter_by(id=area.parking_lot_id).with_for_update().first()
    if not lot or not lot.is_active:
        raise HTTPException(409, 'Bãi xe không hoạt động')
    if db.query(Reservation).filter(Reservation.vehicle_id==vehicle.id,
        Reservation.status.in_(['PENDING','CONFIRMED'])).first():
        raise HTTPException(409, 'Xe đã có đặt chỗ đang giữ; hãy hủy đặt chỗ cũ trước')
    # Tạo reservation
    reservation = Reservation(
        user_id=vehicle.user_id or current_user.id,
        vehicle_id=data.vehicle_id,
        parking_spot_id=data.parking_spot_id,
        start_time=data.start_time,
        expiry_time=data.expiry_time,
        status="CONFIRMED",
        created_at=now()
    )

    from models.operations import ParkingSession
    if db.query(ParkingSession).filter_by(vehicle_id=vehicle.id, status="ACTIVE").first():
        raise HTTPException(409, "Xe đang có lượt gửi hoạt động")

    # Giữ ô đỗ
    parking_spot.status = "RESERVED"

    db.add(reservation)
    db.commit()
    db.refresh(reservation)

    return reservation


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

    if reservation.status not in {
        "PENDING",
        "CONFIRMED"
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Đặt chỗ này không thể hủy"
        )

    parking_spot = (
        db.query(ParkingSpot)
        .filter(
            ParkingSpot.id == reservation.parking_spot_id
        )
        .first()
    )

    from models.operations import ParkingSession
    if db.query(ParkingSession).filter_by(reservation_id=reservation.id,status="ACTIVE").first():
        raise HTTPException(409, "Xe đã check-in, không thể hủy đặt chỗ")
    parking_spot = db.query(ParkingSpot).filter_by(id=reservation.parking_spot_id).populate_existing().with_for_update().first()
    db.refresh(reservation, with_for_update=True)
    if reservation.status not in {'PENDING','CONFIRMED'}:
        raise HTTPException(409, 'Đặt chỗ không còn có thể hủy')
    if db.query(ParkingSession).filter_by(reservation_id=reservation.id,status='ACTIVE').first():
        raise HTTPException(409, 'Xe đã check-in')
    reservation.status = "CANCELLED"

    if (
        parking_spot
        and parking_spot.status == "RESERVED"
    ):
        parking_spot.status = released_spot_status(db, parking_spot, reservation.created_at)

    db.commit()
    db.refresh(reservation)

    return reservation