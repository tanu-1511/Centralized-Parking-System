from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import db
from app.analytics import facility_analytics
from app.models import ParkingFacility, ParkingFloor, ParkingSession, ParkingSlot, Reservation, User, Vehicle

PASSWORD = "correct-horse"
NOW = datetime(2026, 10, 10, 12, 0)


def build_facility(app):
    """Facility with three slots: A1 occupied, A2 free, A3 reserved now."""
    with app.app_context():
        user = User(username="alice", email="alice@example.com",
                    password_hash=generate_password_hash(PASSWORD), role="user")
        facility = ParkingFacility(name="Stats Mall", address="1 Road", city="Pune", status="active")
        db.session.add_all([user, facility])
        db.session.flush()
        floor = ParkingFloor(facility_id=facility.facility_id, floor_number=1)
        db.session.add(floor)
        db.session.flush()
        slots = {}
        for number in ("A1", "A2", "A3"):
            slot = ParkingSlot(floor_id=floor.floor_id, slot_number=number, slot_type="standard",
                               is_ev_charging=False, is_accessible=False, map_x=1.0, map_y=1.0,
                               operational_status="active")
            db.session.add(slot)
            db.session.flush()
            slots[number] = slot.slot_id
        vehicle_1 = Vehicle(user_id=user.user_id, vehicle_number="AAA1111", vehicle_type="car")
        vehicle_2 = Vehicle(user_id=user.user_id, vehicle_number="BBB2222", vehicle_type="car")
        db.session.add_all([vehicle_1, vehicle_2])
        db.session.flush()

        # A1: car parked since 11:30 (open session).
        db.session.add(ParkingSession(vehicle_id=vehicle_1.vehicle_id, slot_id=slots["A1"],
                                      entry_time=NOW - timedelta(minutes=30), status="active"))
        # A2: a completed 60-minute session earlier in the day.
        db.session.add(ParkingSession(vehicle_id=vehicle_2.vehicle_id, slot_id=slots["A2"],
                                      entry_time=NOW - timedelta(hours=3),
                                      exit_time=NOW - timedelta(hours=2), status="completed"))
        # A3: confirmed reservation covering now.
        db.session.add(Reservation(user_id=user.user_id, vehicle_id=vehicle_1.vehicle_id,
                                   slot_id=slots["A3"], start_time=NOW - timedelta(minutes=10),
                                   end_time=NOW + timedelta(hours=1),
                                   reservation_type="standard", status="confirmed"))
        # A2: a cancelled future reservation.
        db.session.add(Reservation(user_id=user.user_id, vehicle_id=vehicle_2.vehicle_id,
                                   slot_id=slots["A2"], start_time=NOW + timedelta(hours=2),
                                   end_time=NOW + timedelta(hours=3),
                                   reservation_type="standard", status="cancelled"))
        db.session.commit()
        return facility.facility_id


def log_in(client, email):
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    client.post("/login", data={"email": email, "password": PASSWORD, "csrf_token": token})


def test_summary_figures_come_from_database(app):
    facility_id = build_facility(app)
    with app.app_context():
        facility = db.session.get(ParkingFacility, facility_id)
        stats = facility_analytics(facility, now=NOW)

    assert stats["total_slots"] == 3
    assert stats["occupied"] == 1
    assert stats["reserved"] == 1
    assert stats["available"] == 1
    assert stats["average_duration_minutes"] == 60
    assert stats["completed_sessions"] == 1
    assert stats["reservation_counts"]["confirmed"] == 1
    assert stats["reservation_counts"]["cancelled"] == 1


def test_floor_usage_counts_occupied_and_reserved_as_busy(app):
    facility_id = build_facility(app)
    with app.app_context():
        facility = db.session.get(ParkingFacility, facility_id)
        floor_row = facility_analytics(facility, now=NOW)["floors"][0]

    assert floor_row["total"] == 3
    assert floor_row["usage_percent"] == 67


def test_peak_hours_list_entry_hours(app):
    facility_id = build_facility(app)
    with app.app_context():
        facility = db.session.get(ParkingFacility, facility_id)
        peaks = facility_analytics(facility, now=NOW)["peak_hours"]

    assert len(peaks) == 2


def test_dashboard_requires_manager(client, app):
    facility_id = build_facility(app)
    with app.app_context():
        db.session.add(User(username="bob", email="bob@example.com",
                            password_hash=generate_password_hash(PASSWORD), role="user"))
        db.session.commit()
    log_in(client, "bob@example.com")

    assert client.get(f"/facilities/{facility_id}/analytics").status_code == 403


def test_admin_sees_dashboard(client, app):
    facility_id = build_facility(app)
    with app.app_context():
        db.session.add(User(username="root", email="root@example.com",
                            password_hash=generate_password_hash(PASSWORD), role="admin"))
        db.session.commit()
    log_in(client, "root@example.com")

    response = client.get(f"/facilities/{facility_id}/analytics")

    assert response.status_code == 200
    assert b"Average parking duration" in response.data
