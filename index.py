"""Vercel entry point. Vercel's Flask setup runs the app defined here.

Vercel's filesystem is read-only except /tmp, so the database lives there
unless DATABASE_URL is set in the Vercel project settings.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/parking.db")

from app import create_app  # noqa: E402

app = create_app()
