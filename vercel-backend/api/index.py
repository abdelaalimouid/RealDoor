"""Vercel Python entry point — exposes the FastAPI ASGI app.

Vercel routes every request to this function (see vercel.json) and the FastAPI app
matches on the original path (e.g. /api/meta).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_server import app  # noqa: E402  (FastAPI ASGI application)
