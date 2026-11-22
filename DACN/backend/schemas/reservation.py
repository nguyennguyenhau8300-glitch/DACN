from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field


ArrivalStatus = Literal['PENDING', 'UPCOMING', 'READY', 'CHECKED_IN', 'EXPIRED', 'CANCELLED', 'COMPLETED']


class ReservationCreate(BaseModel):
    vehicle_id: int = Field(gt=0)
    parking_spot_id: int = Field(gt=0)
    start_time: datetime
    expiry_time: datetime | None = None
    end_time: datetime | None = None


class ReservationPolicyResponse(BaseModel):
    max_advance_minutes: int
    checkin_window_minutes: int
    server_time: datetime
    timezone: Literal['Asia/Ho_Chi_Minh'] = 'Asia/Ho_Chi_Minh'


class ReservationResponse(BaseModel):
    id: int
    user_id: int
    vehicle_id: int
    parking_spot_id: int
    start_time: datetime
    expiry_time: datetime
    end_time: datetime | None = None
    status: str
    arrival_status: ArrivalStatus
    created_at: datetime

    model_config = {
        "from_attributes": True
    }
