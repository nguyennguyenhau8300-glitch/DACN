from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.parking_area import ParkingArea
from models.parking_lot import ParkingLot
from models.user import User
from schemas.parking_area import (
    ParkingAreaCreate,
    ParkingAreaResponse,
    ParkingAreaUpdate
)


router = APIRouter(
    prefix="/parking-areas",
    tags=["Parking Areas"]
)


# =========================================================
# DANH SÁCH KHU VỰC
# =========================================================
@router.get(
    "",
    response_model=list[ParkingAreaResponse]
)
def get_parking_areas(
    parking_lot_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(ParkingArea)

    if parking_lot_id is not None:
        query = query.filter(
            ParkingArea.parking_lot_id == parking_lot_id
        )

    return query.order_by(ParkingArea.id.asc()).all()


# =========================================================
# CHI TIẾT KHU VỰC
# =========================================================
@router.get(
    "/{area_id}",
    response_model=ParkingAreaResponse
)
def get_parking_area(
    area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    area = (
        db.query(ParkingArea)
        .filter(ParkingArea.id == area_id)
        .first()
    )

    if not area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy khu vực"
        )

    return area


# =========================================================
# THÊM KHU VỰC
# =========================================================
@router.post(
    "",
    response_model=ParkingAreaResponse,
    status_code=status.HTTP_201_CREATED
)
def create_parking_area(
    data: ParkingAreaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ ADMIN mới có quyền thêm khu vực"
        )

    parking_lot = (
        db.query(ParkingLot)
        .filter(ParkingLot.id == data.parking_lot_id)
        .first()
    )

    if not parking_lot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bãi đỗ xe không tồn tại"
        )

    area = ParkingArea(
        parking_lot_id=data.parking_lot_id,
        name=data.name.strip(),
        floor_number=data.floor_number,
        description=data.description
    )

    db.add(area)
    db.commit()
    db.refresh(area)

    return area


# =========================================================
# CẬP NHẬT KHU VỰC
# =========================================================
@router.put(
    "/{area_id}",
    response_model=ParkingAreaResponse
)
def update_parking_area(
    area_id: int,
    data: ParkingAreaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ ADMIN mới có quyền cập nhật khu vực"
        )

    area = (
        db.query(ParkingArea)
        .filter(ParkingArea.id == area_id)
        .first()
    )

    if not area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy khu vực"
        )

    update_data = data.model_dump(
        exclude_unset=True
    )

    for key, value in update_data.items():
        setattr(area, key, value)

    db.commit()
    db.refresh(area)

    return area


# =========================================================
# XÓA KHU VỰC
# =========================================================
@router.delete(
    "/{area_id}"
)
def delete_parking_area(
    area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ ADMIN mới có quyền xóa khu vực"
        )

    area = (
        db.query(ParkingArea)
        .filter(ParkingArea.id == area_id)
        .first()
    )

    if not area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy khu vực"
        )

    from models.parking_spot import ParkingSpot
    if db.query(ParkingSpot).filter_by(parking_area_id=area.id).first():
        raise HTTPException(409, 'Còn dữ liệu con; không thể xóa')
    db.delete(area)
    db.commit()

    return {
        "message": "Xóa khu vực thành công"
    }