from typing import Literal
from schemas.input import InputModel
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class SpotInput(InputModel):
    @field_validator('sensor_code', check_fields=False)
    @classmethod
    def sensor_code_value(cls,value):
        return value or None

class ParkingSpotCreate(SpotInput):
    non_nullable = {'spot_type', 'status', 'spot_code', 'parking_area_id', 'energy_type','charger_type','charger_status'}
    parking_area_id: int

    spot_code: str = Field(
        min_length=1,
        max_length=30
    )

    spot_type: Literal['MOTORBIKE','CAR','DISABLED']
    energy_type: Literal['GASOLINE','ELECTRIC'] = 'GASOLINE'
    charger_type: Literal['NONE','SOCKET','EV_CHARGER'] = 'NONE'
    charging_station_code: str | None = Field(None,min_length=1,max_length=100)
    charging_port_code: str | None = Field(None,min_length=1,max_length=30)
    charging_power_kw: Decimal | None = Field(None,gt=0,max_digits=8,decimal_places=2)
    charger_status: Literal['NOT_APPLICABLE','PLANNED','READY','OFFLINE','MAINTENANCE'] = 'NOT_APPLICABLE'

    position_x: Decimal | None = None
    position_y: Decimal | None = None

    sensor_code: str | None = Field(
        default=None,
        max_length=100
    )


class ParkingSpotUpdate(SpotInput):
    non_nullable = {'spot_type', 'status', 'spot_code', 'parking_area_id', 'energy_type','charger_type','charger_status'}
    spot_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=30
    )

    spot_type: Literal['MOTORBIKE','CAR','DISABLED'] | None = None
    energy_type: Literal['GASOLINE','ELECTRIC'] | None = None
    charger_type: Literal['NONE','SOCKET','EV_CHARGER'] | None = None
    charging_station_code: str | None = Field(None,min_length=1,max_length=100)
    charging_port_code: str | None = Field(None,min_length=1,max_length=30)
    charging_power_kw: Decimal | None = Field(None,gt=0,max_digits=8,decimal_places=2)
    charger_status: Literal['NOT_APPLICABLE','PLANNED','READY','OFFLINE','MAINTENANCE'] | None = None
    status: str | None = None

    position_x: Decimal | None = None
    position_y: Decimal | None = None

    sensor_code: str | None = Field(
        default=None,
        max_length=100
    )


class ParkingSpotResponse(BaseModel):
    available_for_booking: bool | None = None
    id: int
    parking_area_id: int
    spot_code: str
    spot_type: str
    energy_type: str
    charger_type: str
    charging_station_code: str | None
    charging_port_code: str | None
    charging_power_kw: Decimal | None
    charger_status: str
    status: str
    position_x: Decimal | None
    position_y: Decimal | None
    sensor_code: str | None
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class ParkingSnapshotResponse(BaseModel):
    spots: list[ParkingSpotResponse]
    capacity: dict
