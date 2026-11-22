from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field

class ORMResponse(BaseModel):
    model_config = {'from_attributes': True}

class CheckIn(BaseModel):
    vehicle_id: int = Field(gt=0)
    parking_spot_id: int = Field(gt=0)
    reservation_id: int | None = Field(default=None, gt=0)
    entry_plate_image: str | None = Field(default=None, max_length=2000)
    entry_plate_confidence: Decimal | None = Field(default=None, ge=0, le=1)

class CheckOut(BaseModel):
    exit_plate_image: str | None = Field(default=None, max_length=2000)
    exit_plate_confidence: Decimal | None = Field(default=None, ge=0, le=1)

class FeeLine(BaseModel):
    kind: Literal['FIRST_HOUR', 'ADDITIONAL_HOURS', 'TIME_BAND']
    hours: int
    unit_price: Decimal
    amount: Decimal
    start_minute: int | None = None
    end_minute: int | None = None


class FeeCalculation(BaseModel):
    elapsed_seconds: Decimal
    billed_hours: int
    lines: list[FeeLine]
    parking_fee: Decimal
    charging_fee: Decimal = Decimal('0.00')


class FeeBreakdown(FeeCalculation):
    pricing_rule_id: int
    vehicle_type: str
    energy_type: str


class SessionCharge(ORMResponse):
    id: int
    entry_time: datetime
    exit_time: datetime | None
    total_amount: Decimal
    fee_breakdown: FeeBreakdown | None = None


class SessionResponse(SessionCharge):
    vehicle_id: int
    parking_spot_id: int | None
    reservation_id: int | None
    status: str
    entry_plate_image: str | None
    exit_plate_image: str | None
    entry_plate_confidence: Decimal | None
    exit_plate_confidence: Decimal | None

class PricingCreate(BaseModel):
    parking_lot_id: int = Field(gt=0)
    vehicle_type: Literal['MOTORBIKE','CAR']
    energy_type: Literal['GASOLINE','ELECTRIC'] = 'GASOLINE'
    first_hour_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    additional_hour_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    is_active: bool = True

class PricingResponse(PricingCreate, ORMResponse):
    id: int
    created_at: datetime
    time_bands: list[dict] = Field(default_factory=list)

class PaymentCreate(BaseModel):
    parking_session_id: int = Field(gt=0)
    payment_method: Literal['CASH'] = 'CASH'

class PaymentResponse(ORMResponse):
    id: int
    parking_session_id: int
    amount: Decimal
    payment_method: str
    status: str
    transaction_code: str | None
    paid_at: datetime | None
    created_at: datetime


class RevenueReceipt(BaseModel):
    payment: PaymentResponse
    session: SessionCharge
    sandbox: bool


class RevenueReceipts(BaseModel):
    items: list[RevenueReceipt]
    has_more: bool
