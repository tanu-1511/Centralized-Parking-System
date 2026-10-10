"""Load demo data into the development database.

Run from the project folder with the venv active:

    python -m app.seed

It adds one facility with two floors and twelve slots, two vehicles, one parked
car, one finished visit, and one upcoming booking. Running it again adds no
duplicate data, but it always sets the three demo accounts to the demo password,
so a demo login works even if an account with that email already existed.
The demo accounts share one password. Use them for local testing only.
"""
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import ParkingFacility, ParkingFloor, ParkingSession, ParkingSlot, Reservation, User, Vehicle

DEMO_FACILITY = "Demo Mall"
DEMO_PASSWORD = "demo-password-123"
DEMO_ACCOUNTS = (
    ("admin@example.com", "Demo Admin", "admin", False),
    ("lot.manager@example.com", "Lot Manager", "parking_admin", True),
    ("driver@example.com", "Demo Driver", "user", False),
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


def _add_facility_layout(facility):
    """Floors and slots. Returns the slots by number, for the visit and booking below."""
    ground = ParkingFloor(facility_id=facility.facility_id, floor_number=1, name="Ground")
    upper = ParkingFloor(facility_id=facility.facility_id, floor_number=2, name="Upper")
    db.session.add_all([ground, upper])
    db.session.flush()

    # Ground floor: a 4 x 2 grid. A5 has EV charging, A6 is accessible, A8 is compact.
    slots = {}
    for index in range(8):
        number = f"A{index + 1}"
        slots[number] = _slot(
            ground, number,
            slot_type="compact" if number == "A8" else "standard",
            ev=number == "A5", accessible=number == "A6",
            x=1000 + (index % 4) * 2500, y=1500 + (index // 4) * 4000,
        )

    # Upper floor: B4 is under maintenance, so it shows as unavailable on the map.
    for index in range(4):
        number = f"B{index + 1}"
        slots[number] = _slot(
            upper, number,
            x=1000 + index * 2500, y=2000,
            status="maintenance" if number == "B4" else "active",
        )
    return slots


def _ensure_accounts(facility):
    """Create each demo account if missing. Always set the demo password and facility link."""
    for email, username, role, manages_facility in DEMO_ACCOUNTS:
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(username=username, email=email)
            db.session.add(user)
        user.username = username
        user.role = role
        user.password_hash = generate_password_hash(DEMO_PASSWORD)
        user.facility_id = facility.facility_id if manages_facility else None
    db.session.flush()


def seed_demo(now=None):
    """Add the demo data. Returns True if the facility was created now, False if it already existed."""
    now = now or datetime.now().replace(second=0, microsecond=0)
    facility = ParkingFacility.query.filter_by(name=DEMO_FACILITY).first()
    created = facility is None

    if created:
        facility = ParkingFacility(name=DEMO_FACILITY, address="12 MG Road", city="Pune", status="active")
        db.session.add(facility)
        db.session.flush()
        slots = _add_facility_layout(facility)

    _ensure_accounts(facility)

    if created:
        driver = User.query.filter_by(email="driver@example.com").first()
        car = Vehicle(user_id=driver.user_id, vehicle_number="MH12AB1234", vehicle_type="car", vehicle_model="Swift")
        bike = Vehicle(user_id=driver.user_id, vehicle_number="MH14XY9876", vehicle_type="motorcycle", vehicle_model=None)
        db.session.add_all([car, bike])
        db.session.flush()

        # A car that came in an hour ago and is still parked in A2.
        db.session.add(ParkingSession(
            vehicle_id=car.vehicle_id, slot_id=slots["A2"].slot_id,
            entry_time=now - timedelta(hours=1), exit_time=None, status="active",
        ))
        # A finished visit yesterday, for history and analytics.
        db.session.add(ParkingSession(
            vehicle_id=bike.vehicle_id, slot_id=slots["A3"].slot_id,
            entry_time=now - timedelta(days=1, hours=3), exit_time=now - timedelta(days=1, hours=1),
            status="completed",
        ))
        # A confirmed booking for tomorrow morning on the upper floor.
        tomorrow = (now + timedelta(days=1)).replace(hour=10, minute=0)
        db.session.add(Reservation(
            user_id=driver.user_id, vehicle_id=car.vehicle_id, slot_id=slots["B1"].slot_id,
            start_time=tomorrow, end_time=tomorrow + timedelta(hours=2),
            reservation_type="standard", status="confirmed", created_at=now,
        ))

    db.session.commit()
    return created


def main():
    app = create_app()
    with app.app_context():
        added = seed_demo()
    if added:
        print("Demo data added.")
    else:
        print("Demo data was already present. Demo passwords were reset.")
    print(f"Demo logins (password {DEMO_PASSWORD}):")
    for email, _, role, _ in DEMO_ACCOUNTS:
        print(f"  {email}  ({role})")


if __name__ == "__main__":
    main()
