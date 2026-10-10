from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app import db
from app.detection import parse_feed, record_observations
from app.models import OccupancyEvent, ParkingFacility, ParkingSlot
from app.security import csrf_token, current_user, login_required, require_csrf
from app.services import can_manage_facility

detection = Blueprint("detection", __name__)


def _authorize(facility_id):
    db.get_or_404(ParkingFacility, facility_id)
    user = current_user()
    if not can_manage_facility(user, facility_id):
        abort(403)
    return user


def _facility_slots(facility):
    return [slot for floor in facility.floors for slot in floor.slots]


def _slot_lookup(slots):
    counts = {}
    lookup = {}
    for slot in slots:
        counts[slot.slot_number] = counts.get(slot.slot_number, 0) + 1
        lookup[slot.slot_number] = slot.slot_id
    return {
        number: (lookup[number] if counts[number] == 1 else None)
        for number in counts
    }


@detection.route("/facilities/<int:facility_id>/detections")
@login_required
def detection_page(facility_id):
    facility = db.get_or_404(ParkingFacility, facility_id)
    user = _authorize(facility_id)
    slot_ids = [slot.slot_id for slot in _facility_slots(facility)]
    events = (
        OccupancyEvent.query.filter(OccupancyEvent.parking_slot_id.in_(slot_ids))
        .order_by(OccupancyEvent.event_time.desc(), OccupancyEvent.event_id.desc())
        .limit(50)
        .all()
        if slot_ids else []
    )
    return render_template(
        "detection.html",
        facility=facility,
        events=events,
        user=user,
        csrf_token=csrf_token(),
    )


@detection.route("/facilities/<int:facility_id>/detections", methods=["POST"])
@login_required
def submit_feed(facility_id):
    require_csrf()
    facility = db.get_or_404(ParkingFacility, facility_id)
    _authorize(facility_id)
    lookup = _slot_lookup(_facility_slots(facility))
    observations, problems = parse_feed(request.form.get("feed", ""), lookup)

    for message in problems:
        flash(message, "error")
    if observations:
        written = record_observations(observations)
        flash(f"Feed recorded: {len(observations)} observations, {written} changes saved.", "success")
    elif not problems:
        flash("The feed was empty.", "error")
    return redirect(url_for("detection.detection_page", facility_id=facility_id))
