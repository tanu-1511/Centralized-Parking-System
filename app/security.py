import secrets
from functools import wraps

from flask import abort, redirect, request, session, url_for


def csrf_token():
    """Return this session's CSRF token, creating one if needed."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def require_csrf():
    """Abort with 400 unless the submitted form carries this session's token."""
    expected = session.get("csrf_token", "")
    submitted = request.form.get("csrf_token", "")
    if not expected or not secrets.compare_digest(
        expected.encode(), submitted.encode()
    ):
        abort(400)


def current_user():
    """Return the signed-in User, or None.

    Looked up on every call rather than cached in flask.g: g can outlive a
    single request (for example inside a test's app context), which would
    hand one user's identity to the next request.
    """
    from app import db
    from app.models import User

    user_id = session.get("user_id")
    if user_id is None:
        return None
    return db.session.get(User, user_id)


def login_required(view):
    """Redirect anonymous visitors to the login page."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapper


def roles_required(*allowed_roles):
    """Allow only signed-in users whose role is in allowed_roles.

    Anonymous visitors are redirected to login; signed-in users with the
    wrong role get 403.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return redirect(url_for("auth.login"))
            if user.role not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator
