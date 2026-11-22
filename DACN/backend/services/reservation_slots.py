from sqlalchemy import exists

from models.operations import ParkingSession
from models.parking_area import ParkingArea
from models.parking_spot import ParkingSpot
from models.reservation import Reservation
from services.iot_service import devices_allow_entry, load_devices_for_availability
from services.reservation_policy import overlaps_window, slot_follows_active_stay


def active_stays(db):
    return db.query(
        ParkingSession.parking_spot_id, ParkingSession.vehicle_id, Reservation.end_time,
    ).outerjoin(Reservation, Reservation.id == ParkingSession.reservation_id).filter(ParkingSession.status == 'ACTIVE')


def spot_accepts_slot(spot, active_departures, start, at):
    if spot.status not in {'AVAILABLE', 'RESERVED', 'OCCUPIED'}:
        return False
    if spot.id in active_departures:
        return slot_follows_active_stay(active_departures[spot.id], start, at)
    return spot.status != 'OCCUPIED'


def free_spots(db, lot_id, vehicle_type, energy_type, start, end, at):
    types = ('CAR', 'DISABLED') if vehicle_type == 'CAR' else (vehicle_type,)
    conflicting = exists().where(Reservation.parking_spot_id == ParkingSpot.id, overlaps_window(start, end, at))
    spots = db.query(ParkingSpot).join(ParkingArea).filter(
        ParkingArea.parking_lot_id == lot_id, ParkingSpot.spot_type.in_(types),
        ParkingSpot.energy_type == energy_type, ~conflicting,
    ).order_by(ParkingSpot.spot_code).all()
    ids = [spot.id for spot in spots]
    if not ids:
        return []
    departures = {
        spot_id: end_time for spot_id, _, end_time in active_stays(db).filter(ParkingSession.parking_spot_id.in_(ids))
    }
    devices, overheated = load_devices_for_availability(db, ids)
    eligible = []
    for spot in spots:
        if not spot_accepts_slot(spot, departures, start, at):
            continue
        if energy_type == 'ELECTRIC' and spot.charger_status != 'READY':
            continue
        in_use = spot.id in departures
        if devices_allow_entry(
            devices.get(spot.id, ()), at=at, overheated_ids=overheated,
            allow_occupied_sensor=in_use or spot.status == 'RESERVED', allow_busy_charger=in_use,
        ):
            spot.available_for_booking = True
            eligible.append(spot)
    return eligible
