from app import db


class ParkingSession(db.Model):
    __tablename__ = "parking_sessions"

    session_id = db.Column(db.Integer, primary_key=True)

    vehicle_id = db.Column(
        db.Integer,
        db.ForeignKey("vehicles.vehicle_id"),
        nullable=False
    )

    slot_id = db.Column(
        db.Integer,
        db.ForeignKey("parking_slots.slot_id"),
        nullable=False
    )

    entry_time = db.Column(db.DateTime, nullable=False)
    exit_time = db.Column(db.DateTime, nullable=True)

    status = db.Column(
        db.String(20),
        nullable=False,
        default="active"
    )

    vehicle = db.relationship(
        "Vehicle",
        back_populates="parking_sessions"
    )

    slot = db.relationship(
        "ParkingSlot",
        back_populates="parking_sessions"
    )

    occupancy_events = db.relationship(
        "OccupancyEvent",
        back_populates="parking_session"
    )