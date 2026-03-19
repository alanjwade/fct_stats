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


def import_historical_records(db_path: str = None):
    """Import historical records from JSON into the database."""
    logger.info("Importing historical school records...")
    
    # Load JSON file
    json_path = Path(__file__).parent.parent / 'data' / 'snapshots' / 'historic' / 'historical_records.json'
    if not json_path.exists():
        logger.warning(f"Historical records file not found: {json_path}")
        logger.info("Run scripts/parse_historical_records.py first to generate it")
        return
    
    with open(json_path, 'r') as f:
        records = json.load(f)
    
    db = get_database(db_path)
    event_matcher = get_event_matcher()
    
    # Import all records (now in common format)
    logger.info(f"Processing records from {json_path}...")
    count = import_records(db, event_matcher, records)
    
    logger.info(f"Total NEW historical records imported: {count}")
    logger.info(f"(Existing records were skipped - run with --debug to see details)")
    
    return count


def import_records(db, event_matcher, records):
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
            
            # Create a virtual meet for this historical record
            # Use the meet name from the record
            meet_name = record['meet']
            meet_date = f"{record['year']}-01-01" if record.get('year') else None
            
            meet_id = db.get_or_create_meet(
                name=meet_name,
                meet_date=meet_date,
                venue=record['meet'],
                location=record['meet'],
                season=str(record['year']) if record.get('year') else None,
                level=record.get('level', 'varsity')
            )
            
            # Handle relay vs individual
            if record.get('is_relay') and record.get('relay_members'):
                # For relays, create a result for the first team member
                # and link the others via relay_members table
                if not record['relay_members']:
                    logger.warning(f"Relay event {record['event']} has no team members")
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
                    place=1,  # All historical records are #1
                    level=record.get('level', 'varsity'),
                    notes=f"School Record as of {record.get('year', 'Unknown')}"
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
                    logger.info(f"  Added relay: {record['event']} - {record['relay_members']}")
                else:
                    skipped += 1
                    logger.debug(f"  Skipped relay (already exists): {record['event']} - {record['relay_members']}")
            
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
                    place=1,  # All historical records are #1
                    level=record.get('level', 'varsity'),
                    notes=f"School Record as of {record.get('year', 'Unknown')}"
                )
                
                if result_id:
                    count += 1
                    logger.info(f"  Added: {record['event']} - {first_name} {last_name} - {record['mark_display']}")
                else:
                    skipped += 1
                    logger.debug(f"  Skipped (already exists): {record['event']} - {first_name} {last_name} - {record['mark_display']}")
        
        except Exception as e:
            logger.error(f"Error importing record {record.get('event')}: {e}")
    
    logger.info(f"  Summary: {count} added, {skipped} skipped")
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
