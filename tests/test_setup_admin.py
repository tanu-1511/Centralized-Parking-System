from app.models import User

TOKEN = "test-setup-token-123"
PASSWORD = "correct-horse"


def fetch_csrf(client):
    client.get("/setup-admin")
    with client.session_transaction() as sess:
        return sess["csrf_token"]


def test_page_is_hidden_without_setup_token(app, client, monkeypatch):
    monkeypatch.delenv("ADMIN_SETUP_TOKEN", raising=False)
    assert client.get("/setup-admin").status_code == 404


def test_wrong_token_creates_no_admin(app, client, monkeypatch):
    monkeypatch.setenv("ADMIN_SETUP_TOKEN", TOKEN)
    token = fetch_csrf(client)
    response = client.post("/setup-admin", data={
        "csrf_token": token, "setup_token": "wrong", "username": "root",
        "email": "root@example.com", "password": PASSWORD,
    })
    assert response.status_code == 200
    assert b"Setup token is incorrect." in response.data
    with app.app_context():
        assert User.query.filter_by(role="admin").count() == 0


def test_correct_token_creates_admin_then_page_closes(app, client, monkeypatch):
    monkeypatch.setenv("ADMIN_SETUP_TOKEN", TOKEN)
    token = fetch_csrf(client)
    response = client.post("/setup-admin", data={
        "csrf_token": token, "setup_token": TOKEN, "username": "root",
        "email": "Root@Example.com", "password": PASSWORD,
    })
    assert response.status_code == 302
    with app.app_context():
        admin = User.query.filter_by(role="admin").one()
        assert admin.email == "root@example.com"
    # Once an admin exists, the page is gone.
    assert client.get("/setup-admin").status_code == 404
