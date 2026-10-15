from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ReservationCreate(BaseModel):
    vehicle_id: int = Field(gt=0)
    parking_spot_id: int = Field(gt=0)
    start_time: datetime
    expiry_time: datetime


class ReservationResponse(BaseModel):
    id: int
    user_id: int
    vehicle_id: int
    parking_spot_id: int
    start_time: datetime
    expiry_time: datetime
    status: str
    created_at: datetime

    model_config = {
        "from_attributes": True
    }