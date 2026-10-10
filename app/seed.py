"""Load demo data into the development database.

Run from the project folder with the venv active:

    python -m app.seed

It adds one facility with two floors, a few vehicles, one parked car, and one
upcoming booking. Running it again changes nothing if the demo facility exists.
The demo accounts share one password. Use them for local testing only.
"""
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import ParkingFacility, ParkingFloor, ParkingSession, ParkingSlot, Reservation, User, Vehicle

DEMO_FACILITY = "Demo Mall"
DEMO_PASSWORD = "demo-password-123"
DEMO_ACCOUNTS = (
    ("admin@example.com", "Demo Admin", "admin", None),
    ("lot.manager@example.com", "Lot Manager", "parking_admin", "facility"),
    ("driver@example.com", "Demo Driver", "user", None),
)


def _slot(floor, number, slot_type="standard", ev=False, accessible=False, x=0, y=0, status="active"):
    slot = ParkingSlot(
        floor_id=floor.floor_id, slot_number=number, slot_type=slot_type,
        is_ev_charging=ev, is_accessible=accessible, map_x=x, map_y=y,
        operational_status=status,
    )
    db.session.add(slot)
    db.session.flush()
    return slot


def seed_demo(now=None):
    """Create the demo data. Returns True if it was added, False if it already exists."""
    if ParkingFacility.query.filter_by(name=DEMO_FACILITY).first():
        return False
    now = now or datetime.now().replace(second=0, microsecond=0)

    facility = ParkingFacility(name=DEMO_FACILITY, address="12 MG Road", city="Pune", status="active")
    db.session.add(facility)
    db.session.flush()

    ground = ParkingFloor(facility_id=facility.facility_id, floor_number=1, name="Ground")
    upper = ParkingFloor(facility_id=facility.facility_id, floor_number=2, name="Upper")
    db.session.add_all([ground, upper])
    db.session.flush()

    # Ground floor: a 4 x 2 grid. A5 has EV charging, A6 is accessible, A8 is compact.
    ground_slots = {}
    for index in range(8):
        number = f"A{index + 1}"
        ground_slots[number] = _slot(
            ground, number,
            slot_type="compact" if number == "A8" else "standard",
            ev=number == "A5", accessible=number == "A6",
            x=1000 + (index % 4) * 2500, y=1500 + (index // 4) * 4000,
        )

    # Upper floor: B4 is under maintenance, so it shows as unavailable on the map.
    upper_slots = {}
    for index in range(4):
        number = f"B{index + 1}"
        upper_slots[number] = _slot(
            upper, number,
            x=1000 + index * 2500, y=2000,
            status="maintenance" if number == "B4" else "active",
        )

    for email, username, role, link in DEMO_ACCOUNTS:
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(
                username=username, email=email,
                password_hash=generate_password_hash(DEMO_PASSWORD), role=role,
                facility_id=facility.facility_id if link == "facility" else None,
            )
            db.session.add(user)
            db.session.flush()

    driver = User.query.filter_by(email="driver@example.com").first()
    car = Vehicle(user_id=driver.user_id, vehicle_number="MH12AB1234", vehicle_type="car", vehicle_model="Swift")
    bike = Vehicle(user_id=driver.user_id, vehicle_number="MH14XY9876", vehicle_type="motorcycle", vehicle_model=None)
    db.session.add_all([car, bike])
    db.session.flush()

    # A car that came in an hour ago and is still parked in A2.
    db.session.add(ParkingSession(
        vehicle_id=car.vehicle_id, slot_id=ground_slots["A2"].slot_id,
        entry_time=now - timedelta(hours=1), exit_time=None, status="active",
    ))
    # A finished visit yesterday, for history and analytics.
    db.session.add(ParkingSession(
        vehicle_id=bike.vehicle_id, slot_id=ground_slots["A3"].slot_id,
        entry_time=now - timedelta(days=1, hours=3), exit_time=now - timedelta(days=1, hours=1),
        status="completed",
    ))
    # A confirmed booking for tomorrow morning on the upper floor.
    tomorrow = (now + timedelta(days=1)).replace(hour=10, minute=0)
    db.session.add(Reservation(
        user_id=driver.user_id, vehicle_id=car.vehicle_id, slot_id=upper_slots["B1"].slot_id,
        start_time=tomorrow, end_time=tomorrow + timedelta(hours=2),
        reservation_type="standard", status="confirmed", created_at=now,
    ))

    db.session.commit()
    return True


def main():
    app = create_app()
    with app.app_context():
        added = seed_demo()
    if added:
        print("Demo data added.")
    else:
        print("Demo data is already present. Nothing changed.")
    print(f"Demo logins (password {DEMO_PASSWORD}):")
    for email, _, role, _ in DEMO_ACCOUNTS:
        print(f"  {email}  ({role})")


if __name__ == "__main__":
    main()
