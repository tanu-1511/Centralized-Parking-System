import math
from collections import Counter

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app import db
from app.models import ParkingFacility, ParkingFloor, ParkingSlot, User
from app.services import (
    STATE_AVAILABLE,
    STATE_OCCUPIED,
    STATE_RESERVED,
    STATE_UNAVAILABLE,
    slot_states,
)
from app.security import (
    csrf_token,
    current_user,
    login_required,
    require_csrf,
    roles_required,
)

facilities = Blueprint("facilities", __name__)

FACILITY_STATUSES = ("active", "inactive")
SLOT_TYPES = ("standard", "compact", "motorcycle")
SLOT_STATUSES = ("active", "maintenance", "inactive")
ASSIGNABLE_ROLES = ("user", "parking_admin")


def _can_manage(user, facility_id):
    if user.role == "admin":
        return True
    return user.role == "parking_admin" and user.facility_id == facility_id


def _require_manage(facility_id):
    """404 if the facility is missing; 403 unless the user may manage it."""
    db.get_or_404(ParkingFacility, facility_id)
    user = current_user()
    if not _can_manage(user, facility_id):
        abort(403)
    return user


def _floor_in_facility(facility_id, floor_id):
    floor = db.session.get(ParkingFloor, floor_id)
    if floor is None or floor.facility_id != facility_id:
        abort(404)
    return floor


def _parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _flash_errors(errors):
    for message in errors:
        flash(message, "error")


# ---------- Facilities ----------

def _facility_values():
    return {
        "name": request.form.get("name", "").strip(),
        "address": request.form.get("address", "").strip(),
        "city": request.form.get("city", "").strip(),
        "status": request.form.get("status", "active"),
    }


def _validate_facility(values):
    errors = []
    if not values["name"] or len(values["name"]) > 150:
        errors.append("Facility name is required (max 150 characters).")
    if not values["address"] or len(values["address"]) > 255:
        errors.append("Address is required (max 255 characters).")
    if not values["city"] or len(values["city"]) > 100:
        errors.append("City is required (max 100 characters).")
    if values["status"] not in FACILITY_STATUSES:
        errors.append("Status must be active or inactive.")
    return errors


@facilities.route("/facilities")
@login_required
def list_facilities():
    all_facilities = ParkingFacility.query.order_by(ParkingFacility.name).all()
    return render_template(
        "facilities.html",
        facilities=all_facilities,
        user=current_user(),
        statuses=FACILITY_STATUSES,
        csrf_token=csrf_token(),
    )


@facilities.route("/facilities", methods=["POST"])
@roles_required("admin")
def create_facility():
    require_csrf()
    values = _facility_values()
    errors = _validate_facility(values)
    if errors:
        _flash_errors(errors)
    else:
        db.session.add(ParkingFacility(**values))
        db.session.commit()
        flash("Facility created.", "success")
    return redirect(url_for("facilities.list_facilities"))


@facilities.route("/facilities/<int:facility_id>")
@login_required
def facility_detail(facility_id):
    facility = db.get_or_404(ParkingFacility, facility_id)
    user = current_user()
    floors = (
        ParkingFloor.query.filter_by(facility_id=facility_id)
        .order_by(ParkingFloor.floor_number)
        .all()
    )
    return render_template(
        "facility_detail.html",
        facility=facility,
        floors=floors,
        user=user,
        can_manage=_can_manage(user, facility_id),
        statuses=FACILITY_STATUSES,
        slot_types=SLOT_TYPES,
        slot_statuses=SLOT_STATUSES,
        csrf_token=csrf_token(),
    )


@facilities.route("/facilities/<int:facility_id>/edit", methods=["POST"])
@login_required
def update_facility(facility_id):
    require_csrf()
    _require_manage(facility_id)
    facility = db.get_or_404(ParkingFacility, facility_id)
    values = _facility_values()
    errors = _validate_facility(values)
    if errors:
        _flash_errors(errors)
    else:
        for field, value in values.items():
            setattr(facility, field, value)
        db.session.commit()
        flash("Facility updated.", "success")
    return redirect(url_for("facilities.facility_detail", facility_id=facility_id))


# ---------- Floors ----------

@facilities.route("/facilities/<int:facility_id>/floors", methods=["POST"])
@login_required
def create_floor(facility_id):
    require_csrf()
    _require_manage(facility_id)
    floor_number = _parse_int(request.form.get("floor_number", ""))
    name = request.form.get("name", "").strip()

    errors = []
    if floor_number is None or not -10 <= floor_number <= 100:
        errors.append("Floor number must be a whole number from -10 to 100.")
    if len(name) > 50:
        errors.append("Floor name must be 50 characters or fewer.")
    if not errors and ParkingFloor.query.filter_by(
        facility_id=facility_id, floor_number=floor_number
    ).first():
        errors.append("That floor number already exists in this facility.")

    if errors:
        _flash_errors(errors)
    else:
        db.session.add(
            ParkingFloor(
                facility_id=facility_id,
                floor_number=floor_number,
                name=name or None,
            )
        )
        db.session.commit()
        flash("Floor added.", "success")
    return redirect(url_for("facilities.facility_detail", facility_id=facility_id))


# ---------- Slots ----------

def _slot_values(floor_id):
    values = {
        "floor_id": floor_id,
        "slot_number": request.form.get("slot_number", "").strip(),
        "slot_type": request.form.get("slot_type", "standard"),
        "is_ev_charging": "is_ev_charging" in request.form,
        "is_accessible": "is_accessible" in request.form,
        "map_x": _parse_float(request.form.get("map_x", "0")),
        "map_y": _parse_float(request.form.get("map_y", "0")),
        "operational_status": request.form.get("operational_status", "active"),
    }
    return values, _validate_slot(values)


def _validate_slot(values):
    errors = []
    if not values["slot_number"] or len(values["slot_number"]) > 20:
        errors.append("Slot number is required (max 20 characters).")
    if values["slot_type"] not in SLOT_TYPES:
        errors.append("Choose a valid slot type.")
    if values["operational_status"] not in SLOT_STATUSES:
        errors.append("Choose a valid slot status.")
    coords = (values["map_x"], values["map_y"])
    if any(c is None or not 0 <= c <= 10000 for c in coords):
        errors.append("Map coordinates must be numbers between 0 and 10000.")
    return errors


@facilities.route(
    "/facilities/<int:facility_id>/floors/<int:floor_id>/slots", methods=["POST"]
)
@login_required
def create_slot(facility_id, floor_id):
    require_csrf()
    _require_manage(facility_id)
    _floor_in_facility(facility_id, floor_id)
    values, errors = _slot_values(floor_id)

    if not errors and ParkingSlot.query.filter_by(
        floor_id=floor_id, slot_number=values["slot_number"]
    ).first():
        errors.append("That slot number already exists on this floor.")

    if errors:
        _flash_errors(errors)
    else:
        db.session.add(ParkingSlot(**values))
        db.session.commit()
        flash("Slot added.", "success")
    return redirect(url_for("facilities.facility_detail", facility_id=facility_id))


@facilities.route(
    "/facilities/<int:facility_id>/slots/<int:slot_id>/status", methods=["POST"]
)
@login_required
def update_slot_status(facility_id, slot_id):
    require_csrf()
    _require_manage(facility_id)
    slot = db.session.get(ParkingSlot, slot_id)
    if slot is None or slot.floor.facility_id != facility_id:
        abort(404)

    status = request.form.get("operational_status", "")
    if status not in SLOT_STATUSES:
        flash("Choose a valid slot status.", "error")
    else:
        slot.operational_status = status
        db.session.commit()
        flash("Slot status updated.", "success")
    return redirect(url_for("facilities.facility_detail", facility_id=facility_id))


# ---------- Admin: assign roles ----------

@facilities.route("/admin/users")
@roles_required("admin")
def manage_users():
    users = User.query.order_by(User.email).all()
    all_facilities = ParkingFacility.query.order_by(ParkingFacility.name).all()
    return render_template(
        "admin_users.html",
        users=users,
        facilities=all_facilities,
        user=current_user(),
        csrf_token=csrf_token(),
    )


@facilities.route("/admin/users/<int:user_id>", methods=["POST"])
@roles_required("admin")
def assign_user_role(user_id):
    require_csrf()
    target = db.get_or_404(User, user_id)
    actor = current_user()

    if target.user_id == actor.user_id:
        flash("You cannot change your own role here.", "error")
    elif target.role == "admin":
        flash("System admin accounts cannot be changed here.", "error")
    else:
        role = request.form.get("role", "")
        facility_id = _parse_int(request.form.get("facility_id", ""))

        if role == "user":
            target.role = "user"
            target.facility_id = None
        elif (
            role == "parking_admin"
            and facility_id is not None
            and db.session.get(ParkingFacility, facility_id) is not None
        ):
            target.role = "parking_admin"
            target.facility_id = facility_id
        else:
            flash("Choose a role. A parking administrator needs a facility.", "error")
            return redirect(url_for("facilities.manage_users"))

        db.session.commit()
        flash("User updated.", "success")
    return redirect(url_for("facilities.manage_users"))


# ---------- Parking map ----------

MAP_STATES = (STATE_AVAILABLE, STATE_OCCUPIED, STATE_RESERVED, STATE_UNAVAILABLE)


@facilities.route("/facilities/<int:facility_id>/map")
@login_required
def facility_map(facility_id):
    facility = db.get_or_404(ParkingFacility, facility_id)
    only_ev = request.args.get("ev") == "1"
    only_accessible = request.args.get("accessible") == "1"
    only_state = request.args.get("state", "")
    if only_state not in MAP_STATES:
        only_state = ""

    floors = (
        ParkingFloor.query.filter_by(facility_id=facility_id)
        .order_by(ParkingFloor.floor_number)
        .all()
    )
    all_slots = [slot for floor in floors for slot in floor.slots]
    states = slot_states(all_slots)

    floor_views = []
    for floor in floors:
        shown = []
        for slot in sorted(floor.slots, key=lambda s: s.slot_number):
            state = states[slot.slot_id]
            if only_ev and not slot.is_ev_charging:
                continue
            if only_accessible and not slot.is_accessible:
                continue
            if only_state and state != only_state:
                continue
            shown.append({
                "slot": slot,
                "state": state,
                # Stored coordinates run 0-10000; convert to percent of the box.
                "left": round(slot.map_x / 100, 2),
                "top": round(slot.map_y / 100, 2),
            })
        floor_views.append({"floor": floor, "slots": shown})

    counts = Counter(states.values())
    return render_template(
        "facility_map.html",
        facility=facility,
        floor_views=floor_views,
        counts={state: counts.get(state, 0) for state in MAP_STATES},
        only_ev=only_ev,
        only_accessible=only_accessible,
        only_state=only_state,
        map_states=MAP_STATES,
        user=current_user(),
    )
