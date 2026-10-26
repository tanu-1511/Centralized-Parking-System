"""One-time page to create the first admin account on a hosted site.

It stays off unless the ADMIN_SETUP_TOKEN environment variable is set, and it
returns 404 as soon as any admin account exists. Remove the variable after use.
"""
import hmac
import os

from flask import Blueprint, abort, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from app import db
from app.models import User
from app.security import csrf_token, require_csrf

setup_admin = Blueprint("setup_admin", __name__)

MIN_PASSWORD_LENGTH = 8


def _setup_open():
    return bool(os.environ.get("ADMIN_SETUP_TOKEN")) and User.query.filter_by(role="admin").first() is None


@setup_admin.route("/setup-admin", methods=["GET", "POST"])
def setup_form():
    if not _setup_open():
        abort(404)

    error = None
    if request.method == "POST":
        require_csrf()
        expected = os.environ.get("ADMIN_SETUP_TOKEN", "")
        given = request.form.get("setup_token", "")
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not hmac.compare_digest(given.encode(), expected.encode()):
            error = "Setup token is incorrect."
        elif not username or "@" not in email:
            error = "Enter a username and a valid email."
        elif len(password) < MIN_PASSWORD_LENGTH:
            error = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        elif User.query.filter_by(email=email).first():
            error = "An account with this email already exists."
        else:
            db.session.add(User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                role="admin",
            ))
            db.session.commit()
            return redirect(url_for("auth.login", registered=1))

    return render_template("setup_admin.html", error=error, csrf_token=csrf_token())
