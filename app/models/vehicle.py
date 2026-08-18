from app import db


class Vehicle(db.Model):
    __tablename__ = "vehicles"

    vehicle_id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False
    )

    vehicle_number = db.Column(
        db.String(20),
        unique=True,
        nullable=False
    )

    vehicle_type = db.Column(db.String(30), nullable=False)
    vehicle_model = db.Column(db.String(50), nullable=True)

    user = db.relationship(
        "User",
        back_populates="vehicles"
    )

    reservations = db.relationship(
        "Reservation",
        back_populates="vehicle"
    )

    parking_sessions = db.relationship(
        "ParkingSession",
        back_populates="vehicle"
    )

    occupancy_events = db.relationship(
        "OccupancyEvent",
        back_populates="vehicle"
    )