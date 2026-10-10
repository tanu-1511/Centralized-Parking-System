from werkzeug.security import generate_password_hash

from app import db
from app.models import User, Vehicle

PASSWORD = "correct-horse"


def make_user(app, email):
    with app.app_context():
        user = User(
            username=email.split("@")[0],
            email=email,
            password_hash=generate_password_hash(PASSWORD),
            role="user",
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


def log_in(client, email):
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    client.post("/login", data={"email": email, "password": PASSWORD, "csrf_token": token})
    client.get("/dashboard")
    with client.session_transaction() as sess:
        return sess["csrf_token"]


def register(client, token, number="MH12AB1234", **overrides):
    data = {"vehicle_number": number, "vehicle_type": "car", "vehicle_model": "", "csrf_token": token}
    data.update(overrides)
    return client.post("/vehicles", data=data)


def test_user_registers_vehicle_for_self(client, app):
    alice = make_user(app, "alice@example.com")
    token = log_in(client, "alice@example.com")

    response = register(client, token, vehicle_model="Swift")

    assert response.status_code == 302
    with app.app_context():
        vehicle = Vehicle.query.filter_by(vehicle_number="MH12AB1234").one()
        assert vehicle.user_id == alice
        assert vehicle.vehicle_model == "Swift"


def test_vehicle_number_is_normalized(client, app):
    make_user(app, "alice@example.com")
    token = log_in(client, "alice@example.com")

    register(client, token, number=" mh12 ab 1234 ")

    with app.app_context():
        assert Vehicle.query.filter_by(vehicle_number="MH12AB1234").count() == 1


def test_invalid_vehicle_number_is_rejected(client, app):
    make_user(app, "alice@example.com")
    token = log_in(client, "alice@example.com")

    register(client, token, number="!!")

    with app.app_context():
        assert Vehicle.query.count() == 0


def test_duplicate_vehicle_number_is_rejected(client, app):
    bob = make_user(app, "bob@example.com")
    make_vehicle(app, bob, "MH12AB1234")
    make_user(app, "alice@example.com")
    token = log_in(client, "alice@example.com")

    register(client, token, number="MH12AB1234")

    with app.app_context():
        assert Vehicle.query.count() == 1


def test_list_shows_only_own_vehicles(client, app):
    alice = make_user(app, "alice@example.com")
    bob = make_user(app, "bob@example.com")
    make_vehicle(app, alice, "AAA1111")
    make_vehicle(app, bob, "BBB2222")
    log_in(client, "alice@example.com")

    response = client.get("/vehicles")

    assert b"AAA1111" in response.data
    assert b"BBB2222" not in response.data


def test_user_cannot_edit_another_users_vehicle(client, app):
    bob = make_user(app, "bob@example.com")
    bobs_vehicle = make_vehicle(app, bob, "BBB2222")
    make_user(app, "alice@example.com")
    token = log_in(client, "alice@example.com")

    response = client.post(
        f"/vehicles/{bobs_vehicle}/edit",
        data={"vehicle_number": "HACKED1", "vehicle_type": "van", "csrf_token": token},
    )

    assert response.status_code == 404
    with app.app_context():
        assert db.session.get(Vehicle, bobs_vehicle).vehicle_number == "BBB2222"


def test_owner_can_edit_own_vehicle(client, app):
    alice = make_user(app, "alice@example.com")
    vehicle_id = make_vehicle(app, alice, "AAA1111")
    token = log_in(client, "alice@example.com")

    response = client.post(
        f"/vehicles/{vehicle_id}/edit",
        data={"vehicle_number": "AAA1111", "vehicle_type": "van", "vehicle_model": "Van X", "csrf_token": token},
    )

    assert response.status_code == 302
    with app.app_context():
        vehicle = db.session.get(Vehicle, vehicle_id)
        assert vehicle.vehicle_type == "van"
        assert vehicle.vehicle_model == "Van X"


def test_anonymous_visitor_cannot_list_vehicles(client):
    response = client.get("/vehicles")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
