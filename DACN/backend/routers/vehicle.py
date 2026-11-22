from services.vehicle_service import normalized_plate, plate_expression
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.user import User
from models.vehicle import Vehicle
from schemas.vehicle import (
    VehicleCreate,
    VehicleResponse,
    VehicleUpdate
)


router = APIRouter(
    prefix="/vehicles",
    tags=["Vehicles"]
)


# =========================================================
# THÊM PHƯƠNG TIỆN
# =========================================================
@router.post(
    "",
    response_model=VehicleResponse,
    status_code=status.HTTP_201_CREATED
)
def create_vehicle(
    data: VehicleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    license_plate = data.license_plate.upper().strip()

    existing_vehicle = (
        db.query(Vehicle)
        .filter(plate_expression(Vehicle.license_plate) == normalized_plate(license_plate))
        .first()
    )

    if existing_vehicle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Biển số xe đã tồn tại"
        )

    allowed_types = {
        "MOTORBIKE",
        "CAR",
    }

    vehicle_type = data.vehicle_type.upper()

    if vehicle_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Loại phương tiện phải là "
                "MOTORBIKE hoặc CAR; energy_type chọn GASOLINE/ELECTRIC"
            )
        )

    vehicle = Vehicle(
        user_id=current_user.id,
        license_plate=license_plate,
        vehicle_type=vehicle_type,
        energy_type=data.energy_type,
        brand=data.brand,
        color=data.color
    )

    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    return vehicle


# =========================================================
# DANH SÁCH XE CỦA TÀI KHOẢN
# =========================================================
@router.get(
    "",
    response_model=list[VehicleResponse]
)
def get_my_vehicles(
    vehicle_type: str | None = None,
    energy_type: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query=db.query(Vehicle).filter(Vehicle.user_id==current_user.id)
    if vehicle_type:query=query.filter(Vehicle.vehicle_type==vehicle_type.upper())
    if energy_type:query=query.filter(Vehicle.energy_type==energy_type.upper())
    return query.order_by(Vehicle.id.desc()).all()



# =========================================================
# XEM CHI TIẾT XE
# =========================================================
@router.get(
    "/{vehicle_id}",
    response_model=VehicleResponse
)
def get_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    vehicle = (
        db.query(Vehicle)
        .filter(
            Vehicle.id == vehicle_id,
            Vehicle.user_id == current_user.id
        )
        .first()
    )

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương tiện"
        )

    return vehicle


# =========================================================
# CẬP NHẬT XE
# =========================================================
@router.put(
    "/{vehicle_id}",
    response_model=VehicleResponse
)
def update_vehicle(
    vehicle_id: int,
    data: VehicleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    vehicle = (
        db.query(Vehicle)
        .filter(
            Vehicle.id == vehicle_id,
            Vehicle.user_id == current_user.id
        )
        .populate_existing().with_for_update().first()
    )

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương tiện"
        )

    from models.operations import ParkingSession
    from models.reservation import Reservation
    if db.query(ParkingSession).filter_by(vehicle_id=vehicle_id,status='ACTIVE').first() or db.query(Reservation).filter(
        Reservation.vehicle_id==vehicle_id,Reservation.status.in_(['PENDING','CONFIRMED'])).first():
        raise HTTPException(409, 'Xe đang gửi hoặc có đặt chỗ; không thể chỉnh sửa')
    update_data = data.model_dump(
        exclude_unset=True
    )

    if any(key in update_data and update_data[key] is None for key in ['license_plate', 'vehicle_type']):
        raise HTTPException(422, 'Trường bắt buộc không được null')

    if "license_plate" in update_data:
        new_plate = update_data["license_plate"].upper().strip()

        duplicate = (
            db.query(Vehicle)
            .filter(
                plate_expression(Vehicle.license_plate) == normalized_plate(new_plate),
                Vehicle.id != vehicle_id
            )
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=400,
                detail="Biển số xe đã tồn tại"
            )

        update_data["license_plate"] = new_plate

    if "vehicle_type" in update_data:
        new_type = update_data["vehicle_type"].upper()

        if new_type not in {
            "MOTORBIKE",
            "CAR",
            }:
            raise HTTPException(
                status_code=400,
                detail="Loại phương tiện không hợp lệ"
            )

        update_data["vehicle_type"] = new_type

    if db.query(ParkingSession).filter_by(vehicle_id=vehicle_id).first():
        if any(key in update_data and update_data[key] != getattr(vehicle,key) for key in ['license_plate','vehicle_type','energy_type']):
            raise HTTPException(409, 'Xe đã có lịch sử gửi; không được đổi biển số hoặc loại xe')
    for key, value in update_data.items():
        setattr(vehicle, key, value)

    db.commit()
    db.refresh(vehicle)

    return vehicle


# =========================================================
# XÓA XE
# =========================================================
@router.delete(
    "/{vehicle_id}"
)
def delete_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    vehicle = (
        db.query(Vehicle)
        .filter(
            Vehicle.id == vehicle_id,
            Vehicle.user_id == current_user.id
        )
        .populate_existing().with_for_update().first()
    )

    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phương tiện"
        )

    from models.operations import ParkingSession
    from models.reservation import Reservation
    if db.query(ParkingSession).filter_by(vehicle_id=vehicle_id).first() or db.query(Reservation).filter_by(vehicle_id=vehicle_id).first():
        raise HTTPException(409, 'Xe có lịch sử gửi hoặc đặt chỗ; không thể xóa')
    db.delete(vehicle)
    db.commit()

    return {
        "message": "Xóa phương tiện thành công"
    }