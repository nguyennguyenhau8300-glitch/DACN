from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from database import Base


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint(
            'end_time IS NULL OR (start_time < expiry_time AND expiry_time <= end_time)',
            name='ck_reservation_slot_end',
        ),
    )

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

    end_time = Column(DateTime, nullable=True)

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
