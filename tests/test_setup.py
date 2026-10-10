from sqlalchemy import inspect
from sqlalchemy.orm import configure_mappers

from app import db

EXPECTED_TABLES = {
    "users",
    "vehicles",
    "parking_facilities",
    "parking_floors",
    "parking_slots",
    "reservations",
    "parking_sessions",
    "occupancy_events",
}


def test_model_relationships_configure():
    # Fails if any back_populates pair is missing or mismatched.
    configure_mappers()


def test_all_expected_tables_are_created(app):
    tables = set(inspect(db.engine).get_table_names())
    assert EXPECTED_TABLES <= tables


def test_tests_use_temporary_database(app):
    assert app.config["SQLALCHEMY_DATABASE_URI"].endswith("test.db")


def test_homepage_loads(client):
    response = client.get("/")
    assert response.status_code == 200
