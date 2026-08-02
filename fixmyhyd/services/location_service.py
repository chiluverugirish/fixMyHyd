"""
Location service for handling location-related operations.
"""

from typing import Optional, Dict, Any
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderUnavailable
from sqlalchemy.orm import Session
import logging

from config import settings

logger = logging.getLogger(__name__)


class LocationService:
    """Service for location operations."""
    
    def __init__(self, db: Session):
        self.db = db
        self._geocoder = None
    
    @property
    def geocoder(self):
        if self._geocoder is None:
            self._geocoder = Nominatim(user_agent="fixmyhyd", timeout=settings.GEOCODE_TIMEOUT)
        return self._geocoder
    
    async def process_location(
        self,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        location_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process location from GPS coordinates or text address."""
        location_data = {
            "location": None,
            "zone": None,
            "gps_lat": lat,
            "gps_lng": lng
        }
        
        # If GPS coordinates provided, reverse geocode
        if lat and lng:
            try:
                location = self.geocoder.reverse((lat, lng), exactly_one=True)
                if location:
                    location_data["location"] = location.address
                    location_data["zone"] = self._extract_zone(location.address)
            except (GeocoderUnavailable, Exception) as e:
                logger.warning(f"Reverse geocoding failed: {e}")
        
        # If text address provided, geocode it
        elif location_text:
            try:
                location = self.geocoder.geocode(location_text, exactly_one=True)
                if location:
                    location_data["location"] = location.address
                    location_data["gps_lat"] = location.latitude
                    location_data["gps_lng"] = location.longitude
                    location_data["zone"] = self._extract_zone(location.address)
                else:
                    location_data["location"] = location_text
            except (GeocoderUnavailable, Exception) as e:
                logger.warning(f"Geocoding failed: {e}")
                location_data["location"] = location_text
        
        return location_data
    
    def _extract_zone(self, address: str) -> Optional[str]:
        """Extract Hyderabad zone from address."""
        # Hyderabad zones (simplified)
        zones = [
            "Charminar", "Khairatabad", "Secunderabad", "Lal Bahadur Nagar",
            "Serilingampally", "Kukatpally", "Gachibowli", "Madhapur",
            "Banjara Hills", "Jubilee Hills", "Old City", "New City"
        ]
        
        address_lower = address.lower()
        for zone in zones:
            if zone.lower() in address_lower:
                return zone
        
        return "Unknown"
    
    def validate_coordinates(self, lat: float, lng: float) -> bool:
        """Validate GPS coordinates are within Hyderabad bounds."""
        # Approximate Hyderabad bounds
        HYDERABAD_BOUNDS = {
            "min_lat": 17.2,
            "max_lat": 17.6,
            "min_lng": 78.2,
            "max_lng": 78.6
        }
        
        return (
            HYDERABAD_BOUNDS["min_lat"] <= lat <= HYDERABAD_BOUNDS["max_lat"] and
            HYDERABAD_BOUNDS["min_lng"] <= lng <= HYDERABAD_BOUNDS["max_lng"]
        )
