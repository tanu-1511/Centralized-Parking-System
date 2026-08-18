from app import db


class OccupancyEvent(db.Model):
    __tablename__ = "occupancy_events"

    event_id = db.Column(db.Integer, primary_key=True)

    parking_slot_id = db.Column(
        db.Integer,
        db.ForeignKey("parking_slots.slot_id"),
        nullable=False
    )

    vehicle_id = db.Column(
        db.Integer,
        db.ForeignKey("vehicles.vehicle_id"),
        nullable=True
    )

    parking_session_id = db.Column(
        db.Integer,
        db.ForeignKey("parking_sessions.session_id"),
        nullable=True
    )

    event_time = db.Column(db.DateTime, nullable=False)

    event_type = db.Column(
        db.String(30),
        nullable=False
    )

    slot = db.relationship(
        "ParkingSlot",
        back_populates="occupancy_events"
    )

    vehicle = db.relationship(
        "Vehicle",
        back_populates="occupancy_events"
    )

    parking_session = db.relationship(
        "ParkingSession",
        back_populates="occupancy_events"
    )