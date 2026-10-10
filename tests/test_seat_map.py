from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import db
from app.models import ParkingFacility, ParkingFloor, ParkingSlot, Reservation, User, Vehicle

PASSWORD = "correct-horse"


def build_world(app):
    """One facility, one floor, three slots in a row, a driver with a car, and
    slot A2 already booked for tomorrow 10:00-12:00."""
    with app.app_context():
        facility = ParkingFacility(name="Seat Mall", address="1 Road", city="Pune", status="active")
        db.session.add(facility)
        db.session.flush()
        floor = ParkingFloor(facility_id=facility.facility_id, floor_number=1)
        db.session.add(floor)
        db.session.flush()
        slots = {}
        for index, number in enumerate(("A1", "A2", "A3")):
            slot = ParkingSlot(floor_id=floor.floor_id, slot_number=number, slot_type="standard",
                               is_ev_charging=False, is_accessible=False,
                               map_x=1000 + index * 2500, map_y=1500, operational_status="active")
            db.session.add(slot)
            db.session.flush()
            slots[number] = slot.slot_id
        user = User(username="seat", email="seat@example.com",
                    password_hash=generate_password_hash(PASSWORD), role="user")
        db.session.add(user)
        db.session.flush()
        vehicle = Vehicle(user_id=user.user_id, vehicle_number="SEAT0001", vehicle_type="car")
        db.session.add(vehicle)
        db.session.flush()
        tomorrow = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        db.session.add(Reservation(user_id=user.user_id, vehicle_id=vehicle.vehicle_id,
                                   slot_id=slots["A2"], start_time=tomorrow,
                                   end_time=tomorrow + timedelta(hours=2),
                                   reservation_type="standard", status="confirmed", created_at=datetime.now()))
        db.session.commit()
        return facility.facility_id, tomorrow


def login(client):
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    client.post("/login", data={"email": "seat@example.com", "password": PASSWORD, "csrf_token": token})


def test_seat_map_marks_booked_seat_as_taken(app, client):
    facility_id, tomorrow = build_world(app)
    login(client)
    start = tomorrow.strftime("%Y-%m-%dT%H:%M")
    end = (tomorrow + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    html = client.get(f"/reservations/new?facility={facility_id}&start_time={start}&end_time={end}").get_data(as_text=True)

    assert 'class="seat free"' in html
    assert 'class="seat taken"' in html
    assert html.count('class="seat-input"') == 3


def test_seat_map_waits_for_a_time(app, client):
    facility_id, _ = build_world(app)
    login(client)
    html = client.get(f"/reservations/new?facility={facility_id}").get_data(as_text=True)

    assert 'class="seat pick"' in html
    assert 'class="seat free"' not in html
    assert "Choose a start and end time above" in html


def test_seat_map_back_to_back_booking_is_free(app, client):
    facility_id, tomorrow = build_world(app)
    login(client)
    # Starts exactly when the booking on A2 ends, so it does not overlap.
    start = (tomorrow + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    end = (tomorrow + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    html = client.get(f"/reservations/new?facility={facility_id}&start_time={start}&end_time={end}").get_data(as_text=True)
    assert 'class="seat taken"' not in html
