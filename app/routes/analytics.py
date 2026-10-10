from flask import Blueprint, abort, render_template

from app import db
from app.analytics import facility_analytics
from app.models import ParkingFacility
from app.security import current_user, login_required
from app.services import can_manage_facility

analytics = Blueprint("analytics", __name__)


@analytics.route("/facilities/<int:facility_id>/analytics")
@login_required
def facility_dashboard(facility_id):
    facility = db.get_or_404(ParkingFacility, facility_id)
    user = current_user()
    if not can_manage_facility(user, facility_id):
        abort(403)
    return render_template(
        "analytics.html",
        facility=facility,
        stats=facility_analytics(facility),
        user=user,
    )
