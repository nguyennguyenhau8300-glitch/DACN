from services.parking_service import now, staff
import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.parking_spot import ParkingSpot
from models.sensor_log import SensorLog
from models.user import User
from schemas.sensor import (
    SensorDataCreate,
    SensorLogResponse,
    SensorUpdateResponse
)


router = APIRouter(
    prefix="/iot",
    tags=["IoT"]
)


# =========================================================
# CẢM BIẾN GỬI TRẠNG THÁI Ô ĐỖ
# =========================================================
@router.post(
    "/sensor",
    response_model=SensorUpdateResponse
)
def update_sensor(
    data: SensorDataCreate,
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db)
):
    key = os.getenv("IOT_API_KEY")
    if not key:
        raise HTTPException(503, "Cần cấu hình IOT_API_KEY")
    if not x_api_key or not secrets.compare_digest(x_api_key.encode("utf-8"),key.encode("utf-8")):
        raise HTTPException(401, "API key thiết bị không hợp lệ")
    sensor_code = data.sensor_code.strip()
    sensor_status = data.sensor_status.upper().strip()

    allowed_statuses = {
        "AVAILABLE",
        "OCCUPIED"
    }

    if sensor_status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sensor_status chỉ được AVAILABLE hoặc OCCUPIED"
        )

    # Tìm ô đỗ dựa vào mã cảm biến
    spot = (
        db.query(ParkingSpot)
        .filter(ParkingSpot.sensor_code == sensor_code)
        .populate_existing().with_for_update()
        .first()
    )

    if not spot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy cảm biến"
        )

    from models.iot_device import IotDevice
    from services.iot_service import apply_sensor
    if db.query(IotDevice.id).filter_by(parking_spot_id=spot.id, kind='SENSOR').first():
        raise HTTPException(409, 'Cảm biến đã đăng ký; dùng khóa riêng và API /iot/devices/{code}/telemetry')
    result = apply_sensor(db, spot, sensor_status)
    result['message'] = 'Cập nhật trạng thái cảm biến thành công'
    db.commit()
    return result


# =========================================================
# XEM LỊCH SỬ CẢM BIẾN
# =========================================================
@router.get(
    "/sensor-logs",
    response_model=list[SensorLogResponse]
)
def get_sensor_logs(
    parking_spot_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    staff(current_user)
    query = db.query(SensorLog)

    if parking_spot_id is not None:
        query = query.filter(
            SensorLog.parking_spot_id == parking_spot_id
        )

    return (
        query
        .order_by(SensorLog.recorded_at.desc())
        .limit(limit)
        .all()
    )