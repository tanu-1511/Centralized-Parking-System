"""Camera-based occupancy: decide each slot's state from a video.

Each slot has a rectangle (ROI) in the video frame. A slot counts as occupied
when enough pixels inside its rectangle differ from an empty-lot reference
image. A Debouncer requires the new state to hold for several frames before it
is reported, so a shadow or a passing pedestrian does not create events.

This works for a fixed camera and good lighting. It is not a vehicle detector:
it compares pixels against the empty reference.
"""
import json

import cv2
import numpy as np


def load_rois(path):
    """Read {"A1": [x, y, width, height], ...} from a JSON file."""
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    rois = {}
    for number, box in raw.items():
        x, y, width, height = (int(value) for value in box)
        if width <= 0 or height <= 0:
            raise ValueError(f"The box for {number} needs a positive width and height.")
        rois[number] = (x, y, width, height)
    return rois


def load_gray(path):
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Could not read the reference image: {path}")
    return cv2.GaussianBlur(image, (5, 5), 0)


def slot_occupancy(frame_gray, reference_gray, rois, pixel_threshold=40, changed_fraction=0.25):
    """Return {slot_number: occupied} for one frame."""
    if frame_gray.shape != reference_gray.shape:
        raise ValueError("The video frame and the reference image have different sizes.")
    difference = cv2.absdiff(frame_gray, reference_gray)
    result = {}
    for number, (x, y, width, height) in rois.items():
        region = difference[y:y + height, x:x + width]
        if region.size == 0:
            raise ValueError(f"The box for {number} lies outside the video frame.")
        changed = np.count_nonzero(region > pixel_threshold) / region.size
        result[number] = bool(changed >= changed_fraction)
    return result


class Debouncer:
    """Report a slot's state only after it has held for `required_frames` frames.

    Every slot starts as vacant, so an empty lot produces no events.
    """

    def __init__(self, required_frames=5):
        self.required_frames = required_frames
        self.confirmed = {}
        self.candidate = {}

    def update(self, observations):
        """Take {slot_number: occupied} for one frame; return the confirmed changes."""
        changes = {}
        for number, occupied in observations.items():
            if occupied == self.confirmed.get(number, False):
                self.candidate.pop(number, None)
                continue
            candidate_state, count = self.candidate.get(number, (occupied, 0))
            count = count + 1 if candidate_state == occupied else 1
            if count >= self.required_frames:
                self.confirmed[number] = occupied
                changes[number] = occupied
                self.candidate.pop(number, None)
            else:
                self.candidate[number] = (occupied, count)
        return changes


def iterate_video(video_path, reference_path, rois, sample_every=5, **thresholds):
    """Yield (seconds_into_video, {slot_number: occupied}) for sampled frames."""
    reference = load_gray(reference_path)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open the video: {video_path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index % sample_every == 0:
                gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0)
                yield index / fps, slot_occupancy(gray, reference, rois, **thresholds)
            index += 1
    finally:
        capture.release()
