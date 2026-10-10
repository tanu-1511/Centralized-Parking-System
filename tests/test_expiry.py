from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import db
from app.models import ParkingFacility, ParkingFloor, ParkingSession, ParkingSlot, Reservation, User, Vehicle
from app.services import (
    RESERVATION_CANCELLED,
    RESERVATION_CONFIRMED,
    RESERVATION_EXPIRED,
    STATE_AVAILABLE,
    expire_stale_reservations,
    slot_states,
)

NOW = datetime(2026, 10, 10, 12, 0)


def setup_world(app):
    """Create one user, vehicle, and slot. Returns their ids."""
    with app.app_context():
        user = User(username="alice", email="alice@example.com",
                    password_hash=generate_password_hash("pw-12345"), role="user")
        facility = ParkingFacility(name="Expiry Mall", address="1 Road", city="Pune", status="active")
        db.session.add_all([user, facility])
        db.session.flush()
        floor = ParkingFloor(facility_id=facility.facility_id, floor_number=1)
        db.session.add(floor)
        db.session.flush()
        slot = ParkingSlot(floor_id=floor.floor_id, slot_number="A1", slot_type="standard",
                           is_ev_charging=False, is_accessible=False, map_x=1.0, map_y=1.0,
                           operational_status="active")
        vehicle = Vehicle(user_id=user.user_id, vehicle_number="AAA1111", vehicle_type="car")
        db.session.add_all([slot, vehicle])
        db.session.commit()
        return user.user_id, vehicle.vehicle_id, slot.slot_id


def add_reservation(app, ids, start, end, status=RESERVATION_CONFIRMED):
    user_id, vehicle_id, slot_id = ids
    with app.app_context():
        reservation = Reservation(user_id=user_id, vehicle_id=vehicle_id, slot_id=slot_id,
                                  start_time=start, end_time=end,
                                  reservation_type="standard", status=status)
        db.session.add(reservation)
        db.session.commit()
        return reservation.reservation_id


def status_of(app, reservation_id):
    with app.app_context():
        return db.session.get(Reservation, reservation_id).status


def test_missed_reservation_expires_after_grace(app):
    ids = setup_world(app)
    rid = add_reservation(app, ids, NOW - timedelta(minutes=30), NOW + timedelta(hours=1))

    with app.app_context():
        assert expire_stale_reservations(NOW) == 1
    assert status_of(app, rid) == RESERVATION_EXPIRED


def test_reservation_within_grace_stays_confirmed(app):
    ids = setup_world(app)
    rid = add_reservation(app, ids, NOW - timedelta(minutes=5), NOW + timedelta(hours=1))

    with app.app_context():
        assert expire_stale_reservations(NOW) == 0
    assert status_of(app, rid) == RESERVATION_CONFIRMED


def test_driver_who_arrived_keeps_reservation(app):
    user_id, vehicle_id, slot_id = setup_world(app)
    rid = add_reservation(app, (user_id, vehicle_id, slot_id),
                          NOW - timedelta(minutes=30), NOW + timedelta(hours=1))
    with app.app_context():
        db.session.add(ParkingSession(vehicle_id=vehicle_id, slot_id=slot_id,
                                      entry_time=NOW - timedelta(minutes=25), status="active"))
        db.session.commit()

    with app.app_context():
        expire_stale_reservations(NOW)
    assert status_of(app, rid) == RESERVATION_CONFIRMED


def test_expired_reservation_frees_the_slot(app):
    ids = setup_world(app)
    add_reservation(app, ids, NOW - timedelta(minutes=30), NOW + timedelta(hours=1))
    slot_id = ids[2]

    with app.app_context():
        slot = db.session.get(ParkingSlot, slot_id)
        assert slot_states([slot], now=NOW)[slot_id] == STATE_AVAILABLE


def test_cancelled_reservation_is_not_touched(app):
    ids = setup_world(app)
    rid = add_reservation(app, ids, NOW - timedelta(minutes=30), NOW + timedelta(hours=1),
                          status=RESERVATION_CANCELLED)

    with app.app_context():
        assert expire_stale_reservations(NOW) == 0
    assert status_of(app, rid) == RESERVATION_CANCELLED
