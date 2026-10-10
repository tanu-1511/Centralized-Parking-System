from werkzeug.security import generate_password_hash

from app import db
from app.models import User

PASSWORD = "correct-horse"


def make_user(app, email, role):
    with app.app_context():
        db.session.add(User(
            username=email.split("@")[0],
            email=email,
            password_hash=generate_password_hash(PASSWORD),
            role=role,
        ))
        db.session.commit()


def log_in(client, email):
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    return client.post(
        "/login", data={"email": email, "password": PASSWORD, "csrf_token": token}
    )


def test_dashboard_redirects_anonymous_visitor_to_login(client):
    response = client.get("/dashboard")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_dashboard_shows_signed_in_user(client, app):
    make_user(app, "alice@example.com", "user")
    log_in(client, "alice@example.com")

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert b"alice" in response.data


def test_admin_page_redirects_anonymous_visitor_to_login(client):
    response = client.get("/admin")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_page_forbidden_for_regular_user(client, app):
    make_user(app, "alice@example.com", "user")
    log_in(client, "alice@example.com")

    assert client.get("/admin").status_code == 403


def test_admin_page_forbidden_for_parking_admin(client, app):
    # Facility-scoped admin pages come in a later step; for now only
    # the system admin role may open /admin.
    make_user(app, "pat@example.com", "parking_admin")
    log_in(client, "pat@example.com")

    assert client.get("/admin").status_code == 403


def test_admin_page_allowed_for_admin(client, app):
    make_user(app, "root@example.com", "admin")
    log_in(client, "root@example.com")

    response = client.get("/admin")

    assert response.status_code == 200
    assert b"Administration" in response.data
