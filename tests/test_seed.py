from werkzeug.security import check_password_hash

from app.models import ParkingFacility, ParkingSession, ParkingSlot, Reservation, User, Vehicle
from app.seed import DEMO_FACILITY, DEMO_PASSWORD, seed_demo


def test_seed_adds_demo_data_once(app):
    with app.app_context():
        assert seed_demo() is True
        assert ParkingFacility.query.filter_by(name=DEMO_FACILITY).count() == 1
        assert ParkingSlot.query.count() == 12
        assert User.query.filter_by(role="admin").count() == 1
        assert Vehicle.query.count() == 2
        assert ParkingSession.query.filter_by(exit_time=None).count() == 1
        assert Reservation.query.filter_by(status="confirmed").count() == 1

        # Running it again adds no duplicate data.
        assert seed_demo() is False
        assert ParkingFacility.query.count() == 1
        assert ParkingSlot.query.count() == 12
        assert Vehicle.query.count() == 2


def test_seed_sets_demo_password_even_for_existing_account(app):
    from app import db
    with app.app_context():
        db.session.add(User(username="old", email="driver@example.com",
                            password_hash="stale", role="user"))
        db.session.commit()
        seed_demo()
        driver = User.query.filter_by(email="driver@example.com").first()
        assert check_password_hash(driver.password_hash, DEMO_PASSWORD)
        assert User.query.filter_by(email="driver@example.com").count() == 1
