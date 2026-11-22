from sqlalchemy import Column, ForeignKey, Integer, String, Text

from database import Base


class ParkingArea(Base):
    __tablename__ = "parking_areas"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    parking_lot_id = Column(
        Integer,
        ForeignKey(
            "parking_lots.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    name = Column(
        String(100),
        nullable=False
    )

    floor_number = Column(
        Integer,
        nullable=True
    )

    description = Column(
        Text,
        nullable=True
    )