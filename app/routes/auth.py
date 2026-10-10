import re

from flask import Blueprint, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models import User
from app.security import csrf_token, require_csrf

auth = Blueprint("auth", __name__)

EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_PATTERN = re.compile(r"\+?[0-9][0-9 \-()]{5,14}")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
DUPLICATE_EMAIL_MESSAGE = "An account with this email already exists."
INVALID_LOGIN_MESSAGE = "Invalid email or password."

# Checked against unknown emails too, so response time does not reveal which
# accounts exist.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def _validate_signup(username, email, phone, password):
    errors = []
    if not username or len(username) > 80:
        errors.append("Username is required and must be 80 characters or fewer.")
    if len(email) > 120 or not EMAIL_PATTERN.fullmatch(email):
        errors.append("Enter a valid email address.")
    if phone and not PHONE_PATTERN.fullmatch(phone):
        errors.append("Enter a valid phone number (digits, spaces, + - ( ) only).")
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    elif len(password) > MAX_PASSWORD_LENGTH:
        errors.append(f"Password must be {MAX_PASSWORD_LENGTH} characters or fewer.")
    return errors


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    errors = []
    form = {"username": "", "email": "", "phone": ""}

    if request.method == "POST":
        require_csrf()
        form = {
            "username": request.form.get("username", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "phone": request.form.get("phone", "").strip(),
        }
        password = request.form.get("password", "")

        errors = _validate_signup(
            form["username"], form["email"], form["phone"], password
        )
        if not errors and User.query.filter_by(email=form["email"]).first():
            errors.append(DUPLICATE_EMAIL_MESSAGE)

        if not errors:
            # The role is always "user". Nothing from the form can set it.
            user = User(
                username=form["username"],
                email=form["email"],
                phone=form["phone"] or None,
                password_hash=generate_password_hash(password),
                role="user",
            )
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                errors.append(DUPLICATE_EMAIL_MESSAGE)
            else:
                return redirect(url_for("auth.login", registered=1))

    return render_template(
        "signup.html", errors=errors, form=form, csrf_token=csrf_token()
    )


@auth.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        require_csrf()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        stored_hash = user.password_hash if user else _DUMMY_HASH
        password_ok = check_password_hash(stored_hash, password)

        if user and password_ok:
            session.clear()
            session["user_id"] = user.user_id
            return redirect(url_for("main.home"))

        error = INVALID_LOGIN_MESSAGE

    return render_template(
        "login.html",
        error=error,
        registered=request.args.get("registered") == "1",
        csrf_token=csrf_token(),
    )


@auth.route("/logout", methods=["POST"])
def logout():
    require_csrf()
    session.clear()
    return redirect(url_for("main.home"))
