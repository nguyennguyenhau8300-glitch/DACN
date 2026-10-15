from types import SimpleNamespace
from services.layout_service import CAPACITY_FIELDS, quotas, validate_capacity, initialize_layout, capacity_summary
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.parking_lot import ParkingLot
from models.user import User
from schemas.parking_lot import (
    ParkingLotCreate,
    ParkingLotResponse,
    ParkingLotUpdate
)


router = APIRouter(
    prefix="/parking-lots",
    tags=["Parking Lots"]
)


# =========================================================
# DANH SÁCH BÃI XE
# =========================================================
@router.get(
    "",
    response_model=list[ParkingLotResponse]
)
def get_parking_lots(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return (
        db.query(ParkingLot)
        .order_by(ParkingLot.id.asc())
        .all()
    )


# =========================================================
# XEM CHI TIẾT BÃI XE
# =========================================================
@router.get(
    "/{parking_lot_id}",
    response_model=ParkingLotResponse
)
def get_parking_lot(
    parking_lot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    parking_lot = (
        db.query(ParkingLot)
        .filter(ParkingLot.id == parking_lot_id)
        .first()
    )

    if not parking_lot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy bãi đỗ xe"
        )

    return parking_lot


# =========================================================
# THÊM BÃI XE
# =========================================================
@router.post(
    "",
    response_model=ParkingLotResponse,
    status_code=status.HTTP_201_CREATED
)
def create_parking_lot(
    data: ParkingLotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Tạm thời chỉ ADMIN mới được thêm bãi xe
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ ADMIN mới có quyền thêm bãi đỗ xe"
        )

    quotas(data)
    parking_lot = ParkingLot(
        name=data.name.strip(),
        address=data.address.strip(),
        latitude=data.latitude,
        longitude=data.longitude,
        description=data.description,
        **{k:getattr(data,k) for k in CAPACITY_FIELDS}
    )

    db.add(parking_lot)
    db.commit()
    db.refresh(parking_lot)

    return parking_lot


# =========================================================
# CẬP NHẬT BÃI XE
# =========================================================
@router.put(
    "/{parking_lot_id}",
    response_model=ParkingLotResponse
)
def update_parking_lot(
    parking_lot_id: int,
    data: ParkingLotUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ ADMIN mới có quyền cập nhật bãi đỗ xe"
        )

    parking_lot = (
        db.query(ParkingLot)
        .filter(ParkingLot.id == parking_lot_id)
        .populate_existing().with_for_update().first()
    )

    if not parking_lot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy bãi đỗ xe"
        )

    update_data = data.model_dump(
        exclude_unset=True
    )

    candidate=SimpleNamespace(**{key:update_data.get(key,getattr(parking_lot,key)) for key in CAPACITY_FIELDS})
    validate_capacity(db,parking_lot,candidate)
    for key, value in update_data.items():
        setattr(parking_lot, key, value)

    db.commit()
    db.refresh(parking_lot)

    return parking_lot


# =========================================================
# XÓA / VÔ HIỆU HÓA BÃI XE
# =========================================================
@router.delete(
    "/{parking_lot_id}"
)
def delete_parking_lot(
    parking_lot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ ADMIN mới có quyền xóa bãi đỗ xe"
        )

    parking_lot = (
        db.query(ParkingLot)
        .filter(ParkingLot.id == parking_lot_id)
        .first()
    )

    if not parking_lot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy bãi đỗ xe"
        )

    # Không xóa vật lý để tránh ảnh hưởng dữ liệu lịch sử
    parking_lot.is_active = False

    db.commit()

    return {
        "message": "Đã vô hiệu hóa bãi đỗ xe"
    }

@router.get('/{parking_lot_id}/capacity')
def get_capacity(parking_lot_id: int,db: Session=Depends(get_db),current_user: User=Depends(get_current_user)):
    lot=db.get(ParkingLot,parking_lot_id)
    if not lot:raise HTTPException(404,'Không tìm thấy bãi xe')
    return capacity_summary(db,lot)

@router.post('/{parking_lot_id}/initialize-layout')
def create_layout(parking_lot_id: int,db: Session=Depends(get_db),current_user: User=Depends(get_current_user)):
    if current_user.role!='ADMIN':raise HTTPException(403,'Chỉ ADMIN được khởi tạo sơ đồ')
    return initialize_layout(db,parking_lot_id)
