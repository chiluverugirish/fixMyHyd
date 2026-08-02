"""
FixMyHyd package initialization.
"""

__version__ = "1.0.0"

from .database import init_db, close_db, get_db_session
from .models import User, Admin, Complaint, StatusHistory
from .schemas import (
    ComplaintCreate, ComplaintResponse, ComplaintListResponse,
    UserCreate, UserResponse, UserLogin
)
from .services import UserService, ComplaintService, LocationService
from .constants import COMPLAINT_CATEGORIES

__all__ = [
    "init_db",
    "close_db", 
    "get_db_session",
    "User",
    "Admin",
    "Complaint",
    "StatusHistory",
    "ComplaintCreate",
    "ComplaintResponse",
    "ComplaintListResponse",
    "UserCreate",
    "UserResponse",
    "UserLogin",
    "UserService",
    "ComplaintService",
    "LocationService",
    "COMPLAINT_CATEGORIES"
]
