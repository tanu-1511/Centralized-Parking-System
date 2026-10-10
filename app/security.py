import secrets

from flask import abort, request, session


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
