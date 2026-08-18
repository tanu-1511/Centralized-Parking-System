from app import db


class ParkingFacility(db.Model):
    __tablename__ = "parking_facilities"

    facility_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")

    floors = db.relationship(
        "ParkingFloor",
        back_populates="facility"
    )

    parking_admins = db.relationship(
        "User",
        back_populates="facility"
    )