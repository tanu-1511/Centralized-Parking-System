from app import db


class ParkingFloor(db.Model):
    __tablename__ = "parking_floors"

    floor_id = db.Column(db.Integer, primary_key=True)

    facility_id = db.Column(
        db.Integer,
        db.ForeignKey("parking_facilities.facility_id"),
        nullable=False
    )

    floor_number = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(50), nullable=True)

    facility = db.relationship(
        "ParkingFacility",
        back_populates="floors"
    )

    slots = db.relationship(
        "ParkingSlot",
        back_populates="floor"
    )