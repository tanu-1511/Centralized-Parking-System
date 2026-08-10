from flask import Flask

def create_app():
    app = Flask(__name__)

    @app.route("/")
    def home():
        return "Centralized Parking Management System"

    return app