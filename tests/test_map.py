from datetime import datetime

from werkzeug.security import generate_password_hash

from app import db
from app.models import ParkingFacility, ParkingFloor, ParkingSession, ParkingSlot, Reservation, User, Vehicle
from app.services import (
    STATE_AVAILABLE,
    STATE_OCCUPIED,
    STATE_RESERVED,
    STATE_UNAVAILABLE,
    slot_states,
)

PASSWORD = "correct-horse"
NOW = datetime(2026, 10, 10, 12, 0)


def make_user(app, email, role="user", facility_id=None):
    with app.app_context():
        user = User(
            username=email.split("@")[0],
            email=email,
            password_hash=generate_password_hash(PASSWORD),
            role=role,
            facility_id=facility_id,
        )
        db.session.add(user)
        db.session.commit()
        return user.user_id


def make_facility(app):
    with app.app_context():
        facility = ParkingFacility(name="Map Mall", address="1 Road", city="Pune", status="active")
        db.session.add(facility)
        db.session.commit()
        return facility.facility_id


def make_floor(app, facility_id):
    with app.app_context():
        floor = ParkingFloor(facility_id=facility_id, floor_number=1)
        db.session.add(floor)
        db.session.commit()
        return floor.floor_id


def make_slot(app, floor_id, number, **overrides):
    values = dict(
        floor_id=floor_id,
        slot_number=number,
        slot_type="standard",
        is_ev_charging=False,
        is_accessible=False,
        map_x=1000.0,
        map_y=2000.0,
        operational_status="active",
    )
    values.update(overrides)
    with app.app_context():
        slot = ParkingSlot(**values)
        db.session.add(slot)
        db.session.commit()
        return slot.slot_id


def make_vehicle(app, user_id):
    with app.app_context():
        vehicle = Vehicle(user_id=user_id, vehicle_number="MH12AB0001", vehicle_type="car")
        db.session.add(vehicle)
        db.session.commit()
        return vehicle.vehicle_id


def log_in(client, email):
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    client.post("/login", data={"email": email, "password": PASSWORD, "csrf_token": token})


def states_for(app, slot_ids):
    with app.app_context():
        slots = [db.session.get(ParkingSlot, sid) for sid in slot_ids]
        return slot_states(slots, now=NOW)


def test_free_active_slot_is_available(app):
    floor_id = make_floor(app, make_facility(app))
    slot_id = make_slot(app, floor_id, "A1")

    assert states_for(app, [slot_id])[slot_id] == STATE_AVAILABLE


def test_slot_with_open_session_is_occupied(app):
    user_id = make_user(app, "alice@example.com")
    floor_id = make_floor(app, make_facility(app))
    slot_id = make_slot(app, floor_id, "A1")
    vehicle_id = make_vehicle(app, user_id)
    with app.app_context():
        db.session.add(ParkingSession(vehicle_id=vehicle_id, slot_id=slot_id, entry_time=NOW, status="active"))
        db.session.commit()

    assert states_for(app, [slot_id])[slot_id] == STATE_OCCUPIED


def test_closed_session_does_not_occupy_slot(app):
    user_id = make_user(app, "alice@example.com")
    floor_id = make_floor(app, make_facility(app))
    slot_id = make_slot(app, floor_id, "A1")
    vehicle_id = make_vehicle(app, user_id)
    with app.app_context():
        db.session.add(ParkingSession(vehicle_id=vehicle_id, slot_id=slot_id, entry_time=NOW, exit_time=NOW, status="completed"))
        db.session.commit()

    assert states_for(app, [slot_id])[slot_id] == STATE_AVAILABLE


def test_confirmed_reservation_covering_now_marks_reserved(app):
    user_id = make_user(app, "alice@example.com")
    floor_id = make_floor(app, make_facility(app))
    slot_id = make_slot(app, floor_id, "A1")
    vehicle_id = make_vehicle(app, user_id)
    with app.app_context():
        db.session.add(Reservation(
            user_id=user_id, vehicle_id=vehicle_id, slot_id=slot_id,
            start_time=datetime(2026, 10, 10, 11, 50), end_time=datetime(2026, 10, 10, 13, 0),
            reservation_type="hourly", status="confirmed",
        ))
        db.session.commit()

    assert states_for(app, [slot_id])[slot_id] == STATE_RESERVED


def test_future_reservation_does_not_mark_reserved_now(app):
    user_id = make_user(app, "alice@example.com")
    floor_id = make_floor(app, make_facility(app))
    slot_id = make_slot(app, floor_id, "A1")
    vehicle_id = make_vehicle(app, user_id)
    with app.app_context():
        db.session.add(Reservation(
            user_id=user_id, vehicle_id=vehicle_id, slot_id=slot_id,
            start_time=datetime(2026, 10, 10, 14, 0), end_time=datetime(2026, 10, 10, 16, 0),
            reservation_type="hourly", status="confirmed",
        ))
        db.session.commit()

    assert states_for(app, [slot_id])[slot_id] == STATE_AVAILABLE


def test_maintenance_slot_is_unavailable_even_when_free(app):
    floor_id = make_floor(app, make_facility(app))
    slot_id = make_slot(app, floor_id, "A1", operational_status="maintenance")

    assert states_for(app, [slot_id])[slot_id] == STATE_UNAVAILABLE


def test_occupied_takes_priority_over_reserved(app):
    user_id = make_user(app, "alice@example.com")
    floor_id = make_floor(app, make_facility(app))
    slot_id = make_slot(app, floor_id, "A1")
    vehicle_id = make_vehicle(app, user_id)
    with app.app_context():
        db.session.add(ParkingSession(vehicle_id=vehicle_id, slot_id=slot_id, entry_time=NOW, status="active"))
        db.session.add(Reservation(
            user_id=user_id, vehicle_id=vehicle_id, slot_id=slot_id,
            start_time=datetime(2026, 10, 10, 11, 50), end_time=datetime(2026, 10, 10, 13, 0),
            reservation_type="hourly", status="confirmed",
        ))
        db.session.commit()

    assert states_for(app, [slot_id])[slot_id] == STATE_OCCUPIED


def test_map_requires_sign_in(client, app):
    facility_id = make_facility(app)

    response = client.get(f"/facilities/{facility_id}/map")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_map_ev_filter_hides_non_ev_slots(client, app):
    make_user(app, "alice@example.com")
    facility_id = make_facility(app)
    floor_id = make_floor(app, facility_id)
    make_slot(app, floor_id, "EV-SLOT", is_ev_charging=True)
    make_slot(app, floor_id, "PLAIN-SLOT", is_ev_charging=False)
    log_in(client, "alice@example.com")

    response = client.get(f"/facilities/{facility_id}/map?ev=1")

    assert response.status_code == 200
    assert b"EV-SLOT" in response.data
    assert b"PLAIN-SLOT" not in response.data
