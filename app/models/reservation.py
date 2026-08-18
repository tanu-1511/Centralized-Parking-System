from app import db


class Reservation(db.Model):
    __tablename__ = "reservations"

    reservation_id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False
    )

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

    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)

    reservation_type = db.Column(
        db.String(20),
        nullable=False
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending"
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now()
    )

    user = db.relationship(
        "User",
        back_populates="reservations"
    )

    vehicle = db.relationship(
        "Vehicle",
        back_populates="reservations"
    )

    slot = db.relationship(
        "ParkingSlot",
        back_populates="reservations"
    )