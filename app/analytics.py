from collections import Counter
from datetime import datetime

from app.models import ParkingSession, Reservation
from app.services import (
    STATE_AVAILABLE,
    STATE_OCCUPIED,
    STATE_RESERVED,
    STATE_UNAVAILABLE,
    slot_states,
)


def facility_analytics(facility, now=None):
    """Summary figures for one facility, computed from the database."""
    now = now or datetime.now()
    floors = sorted(facility.floors, key=lambda f: f.floor_number)
    slots = [slot for floor in floors for slot in floor.slots]
    slot_ids = [slot.slot_id for slot in slots]
    states = slot_states(slots, now)
    totals = Counter(states.values())

    sessions = (
        ParkingSession.query.filter(ParkingSession.slot_id.in_(slot_ids)).all()
        if slot_ids else []
    )
    durations = [
        (s.exit_time - s.entry_time).total_seconds() / 60
        for s in sessions if s.exit_time is not None
    ]
    entry_hours = Counter(s.entry_time.hour for s in sessions)

    reservations = (
        Reservation.query.filter(Reservation.slot_id.in_(slot_ids)).all()
        if slot_ids else []
    )

    floor_rows = []
    for floor in floors:
        floor_states = Counter(states[slot.slot_id] for slot in floor.slots)
        total = len(floor.slots)
        busy = floor_states[STATE_OCCUPIED] + floor_states[STATE_RESERVED]
        floor_rows.append({
            "floor": floor,
            "total": total,
            "available": floor_states[STATE_AVAILABLE],
            "occupied": floor_states[STATE_OCCUPIED],
            "reserved": floor_states[STATE_RESERVED],
            "unavailable": floor_states[STATE_UNAVAILABLE],
            "usage_percent": round(100 * busy / total) if total else 0,
        })

    return {
        "total_slots": len(slots),
        "available": totals[STATE_AVAILABLE],
        "occupied": totals[STATE_OCCUPIED],
        "reserved": totals[STATE_RESERVED],
        "unavailable": totals[STATE_UNAVAILABLE],
        "average_duration_minutes": round(sum(durations) / len(durations)) if durations else None,
        "completed_sessions": len(durations),
        "peak_hours": entry_hours.most_common(3),
        "reservation_counts": Counter(r.status for r in reservations),
        "floors": floor_rows,
    }
