from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import db
from app.models import ParkingFacility, ParkingFloor, ParkingSlot, Reservation, User, Vehicle

PASSWORD = "correct-horse"
FMT = "%Y-%m-%dT%H:%M"

# Bookings are placed tomorrow so they are always in the future when tests run.
BASE = (datetime.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)


def make_user(app, email):
    with app.app_context():
        user = User(
            username=email.split("@")[0], email=email,
            password_hash=generate_password_hash(PASSWORD), role="user",
        )
        db.session.add(user)
        db.session.commit()
        return user.user_id


def make_vehicle(app, user_id, number):
    with app.app_context():
        vehicle = Vehicle(user_id=user_id, vehicle_number=number, vehicle_type="car")
        db.session.add(vehicle)
        db.session.commit()
        return vehicle.vehicle_id


def make_slot(app, number="A1", **overrides):
    with app.app_context():
        facility = ParkingFacility(name="Booking Mall", address="1 Road", city="Pune", status="active")
        db.session.add(facility)
        db.session.flush()
        floor = ParkingFloor(facility_id=facility.facility_id, floor_number=1)
        db.session.add(floor)
        db.session.flush()
        values = dict(
            floor_id=floor.floor_id, slot_number=number, slot_type="standard",
            is_ev_charging=False, is_accessible=False, map_x=1.0, map_y=1.0,
            operational_status="active",
        )
        values.update(overrides)
        slot = ParkingSlot(**values)
        db.session.add(slot)
        db.session.commit()
        return slot.slot_id


def make_reservation(app, user_id, vehicle_id, slot_id, start, end, status="confirmed"):
    with app.app_context():
        db.session.add(Reservation(
            user_id=user_id, vehicle_id=vehicle_id, slot_id=slot_id,
            start_time=start, end_time=end, reservation_type="standard", status=status,
        ))
        db.session.commit()


def log_in(client, email):
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    client.post("/login", data={"email": email, "password": PASSWORD, "csrf_token": token})
    client.get("/dashboard")
    with client.session_transaction() as sess:
        return sess["csrf_token"]


def book(client, token, vehicle_id, slot_id, start, end, reservation_type="standard"):
    return client.post("/reservations", data={
        "vehicle_id": str(vehicle_id), "slot_id": str(slot_id),
        "start_time": start.strftime(FMT), "end_time": end.strftime(FMT),
        "reservation_type": reservation_type, "csrf_token": token,
    })


def count_reservations(app):
    with app.app_context():
        return Reservation.query.count()


def test_valid_booking_is_confirmed(client, app):
    alice = make_user(app, "alice@example.com")
    vehicle = make_vehicle(app, alice, "AAA1111")
    slot = make_slot(app)
    token = log_in(client, "alice@example.com")

    response = book(client, token, vehicle, slot, BASE, BASE + timedelta(hours=2))

    assert response.status_code == 302
    with app.app_context():
        reservation = Reservation.query.one()
        assert reservation.status == "confirmed"
        assert reservation.user_id == alice


def test_end_before_start_is_rejected(client, app):
    alice = make_user(app, "alice@example.com")
    vehicle = make_vehicle(app, alice, "AAA1111")
    slot = make_slot(app)
    token = log_in(client, "alice@example.com")

    book(client, token, vehicle, slot, BASE + timedelta(hours=2), BASE)

    assert count_reservations(app) == 0


def test_too_short_booking_is_rejected(client, app):
    alice = make_user(app, "alice@example.com")
    vehicle = make_vehicle(app, alice, "AAA1111")
    slot = make_slot(app)
    token = log_in(client, "alice@example.com")

    book(client, token, vehicle, slot, BASE, BASE + timedelta(minutes=15))

    assert count_reservations(app) == 0


def test_too_long_booking_is_rejected(client, app):
    alice = make_user(app, "alice@example.com")
    vehicle = make_vehicle(app, alice, "AAA1111")
    slot = make_slot(app)
    token = log_in(client, "alice@example.com")

    book(client, token, vehicle, slot, BASE, BASE + timedelta(hours=13))

    assert count_reservations(app) == 0


def test_past_start_is_rejected(client, app):
    alice = make_user(app, "alice@example.com")
    vehicle = make_vehicle(app, alice, "AAA1111")
    slot = make_slot(app)
    token = log_in(client, "alice@example.com")
    past = datetime.now() - timedelta(days=1)

    book(client, token, vehicle, slot, past, past + timedelta(hours=1))

    assert count_reservations(app) == 0


def test_someone_elses_vehicle_is_rejected(client, app):
    bob = make_user(app, "bob@example.com")
    bobs_vehicle = make_vehicle(app, bob, "BBB2222")
    make_user(app, "alice@example.com")
    slot = make_slot(app)
    token = log_in(client, "alice@example.com")

    book(client, token, bobs_vehicle, slot, BASE, BASE + timedelta(hours=1))

    assert count_reservations(app) == 0


def test_inactive_slot_is_rejected(client, app):
    alice = make_user(app, "alice@example.com")
    vehicle = make_vehicle(app, alice, "AAA1111")
    slot = make_slot(app, operational_status="maintenance")
    token = log_in(client, "alice@example.com")

    book(client, token, vehicle, slot, BASE, BASE + timedelta(hours=1))

    assert count_reservations(app) == 0


def test_overlapping_booking_is_rejected(client, app):
    alice = make_user(app, "alice@example.com")
    bob = make_user(app, "bob@example.com")
    alices_vehicle = make_vehicle(app, alice, "AAA1111")
    bobs_vehicle = make_vehicle(app, bob, "BBB2222")
    slot = make_slot(app)
    make_reservation(app, alice, alices_vehicle, slot, BASE, BASE + timedelta(hours=2))
    token = log_in(client, "bob@example.com")

    book(client, token, bobs_vehicle, slot, BASE + timedelta(hours=1), BASE + timedelta(hours=3))

    assert count_reservations(app) == 1


def test_back_to_back_booking_is_allowed(client, app):
    alice = make_user(app, "alice@example.com")
    bob = make_user(app, "bob@example.com")
    alices_vehicle = make_vehicle(app, alice, "AAA1111")
    bobs_vehicle = make_vehicle(app, bob, "BBB2222")
    slot = make_slot(app)
    make_reservation(app, alice, alices_vehicle, slot, BASE, BASE + timedelta(hours=2))
    token = log_in(client, "bob@example.com")

    book(client, token, bobs_vehicle, slot, BASE + timedelta(hours=2), BASE + timedelta(hours=4))

    assert count_reservations(app) == 2


def test_ev_type_needs_ev_slot(client, app):
    alice = make_user(app, "alice@example.com")
    vehicle = make_vehicle(app, alice, "AAA1111")
    slot = make_slot(app, is_ev_charging=False)
    token = log_in(client, "alice@example.com")

    book(client, token, vehicle, slot, BASE, BASE + timedelta(hours=1), reservation_type="ev_charging")

    assert count_reservations(app) == 0


def test_user_cancels_own_reservation_and_slot_frees_up(client, app):
    alice = make_user(app, "alice@example.com")
    alices_vehicle = make_vehicle(app, alice, "AAA1111")
    slot = make_slot(app)
    make_reservation(app, alice, alices_vehicle, slot, BASE, BASE + timedelta(hours=2))
    with app.app_context():
        reservation_id = Reservation.query.one().reservation_id
    token = log_in(client, "alice@example.com")

    client.post(f"/reservations/{reservation_id}/cancel", data={"csrf_token": token})

    with app.app_context():
        assert db.session.get(Reservation, reservation_id).status == "cancelled"

    # The same time on the same slot is now free for another user.
    bob = make_user(app, "bob@example.com")
    bobs_vehicle = make_vehicle(app, bob, "BBB2222")
    bob_token = log_in(client, "bob@example.com")
    book(client, bob_token, bobs_vehicle, slot, BASE, BASE + timedelta(hours=2))

    assert count_reservations(app) == 2


def test_user_cannot_cancel_someone_elses_reservation(client, app):
    alice = make_user(app, "alice@example.com")
    alices_vehicle = make_vehicle(app, alice, "AAA1111")
    slot = make_slot(app)
    make_reservation(app, alice, alices_vehicle, slot, BASE, BASE + timedelta(hours=2))
    with app.app_context():
        reservation_id = Reservation.query.one().reservation_id
    make_user(app, "bob@example.com")
    token = log_in(client, "bob@example.com")

    response = client.post(f"/reservations/{reservation_id}/cancel", data={"csrf_token": token})

    assert response.status_code == 404
    with app.app_context():
        assert db.session.get(Reservation, reservation_id).status == "confirmed"


def test_my_reservations_shows_only_own(client, app):
    alice = make_user(app, "alice@example.com")
    bob = make_user(app, "bob@example.com")
    make_reservation(app, alice, make_vehicle(app, alice, "AAA1111"), make_slot(app, "ALICE-SLOT"), BASE, BASE + timedelta(hours=1))
    make_reservation(app, bob, make_vehicle(app, bob, "BBB2222"), make_slot(app, "BOB-SLOT"), BASE + timedelta(days=1), BASE + timedelta(days=1, hours=1))
    log_in(client, "alice@example.com")

    response = client.get("/reservations/mine")

    assert b"ALICE-SLOT" in response.data
    assert b"BOB-SLOT" not in response.data
