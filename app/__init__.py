from flask import Flask


def create_app():
    app = Flask(__name__)

    from app.routes.main import main
    from app.routes.auth import auth

    app.register_blueprint(main)
    app.register_blueprint(auth)

    return app