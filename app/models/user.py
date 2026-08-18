from app import db


class User(db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(15), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)

    facility_id = db.Column(
        db.Integer,
        db.ForeignKey("parking_facilities.facility_id"),
        nullable=True
    )

    vehicles = db.relationship(
        "Vehicle",
        back_populates="user"
    )

    reservations = db.relationship(
        "Reservation",
        back_populates="user"
    )

    facility = db.relationship(
        "ParkingFacility",
        back_populates="parking_admins"
    )