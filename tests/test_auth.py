import pytest
from werkzeug.security import check_password_hash

from app.models import User

VALID = {
    "username": "alice",
    "email": "Alice@Example.com",
    "phone": "+91 98765 43210",
    "password": "correct-horse",
}


def fetch_csrf(client, path):
    """Load a page so the session gets a CSRF token, then return it."""
    client.get(path)
    with client.session_transaction() as sess:
        return sess["csrf_token"]


def signup(client, **overrides):
    data = {**VALID, **overrides}
    data.setdefault("csrf_token", fetch_csrf(client, "/signup"))
    return client.post("/signup", data=data)


def login(client, email="alice@example.com", password=VALID["password"]):
    token = fetch_csrf(client, "/login")
    return client.post(
        "/login", data={"email": email, "password": password, "csrf_token": token}
    )


def test_signup_creates_regular_user_with_hashed_password(client, app):
    response = signup(client)

    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email="alice@example.com").one()
        assert user.role == "user"
        assert user.password_hash != VALID["password"]
        assert check_password_hash(user.password_hash, VALID["password"])


def test_signup_ignores_role_sent_by_form(client, app):
    signup(client, email="mallory@example.com", role="admin")

    with app.app_context():
        assert User.query.filter_by(email="mallory@example.com").one().role == "user"


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"password": "short"},
        {"username": ""},
        {"phone": "abc"},
    ],
)
def test_signup_rejects_invalid_input(client, app, overrides):
    response = signup(client, **overrides)

    assert response.status_code == 200
    with app.app_context():
        assert User.query.count() == 0


def test_duplicate_email_is_rejected(client, app):
    signup(client)
    response = signup(client, username="someone-else")

    assert response.status_code == 200
    assert b"already exists" in response.data
    with app.app_context():
        assert User.query.count() == 1


def test_signup_with_bad_csrf_token_is_rejected(client, app):
    response = signup(client, csrf_token="forged")

    assert response.status_code == 400
    with app.app_context():
        assert User.query.count() == 0


def test_valid_login_sets_session(client):
    signup(client)
    response = login(client)

    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert "user_id" in sess


def test_wrong_password_gives_generic_error(client):
    signup(client)
    response = login(client, password="wrong-password")

    assert response.status_code == 200
    assert b"Invalid email or password." in response.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_unknown_email_gives_same_generic_error(client):
    response = login(client, email="nobody@example.com")

    assert response.status_code == 200
    assert b"Invalid email or password." in response.data


def test_logout_clears_session(client):
    signup(client)
    login(client)
    token = fetch_csrf(client, "/")

    response = client.post("/logout", data={"csrf_token": token})

    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_logout_requires_post(client):
    assert client.get("/logout").status_code == 405
