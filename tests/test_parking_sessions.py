from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import db
from app.models import OccupancyEvent, ParkingFacility, ParkingFloor, ParkingSession, ParkingSlot, User, Vehicle

PASSWORD = "correct-horse"


def make_user(app, email, role="user", facility_id=None):
    with app.app_context():
        user = User(username=email.split("@")[0], email=email,
                    password_hash=generate_password_hash(PASSWORD),
                    role=role, facility_id=facility_id)
        db.session.add(user)
        db.session.commit()
        return user.user_id


def make_facility_with_slot(app, name, slot_number="A1", **slot_overrides):
    with app.app_context():
        facility = ParkingFacility(name=name, address="1 Road", city="Pune", status="active")
        db.session.add(facility)
        db.session.flush()
        floor = ParkingFloor(facility_id=facility.facility_id, floor_number=1)
        db.session.add(floor)
        db.session.flush()
        values = dict(floor_id=floor.floor_id, slot_number=slot_number, slot_type="standard",
                      is_ev_charging=False, is_accessible=False, map_x=1.0, map_y=1.0,
                      operational_status="active")
        values.update(slot_overrides)
        slot = ParkingSlot(**values)
        db.session.add(slot)
        db.session.commit()
        return facility.facility_id, slot.slot_id


def make_vehicle(app, user_id, number):
    with app.app_context():
        vehicle = Vehicle(user_id=user_id, vehicle_number=number, vehicle_type="car")
        db.session.add(vehicle)
        db.session.commit()
        return vehicle.vehicle_id


def log_in(client, email):
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    client.post("/login", data={"email": email, "password": PASSWORD, "csrf_token": token})
    client.get("/dashboard")
    with client.session_transaction() as sess:
        return sess["csrf_token"]


def start(client, token, facility_id, plate, slot_id):
    return client.post(f"/facilities/{facility_id}/sessions/start",
                       data={"vehicle_number": plate, "slot_id": str(slot_id), "csrf_token": token})


def count(app, model):
    with app.app_context():
        return model.query.count()


def test_admin_records_entry_and_exit(client, app):
    facility_id, slot_id = make_facility_with_slot(app, "Gate Mall")
    owner = make_user(app, "alice@example.com")
    make_vehicle(app, owner, "AAA1111")
    make_user(app, "root@example.com", role="admin")
    token = log_in(client, "root@example.com")

    start(client, token, facility_id, "aaa 1111", slot_id)

    with app.app_context():
        parking = ParkingSession.query.one()
        assert parking.status == "active" and parking.exit_time is None
        assert OccupancyEvent.query.filter_by(event_type="occupied").count() == 1
    with app.app_context():
        session_id = ParkingSession.query.one().session_id
    client.post(f"/facilities/{facility_id}/sessions/{session_id}/end", data={"csrf_token": token})

    with app.app_context():
        parking = db.session.get(ParkingSession, session_id)
        assert parking.status == "completed" and parking.exit_time is not None
        assert OccupancyEvent.query.filter_by(event_type="vacated").count() == 1


def test_unknown_vehicle_is_rejected(client, app):
    facility_id, slot_id = make_facility_with_slot(app, "Gate Mall")
    make_user(app, "root@example.com", role="admin")
    token = log_in(client, "root@example.com")

    start(client, token, facility_id, "NOPE9999", slot_id)

    assert count(app, ParkingSession) == 0


def test_slot_from_other_facility_is_rejected(client, app):
    facility_a, _ = make_facility_with_slot(app, "A")
    _, slot_b = make_facility_with_slot(app, "B")
    owner = make_user(app, "alice@example.com")
    make_vehicle(app, owner, "AAA1111")
    make_user(app, "root@example.com", role="admin")
    token = log_in(client, "root@example.com")

    start(client, token, facility_a, "AAA1111", slot_b)

    assert count(app, ParkingSession) == 0


def test_inactive_slot_is_rejected(client, app):
    facility_id, slot_id = make_facility_with_slot(app, "Gate Mall", operational_status="maintenance")
    owner = make_user(app, "alice@example.com")
    make_vehicle(app, owner, "AAA1111")
    make_user(app, "root@example.com", role="admin")
    token = log_in(client, "root@example.com")

    start(client, token, facility_id, "AAA1111", slot_id)

    assert count(app, ParkingSession) == 0


def test_occupied_slot_rejects_second_vehicle(client, app):
    facility_id, slot_id = make_facility_with_slot(app, "Gate Mall")
    owner = make_user(app, "alice@example.com")
    make_vehicle(app, owner, "AAA1111")
    make_vehicle(app, owner, "BBB2222")
    make_user(app, "root@example.com", role="admin")
    token = log_in(client, "root@example.com")

    start(client, token, facility_id, "AAA1111", slot_id)
    start(client, token, facility_id, "BBB2222", slot_id)

    assert count(app, ParkingSession) == 1


def test_vehicle_already_parked_elsewhere_is_rejected(client, app):
    facility_id, slot_1 = make_facility_with_slot(app, "Gate Mall", slot_number="A1")
    with app.app_context():
        floor_id = db.session.get(ParkingSlot, slot_1).floor_id
        second = ParkingSlot(floor_id=floor_id, slot_number="A2", slot_type="standard",
                             is_ev_charging=False, is_accessible=False, map_x=2.0, map_y=2.0,
                             operational_status="active")
        db.session.add(second)
        db.session.commit()
        slot_2 = second.slot_id
    owner = make_user(app, "alice@example.com")
    make_vehicle(app, owner, "AAA1111")
    make_user(app, "root@example.com", role="admin")
    token = log_in(client, "root@example.com")

    start(client, token, facility_id, "AAA1111", slot_1)
    start(client, token, facility_id, "AAA1111", slot_2)

    assert count(app, ParkingSession) == 1


def test_regular_user_cannot_record_entry(client, app):
    facility_id, slot_id = make_facility_with_slot(app, "Gate Mall")
    owner = make_user(app, "alice@example.com")
    make_vehicle(app, owner, "AAA1111")
    token = log_in(client, "alice@example.com")

    response = start(client, token, facility_id, "AAA1111", slot_id)

    assert response.status_code == 403
    assert count(app, ParkingSession) == 0


def test_parking_admin_of_other_facility_is_refused(client, app):
    facility_a, _ = make_facility_with_slot(app, "A")
    facility_b, slot_b = make_facility_with_slot(app, "B")
    owner = make_user(app, "alice@example.com")
    make_vehicle(app, owner, "AAA1111")
    make_user(app, "pat@example.com", role="parking_admin", facility_id=facility_a)
    token = log_in(client, "pat@example.com")

    response = start(client, token, facility_b, "AAA1111", slot_b)

    assert response.status_code == 403


def test_ending_session_through_wrong_facility_is_404(client, app):
    facility_a, slot_a = make_facility_with_slot(app, "A")
    facility_b, _ = make_facility_with_slot(app, "B")
    owner = make_user(app, "alice@example.com")
    vehicle = make_vehicle(app, owner, "AAA1111")
    with app.app_context():
        parking = ParkingSession(vehicle_id=vehicle, slot_id=slot_a,
                                 entry_time=datetime.now() - timedelta(minutes=10), status="active")
        db.session.add(parking)
        db.session.commit()
        session_id = parking.session_id
    make_user(app, "root@example.com", role="admin")
    token = log_in(client, "root@example.com")

    response = client.post(f"/facilities/{facility_b}/sessions/{session_id}/end",
                           data={"csrf_token": token})

    assert response.status_code == 404
    with app.app_context():
        assert db.session.get(ParkingSession, session_id).status == "active"


def test_ending_twice_records_one_exit(client, app):
    facility_id, slot_id = make_facility_with_slot(app, "Gate Mall")
    owner = make_user(app, "alice@example.com")
    vehicle = make_vehicle(app, owner, "AAA1111")
    with app.app_context():
        parking = ParkingSession(vehicle_id=vehicle, slot_id=slot_id,
                                 entry_time=datetime.now() - timedelta(minutes=10), status="active")
        db.session.add(parking)
        db.session.commit()
        session_id = parking.session_id
    make_user(app, "root@example.com", role="admin")
    token = log_in(client, "root@example.com")

    client.post(f"/facilities/{facility_id}/sessions/{session_id}/end", data={"csrf_token": token})
    client.post(f"/facilities/{facility_id}/sessions/{session_id}/end", data={"csrf_token": token})

    with app.app_context():
        assert OccupancyEvent.query.filter_by(event_type="vacated").count() == 1
