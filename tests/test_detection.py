from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import db
from app.detection import parse_feed, record_observations
from app.models import OccupancyEvent, ParkingFacility, ParkingFloor, ParkingSlot, User

PASSWORD = "correct-horse"
NOW = datetime(2026, 10, 10, 12, 0)


def build_slots(app):
    with app.app_context():
        facility = ParkingFacility(name="Feed Mall", address="1 Road", city="Pune", status="active")
        db.session.add(facility)
        db.session.flush()
        floor = ParkingFloor(facility_id=facility.facility_id, floor_number=1)
        db.session.add(floor)
        db.session.flush()
        ids = {}
        for number in ("A1", "A2"):
            slot = ParkingSlot(floor_id=floor.floor_id, slot_number=number, slot_type="standard",
                               is_ev_charging=False, is_accessible=False, map_x=1.0, map_y=1.0,
                               operational_status="active")
            db.session.add(slot)
            db.session.flush()
            ids[number] = slot.slot_id
        db.session.commit()
        return facility.facility_id, ids


def event_count(app):
    with app.app_context():
        return OccupancyEvent.query.count()


def test_event_written_only_when_state_changes(app):
    _, ids = build_slots(app)
    slot = ids["A1"]

    with app.app_context():
        assert record_observations([(slot, True)], now=NOW) == 1
        assert record_observations([(slot, True)], now=NOW + timedelta(minutes=1)) == 0
        assert record_observations([(slot, False)], now=NOW + timedelta(minutes=2)) == 1
        assert record_observations([(slot, False)], now=NOW + timedelta(minutes=3)) == 0

    assert event_count(app) == 2


def test_detection_events_have_no_vehicle_attached(app):
    _, ids = build_slots(app)
    with app.app_context():
        record_observations([(ids["A1"], True)], now=NOW)
        event = OccupancyEvent.query.one()
        assert event.vehicle_id is None
        assert event.parking_session_id is None


def test_parse_feed_reads_valid_lines_and_reports_problems(app):
    _, ids = build_slots(app)
    text = "A1 occupied\n# a comment\nA2 vacant\nZ9 occupied\nA1 broken\n"

    observations, problems = parse_feed(text, {"A1": ids["A1"], "A2": ids["A2"]})

    assert observations == [(ids["A1"], True), (ids["A2"], False)]
    assert len(problems) == 2


def test_manager_records_feed_through_the_page(client, app):
    facility_id, ids = build_slots(app)
    with app.app_context():
        db.session.add(User(username="root", email="root@example.com",
                            password_hash=generate_password_hash(PASSWORD), role="admin"))
        db.session.commit()
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    client.post("/login", data={"email": "root@example.com", "password": PASSWORD, "csrf_token": token})
    client.get("/dashboard")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]

    response = client.post(f"/facilities/{facility_id}/detections",
                           data={"feed": "A1 occupied", "csrf_token": token})

    assert response.status_code == 302
    assert event_count(app) == 1


def test_regular_user_cannot_submit_feed(client, app):
    facility_id, _ = build_slots(app)
    with app.app_context():
        db.session.add(User(username="alice", email="alice@example.com",
                            password_hash=generate_password_hash(PASSWORD), role="user"))
        db.session.commit()
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    client.post("/login", data={"email": "alice@example.com", "password": PASSWORD, "csrf_token": token})
    client.get("/dashboard")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]

    response = client.post(f"/facilities/{facility_id}/detections",
                           data={"feed": "A1 occupied", "csrf_token": token})

    assert response.status_code == 403
    assert event_count(app) == 0
