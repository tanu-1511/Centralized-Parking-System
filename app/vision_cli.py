"""Run camera occupancy on a video and record the changes.

Example (PowerShell, from the project folder, venv active):

    python -m app.vision_cli --facility-id 1 --video demo.mp4 \
        --reference empty_lot.png --config rois.json

Each confirmed change becomes an occupancy event, timestamped from the
video's own clock, so the feed page shows the demo as it played.
"""
import argparse
from datetime import datetime, timedelta

from app import create_app, db
from app.detection import record_observations
from app.models import ParkingFacility
from app.vision import Debouncer, iterate_video, load_rois


def run_feed(app, video, reference, config, facility_id, sample_every=5,
             required_frames=5, start_time=None):
    """Process the video and return the number of occupancy events written."""
    rois = load_rois(config)
    start = start_time or datetime.now()
    with app.app_context():
        facility = db.session.get(ParkingFacility, facility_id)
        if facility is None:
            raise ValueError(f"No facility with id {facility_id}.")
        slots = [slot for floor in facility.floors for slot in floor.slots]
        ids = {}
        for slot in slots:
            if slot.slot_number in ids:
                raise ValueError(f"Slot number {slot.slot_number} is used on more than one floor.")
            ids[slot.slot_number] = slot.slot_id
        missing = sorted(set(rois) - set(ids))
        if missing:
            raise ValueError(f"The config names slots not in this facility: {', '.join(missing)}")

        debouncer = Debouncer(required_frames=required_frames)
        written = 0
        for seconds, observed in iterate_video(video, reference, rois, sample_every=sample_every):
            changes = debouncer.update(observed)
            if changes:
                moment = start + timedelta(seconds=seconds)
                written += record_observations(
                    [(ids[number], occupied) for number, occupied in changes.items()],
                    now=moment,
                )
        return written


def main():
    parser = argparse.ArgumentParser(description="Record occupancy changes from a video.")
    parser.add_argument("--facility-id", type=int, required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--reference", required=True, help="Photo of the empty lot, same size as the video.")
    parser.add_argument("--config", required=True, help="JSON file mapping slot numbers to [x, y, w, h].")
    parser.add_argument("--sample-every", type=int, default=5, help="Check every Nth frame.")
    parser.add_argument("--required-frames", type=int, default=5,
                        help="Sampled frames a change must hold before it is recorded.")
    args = parser.parse_args()

    app = create_app()
    written = run_feed(app, args.video, args.reference, args.config, args.facility_id,
                       sample_every=args.sample_every, required_frames=args.required_frames)
    print(f"Done. Occupancy events written: {written}")


if __name__ == "__main__":
    main()
