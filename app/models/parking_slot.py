from app import db


class ParkingSlot(db.Model):
    __tablename__ = "parking_slots"

    slot_id = db.Column(db.Integer, primary_key=True)

    floor_id = db.Column(
        db.Integer,
        db.ForeignKey("parking_floors.floor_id"),
        nullable=False
    )

    slot_number = db.Column(db.String(20), nullable=False)
    slot_type = db.Column(db.String(30), nullable=False)

    is_ev_charging = db.Column(db.Boolean, nullable=False, default=False)
    is_accessible = db.Column(db.Boolean, nullable=False, default=False)

    map_x = db.Column(db.Float, nullable=False)
    map_y = db.Column(db.Float, nullable=False)

    operational_status = db.Column(
        db.String(20),
        nullable=False,
        default="active"
    )

    floor = db.relationship(
        "ParkingFloor",
        back_populates="slots"
    )