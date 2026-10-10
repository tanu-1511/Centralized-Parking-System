from app import db
from app.models import User
from werkzeug.security import generate_password_hash

PASSWORD = "correct-horse"


def make_user(app, email="fe@example.com"):
    with app.app_context():
        db.session.add(User(username="fe", email=email,
                            password_hash=generate_password_hash(PASSWORD), role="user"))
        db.session.commit()


def login(client, email="fe@example.com"):
    client.get("/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    return client.post("/login", data={"email": email, "password": PASSWORD, "csrf_token": token})


def test_stylesheet_is_served(client):
    response = client.get("/static/style.css")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '[data-theme="dark"]' in body
    assert "prefers-color-scheme: dark" in body


def test_public_pages_share_layout_and_theme_toggle(client):
    for path in ("/", "/login", "/signup"):
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "style.css" in html
        assert 'id="theme-toggle"' in html
        assert "Sign up" in html  # logged-out nav


def test_signed_in_nav_shows_app_links_and_logout(app, client):
    make_user(app)
    login(client)
    html = client.get("/dashboard").get_data(as_text=True)
    assert "/vehicles" in html
    assert "/reservations/mine" in html
    assert "Logout" in html
    assert "Sign up" not in html

