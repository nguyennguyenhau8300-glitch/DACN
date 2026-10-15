from typing import Literal
from schemas.input import InputModel
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class VehicleInput(InputModel):
    @field_validator('license_plate', check_fields=False)
    @classmethod
    def valid_plate(cls,value):
        if value is None: return value
        import re
        if not re.fullmatch(r'[A-Za-z0-9 .-]+',value) or len(re.sub(r'[^A-Za-z0-9]','',value))<5:
            raise ValueError('Biển số chỉ gồm chữ Latin, chữ số, dấu cách/chấm/gạch')
        return value.upper()

class VehicleCreate(VehicleInput):
    non_nullable = {'license_plate', 'vehicle_type', 'energy_type'}
    license_plate: str = Field(
        min_length=5,
        max_length=20
    )

    vehicle_type: Literal['MOTORBIKE','CAR']
    energy_type: Literal['GASOLINE','ELECTRIC'] = 'GASOLINE'

    brand: str | None = Field(
        default=None,
        max_length=50
    )

    color: str | None = Field(
        default=None,
        max_length=50
    )


class VehicleUpdate(VehicleInput):
    non_nullable = {'license_plate', 'vehicle_type', 'energy_type'}
    license_plate: str | None = Field(
        default=None,
        min_length=5,
        max_length=20
    )

    vehicle_type: Literal['MOTORBIKE','CAR'] | None = None
    energy_type: Literal['GASOLINE','ELECTRIC'] | None = None

    brand: str | None = Field(
        default=None,
        max_length=50
    )

    color: str | None = Field(
        default=None,
        max_length=50
    )


class VehicleResponse(BaseModel):
    id: int
    user_id: int | None
    license_plate: str
    vehicle_type: str
    energy_type: str
    brand: str | None
    color: str | None
    created_at: datetime

    model_config = {
        "from_attributes": True
    }