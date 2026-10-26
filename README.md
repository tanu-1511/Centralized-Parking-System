# Centralized Parking Management System

One platform for finding, reserving, and managing parking across several facilities. Drivers book slots, track their cars, and review history. Facility managers record entries and exits, watch live slot states, and read usage analytics. A camera script can feed occupancy into the system from a video.

Built with Flask, SQLite, and SQLAlchemy. Optional camera support uses OpenCV.


---

## Features

**Drivers**
- Sign up, log in, and log out
- Register vehicles (car, motorcycle, van) with a model name
- Book a slot for a chosen time window, using a seat map like a cinema
- View and cancel your reservations
- See your parking history and most-used spots
- Find where each of your vehicles is parked, or where it was last left

**Facility managers (parking admins)**
- Record vehicle entries and exits by hand
- Live map of every floor, coloured and patterned by slot state
- Analytics: slot usage per floor, average parking time, peak hours, reservation counts
- Occupancy feed: type detections by hand, or let the camera script record them

**System admins**
- Create facilities, floors, and slots
- Set each slot's status (active, maintenance, inactive)
- Assign users as parking admins for one facility

---

## Quick start (Windows, PowerShell)

Requires Python 3.11 or newer.

```powershell
git clone https://github.com/tanu-1511/centralized-parking-system.git
cd centralized-parking-system

python -m venv venv
venv\Scripts\Activate.ps1

pip install -r requirements-dev.txt
copy .env.example .env
```

Open `.env` and set `SECRET_KEY` to a long random string. Then run the app:

```powershell
python run.py
```

Open http://127.0.0.1:5000 in your browser.

The database is created automatically at `instance/parking.db` the first time the app starts. Nothing needs to be installed separately.

### Load demo data

```powershell
python -m app.seed
```

This adds a demo facility (Demo Mall) with two floors, twelve slots, two vehicles, a parked car, and an upcoming booking. Three accounts are created, all with the password `demo-password-123`:

| Email | Role |
|---|---|
| `admin@example.com` | System admin |
| `lot.manager@example.com` | Parking admin for Demo Mall |
| `driver@example.com` | Driver |

Running the command again adds no duplicate data, but it resets those three passwords to the demo password. Use these accounts for local testing only.

---

## Running the tests

```powershell
pytest -v
```

Tests use a throwaway SQLite database in a temporary folder, so your `instance/parking.db` is never touched.

---

## Using the app

### Roles

| Role | What it can do |
|---|---|
| `user` | Drivers: vehicles, bookings, history, vehicle locator |
| `parking_admin` | Everything `user` can do, plus the live map, entries and exits, analytics, and the occupancy feed for one assigned facility |
| `admin` | Everything, plus creating facilities and managing floors, slots, and roles. Created by the seed script or directly in the database |

### Booking a slot

1. Register a vehicle under **Vehicles**.
2. Open **Book**, choose a facility, reservation type, and start and end times.
3. Pick a free seat on the seat map, choose your vehicle, and press **Book selected seat**.

Seat states:

| Seat | Meaning |
|---|---|
| Outlined | Free for your time window |
| Striped | Taken, overlaps another booking |
| Dashed | Unavailable (maintenance or inactive, or not suitable for the chosen type) |

Booking rules:
- Duration between 30 minutes and 12 hours
- Start time must be in the future
- Only your own vehicles
- EV reservations need an EV slot, and accessible reservations need an accessible slot
- Back-to-back bookings are allowed; overlapping ones are not
- Only confirmed bookings can be cancelled

**Expiry:** a booking expires 15 minutes after its start unless the car has entered that slot in that window. Expired bookings free the slot. Expiry is checked whenever the booking page or your reservations page loads.

### Live map and entries

Parking admins open a facility, then **Live map** to see every slot. **Entries and exits** lets them record a vehicle arriving or leaving. A slot is shown as occupied while a parking session is open on it, and as reserved while a confirmed booking covers the current time.

Slot priority: unavailable > occupied > reserved > available.

### Analytics

**Analytics** shows, for one facility:
- Current counts by state, and usage per floor (occupied plus reserved, as a share of all slots)
- Average parking duration from completed sessions
- Peak entry hours
- Reservation counts by status

### Occupancy feed

**Occupancy feed** shows the latest detected state of each slot and a log of changes. It refreshes every 5 seconds without losing text you've typed. You can record detections by hand:

```
A1 occupied
A2 vacant
```

Only changes are logged. Repeating the same state adds no new event.

---

## Camera occupancy (optional)

The camera script reads a video of a parking lot and records changes in slot state. It works with a fixed camera and steady lighting. It detects a change in pixels against a photo of the empty lot. It does not recognise vehicles.

### 1. Install the camera packages

```powershell
pip install -r requirements-camera.txt
```

### 2. Prepare three files in the project folder

- **Demo video**, for example `demo.mp4`
- **Reference photo** of the empty lot, `empty_lot.png`, the same width and height as the video
- **Slot boxes**, `rois.json`, one rectangle per slot in video pixels as `[x, y, width, height]`:

```json
{
    "A1": [40, 120, 140, 260],
    "A2": [200, 120, 140, 260],
    "A3": [360, 120, 140, 260]
}
```

`rois.example.json` shows the format. The slot names must match slot numbers in the facility.

### 3. Run it

```powershell
python -m app.vision_cli --facility-id 1 --video demo.mp4 --reference empty_lot.png --config rois.json
```

Open the facility's **Occupancy feed** page to watch the states change as the video plays. Events are timestamped from the video's own clock.

Tuning options:
- `--required-frames 5` (default): a change must hold this many sampled frames before it is recorded. Raise it if slots flicker.
- `--sample-every 5` (default): check every fifth frame. Lower it for more detail; raise it for speed.

Pixel thresholds are set in `app/vision.py`: a pixel counts as changed when it differs by more than 40, and a slot is occupied when at least 25% of its box has changed.

---

## Project layout

```
run.py                  Starts the development server
app/
  __init__.py           App factory, blueprints, database setup
  models/               Database tables (users, vehicles, facilities, floors, slots,
                        reservations, parking sessions, occupancy events)
  routes/               Pages and form handlers, one file per feature
  services.py           Slot states, booking conflicts, expiry rules
  analytics.py          Figures for the analytics page
  detection.py          Occupancy events and feed parsing
  vision.py             Camera analysis (OpenCV)
  vision_cli.py         Command line tool for the camera script
  seed.py               Demo data loader
  security.py           Login checks, roles, CSRF tokens
  templates/            HTML pages (all extend base.html)
  static/               style.css (black and white themes), app.js (live updates, search, sorting)
tests/                  Automated tests
instance/               Local database (not tracked by git)
```

## Configuration

Set these in `.env` (never commit it):

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs login sessions | A random key per run (sessions reset on restart) |
| `DATABASE_URL` | Database location | `sqlite:///parking.db` in the `instance/` folder |

## Themes

Use the **Black / white** button in the top bar to switch between black-on-white and white-on-black. The app follows your system setting until you choose one. The choice is saved in your browser only.

## Known limitations

- Expiry, live refresh, and camera results are checked when pages load or the camera script runs. There is no background scheduler.
- Bookings cannot be edited. Cancel and book again.
- Facilities, floors, slots, and vehicles cannot be deleted yet.
- Two people booking the same seat at the exact same moment is possible on SQLite. Normal use is not affected.
- The camera method needs a fixed camera and steady lighting. Shadows or light changes can count as occupied.
- The app is for local use. It has no production hosting setup yet.

## Troubleshooting

- **`ModuleNotFoundError: No module named 'cv2'`** when running tests: install the camera packages with `pip install -r requirements-camera.txt`.
- **`No module named 'app'`** when running `pytest`: run it from the project folder with the venv active. `pytest.ini` already sets the path.
- **Demo login says "Invalid email or password"**: run `python -m app.seed` again to reset the demo passwords.
- **The page shows old content**: refresh the browser. Some pages update automatically every few seconds.
