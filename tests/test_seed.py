from app.models import ParkingFacility, ParkingSession, ParkingSlot, Reservation, User, Vehicle
from app.seed import DEMO_FACILITY, seed_demo


def test_seed_adds_demo_data_once(app):
    with app.app_context():
        assert seed_demo() is True
        assert ParkingFacility.query.filter_by(name=DEMO_FACILITY).count() == 1
        assert ParkingSlot.query.count() == 12
        assert User.query.filter_by(role="admin").count() == 1
        assert Vehicle.query.count() == 2
        assert ParkingSession.query.filter_by(exit_time=None).count() == 1
        assert Reservation.query.filter_by(status="confirmed").count() == 1

        # Running it again must not duplicate anything.
        assert seed_demo() is False
        assert ParkingFacility.query.count() == 1
        assert ParkingSlot.query.count() == 12
