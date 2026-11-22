from types import SimpleNamespace
from services.layout_service import CHARGING_FIELDS, lock_lot_for_area, validate_charging, check_new_spot_capacity, spot_availability
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.parking_area import ParkingArea
from models.parking_lot import ParkingLot
from models.parking_spot import ParkingSpot
from models.user import User
from schemas.parking_spot import (
    ParkingSpotCreate,
    ParkingSpotResponse,
    ParkingSpotUpdate
)


router = APIRouter(
    prefix="/parking-spots",
    tags=["Parking Spots"]
)


# =========================================================
# DANH SÁCH Ô ĐỖ
# =========================================================
@router.get(
    "",
    response_model=list[ParkingSpotResponse]
)
def get_parking_spots(
    parking_area_id: int | None = None,
    parking_lot_id: int | None = None,
    spot_status: str | None = None,
    vehicle_type: str | None = None,
    energy_type: str | None = None,
    charging_ready: bool | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = (db.query(ParkingSpot, ParkingLot.is_active)
             .select_from(ParkingSpot).outerjoin(ParkingArea).outerjoin(ParkingLot))
    if parking_lot_id is not None:query=query.filter(ParkingArea.parking_lot_id==parking_lot_id)

    if vehicle_type:query=query.filter(ParkingSpot.spot_type==vehicle_type.upper())
    if energy_type:query=query.filter(ParkingSpot.energy_type==energy_type.upper())

    if parking_area_id is not None:
        query = query.filter(
            ParkingSpot.parking_area_id == parking_area_id
        )

    if spot_status is not None:
        query = query.filter(
            ParkingSpot.status == spot_status.upper()
        )

    states = spot_availability(db, query.order_by(ParkingSpot.id).all())
    return [spot for spot, ready in states if charging_ready is None or ready == charging_ready]


# =========================================================
# CHI TIẾT Ô ĐỖ
# =========================================================
@router.get(
    "/{spot_id}",
    response_model=ParkingSpotResponse
)
def get_parking_spot(
    spot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    spot = (
        db.query(ParkingSpot)
        .filter(ParkingSpot.id == spot_id)
        .first()
    )

    if not spot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy ô đỗ xe"
        )

    return spot


# =========================================================
# THÊM Ô ĐỖ
# =========================================================
@router.post(
    "",
    response_model=ParkingSpotResponse,
    status_code=status.HTTP_201_CREATED
)
def create_parking_spot(
    data: ParkingSpotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ ADMIN mới có quyền thêm ô đỗ"
        )

    area = (
        db.query(ParkingArea)
        .filter(
            ParkingArea.id == data.parking_area_id
        )
        .first()
    )

    if not area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Khu vực không tồn tại"
        )

    spot_code = data.spot_code.upper().strip()
    spot_type = data.spot_type.upper().strip()

    allowed_types = {
        "MOTORBIKE",
        "CAR",
        "DISABLED"
    }

    if spot_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Loại ô đỗ phải là MOTORBIKE, CAR hoặc DISABLED"
            )
        )

    existing_spot = (
        db.query(ParkingSpot)
        .filter(
            ParkingSpot.parking_area_id == data.parking_area_id,
            ParkingSpot.spot_code == spot_code
        )
        .first()
    )

    if existing_spot:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã ô đỗ đã tồn tại trong khu vực này"
        )

    validate_charging(data)
    lot=lock_lot_for_area(db,data.parking_area_id)
    check_new_spot_capacity(db,lot,spot_type,data.energy_type)
    spot = ParkingSpot(
        parking_area_id=data.parking_area_id,
        spot_code=spot_code,
        spot_type=spot_type,
        status="AVAILABLE",
        position_x=data.position_x,
        position_y=data.position_y,
        sensor_code=data.sensor_code,
        **{k:getattr(data,k) for k in CHARGING_FIELDS}
    )

    db.add(spot)
    db.commit()
    db.refresh(spot)

    return spot


# =========================================================
# CẬP NHẬT Ô ĐỖ
# =========================================================
@router.put(
    "/{spot_id}",
    response_model=ParkingSpotResponse
)
def update_parking_spot(
    spot_id: int,
    data: ParkingSpotUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ ADMIN mới có quyền cập nhật ô đỗ"
        )

    spot = (
        db.query(ParkingSpot)
        .filter(ParkingSpot.id == spot_id)
        .populate_existing().with_for_update().first()
    )

    if not spot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy ô đỗ xe"
        )

    from models.operations import ParkingSession
    from models.reservation import Reservation
    busy = db.query(ParkingSession).filter_by(parking_spot_id=spot_id,status='ACTIVE').first() or db.query(Reservation).filter(
        Reservation.parking_spot_id==spot_id,Reservation.status.in_(['PENDING','CONFIRMED'])).first()
    if busy:
        raise HTTPException(409, 'Ô đỗ đang được sử dụng hoặc giữ chỗ')
    if data.status and data.status.upper() in {'OCCUPIED','RESERVED'}:
        raise HTTPException(400, 'Dùng API check-in hoặc đặt chỗ để đổi trạng thái này')
    update_data = data.model_dump(
        exclude_unset=True
    )

    if any(key in update_data and update_data[key] is None for key in ['spot_code', 'spot_type', 'status']):
        raise HTTPException(422, 'Trường bắt buộc không được null')

    if "spot_code" in update_data:
        new_code = update_data["spot_code"].upper().strip()

        duplicate = (
            db.query(ParkingSpot)
            .filter(
                ParkingSpot.parking_area_id == spot.parking_area_id,
                ParkingSpot.spot_code == new_code,
                ParkingSpot.id != spot_id
            )
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mã ô đỗ đã tồn tại"
            )

        update_data["spot_code"] = new_code

    if "spot_type" in update_data:
        new_type = update_data["spot_type"].upper()

        allowed_types = {
            "MOTORBIKE",
            "CAR",
                "DISABLED"
        }

        if new_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Loại ô đỗ không hợp lệ"
            )

        update_data["spot_type"] = new_type

    if "status" in update_data:
        new_status = update_data["status"].upper()

        allowed_statuses = {
            "AVAILABLE",
            "OCCUPIED",
            "RESERVED",
            "MAINTENANCE"
        }

        if new_status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trạng thái ô đỗ không hợp lệ"
            )

        update_data["status"] = new_status

    candidate=SimpleNamespace(**{key:update_data.get(key,getattr(spot,key)) for key in ['spot_type']+CHARGING_FIELDS})
    from models.iot_device import IotDevice
    if candidate.energy_type != 'ELECTRIC' and db.query(IotDevice.id).filter_by(parking_spot_id=spot.id,kind='CHARGER').first():
        raise HTTPException(409,'Ô đã gắn thiết bị sạc; không thể đổi sang xe xăng')
    validate_charging(candidate)
    lot=lock_lot_for_area(db,spot.parking_area_id)
    check_new_spot_capacity(db,lot,candidate.spot_type,candidate.energy_type,exclude_id=spot.id)
    for key, value in update_data.items():
        setattr(spot, key, value)

    db.commit()
    db.refresh(spot)

    return spot


# =========================================================
# XÓA Ô ĐỖ
# =========================================================
@router.delete(
    "/{spot_id}"
)
def delete_parking_spot(
    spot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ ADMIN mới có quyền xóa ô đỗ"
        )

    spot = (
        db.query(ParkingSpot)
        .filter(ParkingSpot.id == spot_id)
        .populate_existing().with_for_update().first()
    )

    if not spot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy ô đỗ xe"
        )

    from models.operations import ParkingSession
    from models.reservation import Reservation
    if db.query(ParkingSession).filter_by(parking_spot_id=spot_id).first() or db.query(Reservation).filter_by(parking_spot_id=spot_id).first():
        raise HTTPException(409, 'Ô đỗ có lịch sử gửi xe hoặc đặt chỗ; hãy dùng MAINTENANCE')
    db.delete(spot)
    db.commit()

    return {
        "message": "Xóa ô đỗ xe thành công"
    }

from pydantic import BaseModel
from typing import Literal

class ChargingStatusUpdate(BaseModel):
    charger_status: Literal['PLANNED','READY','OFFLINE','MAINTENANCE']

@router.patch('/{spot_id}/charging-status',response_model=ParkingSpotResponse)
def set_charging_status(spot_id: int,data: ChargingStatusUpdate,db: Session=Depends(get_db),current_user: User=Depends(get_current_user)):
    if current_user.role not in {'ADMIN','MANAGER'}:raise HTTPException(403,'Chỉ quản lý được đổi trạng thái điểm sạc')
    spot=db.query(ParkingSpot).filter_by(id=spot_id).populate_existing().with_for_update().first()
    if not spot:raise HTTPException(404,'Không tìm thấy ô đỗ')
    if spot.energy_type!='ELECTRIC':raise HTTPException(400,'Ô đỗ này không có điểm sạc')
    spot.charger_status=data.charger_status
    validate_charging(spot)
    db.commit();db.refresh(spot);return spot
