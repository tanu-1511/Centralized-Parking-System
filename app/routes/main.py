from flask import Blueprint, render_template, session

from app import db
from app.models import User
from app.security import csrf_token, current_user, login_required, roles_required

main = Blueprint("main", __name__)


@main.route("/")
def home():
    user = db.session.get(User, session["user_id"]) if "user_id" in session else None
    return render_template("home.html", user=user, csrf_token=csrf_token())


@main.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html", user=current_user(), csrf_token=csrf_token()
    )


@main.route("/admin")
@roles_required("admin")
def admin_home():
    return render_template("admin.html", user=current_user())
