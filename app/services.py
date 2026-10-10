from datetime import datetime, timedelta

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
RESERVATION_EXPIRED = "expired"
RESERVATION_BLOCKING_STATUSES = (RESERVATION_CONFIRMED, "active")

# How long after a reservation starts the driver has to arrive.
RESERVATION_GRACE = timedelta(minutes=15)


def expire_stale_reservations(now=None):
    """Mark confirmed reservations as expired if the driver never arrived.

    A reservation has expired when the grace period after its start has
    passed and no parking session exists for its vehicle and slot within
    the window. Runs on each availability check, so no scheduler is needed.
    Returns the number of reservations expired.
    """
    now = now or datetime.now()
    cutoff = now - RESERVATION_GRACE
    candidates = Reservation.query.filter(
        Reservation.status == RESERVATION_CONFIRMED,
        Reservation.start_time <= cutoff,
    ).all()

    expired = 0
    for reservation in candidates:
        if _driver_arrived(reservation):
            continue
        reservation.status = RESERVATION_EXPIRED
        expired += 1

    if expired:
        db.session.commit()
    return expired


def _driver_arrived(reservation):
    window_start = reservation.start_time - RESERVATION_GRACE
    window_end = reservation.start_time + RESERVATION_GRACE
    return ParkingSession.query.filter(
        ParkingSession.slot_id == reservation.slot_id,
        ParkingSession.vehicle_id == reservation.vehicle_id,
        ParkingSession.entry_time >= window_start,
        ParkingSession.entry_time <= window_end,
    ).first() is not None


def slot_states(slots, now=None):
    """Return {slot_id: state} for the given slots, based on database rows.

    Priority: operational status first (a slot that is not active is
    unavailable), then physical occupancy, then a reservation covering `now`.
    Operational status is never treated as availability on its own.
    """
    now = now or datetime.now()
    expire_stale_reservations(now)

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


def has_conflict(slot_id, start, end, now=None):
    """True if an active reservation on this slot overlaps [start, end).

    Back-to-back bookings (one ends exactly when the next starts) do not overlap.
    Expired reservations are swept first, so they never block a new booking.
    """
    expire_stale_reservations(now)
    return Reservation.query.filter(
        Reservation.slot_id == slot_id,
        Reservation.status.in_(RESERVATION_BLOCKING_STATUSES),
        Reservation.start_time < end,
        Reservation.end_time > start,
    ).first() is not None


def can_manage_facility(user, facility_id):
    """System admins manage every facility; parking admins only their own."""
    if user.role == "admin":
        return True
    return user.role == "parking_admin" and user.facility_id == facility_id
