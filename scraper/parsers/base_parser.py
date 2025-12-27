"""
Base parser class for scraping track meet results.
All parsers must inherit from this class and implement the required methods.
"""

from abc import ABC, abstractmethod
from typing import Optional
import re


class ParsedResult:
    """Data class for a single parsed result."""
    def __init__(
        self,
        event_name: str = "",
        place: Optional[int] = None,
        athlete_name: str = "",
        school: str = "",
        mark_display: str = "",
        mark: Optional[float] = None,
        wind: Optional[float] = None,
        heat: Optional[int] = None,
        lane: Optional[int] = None,
        flight: Optional[int] = None,
        notes: str = "",
        gender: Optional[str] = None,
        year: Optional[int] = None,
        relay_team: Optional[str] = None
    ):
        self.event_name = event_name
        self.place = place
        self.athlete_name = athlete_name
        self.school = school
        self.mark_display = mark_display
        self.mark = mark
        self.wind = wind
        self.heat = heat
        self.lane = lane
        self.flight = flight
        self.notes = notes
        self.gender = gender
        self.year = year
        self.relay_team = relay_team

    def to_dict(self) -> dict:
        return {
            'event_name': self.event_name,
            'place': self.place,
            'athlete_name': self.athlete_name,
            'school': self.school,
            'mark_display': self.mark_display,
            'mark': self.mark,
            'wind': self.wind,
            'heat': self.heat,
            'lane': self.lane,
            'flight': self.flight,
            'notes': self.notes,
            'gender': self.gender,
            'year': self.year,
            'relay_team': self.relay_team,
        }


class BaseParser(ABC):
    """Abstract base class for result parsers."""

    @abstractmethod
    def parse(self, file_path: str, event_config: dict) -> list[ParsedResult]:
        """
        Parse results from a file for a specific event.
        
        Args:
            file_path: Path to the file containing results
            event_config: Configuration dict with keys like:
                - canonical_event: The canonical event name
                - gender: 'boys' or 'girls'
                - level: 'varsity', 'jv', or 'open'
                - event_header: Text to find for multi-event files
                
        Returns:
            List of ParsedResult objects
        """
        pass

    @abstractmethod
    def find_event_section(self, content: str, event_header: str) -> str:
        """
        Extract the section of content for a specific event.
        
        Args:
            content: Full file content
            event_header: Text identifying the event section
            
        Returns:
            The portion of content containing just this event's results
        """
        pass

    def read_file(self, file_path: str) -> str:
        """Read and return file contents."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def parse_time_to_seconds(self, time_str: str) -> Optional[float]:
        """
        Convert a time string to seconds.
        
        Handles formats like:
        - "11.45" (seconds only)
        - "1:23.45" (minutes:seconds)
        - "1:02:34.56" (hours:minutes:seconds)
        """
        if not time_str:
            return None
        
        time_str = time_str.strip()
        
        # Remove any trailing letters (like 'a' for automatic timing)
        time_str = re.sub(r'[a-zA-Z]+$', '', time_str)
        
        try:
            parts = time_str.split(':')
            if len(parts) == 1:
                # Seconds only
                return float(parts[0])
            elif len(parts) == 2:
                # Minutes:seconds
                minutes = int(parts[0])
                seconds = float(parts[1])
                return minutes * 60 + seconds
            elif len(parts) == 3:
                # Hours:minutes:seconds
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError):
            return None
        
        return None

    def parse_distance_to_meters(self, distance_str: str) -> Optional[float]:
        """
        Convert a distance string to meters.
        
        Handles formats like:
        - "45' 6.5\"" (feet and inches)
        - "45-06.50" (feet-inches)
        - "13.87m" (meters)
        - "13.87" (assumed meters if no unit)
        """
        if not distance_str:
            return None
        
        distance_str = distance_str.strip()
        
        # Check for meters
        meters_match = re.match(r'([\d.]+)\s*m', distance_str, re.IGNORECASE)
        if meters_match:
            return float(meters_match.group(1))
        
        # Check for feet and inches: 45' 6.5" or 45-06.50
        feet_inches_match = re.match(
            r"(\d+)['\-]\s*(\d+(?:\.\d+)?)[\"']?",
            distance_str
        )
        if feet_inches_match:
            feet = int(feet_inches_match.group(1))
            inches = float(feet_inches_match.group(2))
            # Convert to meters: 1 foot = 0.3048m, 1 inch = 0.0254m
            return feet * 0.3048 + inches * 0.0254
        
        # Try to parse as plain number (assume meters)
        try:
            return float(distance_str)
        except ValueError:
            return None

    def parse_wind(self, wind_str: str) -> Optional[float]:
        """Parse wind reading from string like '+1.2' or '-0.5' or '1.2'."""
        if not wind_str:
            return None
        
        wind_str = wind_str.strip()
        # Remove common prefixes
        wind_str = re.sub(r'^[wW]:', '', wind_str)
        wind_str = re.sub(r'm/s$', '', wind_str, flags=re.IGNORECASE)
        
        try:
            return float(wind_str)
        except ValueError:
            return None

    def split_name(self, full_name: str) -> tuple[str, str]:
        """
        Split a full name into first and last name.
        
        Handles formats like:
        - "Smith, John" -> ("John", "Smith")
        - "John Smith" -> ("John", "Smith")
        """
        full_name = full_name.strip()
        
        if ',' in full_name:
            # Last, First format
            parts = full_name.split(',', 1)
            last_name = parts[0].strip()
            first_name = parts[1].strip() if len(parts) > 1 else ""
        else:
            # First Last format
            parts = full_name.split()
            if len(parts) >= 2:
                first_name = parts[0]
                last_name = ' '.join(parts[1:])
            elif len(parts) == 1:
                first_name = parts[0]
                last_name = ""
            else:
                first_name = ""
                last_name = ""
        
        return first_name, last_name
