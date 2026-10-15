from datetime import datetime

from pydantic import BaseModel, Field


class SensorDataCreate(BaseModel):
    sensor_code: str = Field(
        min_length=1,
        max_length=100
    )

    sensor_status: str


class SensorLogResponse(BaseModel):
    id: int
    parking_spot_id: int
    sensor_status: str
    recorded_at: datetime

    model_config = {
        "from_attributes": True
    }


class SensorUpdateResponse(BaseModel):
    message: str
    parking_spot_id: int
    spot_code: str
    sensor_code: str
    old_status: str
    new_status: str