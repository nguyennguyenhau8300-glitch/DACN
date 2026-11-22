from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import and_, exists, or_

from models.operations import ParkingSession
from models.reservation import Reservation
from schemas.reservation import ReservationResponse
from services.parking_service import now


MAX_ADVANCE_MINUTES = 120
CHECKIN_WINDOW_MINUTES = 120
LIVE_STATES = ('PENDING', 'CONFIRMED')


def booking_deadline(start, requested_expiry, requested_at, *, end_time=None):
    if any(value is not None and value.tzinfo is not None for value in (start, requested_expiry, end_time)):
        raise HTTPException(400, 'Dùng giờ Việt Nam không kèm múi giờ')
    if start < requested_at:
        raise HTTPException(400, 'Giờ bắt đầu đã qua. Hãy chọn giờ đến mới.')
    if end_time is None and start > requested_at + timedelta(minutes=MAX_ADVANCE_MINUTES):
        raise HTTPException(422, 'Chỉ được đặt trước tối đa 2 giờ kể từ lúc đặt chỗ.')
    window = timedelta(minutes=CHECKIN_WINDOW_MINUTES)
    if end_time is not None:
        if end_time <= start:
            raise HTTPException(422, 'Giờ rời bãi dự kiến phải sau giờ bắt đầu.')
        window = min(window, end_time - start)
    deadline = start + window
    if requested_expiry is None:
        return deadline
    if requested_expiry <= start:
        raise HTTPException(400, 'Hạn nhận xe phải sau giờ bắt đầu.')
    if requested_expiry > deadline:
        raise HTTPException(422, 'Hạn nhận xe không được vượt khung giờ đã chọn.' if end_time is not None
                            else 'Hạn nhận xe tối đa 2 giờ sau giờ bắt đầu.')
    return requested_expiry


def arrival_status(reservation, at, checked_in=False):
    if reservation.status not in LIVE_STATES:
        return reservation.status
    if checked_in:
        return 'CHECKED_IN'
    if at >= reservation.expiry_time:
        return 'EXPIRED'
    if reservation.status == 'PENDING':
        return 'PENDING'
    return 'UPCOMING' if at < reservation.start_time else 'READY'


def current_hold(at):
    """An immediate hold starts on confirmation, a scheduled hold starts at arrival time."""
    return and_(
        Reservation.status.in_(LIVE_STATES), Reservation.expiry_time > at,
        or_(Reservation.end_time.is_(None), Reservation.start_time <= at),
    )


def overlaps_window(start, end, at):
    # Half-open intervals let two reservations use the same spot at consecutive times.
    return and_(
        Reservation.status.in_(LIVE_STATES), Reservation.expiry_time > at,
        or_(
            and_(Reservation.end_time.is_(None), Reservation.expiry_time > start),
            and_(Reservation.start_time < end, Reservation.end_time > start),
        ),
    )


def slot_follows_active_stay(planned_exit, start, at):
    return planned_exit is not None and at < planned_exit <= start


def reservation_view(row, at, checked_in=False):
    return ReservationResponse(
        id=row.id, user_id=row.user_id, vehicle_id=row.vehicle_id, parking_spot_id=row.parking_spot_id,
        start_time=row.start_time, expiry_time=row.expiry_time, end_time=row.end_time,
        status=row.status, created_at=row.created_at,
        arrival_status=arrival_status(row, at, checked_in),
    )


def reservation_views(query):
    checked_in = exists().where(
        ParkingSession.reservation_id == Reservation.id,
        ParkingSession.status == 'ACTIVE',
    )
    at = now()
    return [reservation_view(row, at, active) for row, active in query.add_columns(checked_in)]
