from flask import Blueprint, render_template, session

from app import db
from app.models import User
from app.security import csrf_token

main = Blueprint("main", __name__)


@main.route("/")
def home():
    user = db.session.get(User, session["user_id"]) if "user_id" in session else None
    return render_template("home.html", user=user, csrf_token=csrf_token())
