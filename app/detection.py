"""Occupancy detection interface.

Any source (a camera pipeline, a sensor, or the simulated feed below) produces
observations as (slot_id, occupied) pairs and passes them to
record_observations(). That function is the only place detection writes to the
database, and it writes an event only when a slot's state actually changes.

Detections identify slots, not vehicles, so the events it writes have no
vehicle or parking session attached.
"""
from datetime import datetime

from app import db
from app.models import OccupancyEvent

EVENT_OCCUPIED = "occupied"
EVENT_VACATED = "vacated"
FEED_OCCUPIED = "occupied"
FEED_VACANT = "vacant"


def latest_event_type(slot_id):
    row = (
        OccupancyEvent.query.filter_by(parking_slot_id=slot_id)
        .order_by(OccupancyEvent.event_time.desc(), OccupancyEvent.event_id.desc())
        .first()
    )
    return row.event_type if row else None


def record_observations(observations, now=None):
    """Write one event per slot whose state changed. Returns the number written."""
    now = now or datetime.now()
    written = 0
    for slot_id, occupied in observations:
        event_type = EVENT_OCCUPIED if occupied else EVENT_VACATED
        if latest_event_type(slot_id) == event_type:
            continue
        db.session.add(OccupancyEvent(
            parking_slot_id=slot_id,
            vehicle_id=None,
            parking_session_id=None,
            event_time=now,
            event_type=event_type,
        ))
        written += 1
    db.session.commit()
    return written


def parse_feed(text, slot_ids_by_number):
    """Parse simulated feed lines such as 'A1 occupied' or 'A2 vacant'.

    slot_ids_by_number maps slot number to slot id, or to None when the number
    is used on more than one floor (then it cannot be used unambiguously).
    Returns (observations, problems).
    """
    observations, problems = [], []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2 or parts[1].lower() not in (FEED_OCCUPIED, FEED_VACANT):
            problems.append(f"Line {line_no}: write 'SLOT occupied' or 'SLOT vacant'.")
            continue
        number, state = parts[0], parts[1].lower()
        if number not in slot_ids_by_number:
            problems.append(f"Line {line_no}: no slot called {number} in this facility.")
            continue
        slot_id = slot_ids_by_number[number]
        if slot_id is None:
            problems.append(f"Line {line_no}: {number} exists on more than one floor.")
            continue
        observations.append((slot_id, state == FEED_OCCUPIED))
    return observations, problems
