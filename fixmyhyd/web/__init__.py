"""
Web routes for FixMyHyd FastAPI application (HTML templates).
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from .routes import web_router

__all__ = ["web_router"]
