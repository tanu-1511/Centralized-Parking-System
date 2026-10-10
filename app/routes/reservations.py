from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app import db
from app.models import ParkingFacility, ParkingFloor, ParkingSlot, Reservation, Vehicle
from app.security import csrf_token, current_user, login_required, require_csrf
from app.services import (
    RESERVATION_CANCELLED,
    RESERVATION_CONFIRMED,
    expire_stale_reservations,
    has_conflict,
)

reservations = Blueprint("reservations", __name__)

RESERVATION_TYPES = ("standard", "ev_charging", "accessible")
MIN_DURATION = timedelta(minutes=30)
MAX_DURATION = timedelta(hours=12)
DATETIME_FORMAT = "%Y-%m-%dT%H:%M"

def _parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def _parse_datetime(value):
    try:
        return datetime.strptime(value or "", DATETIME_FORMAT)
    except ValueError:
        return None

def _booking_values():
    return {
        "vehicle_id": _parse_int(request.form.get("vehicle_id")),
        "slot_id": _parse_int(request.form.get("slot_id")),
        "start": _parse_datetime(request.form.get("start_time")),
        "end": _parse_datetime(request.form.get("end_time")),
        "reservation_type": request.form.get("reservation_type", "standard"),
    }

def _validate_booking(values, user, now):
    errors = []
    start, end = values["start"], values["end"]

    if start is None or end is None:
        errors.append("Enter a valid start and end time.")
    else:
        duration = end - start
        if duration <= timedelta(0):
            errors.append("End time must be after start time.")
        elif duration < MIN_DURATION:
            errors.append("Reservations must be at least 30 minutes long.")
        elif duration > MAX_DURATION:
            errors.append("Reservations can be at most 12 hours long.")
        if start < now:
            errors.append("Start time must be in the future.")

    if values["reservation_type"] not in RESERVATION_TYPES:
        errors.append("Choose a valid reservation type.")

    vehicle = (
        db.session.get(Vehicle, values["vehicle_id"])
        if values["vehicle_id"] is not None
        else None
    )
    if vehicle is None or vehicle.user_id != user.user_id:
        errors.append("Choose one of your own vehicles.")

    slot = (
        db.session.get(ParkingSlot, values["slot_id"])
        if values["slot_id"] is not None
        else None
    )
    if slot is None:
        errors.append("Choose a parking slot.")
        return errors

    if slot.operational_status != "active":
        errors.append("That slot is not open for booking.")
    if values["reservation_type"] == "ev_charging" and not slot.is_ev_charging:
        errors.append("An EV charging reservation needs an EV charging slot.")
    if values["reservation_type"] == "accessible" and not slot.is_accessible:
        errors.append("An accessible reservation needs an accessible slot.")
    if (
        not errors
        and has_conflict(slot.slot_id, start, end)
    ):
        errors.append("That slot is already reserved for part of this time.")
    return errors

def _flash_errors(errors):
    for message in errors:
        flash(message, "error")

@reservations.route("/reservations/new")
@login_required
def new_reservation():
    user = current_user()
    my_vehicles = (
        Vehicle.query.filter_by(user_id=user.user_id)
        .order_by(Vehicle.vehicle_number)
        .all()
    )
    bookable_slots = (
        ParkingSlot.query
        .join(ParkingFloor, ParkingSlot.floor_id == ParkingFloor.floor_id)
        .join(ParkingFacility, ParkingFloor.facility_id == ParkingFacility.facility_id)
        .filter(
            ParkingSlot.operational_status == "active",
            ParkingFacility.status == "active",
        )
        .order_by(ParkingFacility.name, ParkingFloor.floor_number, ParkingSlot.slot_number)
        .all()
    )
    return render_template(
        "reservation_new.html",
        user=user,
        vehicles=my_vehicles,
        slots=bookable_slots,
        reservation_types=RESERVATION_TYPES,
        csrf_token=csrf_token(),
    )

@reservations.route("/reservations", methods=["POST"])
@login_required
def create_reservation():
    require_csrf()
    user = current_user()
    values = _booking_values()
    errors = _validate_booking(values, user, datetime.now())
    if errors:
        _flash_errors(errors)
        return redirect(url_for("reservations.new_reservation"))

    db.session.add(Reservation(
        user_id=user.user_id,
        vehicle_id=values["vehicle_id"],
        slot_id=values["slot_id"],
        start_time=values["start"],
        end_time=values["end"],
        reservation_type=values["reservation_type"],
        status=RESERVATION_CONFIRMED,
    ))
    db.session.commit()
    flash("Reservation confirmed.", "success")
    return redirect(url_for("reservations.my_reservations"))

@reservations.route("/reservations/mine")
@login_required
def my_reservations():
    expire_stale_reservations()
    user = current_user()
    mine = (
        Reservation.query.filter_by(user_id=user.user_id)
        .order_by(Reservation.start_time.desc())
        .all()
    )
    return render_template(
        "reservations.html",
        reservations=mine,
        user=user,
        csrf_token=csrf_token(),
    )

@reservations.route("/reservations/<int:reservation_id>/cancel", methods=["POST"])
@login_required
def cancel_reservation(reservation_id):
    require_csrf()
    user = current_user()
    reservation = db.session.get(Reservation, reservation_id)
    if reservation is None or reservation.user_id != user.user_id:
        abort(404)

    if reservation.status != RESERVATION_CONFIRMED:
        flash("Only confirmed reservations can be cancelled.", "error")
    else:
        reservation.status = RESERVATION_CANCELLED
        db.session.commit()
        flash("Reservation cancelled.", "success")
    return redirect(url_for("reservations.my_reservations"))
