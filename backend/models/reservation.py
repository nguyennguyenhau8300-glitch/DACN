from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from database import Base


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    vehicle_id = Column(
        Integer,
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False
    )

    parking_spot_id = Column(
        Integer,
        ForeignKey("parking_spots.id", ondelete="CASCADE"),
        nullable=False
    )

    start_time = Column(
        DateTime,
        nullable=False
    )

    expiry_time = Column(
        DateTime,
        nullable=False
    )

    status = Column(
        String(20),
        nullable=False,
        default="PENDING"
    )

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now()
    )