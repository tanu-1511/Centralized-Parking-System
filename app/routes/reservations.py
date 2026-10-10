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

def _window_ready(start, end, now):
    """True when the chosen times form a bookable window (future start, allowed length)."""
    if start is None or end is None or start < now:
        return False
    return MIN_DURATION <= end - start <= MAX_DURATION


def _seat_state(slot, reservation_type, start, end):
    if slot.operational_status != "active":
        return "unavailable"
    if reservation_type == "ev_charging" and not slot.is_ev_charging:
        return "unavailable"
    if reservation_type == "accessible" and not slot.is_accessible:
        return "unavailable"
    if start is None:
        return "pick"
    if has_conflict(slot.slot_id, start, end):
        return "taken"
    return "free"


def _seat_rows(slots, reservation_type, start, end):
    """Group one floor's slots into rows by their map position, left to right."""
    rows = {}
    for slot in slots:
        rows.setdefault(slot.map_y, []).append(slot)
    return [
        [
            {"slot": slot, "state": _seat_state(slot, reservation_type, start, end)}
            for slot in sorted(rows[y], key=lambda item: item.map_x)
        ]
        for y in sorted(rows)
    ]


@reservations.route("/reservations/new")
@login_required
def new_reservation():
    expire_stale_reservations()
    user = current_user()
    my_vehicles = (
        Vehicle.query.filter_by(user_id=user.user_id)
        .order_by(Vehicle.vehicle_number)
        .all()
    )

    # Facilities that have at least one open slot, for the facility picker.
    open_slots = (
        ParkingSlot.query
        .join(ParkingFloor, ParkingSlot.floor_id == ParkingFloor.floor_id)
        .join(ParkingFacility, ParkingFloor.facility_id == ParkingFacility.facility_id)
        .filter(
            ParkingSlot.operational_status == "active",
            ParkingFacility.status == "active",
        )
        .all()
    )
    facilities = sorted(
        {slot.floor.facility.facility_id: slot.floor.facility for slot in open_slots}.values(),
        key=lambda facility: facility.name,
    )

    facility_id = _parse_int(request.args.get("facility"))
    selected = next(
        (facility for facility in facilities if facility.facility_id == facility_id),
        facilities[0] if facilities else None,
    )

    reservation_type = request.args.get("reservation_type", "standard")
    if reservation_type not in RESERVATION_TYPES:
        reservation_type = "standard"

    start = _parse_datetime(request.args.get("start_time"))
    end = _parse_datetime(request.args.get("end_time"))
    window_ready = _window_ready(start, end, datetime.now())
    seat_start, seat_end = (start, end) if window_ready else (None, None)

    floor_views = []
    if selected:
        for floor in sorted(selected.floors, key=lambda item: item.floor_number):
            if floor.slots:
                floor_views.append({
                    "floor": floor,
                    "rows": _seat_rows(floor.slots, reservation_type, seat_start, seat_end),
                })

    return render_template(
        "reservation_new.html",
        user=user,
        vehicles=my_vehicles,
        facilities=facilities,
        selected_facility=selected,
        floor_views=floor_views,
        window_ready=window_ready,
        start_value=start.strftime(DATETIME_FORMAT) if start else "",
        end_value=end.strftime(DATETIME_FORMAT) if end else "",
        reservation_type=reservation_type,
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
