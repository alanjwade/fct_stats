#!/usr/bin/env python3
"""
Import historical school records from JSON into the database.
This script is called by the scraper to include historical records.
"""

import json
import logging
import sys
from pathlib import Path

# Add parent directory to path so we can import scraper modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.database import get_database
from scraper.event_matcher import get_event_matcher

logger = logging.getLogger(__name__)


def split_name(full_name: str) -> tuple[str, str]:
    """Split a full name into first and last name."""
    if not full_name:
        return "", ""
    
    full_name = full_name.strip()
    
    # Handle "First Last" format
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


def import_historical_records(db_path: str = None):
    """Import historical records from JSON into the database."""
    logger.info("Importing historical school records...")
    
    # Load JSON file
    json_path = Path(__file__).parent.parent / 'data' / 'historical_records.json'
    if not json_path.exists():
        logger.warning(f"Historical records file not found: {json_path}")
        logger.info("Run scripts/parse_historical_records.py first to generate it")
        return
    
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    db = get_database(db_path)
    event_matcher = get_event_matcher()
    
    # Import boys records
    boys_count = import_gender_records(db, event_matcher, data['boys'], 'M')
    
    # Import girls records
    girls_count = import_gender_records(db, event_matcher, data['girls'], 'F')
    
    total = boys_count + girls_count
    logger.info(f"Imported {boys_count} boys records, {girls_count} girls records")
    logger.info(f"Total historical records imported: {total}")
    
    return total


def import_gender_records(db, event_matcher, records, gender):
    """Import records for a specific gender."""
    count = 0
    
    for record in records:
        try:
            # Match to canonical event
            canonical_event = event_matcher.match(record['event'], gender)
            if not canonical_event:
                logger.warning(f"Could not match event: {record['event']}")
                continue
            
            event_info = event_matcher.get_event_info(canonical_event)
            event_id = db.get_or_create_event(canonical_event, event_info)
            
            # Create a virtual meet for this historical record
            # Use the location as the meet name
            meet_name = record['location']
            meet_date = f"{record['year']}-01-01" if record['year'] else None
            
            meet_id = db.get_or_create_meet(
                name=meet_name,
                meet_date=meet_date,
                venue=record['location'],
                location=record['location'],
                season=str(record['year']) if record['year'] else None,
                level='varsity'
            )
            
            # Handle relay vs individual
            if record['is_relay'] and record['relay_members']:
                # For relays, create a result for the first team member
                # and link the others via relay_members table
                if not record['relay_members']:
                    logger.warning(f"Relay event {record['event']} has no team members")
                    continue
                
                # Use first member as the primary athlete for the result
                first_member = record['relay_members'][0]
                first_name, last_name = split_name(first_member)
                
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
                    place=1,  # All historical records are #1
                    level='varsity',
                    notes=f"School Record as of {record['year']}"
                )
                
                if result_id:
                    # Add all relay members (including the first one)
                    for i, member_name in enumerate(record['relay_members'], start=1):
                        mem_first, mem_last = split_name(member_name)
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
                    logger.info(f"  Added relay: {record['event']} - {record['relay_members']}")
            
            else:
                # Individual event
                first_name, last_name = split_name(record['athlete'])
                
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
                    place=1,  # All historical records are #1
                    level='varsity',
                    notes=f"School Record as of {record['year']}"
                )
                
                if result_id:
                    count += 1
                    logger.info(f"  Added: {record['event']} - {record['athlete']} - {record['mark_display']}")
        
        except Exception as e:
            logger.error(f"Error importing record {record.get('event')}: {e}")
    
    return count


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Import historical school records')
    parser.add_argument('--db', help='Path to database file')
    
    args = parser.parse_args()
    
    import_historical_records(args.db)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    main()
