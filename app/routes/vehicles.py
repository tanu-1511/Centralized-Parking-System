import re

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Vehicle
from app.security import csrf_token, current_user, login_required, require_csrf

vehicles = Blueprint("vehicles", __name__)

VEHICLE_TYPES = ("car", "motorcycle", "van")
NUMBER_PATTERN = re.compile(r"[A-Z0-9-]{4,20}")


def _vehicle_values():
    # Spaces are removed and letters upper-cased so "mh12 ab 1234" and
    # "MH12AB1234" are the same vehicle.
    number = re.sub(r"\s+", "", request.form.get("vehicle_number", "")).upper()
    model = request.form.get("vehicle_model", "").strip()
    return {
        "vehicle_number": number,
        "vehicle_type": request.form.get("vehicle_type", "car"),
        "vehicle_model": model or None,
    }


def _validate(values, existing_id=None):
    errors = []
    if not NUMBER_PATTERN.fullmatch(values["vehicle_number"]):
        errors.append("Vehicle number must be 4 to 20 letters, digits or hyphens.")
    if values["vehicle_type"] not in VEHICLE_TYPES:
        errors.append("Choose a valid vehicle type.")
    if values["vehicle_model"] and len(values["vehicle_model"]) > 50:
        errors.append("Vehicle model must be 50 characters or fewer.")
    if not errors:
        existing = Vehicle.query.filter_by(vehicle_number=values["vehicle_number"]).first()
        if existing is not None and existing.vehicle_id != existing_id:
            errors.append("That vehicle number is already registered.")
    return errors


def _flash_errors(errors):
    for message in errors:
        flash(message, "error")


def _owned_vehicle(vehicle_id):
    """Return the vehicle if the signed-in user owns it; otherwise 404."""
    vehicle = db.session.get(Vehicle, vehicle_id)
    if vehicle is None or vehicle.user_id != current_user().user_id:
        abort(404)
    return vehicle


@vehicles.route("/vehicles")
@login_required
def list_vehicles():
    user = current_user()
    mine = (
        Vehicle.query.filter_by(user_id=user.user_id)
        .order_by(Vehicle.vehicle_number)
        .all()
    )
    return render_template(
        "vehicles.html",
        vehicles=mine,
        user=user,
        vehicle_types=VEHICLE_TYPES,
        csrf_token=csrf_token(),
    )


@vehicles.route("/vehicles", methods=["POST"])
@login_required
def create_vehicle():
    require_csrf()
    values = _vehicle_values()
    errors = _validate(values)
    if errors:
        _flash_errors(errors)
        return redirect(url_for("vehicles.list_vehicles"))

    db.session.add(Vehicle(user_id=current_user().user_id, **values))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("That vehicle number is already registered.", "error")
    else:
        flash("Vehicle registered.", "success")
    return redirect(url_for("vehicles.list_vehicles"))


@vehicles.route("/vehicles/<int:vehicle_id>/edit")
@login_required
def edit_vehicle_form(vehicle_id):
    vehicle = _owned_vehicle(vehicle_id)
    return render_template(
        "vehicle_edit.html",
        vehicle=vehicle,
        user=current_user(),
        vehicle_types=VEHICLE_TYPES,
        csrf_token=csrf_token(),
    )


@vehicles.route("/vehicles/<int:vehicle_id>/edit", methods=["POST"])
@login_required
def update_vehicle(vehicle_id):
    require_csrf()
    vehicle = _owned_vehicle(vehicle_id)
    values = _vehicle_values()
    errors = _validate(values, existing_id=vehicle.vehicle_id)
    if errors:
        _flash_errors(errors)
        return redirect(url_for("vehicles.edit_vehicle_form", vehicle_id=vehicle_id))

    for field, value in values.items():
        setattr(vehicle, field, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("That vehicle number is already registered.", "error")
        return redirect(url_for("vehicles.edit_vehicle_form", vehicle_id=vehicle_id))

    flash("Vehicle updated.", "success")
    return redirect(url_for("vehicles.list_vehicles"))
