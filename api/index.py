"""Vercel entry point. Vercel runs the Flask app defined here."""
import os
import sys

# Vercel's filesystem is read-only except /tmp, so the database lives there
# unless DATABASE_URL is set in the Vercel project settings.
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/parking.db")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app  # noqa: E402

app = create_app()
