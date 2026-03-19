#!/usr/bin/env python3
"""
Import all records (historical and performance) into the database.
This script clears the database and imports fresh data from both JSON files.
"""

import json
import logging
import sys
import re
from pathlib import Path
from datetime import datetime

# Add parent directory to path so we can import scraper modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.database import get_database
from scraper.event_matcher import get_event_matcher
from scraper.meet_names import normalize_meet_name

logger = logging.getLogger(__name__)


def load_calendar_events():
    """Load calendar events for date matching."""
    calendar_path = Path(__file__).parent.parent / 'config' / 'calendar_events.json'
    if not calendar_path.exists():
        return []
    
    with open(calendar_path, 'r') as f:
        data = json.load(f)
    # calendar_events.json is {"locationMap": {...}, "events": [...]}
    return data.get('events', data) if isinstance(data, dict) else data


def load_meet_dates():
    """Load meet dates and levels from config file."""
    meets_config_path = Path(__file__).parent.parent / 'config' / 'meets_2025.json'
    meet_info = {}
    
    if meets_config_path.exists():
        with open(meets_config_path, 'r') as f:
            config = json.load(f)
            for meet in config.get('meets', []):
                meet_info[meet['name']] = {
                    'date': meet.get('date'),
                    'level': meet.get('level', 'varsity')
                }
    
    return meet_info


def match_meet_to_date(meet_name, year, calendar_events, meet_dates):
    """Try to match a meet name to a date from meets_2025.json, calendar events, or parse the year."""
    # First, try to find in meets config (for 2025 meets)
    if meet_name in meet_dates:
        date = meet_dates[meet_name]['date']
        if date:
            return date
    
    # Second, try to find in calendar events (for current season meets only)
    # Only match if there's a significant overlap in the title AND the year matches
    for event in calendar_events:
        title = event.get('title', '').lower()
        # Skip generic entries like "Winter Break"
        if title in ['winter break', 'preseason training', 'all-day']:
            continue

        # Only match calendar events for the correct year to avoid assigning
        # future/past dates to historical records (e.g. "Fort Collins 2004"
        # matching the 2026 calendar entry for "Fort Collins JV Scrimmage")
        try:
            event_year = datetime.strptime(event['date'], '%m/%d/%Y').year
            if year and event_year != int(year):
                continue
        except Exception:
            pass

        # Check if meet name contains significant words from the event title
        meet_lower = meet_name.lower()
        # Extract meaningful words (3+ chars) from both
        meet_words = set(word for word in re.findall(r'\b\w{3,}\b', meet_lower))
        title_words = set(word for word in re.findall(r'\b\w{3,}\b', title))
        
        # If 2+ words match, consider it a match
        if len(meet_words & title_words) >= 2:
            # Parse date from MM/DD/YYYY format
            try:
                event_date = datetime.strptime(event['date'], '%m/%d/%Y')
                return event_date.strftime('%Y-%m-%d')
            except:
                pass
    
    # If not found in calendar, check if meet name has embedded year/date
    # Pattern like "Liberty Bell 2012" or "State 2011"
    year_match = re.search(r'(\d{4})', meet_name)
    if year_match:
        year_from_name = year_match.group(1)
        # Use March as a reasonable default for spring track season
        return f"{year_from_name}-03-15"
    
    # Fall back to the year from the record
    if year:
        return f"{year}-03-15"
    
    return None


def import_all_records(db_path: str = None, clear_db: bool = True):
    """Import all records from both JSON files into the database."""
    logger.info("Importing all records (historical + performance)...")
    
    db = get_database(db_path)
    event_matcher = get_event_matcher()
    calendar_events = load_calendar_events()
    meet_dates = load_meet_dates()
    
    # Clear database if requested
    if clear_db:
        logger.info("Clearing existing data from database...")
        db.clear_all()
        logger.info("Database cleared")
    
    # Import historical records first
    historical_path = Path(__file__).parent.parent / 'data' / 'snapshots' / 'historic' / 'historical_records.json'
    if historical_path.exists():
        logger.info(f"Importing historical records from {historical_path}...")
        with open(historical_path, 'r') as f:
            historical_records = json.load(f)
        
        historical_count = import_records(db, event_matcher, historical_records, "Historical", calendar_events, meet_dates)
        logger.info(f"Imported {historical_count} historical records")
    else:
        logger.warning(f"Historical records file not found: {historical_path}")
        historical_count = 0
    
    # Import performance records
    performance_path = Path(__file__).parent.parent / 'data' / 'snapshots' / '2025' / 'parsed_performance_list.json'
    if performance_path.exists():
        logger.info(f"Importing performance records from {performance_path}...")
        with open(performance_path, 'r') as f:
            performance_records = json.load(f)
        
        performance_count = import_records(db, event_matcher, performance_records, "Performance", calendar_events, meet_dates)
        logger.info(f"Imported {performance_count} performance records")
    else:
        logger.warning(f"Performance records file not found: {performance_path}")
        performance_count = 0
    
    total = historical_count + performance_count
    logger.info(f"\n{'='*60}")
    logger.info(f"IMPORT COMPLETE")
    logger.info(f"  Historical records: {historical_count}")
    logger.info(f"  Performance records: {performance_count}")
    logger.info(f"  Total records imported: {total}")
    logger.info(f"{'='*60}")
    
    return total


def import_records(db, event_matcher, records, record_type, calendar_events, meet_dates):
    """Import records in the common format."""
    count = 0
    skipped = 0
    
    for record in records:
        try:
            gender = record['gender']
            
            # Match to canonical event
            canonical_event = event_matcher.match(record['event'], gender)
            if not canonical_event:
                logger.warning(f"Could not match event: {record['event']}")
                continue
            
            event_info = event_matcher.get_event_info(canonical_event)
            event_id = db.get_or_create_event(canonical_event, event_info)
            
            # Create a virtual meet for this record
            meet_name = normalize_meet_name(record['meet'])
            meet_date = match_meet_to_date(meet_name, record.get('year'), calendar_events, meet_dates)
            
            # Get level from record or from meet_dates config
            level = record.get('level', 'varsity')
            if meet_name in meet_dates:
                level = meet_dates[meet_name]['level']
            
            meet_id = db.get_or_create_meet(
                name=meet_name,
                meet_date=meet_date,
                venue=record['meet'],
                location=record['meet'],
                season=str(record['year']) if record.get('year') else None,
                level=level
            )
            
            # Handle relay vs individual
            if record.get('is_relay') and record.get('relay_members'):
                # For relays, create a result for the first team member
                if not record['relay_members']:
                    logger.debug(f"Relay event {record['event']} has no team members")
                    continue
                
                # Use first member as the primary athlete for the result
                first_member = record['relay_members'][0]
                mem_parts = first_member.strip().split()
                if len(mem_parts) >= 2:
                    first_name = mem_parts[0]
                    last_name = ' '.join(mem_parts[1:])
                elif len(mem_parts) == 1:
                    first_name = mem_parts[0]
                    last_name = ""
                else:
                    first_name = ""
                    last_name = ""
                
                athlete_id = db.get_or_create_athlete(
                    first_name=first_name,
                    last_name=last_name,
                    gender=gender,
                    graduation_year=record.get('year')
                )
                
                # Add the result
                result_id = db.add_result(
                    athlete_id=athlete_id,
                    event_id=event_id,
                    meet_id=meet_id,
                    mark=record['mark'],
                    mark_display=record['mark_display'],
                    place=1,
                    level=record.get('level', 'varsity'),
                    notes=f"{record_type} record"
                )
                
                if result_id:
                    # Add all relay members (including the first one)
                    for i, member_name in enumerate(record['relay_members'], start=1):
                        mem_parts = member_name.strip().split()
                        if len(mem_parts) >= 2:
                            mem_first = mem_parts[0]
                            mem_last = ' '.join(mem_parts[1:])
                        elif len(mem_parts) == 1:
                            mem_first = mem_parts[0]
                            mem_last = ""
                        else:
                            continue
                        
                        mem_athlete_id = db.get_or_create_athlete(
                            first_name=mem_first,
                            last_name=mem_last,
                            gender=gender,
                            graduation_year=record.get('year')
                        )
                        db.add_relay_member(
                            result_id=result_id,
                            athlete_id=mem_athlete_id,
                            leg_order=i
                        )
                    
                    count += 1
                else:
                    skipped += 1
            
            else:
                # Individual event
                first_name = record.get('athlete_first', '')
                last_name = record.get('athlete_last', '')
                
                athlete_id = db.get_or_create_athlete(
                    first_name=first_name,
                    last_name=last_name,
                    gender=gender,
                    graduation_year=record.get('year')
                )
                
                # Add the result
                result_id = db.add_result(
                    athlete_id=athlete_id,
                    event_id=event_id,
                    meet_id=meet_id,
                    mark=record['mark'],
                    mark_display=record['mark_display'],
                    place=1,
                    level=record.get('level', 'varsity'),
                    notes=f"{record_type} record"
                )
                
                if result_id:
                    count += 1
                else:
                    skipped += 1
        
        except Exception as e:
            logger.error(f"Error importing record {record.get('event')}: {e}")
    
    logger.debug(f"  Summary: {count} added, {skipped} skipped")
    return count


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Import all school records and performance data')
    parser.add_argument('--db', help='Path to database file')
    parser.add_argument('--no-clear', action='store_true', help='Do not clear existing data')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    import_all_records(args.db, clear_db=not args.no_clear)


if __name__ == '__main__':
    main()
