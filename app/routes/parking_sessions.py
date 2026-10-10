import re
from collections import Counter
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app import db
from app.models import OccupancyEvent, ParkingFacility, ParkingSession, ParkingSlot, Vehicle
from app.security import csrf_token, current_user, login_required, require_csrf
from app.services import SESSION_ACTIVE, can_manage_facility

parking_sessions = Blueprint("parking_sessions", __name__)

SESSION_COMPLETED = "completed"
EVENT_OCCUPIED = "occupied"
EVENT_VACATED = "vacated"


def _authorize(facility_id):
    """404 if the facility is missing; 403 unless the user may manage it."""
    db.get_or_404(ParkingFacility, facility_id)
    user = current_user()
    if not can_manage_facility(user, facility_id):
        abort(403)
    return user


def _parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _open_session_for_slot(slot_id):
    return ParkingSession.query.filter(
        ParkingSession.slot_id == slot_id,
        ParkingSession.status == SESSION_ACTIVE,
        ParkingSession.exit_time.is_(None),
    ).first()


def _open_session_for_vehicle(vehicle_id):
    return ParkingSession.query.filter(
        ParkingSession.vehicle_id == vehicle_id,
        ParkingSession.status == SESSION_ACTIVE,
        ParkingSession.exit_time.is_(None),
    ).first()


def _duration_minutes(parking):
    """Minutes between entry and exit, or None while the car is still parked."""
    if parking.exit_time is None:
        return None
    return round((parking.exit_time - parking.entry_time).total_seconds() / 60)


def _location_label(slot):
    return f"{slot.floor.facility.name} \u00b7 floor {slot.floor.floor_number} \u00b7 {slot.slot_number}"


@parking_sessions.route("/facilities/<int:facility_id>/sessions")
@login_required
def facility_sessions(facility_id):
    facility = db.get_or_404(ParkingFacility, facility_id)
    user = _authorize(facility_id)

    facility_slot_ids = [
        slot.slot_id
        for floor in facility.floors
        for slot in floor.slots
    ]
    active = []
    history = []
    if facility_slot_ids:
        query = ParkingSession.query.filter(ParkingSession.slot_id.in_(facility_slot_ids))
        active = query.filter(
            ParkingSession.status == SESSION_ACTIVE,
            ParkingSession.exit_time.is_(None),
        ).order_by(ParkingSession.entry_time).all()
        history = query.filter(ParkingSession.status == SESSION_COMPLETED) \
            .order_by(ParkingSession.exit_time.desc()).limit(50).all()

    open_slots = [
        slot
        for floor in facility.floors
        for slot in floor.slots
        if slot.operational_status == "active" and _open_session_for_slot(slot.slot_id) is None
    ]
    return render_template(
        "facility_sessions.html",
        facility=facility,
        active=active,
        history_rows=[{"session": p, "minutes": _duration_minutes(p)} for p in history],
        open_slots=sorted(open_slots, key=lambda s: (s.floor.floor_number, s.slot_number)),
        user=user,
        csrf_token=csrf_token(),
    )


@parking_sessions.route("/facilities/<int:facility_id>/sessions/start", methods=["POST"])
@login_required
def start_session(facility_id):
    require_csrf()
    _authorize(facility_id)

    plate = re.sub(r"\s+", "", request.form.get("vehicle_number", "")).upper()
    slot_id = _parse_int(request.form.get("slot_id"))
    vehicle = Vehicle.query.filter_by(vehicle_number=plate).first() if plate else None
    slot = db.session.get(ParkingSlot, slot_id) if slot_id is not None else None

    errors = []
    if vehicle is None:
        errors.append("No registered vehicle has that number.")
    if slot is None or slot.floor.facility_id != facility_id:
        errors.append("Choose a slot in this facility.")
    else:
        if slot.operational_status != "active":
            errors.append("That slot is not open.")
        if _open_session_for_slot(slot.slot_id) is not None:
            errors.append("That slot is already occupied.")
    if vehicle is not None and _open_session_for_vehicle(vehicle.vehicle_id) is not None:
        errors.append("That vehicle is already parked.")

    if errors:
        for message in errors:
            flash(message, "error")
        return redirect(url_for("parking_sessions.facility_sessions", facility_id=facility_id))

    now = datetime.now()
    parking = ParkingSession(vehicle_id=vehicle.vehicle_id, slot_id=slot.slot_id,
                             entry_time=now, status=SESSION_ACTIVE)
    db.session.add(parking)
    db.session.flush()
    db.session.add(OccupancyEvent(
        parking_slot_id=slot.slot_id,
        vehicle_id=vehicle.vehicle_id,
        parking_session_id=parking.session_id,
        event_time=now,
        event_type=EVENT_OCCUPIED,
    ))
    db.session.commit()
    flash("Parking started.", "success")
    return redirect(url_for("parking_sessions.facility_sessions", facility_id=facility_id))


@parking_sessions.route(
    "/facilities/<int:facility_id>/sessions/<int:session_id>/end", methods=["POST"]
)
@login_required
def end_session(facility_id, session_id):
    require_csrf()
    _authorize(facility_id)
    parking = db.session.get(ParkingSession, session_id)
    if parking is None or parking.slot.floor.facility_id != facility_id:
        abort(404)

    if parking.status != SESSION_ACTIVE or parking.exit_time is not None:
        flash("That parking session has already ended.", "error")
    else:
        now = datetime.now()
        if now < parking.entry_time:
            flash("Exit time cannot be before entry time.", "error")
            return redirect(url_for("parking_sessions.facility_sessions", facility_id=facility_id))
        parking.exit_time = now
        parking.status = SESSION_COMPLETED
        db.session.add(OccupancyEvent(
            parking_slot_id=parking.slot_id,
            vehicle_id=parking.vehicle_id,
            parking_session_id=parking.session_id,
            event_time=now,
            event_type=EVENT_VACATED,
        ))
        db.session.commit()
        flash("Parking ended.", "success")
    return redirect(url_for("parking_sessions.facility_sessions", facility_id=facility_id))


@parking_sessions.route("/history")
@login_required
def my_history():
    user = current_user()
    vehicle_ids = [v.vehicle_id for v in Vehicle.query.filter_by(user_id=user.user_id).all()]
    sessions = []
    if vehicle_ids:
        sessions = (
            ParkingSession.query.filter(ParkingSession.vehicle_id.in_(vehicle_ids))
            .order_by(ParkingSession.entry_time.desc())
            .all()
        )
    rows = [
        {
            "session": p,
            "location": _location_label(p.slot),
            "minutes": _duration_minutes(p),
        }
        for p in sessions
    ]
    top_spots = Counter(row["location"] for row in rows).most_common(3)
    return render_template("history.html", user=user, rows=rows, top_spots=top_spots)
