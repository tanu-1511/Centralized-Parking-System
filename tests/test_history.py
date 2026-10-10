from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import db
from app.models import ParkingFacility, ParkingFloor, ParkingSession, ParkingSlot, User, Vehicle

PASSWORD = "correct-horse"
NOW = datetime.now()


def make_user(app, email, role="user", facility_id=None):
    with app.app_context():
        user = User(username=email.split("@")[0], email=email,
                    password_hash=generate_password_hash(PASSWORD),
                    role=role, facility_id=facility_id)
        db.session.add(user)
        db.session.commit()
        return user.user_id


def make_facility_slot(app, name, slot_number="A1"):
    with app.app_context():
        facility = ParkingFacility(name=name, address="1 Road", city="Pune", status="active")
        db.session.add(facility)
        db.session.flush()
        floor = ParkingFloor(facility_id=facility.facility_id, floor_number=2)
        db.session.add(floor)
        db.session.flush()
        slot = ParkingSlot(floor_id=floor.floor_id, slot_number=slot_number, slot_type="standard",
                           is_ev_charging=False, is_accessible=False, map_x=1.0, map_y=1.0,
                           operational_status="active")
        db.session.add(slot)
        db.session.commit()
        return facility.facility_id, slot.slot_id


def make_vehicle(app, user_id, number):
    with app.app_context():
        vehicle = Vehicle(user_id=user_id, vehicle_number=number, vehicle_type="car")
        db.session.add(vehicle)
        db.session.commit()
        return vehicle.vehicle_id


def add_session(app, vehicle_id, slot_id, entry, exit_time=None):
    with app.app_context():
        status = "completed" if exit_time else "active"
        db.session.add(ParkingSession(vehicle_id=vehicle_id, slot_id=slot_id,
                                      entry_time=entry, exit_time=exit_time, status=status))
        db.session.commit()


def log_in(client, email):
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    client.post("/login", data={"email": email, "password": PASSWORD, "csrf_token": token})


def test_user_sees_own_sessions_with_duration(client, app):
    alice = make_user(app, "alice@example.com")
    _, slot_id = make_facility_slot(app, "History Mall")
    vehicle_id = make_vehicle(app, alice, "AAA1111")
    add_session(app, vehicle_id, slot_id,
                entry=NOW - timedelta(minutes=100), exit_time=NOW - timedelta(minutes=10))
    log_in(client, "alice@example.com")

    response = client.get("/history")

    assert response.status_code == 200
    assert b"History Mall" in response.data
    assert b"90 min" in response.data


def test_active_session_shows_still_parked(client, app):
    alice = make_user(app, "alice@example.com")
    _, slot_id = make_facility_slot(app, "History Mall")
    vehicle_id = make_vehicle(app, alice, "AAA1111")
    add_session(app, vehicle_id, slot_id, entry=NOW - timedelta(minutes=30))
    log_in(client, "alice@example.com")

    response = client.get("/history")

    assert b"still parked" in response.data


def test_user_does_not_see_others_sessions(client, app):
    alice = make_user(app, "alice@example.com")
    bob = make_user(app, "bob@example.com")
    _, slot_a = make_facility_slot(app, "Alice Lot", slot_number="ALICE-SPOT")
    _, slot_b = make_facility_slot(app, "Bob Lot", slot_number="BOB-SPOT")
    add_session(app, make_vehicle(app, alice, "AAA1111"), slot_a,
                entry=NOW - timedelta(minutes=60), exit_time=NOW - timedelta(minutes=30))
    add_session(app, make_vehicle(app, bob, "BBB2222"), slot_b,
                entry=NOW - timedelta(minutes=60), exit_time=NOW - timedelta(minutes=30))
    log_in(client, "alice@example.com")

    response = client.get("/history")

    assert b"ALICE-SPOT" in response.data
    assert b"BOB-SPOT" not in response.data


def test_most_used_spots_are_counted(client, app):
    alice = make_user(app, "alice@example.com")
    _, slot_id = make_facility_slot(app, "Favourite Lot", slot_number="FAV-1")
    vehicle_id = make_vehicle(app, alice, "AAA1111")
    for hours_ago in (5, 4, 3):
        add_session(app, vehicle_id, slot_id,
                    entry=NOW - timedelta(hours=hours_ago),
                    exit_time=NOW - timedelta(hours=hours_ago) + timedelta(minutes=20))
    log_in(client, "alice@example.com")

    response = client.get("/history")

    assert b"3 visits" in response.data


def test_facility_history_shows_duration(client, app):
    facility_id, slot_id = make_facility_slot(app, "Staff Lot")
    owner = make_user(app, "alice@example.com")
    vehicle_id = make_vehicle(app, owner, "AAA1111")
    add_session(app, vehicle_id, slot_id,
                entry=NOW - timedelta(minutes=100), exit_time=NOW - timedelta(minutes=10))
    make_user(app, "root@example.com", role="admin")
    log_in(client, "root@example.com")

    response = client.get(f"/facilities/{facility_id}/sessions")

    assert response.status_code == 200
    assert b"90 min" in response.data


def test_history_requires_sign_in(client):
    response = client.get("/history")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
