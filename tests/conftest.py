import pytest

from app import create_app, db


@pytest.fixture
def app(tmp_path):
    """Application wired to a throwaway SQLite file inside pytest's temp folder.

    The development database (instance/parking.db) is never touched.
    """
    test_db = tmp_path / "test.db"
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-key",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{test_db.as_posix()}",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
