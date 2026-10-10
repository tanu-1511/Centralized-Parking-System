from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import db
from app.models import ParkingFacility, ParkingFloor, ParkingSession, ParkingSlot, User, Vehicle

PASSWORD = "correct-horse"
NOW = datetime.now()


def make_user(app, email):
    with app.app_context():
        user = User(username=email.split("@")[0], email=email,
                    password_hash=generate_password_hash(PASSWORD), role="user")
        db.session.add(user)
        db.session.commit()
        return user.user_id


def make_slot(app, facility_name, slot_number):
    with app.app_context():
        facility = ParkingFacility(name=facility_name, address="1 Road", city="Pune", status="active")
        db.session.add(facility)
        db.session.flush()
        floor = ParkingFloor(facility_id=facility.facility_id, floor_number=3)
        db.session.add(floor)
        db.session.flush()
        slot = ParkingSlot(floor_id=floor.floor_id, slot_number=slot_number, slot_type="standard",
                           is_ev_charging=False, is_accessible=False, map_x=1.0, map_y=1.0,
                           operational_status="active")
        db.session.add(slot)
        db.session.commit()
        return slot.slot_id


def make_vehicle(app, user_id, number):
    with app.app_context():
        vehicle = Vehicle(user_id=user_id, vehicle_number=number, vehicle_type="car")
        db.session.add(vehicle)
        db.session.commit()
        return vehicle.vehicle_id


def add_session(app, vehicle_id, slot_id, entry, exit_time=None):
    with app.app_context():
        db.session.add(ParkingSession(vehicle_id=vehicle_id, slot_id=slot_id, entry_time=entry,
                                      exit_time=exit_time,
                                      status="completed" if exit_time else "active"))
        db.session.commit()


def log_in(client, email):
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    client.post("/login", data={"email": email, "password": PASSWORD, "csrf_token": token})


def test_parked_vehicle_shows_exact_spot(client, app):
    alice = make_user(app, "alice@example.com")
    slot = make_slot(app, "Locator Mall", "LOC-PARKED")
    add_session(app, make_vehicle(app, alice, "AAA1111"), slot, entry=NOW - timedelta(minutes=20))
    log_in(client, "alice@example.com")

    response = client.get("/locator")

    assert response.status_code == 200
    assert b"LOC-PARKED" in response.data
    assert b"Parked since" in response.data


def test_departed_vehicle_shows_last_spot(client, app):
    alice = make_user(app, "alice@example.com")
    slot = make_slot(app, "Locator Mall", "LOC-LAST")
    add_session(app, make_vehicle(app, alice, "AAA1111"), slot,
                entry=NOW - timedelta(minutes=90), exit_time=NOW - timedelta(minutes=30))
    log_in(client, "alice@example.com")

    response = client.get("/locator")

    assert b"LOC-LAST" in response.data
    assert b"Last left" in response.data


def test_vehicle_never_parked_says_so(client, app):
    alice = make_user(app, "alice@example.com")
    make_vehicle(app, alice, "AAA1111")
    log_in(client, "alice@example.com")

    response = client.get("/locator")

    assert b"No parking recorded yet." in response.data


def test_locator_hides_other_users_vehicles(client, app):
    alice = make_user(app, "alice@example.com")
    bob = make_user(app, "bob@example.com")
    make_vehicle(app, alice, "AAA1111")
    slot = make_slot(app, "Locator Mall", "BOB-SPOT-7")
    add_session(app, make_vehicle(app, bob, "BBB2222"), slot, entry=NOW - timedelta(minutes=5))
    log_in(client, "alice@example.com")

    response = client.get("/locator")

    assert b"BBB2222" not in response.data
    assert b"BOB-SPOT-7" not in response.data


def test_locator_requires_sign_in(client):
    response = client.get("/locator")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
