from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    license_plate = Column(
        String(20),
        unique=True,
        nullable=False,
        index=True
    )

    vehicle_type = Column(
        String(20),
        nullable=False
    )

    energy_type = Column(String(20), nullable=False, default='GASOLINE', server_default='GASOLINE')

    brand = Column(
        String(50),
        nullable=True
    )

    color = Column(
        String(50),
        nullable=True
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )