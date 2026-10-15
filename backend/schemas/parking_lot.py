from schemas.input import InputModel
from datetime import datetime

from pydantic import BaseModel, Field


class CapacityCreate(InputModel):
    car_capacity: int = Field(50,ge=30,le=50)
    motorbike_capacity: int = Field(120,ge=90,le=120)
    electric_car_capacity: int = Field(20,ge=0,le=50)
    electric_motorbike_capacity: int = Field(50,ge=0,le=120)

class ParkingLotCreate(CapacityCreate):
    non_nullable = {'address', 'is_active', 'name', 'car_capacity','motorbike_capacity','electric_car_capacity','electric_motorbike_capacity'}
    name: str = Field(
        min_length=2,
        max_length=150
    )

    address: str = Field(
        min_length=2,
        max_length=255
    )

    latitude: float | None = None
    longitude: float | None = None

    description: str | None = None


class ParkingLotUpdate(InputModel):
    non_nullable = {'address', 'is_active', 'name', 'car_capacity','motorbike_capacity','electric_car_capacity','electric_motorbike_capacity'}
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=150
    )

    address: str | None = Field(
        default=None,
        min_length=2,
        max_length=255
    )

    latitude: float | None = None
    longitude: float | None = None
    description: str | None = None
    is_active: bool | None = None
    car_capacity: int | None = Field(None,ge=30,le=50)
    motorbike_capacity: int | None = Field(None,ge=90,le=120)
    electric_car_capacity: int | None = Field(None,ge=0,le=50)
    electric_motorbike_capacity: int | None = Field(None,ge=0,le=120)


class ParkingLotResponse(BaseModel):
    id: int
    name: str
    address: str
    latitude: float | None
    longitude: float | None
    description: str | None
    is_active: bool
    car_capacity: int
    motorbike_capacity: int
    electric_car_capacity: int
    electric_motorbike_capacity: int
    created_at: datetime

    model_config = {
        "from_attributes": True
    }