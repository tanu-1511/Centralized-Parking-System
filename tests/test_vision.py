import json
from datetime import datetime, timedelta

import cv2
import numpy as np
import pytest

from app import db
from app.models import OccupancyEvent, ParkingFacility, ParkingFloor, ParkingSlot
from app.vision import Debouncer, iterate_video, load_rois, slot_occupancy
from app.vision_cli import run_feed

START = datetime(2026, 10, 10, 9, 0)
FPS = 10
WIDTH, HEIGHT = 200, 300
ROIS = {"A1": (10, 10, 50, 80), "A2": (100, 10, 50, 80)}


def empty_frame():
    return np.full((HEIGHT, WIDTH, 3), 120, dtype=np.uint8)


def frame_with_car(number, coverage=1.0):
    """Paint a bright 'car' over the given share of a slot's box (in BGR)."""
    frame = empty_frame()
    x, y, width, height = ROIS[number]
    painted_height = max(1, int(height * coverage))
    frame[y:y + painted_height, x:x + width] = 255
    return frame


@pytest.fixture
def reference_path(tmp_path):
    path = tmp_path / "empty_lot.png"
    cv2.imwrite(str(path), empty_frame())
    return path


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "rois.json"
    path.write_text(json.dumps({number: list(box) for number, box in ROIS.items()}), encoding="utf-8")
    return path


def write_video(path, frames):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (WIDTH, HEIGHT))
    assert writer.isOpened(), "OpenCV could not open a video writer for the test"
    for frame in frames:
        writer.write(frame)
    writer.release()
    return path


def gray_of(frame):
    return cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0)


def reference_gray():
    return gray_of(empty_frame())


# --- load_rois -------------------------------------------------------------

def test_load_rois_reads_boxes(config_path):
    assert load_rois(config_path) == ROIS


def test_load_rois_rejects_empty_box(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"A1": [10, 10, 0, 50]}), encoding="utf-8")
    with pytest.raises(ValueError, match="positive width and height"):
        load_rois(path)


# --- slot_occupancy --------------------------------------------------------

def test_empty_frame_reports_every_slot_vacant():
    result = slot_occupancy(gray_of(empty_frame()), reference_gray(), ROIS)
    assert result == {"A1": False, "A2": False}


def test_car_in_one_slot_marks_only_that_slot_occupied():
    result = slot_occupancy(gray_of(frame_with_car("A1")), reference_gray(), ROIS)
    assert result == {"A1": True, "A2": False}


def test_small_change_below_quarter_of_slot_is_ignored():
    result = slot_occupancy(gray_of(frame_with_car("A1", coverage=0.10)), reference_gray(), ROIS)
    assert result["A1"] is False


def test_frame_and_reference_must_match_in_size():
    small = np.zeros((10, 10), dtype=np.uint8)
    with pytest.raises(ValueError, match="different sizes"):
        slot_occupancy(small, reference_gray(), ROIS)


def test_box_outside_frame_is_reported():
    with pytest.raises(ValueError, match="outside the video frame"):
        slot_occupancy(reference_gray(), reference_gray(), {"Z9": (500, 500, 10, 10)})


# --- Debouncer -------------------------------------------------------------

def test_debouncer_ignores_a_brief_flicker():
    debouncer = Debouncer(required_frames=3)
    assert debouncer.update({"A1": True}) == {}
    assert debouncer.update({"A1": True}) == {}
    assert debouncer.update({"A1": False}) == {}  # flicker ends, counter resets
    assert debouncer.update({"A1": True}) == {}
    assert debouncer.update({"A1": True}) == {}
    assert debouncer.update({"A1": True}) == {"A1": True}


def test_debouncer_reports_change_after_required_frames():
    debouncer = Debouncer(required_frames=3)
    assert debouncer.update({"A1": True}) == {}
    assert debouncer.update({"A1": True}) == {}
    assert debouncer.update({"A1": True}) == {"A1": True}


def test_debouncer_reports_nothing_while_state_is_steady_vacant():
    debouncer = Debouncer(required_frames=2)
    for _ in range(10):
        assert debouncer.update({"A1": False, "A2": False}) == {}


def test_debouncer_reports_vacated_after_occupied():
    debouncer = Debouncer(required_frames=2)
    debouncer.update({"A1": True})
    assert debouncer.update({"A1": True}) == {"A1": True}
    debouncer.update({"A1": False})
    assert debouncer.update({"A1": False}) == {"A1": False}


# --- iterate_video ---------------------------------------------------------

def test_iterate_video_samples_every_nth_frame_with_video_time(tmp_path, reference_path):
    video = write_video(tmp_path / "demo.avi", [empty_frame()] * 20)
    samples = list(iterate_video(video, reference_path, ROIS, sample_every=5))
    assert [round(seconds, 2) for seconds, _ in samples] == [0.0, 0.5, 1.0, 1.5]
    assert all(observed == {"A1": False, "A2": False} for _, observed in samples)


def test_iterate_video_rejects_missing_video(tmp_path, reference_path):
    with pytest.raises(ValueError, match="Could not open the video"):
        list(iterate_video(tmp_path / "missing.avi", reference_path, ROIS))


# --- run_feed (end to end) -------------------------------------------------

def build_facility(app, numbers=("A1", "A2")):
    with app.app_context():
        facility = ParkingFacility(name="Camera Mall", address="2 Road", city="Pune", status="active")
        db.session.add(facility)
        db.session.flush()
        floor = ParkingFloor(facility_id=facility.facility_id, floor_number=1)
        db.session.add(floor)
        db.session.flush()
        for number in numbers:
            db.session.add(ParkingSlot(
                floor_id=floor.floor_id, slot_number=number, slot_type="standard",
                is_ev_charging=False, is_accessible=False, map_x=1.0, map_y=1.0,
                operational_status="active",
            ))
        db.session.commit()
        return facility.facility_id


def events_for(app, number):
    with app.app_context():
        rows = (OccupancyEvent.query.join(ParkingSlot)
                .filter(ParkingSlot.slot_number == number)
                .order_by(OccupancyEvent.event_time).all())
        return [(row.event_type, row.event_time) for row in rows]


def test_run_feed_records_car_arriving_and_leaving(app, tmp_path, reference_path, config_path):
    # 2 s empty, 3 s with a car in A1, 2 s empty again (10 fps).
    frames = ([empty_frame()] * 20) + ([frame_with_car("A1")] * 30) + ([empty_frame()] * 20)
    video = write_video(tmp_path / "demo.avi", frames)
    facility_id = build_facility(app)

    written = run_feed(app, video, reference_path, config_path, facility_id,
                       sample_every=1, required_frames=3, start_time=START)

    assert written == 2
    a1 = events_for(app, "A1")
    assert [event_type for event_type, _ in a1] == ["occupied", "vacated"]
    assert events_for(app, "A2") == []

    # Changes are confirmed on the 3rd sampled frame of each new state,
    # and timestamped from the video clock (not from the wall clock).
    occupied_at = a1[0][1]
    vacated_at = a1[1][1]
    assert abs(occupied_at - (START + timedelta(seconds=22 / FPS))) < timedelta(milliseconds=200)
    assert abs(vacated_at - (START + timedelta(seconds=52 / FPS))) < timedelta(milliseconds=200)


def test_run_feed_on_steady_empty_video_writes_nothing(app, tmp_path, reference_path, config_path):
    video = write_video(tmp_path / "empty.avi", [empty_frame()] * 30)
    facility_id = build_facility(app)
    assert run_feed(app, video, reference_path, config_path, facility_id,
                    sample_every=1, required_frames=3, start_time=START) == 0


def test_run_feed_rejects_config_naming_unknown_slot(app, tmp_path, reference_path, config_path):
    video = write_video(tmp_path / "demo.avi", [empty_frame()] * 5)
    facility_id = build_facility(app, numbers=("A1",))  # A2 is in the config but not the facility
    with pytest.raises(ValueError, match="not in this facility: A2"):
        run_feed(app, video, reference_path, config_path, facility_id)


def test_run_feed_rejects_unknown_facility(app, tmp_path, reference_path, config_path):
    video = write_video(tmp_path / "demo.avi", [empty_frame()] * 5)
    with pytest.raises(ValueError, match="No facility with id 999"):
        run_feed(app, video, reference_path, config_path, 999)
