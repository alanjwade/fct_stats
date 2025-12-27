"""
Database utilities for the Fort Collins Track Stats scraper.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional
import yaml


class Database:
    """SQLite database wrapper for track stats."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / 'data' / 'fct_stats.db'
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        """Create database schema if it doesn't exist."""
        # Check if tables already exist
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='athletes'")
            if cursor.fetchone():
                # Tables already exist, skip schema creation
                return
        
        # Find schema file relative to this module
        schema_path = Path(__file__).parent.parent / 'database' / 'schema.sql'
        
        if not schema_path.exists():
            # Schema file not found, but tables might already exist
            # This is okay if database was initialized manually
            return
        
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        
        with self.get_connection() as conn:
            conn.executescript(schema_sql)

    @contextmanager
    def get_connection(self):
        """Get a database connection as a context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_or_create_athlete(
        self,
        first_name: str,
        last_name: str,
        gender: str = None,
        graduation_year: int = None
    ) -> int:
        """Get existing athlete or create new one. Returns athlete ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Try to find existing athlete
            cursor.execute("""
                SELECT id FROM athletes 
                WHERE first_name = ? AND last_name = ? 
                AND (graduation_year = ? OR graduation_year IS NULL OR ? IS NULL)
            """, (first_name, last_name, graduation_year, graduation_year))
            
            row = cursor.fetchone()
            if row:
                return row['id']
            
            # Create new athlete
            cursor.execute("""
                INSERT INTO athletes (first_name, last_name, gender, graduation_year)
                VALUES (?, ?, ?, ?)
            """, (first_name, last_name, gender, graduation_year))
            
            return cursor.lastrowid

    def get_or_create_event(self, name: str, event_info: dict = None) -> int:
        """Get existing event or create new one. Returns event ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM events WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return row['id']
            
            # Create new event
            info = event_info or {}
            cursor.execute("""
                INSERT INTO events (name, category, distance_meters, timed, lower_is_better, is_relay, gender_specific)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                info.get('category'),
                info.get('distance_meters'),
                info.get('timed', True),
                info.get('lower_is_better', True),
                info.get('is_relay', False),
                info.get('gender_specific')
            ))
            
            return cursor.lastrowid

    def get_or_create_meet(
        self,
        name: str,
        meet_date: str = None,
        venue: str = None,
        location: str = None,
        season: str = None,
        level: str = 'varsity'
    ) -> int:
        """Get existing meet or create new one. Returns meet ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id FROM meets WHERE name = ? AND meet_date = ?
            """, (name, meet_date))
            
            row = cursor.fetchone()
            if row:
                # Update level if it was added later
                cursor.execute("""
                    UPDATE meets SET level = ? WHERE id = ?
                """, (level, row['id']))
                conn.commit()
                return row['id']
            
            cursor.execute("""
                INSERT INTO meets (name, meet_date, venue, location, season, level)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, meet_date, venue, location, season, level))
            
            return cursor.lastrowid

    def add_result(
        self,
        athlete_id: int,
        event_id: int,
        meet_id: int,
        mark: float,
        mark_display: str = None,
        place: int = None,
        level: str = None,
        wind: float = None,
        heat: int = None,
        lane: int = None,
        flight: int = None,
        notes: str = None
    ) -> Optional[int]:
        """Add a result. Returns result ID or None if duplicate."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    INSERT INTO results 
                    (athlete_id, event_id, meet_id, mark, mark_display, place, level, wind, heat, lane, flight, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    athlete_id, event_id, meet_id, mark, mark_display,
                    place, level, wind, heat, lane, flight, notes
                ))
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # Duplicate result
                return None

    def add_relay_member(
        self,
        result_id: int,
        athlete_id: int,
        leg_order: int,
        split_time: float = None
    ) -> Optional[int]:
        """Add a relay team member. Returns ID or None if duplicate."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    INSERT INTO relay_members (result_id, athlete_id, leg_order, split_time)
                    VALUES (?, ?, ?, ?)
                """, (result_id, athlete_id, leg_order, split_time))
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                return None

    def initialize_events_from_config(self, config_path: str = None):
        """Load canonical events from config into database."""
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'canonical_events.yaml'
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        for event in config['events']:
            self.get_or_create_event(event['name'], event)

    def clear_results(self):
        """Clear all results from the database (keeps athletes, events, meets)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM relay_members")
            cursor.execute("DELETE FROM results")
            conn.commit()
        import logging
        logging.getLogger(__name__).info("Cleared all results from database")

    def clear_meets(self):
        """Clear all meets and their results from the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM relay_members")
            cursor.execute("DELETE FROM results")
            cursor.execute("DELETE FROM meets")
            conn.commit()
        import logging
        logging.getLogger(__name__).info("Cleared all meets and results from database")

    def clear_all(self):
        """Clear entire database (keeps schema)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM relay_members")
            cursor.execute("DELETE FROM results")
            cursor.execute("DELETE FROM meets")
            cursor.execute("DELETE FROM athletes")
            cursor.execute("DELETE FROM events")
            conn.commit()
        import logging
        logging.getLogger(__name__).info("Cleared entire database")


# Singleton instance
_db = None


def get_database(db_path: str = None) -> Database:
    """Get or create the database singleton."""
    global _db
    if _db is None:
        _db = Database(db_path)
    return _db
