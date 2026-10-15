from schemas.input import InputModel
from pydantic import BaseModel, Field


class ParkingAreaCreate(InputModel):
    non_nullable = {'parking_lot_id', 'name'}
    parking_lot_id: int

    name: str = Field(
        min_length=1,
        max_length=100
    )

    floor_number: int | None = None

    description: str | None = None


class ParkingAreaUpdate(InputModel):
    non_nullable = {'parking_lot_id', 'name'}
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100
    )

    floor_number: int | None = None

    description: str | None = None


class ParkingAreaResponse(BaseModel):
    id: int
    parking_lot_id: int
    name: str
    floor_number: int | None
    description: str | None

    model_config = {
        "from_attributes": True
    }