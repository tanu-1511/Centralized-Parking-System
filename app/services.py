from datetime import datetime

from app import db
from app.models import ParkingSession, Reservation

STATE_AVAILABLE = "available"
STATE_OCCUPIED = "occupied"
STATE_RESERVED = "reserved"
STATE_UNAVAILABLE = "unavailable"

SLOT_ACTIVE = "active"
SESSION_ACTIVE = "active"
RESERVATION_CONFIRMED = "confirmed"
RESERVATION_CANCELLED = "cancelled"
RESERVATION_BLOCKING_STATUSES = (RESERVATION_CONFIRMED, "active")


def slot_states(slots, now=None):
    """Return {slot_id: state} for the given slots, based on database rows.

    Priority: operational status first (a slot that is not active is
    unavailable), then physical occupancy, then a reservation covering `now`.
    Operational status is never treated as availability on its own.
    """
    now = now or datetime.now()
    slot_ids = [slot.slot_id for slot in slots]
    if not slot_ids:
        return {}

    occupied = {
        row.slot_id
        for row in ParkingSession.query.filter(
            ParkingSession.slot_id.in_(slot_ids),
            ParkingSession.status == SESSION_ACTIVE,
            ParkingSession.exit_time.is_(None),
        ).all()
    }
    reserved = {
        row.slot_id
        for row in Reservation.query.filter(
            Reservation.slot_id.in_(slot_ids),
            Reservation.status.in_(RESERVATION_BLOCKING_STATUSES),
            Reservation.start_time <= now,
            Reservation.end_time > now,
        ).all()
    }

    states = {}
    for slot in slots:
        if slot.operational_status != SLOT_ACTIVE:
            states[slot.slot_id] = STATE_UNAVAILABLE
        elif slot.slot_id in occupied:
            states[slot.slot_id] = STATE_OCCUPIED
        elif slot.slot_id in reserved:
            states[slot.slot_id] = STATE_RESERVED
        else:
            states[slot.slot_id] = STATE_AVAILABLE
    return states


def has_conflict(slot_id, start, end):
    """True if an active reservation on this slot overlaps [start, end).

    Back-to-back bookings (one ends exactly when the next starts) do not overlap.
    """
    return Reservation.query.filter(
        Reservation.slot_id == slot_id,
        Reservation.status.in_(RESERVATION_BLOCKING_STATUSES),
        Reservation.start_time < end,
        Reservation.end_time > start,
    ).first() is not None
