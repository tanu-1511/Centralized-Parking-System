from werkzeug.security import generate_password_hash

from app import db
from app.models import ParkingFacility, ParkingFloor, ParkingSlot, User

PASSWORD = "correct-horse"

FACILITY = {
    "name": "Airport Parking",
    "address": "Terminal 2",
    "city": "Delhi",
    "status": "active",
}


def make_user(app, email, role, facility_id=None):
    with app.app_context():
        user = User(
            username=email.split("@")[0],
            email=email,
            password_hash=generate_password_hash(PASSWORD),
            role=role,
            facility_id=facility_id,
        )
        db.session.add(user)
        db.session.commit()
        return user.user_id


def make_facility(app, name="Central Mall"):
    with app.app_context():
        facility = ParkingFacility(
            name=name, address="1 Main Road", city="Pune", status="active"
        )
        db.session.add(facility)
        db.session.commit()
        return facility.facility_id


def make_floor(app, facility_id, number=1):
    with app.app_context():
        floor = ParkingFloor(facility_id=facility_id, floor_number=number)
        db.session.add(floor)
        db.session.commit()
        return floor.floor_id


def make_slot(app, floor_id, number="A1"):
    with app.app_context():
        slot = ParkingSlot(
            floor_id=floor_id,
            slot_number=number,
            slot_type="standard",
            is_ev_charging=False,
            is_accessible=False,
            map_x=1.0,
            map_y=2.0,
            operational_status="active",
        )
        db.session.add(slot)
        db.session.commit()
        return slot.slot_id


def log_in(client, email):
    """Sign in and return the CSRF token for the session."""
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    client.post(
        "/login", data={"email": email, "password": PASSWORD, "csrf_token": token}
    )
    client.get("/dashboard")
    with client.session_transaction() as sess:
        return sess["csrf_token"]


def slot_form(token, **overrides):
    data = {
        "slot_number": "B2",
        "slot_type": "standard",
        "map_x": "10",
        "map_y": "20",
        "operational_status": "active",
        "csrf_token": token,
    }
    data.update(overrides)
    return data


# ---------- Facilities ----------

def test_admin_creates_facility(client, app):
    make_user(app, "root@example.com", "admin")
    token = log_in(client, "root@example.com")

    response = client.post("/facilities", data={**FACILITY, "csrf_token": token})

    assert response.status_code == 302
    with app.app_context():
        assert ParkingFacility.query.filter_by(name="Airport Parking").count() == 1


def test_regular_user_cannot_create_facility(client, app):
    make_user(app, "alice@example.com", "user")
    token = log_in(client, "alice@example.com")

    response = client.post("/facilities", data={**FACILITY, "csrf_token": token})

    assert response.status_code == 403
    with app.app_context():
        assert ParkingFacility.query.count() == 0


def test_invalid_facility_is_not_saved(client, app):
    make_user(app, "root@example.com", "admin")
    token = log_in(client, "root@example.com")

    client.post("/facilities", data={**FACILITY, "name": "", "csrf_token": token})

    with app.app_context():
        assert ParkingFacility.query.count() == 0


def test_anonymous_visitor_cannot_view_facility_list(client):
    response = client.get("/facilities")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ---------- Floors and slots ----------

def test_parking_admin_adds_floor_to_own_facility(client, app):
    facility_id = make_facility(app)
    make_user(app, "pat@example.com", "parking_admin", facility_id=facility_id)
    token = log_in(client, "pat@example.com")

    response = client.post(
        f"/facilities/{facility_id}/floors",
        data={"floor_number": "2", "name": "Upper", "csrf_token": token},
    )

    assert response.status_code == 302
    with app.app_context():
        assert ParkingFloor.query.filter_by(facility_id=facility_id).count() == 1


def test_parking_admin_cannot_add_floor_to_other_facility(client, app):
    own = make_facility(app, "Own")
    other = make_facility(app, "Other")
    make_user(app, "pat@example.com", "parking_admin", facility_id=own)
    token = log_in(client, "pat@example.com")

    response = client.post(
        f"/facilities/{other}/floors",
        data={"floor_number": "1", "csrf_token": token},
    )

    assert response.status_code == 403
    with app.app_context():
        assert ParkingFloor.query.count() == 0


def test_duplicate_slot_number_on_same_floor_is_rejected(client, app):
    facility_id = make_facility(app)
    floor_id = make_floor(app, facility_id)
    make_user(app, "root@example.com", "admin")
    token = log_in(client, "root@example.com")
    url = f"/facilities/{facility_id}/floors/{floor_id}/slots"

    client.post(url, data=slot_form(token))
    client.post(url, data=slot_form(token))

    with app.app_context():
        assert ParkingSlot.query.filter_by(floor_id=floor_id).count() == 1


def test_slot_from_other_facility_cannot_be_changed_here(client, app):
    facility_a = make_facility(app, "A")
    facility_b = make_facility(app, "B")
    floor_b = make_floor(app, facility_b)
    slot_b = make_slot(app, floor_b)
    make_user(app, "root@example.com", "admin")
    token = log_in(client, "root@example.com")

    response = client.post(
        f"/facilities/{facility_a}/slots/{slot_b}/status",
        data={"operational_status": "maintenance", "csrf_token": token},
    )

    assert response.status_code == 404
    with app.app_context():
        assert db.session.get(ParkingSlot, slot_b).operational_status == "active"


# ---------- Role assignment ----------

def test_admin_assigns_parking_admin_to_facility(client, app):
    facility_id = make_facility(app)
    bob_id = make_user(app, "bob@example.com", "user")
    make_user(app, "root@example.com", "admin")
    token = log_in(client, "root@example.com")

    response = client.post(
        f"/admin/users/{bob_id}",
        data={"role": "parking_admin", "facility_id": str(facility_id), "csrf_token": token},
    )

    assert response.status_code == 302
    with app.app_context():
        bob = db.session.get(User, bob_id)
        assert bob.role == "parking_admin"
        assert bob.facility_id == facility_id


def test_parking_admin_without_facility_is_refused(client, app):
    bob_id = make_user(app, "bob@example.com", "user")
    make_user(app, "root@example.com", "admin")
    token = log_in(client, "root@example.com")

    client.post(
        f"/admin/users/{bob_id}",
        data={"role": "parking_admin", "facility_id": "", "csrf_token": token},
    )

    with app.app_context():
        assert db.session.get(User, bob_id).role == "user"


def test_system_admin_account_cannot_be_reassigned(client, app):
    other_admin_id = make_user(app, "second@example.com", "admin")
    make_user(app, "root@example.com", "admin")
    token = log_in(client, "root@example.com")

    client.post(
        f"/admin/users/{other_admin_id}",
        data={"role": "user", "csrf_token": token},
    )

    with app.app_context():
        assert db.session.get(User, other_admin_id).role == "admin"


def test_regular_user_cannot_open_role_management(client, app):
    make_user(app, "alice@example.com", "user")
    log_in(client, "alice@example.com")

    assert client.get("/admin/users").status_code == 403
