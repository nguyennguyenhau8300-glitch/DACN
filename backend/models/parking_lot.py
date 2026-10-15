from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from database import Base


class ParkingLot(Base):
    __tablename__ = "parking_lots"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String(150),
        nullable=False
    )

    address = Column(
        String(255),
        nullable=False
    )

    latitude = Column(
        Float,
        nullable=True
    )

    longitude = Column(
        Float,
        nullable=True
    )

    description = Column(
        Text,
        nullable=True
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True
    )

    car_capacity = Column(Integer, nullable=False, default=50, server_default='50')
    motorbike_capacity = Column(Integer, nullable=False, default=120, server_default='120')
    electric_car_capacity = Column(Integer, nullable=False, default=20, server_default='20')
    electric_motorbike_capacity = Column(Integer, nullable=False, default=50, server_default='50')

    created_at = Column(
        DateTime,
        server_default=func.now()
    )