import os
import secrets

from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

load_dotenv()
db = SQLAlchemy()


def create_app(test_config=None):
    app = Flask(__name__)

    # Secret key comes from the environment (.env). If it is missing, a random
    # key is generated for this process only, so sessions reset on restart.
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    # SQLite file lives in the Flask instance folder (instance/parking.db).
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///parking.db"
    )

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    from app.routes.main import main
    from app.routes.auth import auth
    from app.routes.facilities import facilities
    from app.routes.vehicles import vehicles
    from app.routes.reservations import reservations
    from app.routes.parking_sessions import parking_sessions
    from app import models

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(facilities)
    app.register_blueprint(vehicles)
    app.register_blueprint(reservations)
    app.register_blueprint(parking_sessions)

    # Creates any missing tables (existing tables and data are left alone).
    with app.app_context():
        db.create_all()

    return app
