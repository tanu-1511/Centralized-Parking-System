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
    from app import models

    app.register_blueprint(main)
    app.register_blueprint(auth)

    return app