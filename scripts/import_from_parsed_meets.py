#!/usr/bin/env python3
"""
Import all parsed meet JSON files from data/parsed_meets/ into the database.

This replaces import_all_records.py with a simpler approach that reads
from the centralized parsed_meets directory structure.
"""

import json
import logging
import re
import sys
from pathlib import Path

# Add parent directory to path so we can import scraper modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.database import get_database
from scraper.event_matcher import get_event_matcher
from scraper.meet_names import normalize_meet_name

logger = logging.getLogger(__name__)

def _strip_nickname(name: str) -> str:
    """Remove parenthetical nicknames, e.g. '(Denny)' from a name part."""
    return re.sub(r'\s*\([^)]*\)', '', name).strip()


def load_meet_config():
    """Load meet dates and levels from config file."""
    meets_config_path = Path(__file__).parent.parent / 'data' / 'sources' / 'current' / '2025' / 'meets_2025.json'
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


def import_meet_file(db, event_matcher, meet_file: Path, meet_config: dict) -> tuple[int, int]:
    """
    Import a single meet JSON file into the database.
    
    Returns (added_count, skipped_count)
    """
    with open(meet_file, 'r') as f:
        meet_data = json.load(f)
    
    meet_name = meet_data.get('meet_name', meet_file.stem)
    year = meet_data.get('year')
    results = meet_data.get('results', [])
    
    if not results:
        return 0, 0
    
    # Get meet date from config or data
    config_entry = meet_config.get(meet_name, {})
    meet_date = config_entry.get('date') or meet_data.get('date')
    default_level = config_entry.get('level', 'varsity')
    
    added = 0
    skipped = 0
    
    for record in results:
        try:
            gender = record.get('gender')
            if not gender:
                continue
            
            # Match to canonical event
            event_name = record.get('event') or record.get('event_name')
            if not event_name:
                continue
            
            canonical_event = event_matcher.match(event_name, gender)
            if not canonical_event:
                logger.debug(f"Could not match event: {event_name}")
                continue
            
            event_info = event_matcher.get_event_info(canonical_event)
            event_id = db.get_or_create_event(canonical_event, event_info)
            
            # Get meet info - use record's meet name if different from file meet
            record_meet = normalize_meet_name(record.get('meet', meet_name))
            record_config = meet_config.get(record_meet, {})
            record_year = record.get('year') or year
            
            # Prefer the config date (manually curated, authoritative) over the
            # embedded record date, which can be wrong if the source data was mis-dated.
            # Fall back to record date only when the config has no entry for this meet.
            record_date = record_config.get('date') or meet_date or record.get('date')
            
            record_level = record.get('level') or record_config.get('level') or default_level
            
            meet_id = db.get_or_create_meet(
                name=record_meet,
                meet_date=record_date,
                venue=record_meet,
                location=record_meet,
                season=str(record_year) if record_year else None
            )
            
            # Handle relay vs individual
            # Relays are marked with is_relay flag OR detected by "relay" in event name.
            # They may or may not have member names from the source file.
            is_relay = record.get('is_relay', False) or 'relay' in canonical_event.lower()
            
            if is_relay and record.get('relay_members'):
                # Relay event
                members = record['relay_members']
                if not members:
                    continue
                
                # Use first member as primary athlete
                first_member = members[0].strip()
                parts = first_member.split()
                if len(parts) >= 2:
                    first_name = parts[0]
                    last_name = ' '.join(parts[1:])
                else:
                    first_name = first_member
                    last_name = ""
                
                athlete_id = db.get_or_create_athlete(
                    first_name=first_name,
                    last_name=last_name,
                    gender=gender,
                    graduation_year=record.get('year')
                )
                
                result_id = db.add_result(
                    athlete_id=athlete_id,
                    event_id=event_id,
                    meet_id=meet_id,
                    mark=record.get('mark', 0),
                    mark_display=record.get('mark_display', ''),
                    place=record.get('place'),
                    level=record_level,
                    notes=record.get('notes', '')
                )
                
                if result_id:
                    # Add relay members
                    for i, member_name in enumerate(members, start=1):
                        parts = member_name.strip().split()
                        if len(parts) >= 2:
                            mem_first = parts[0]
                            mem_last = ' '.join(parts[1:])
                        else:
                            mem_first = member_name.strip()
                            mem_last = ""
                        
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
                    added += 1
                else:
                    skipped += 1
            else:
                # Individual event (or relay without member names)
                first_name = _strip_nickname(record.get('athlete_first', ''))
                last_name = _strip_nickname(record.get('athlete_last', ''))
                
                # Handle full name if first/last not split
                if not first_name and not last_name:
                    full_name = record.get('athlete_name', '')
                    if full_name:
                        parts = full_name.split()
                        if len(parts) >= 2:
                            first_name = parts[0]
                            last_name = ' '.join(parts[1:])
                        else:
                            first_name = full_name
                
                if not first_name:
                    if is_relay:
                        # Relay record with no individual member names available.
                        # Use a per-event placeholder name so each relay team shows up
                        # distinctly in the Athletes page (e.g. "Fort Collins 4x100m Relay Team").
                        first_name = "Fort Collins"
                        last_name = f"{canonical_event} Team"
                    else:
                        continue
                
                athlete_id = db.get_or_create_athlete(
                    first_name=first_name,
                    last_name=last_name,
                    gender=gender,
                    graduation_year=record.get('year')
                )
                
                result_id = db.add_result(
                    athlete_id=athlete_id,
                    event_id=event_id,
                    meet_id=meet_id,
                    mark=record.get('mark', 0),
                    mark_display=record.get('mark_display', ''),
                    place=record.get('place'),
                    level=record_level,
                    notes=record.get('notes', '')
                )
                
                if result_id:
                    added += 1
                else:
                    skipped += 1
        
        except Exception as e:
            logger.warning(f"Error importing record: {e}")
            skipped += 1
    
    return added, skipped


def import_all_parsed_meets(db_path: str = None, clear_db: bool = True):
    """Import all parsed meet files from data/parsed_meets/."""
    logger.info("Importing from data/parsed_meets/...")
    
    db = get_database(db_path)
    event_matcher = get_event_matcher()
    meet_config = load_meet_config()
    
    parsed_dir = Path(__file__).parent.parent / 'data' / 'generated' / 'parsed' / 'meets'
    
    if not parsed_dir.exists():
        logger.error(f"Parsed meets directory not found: {parsed_dir}")
        logger.info("Run scripts/consolidate_parsed_data.py first")
        return
    
    # Clear database if requested
    if clear_db:
        logger.info("Clearing existing data from database...")
        db.clear_all()
        logger.info("Database cleared")
    
    total_added = 0
    total_skipped = 0
    files_processed = 0
    
    # Process all JSON files in parsed_meets and subdirectories
    for json_file in sorted(parsed_dir.rglob('*.json')):
        relative_path = json_file.relative_to(parsed_dir)
        logger.info(f"Importing {relative_path}...")
        
        added, skipped = import_meet_file(db, event_matcher, json_file, meet_config)
        
        logger.info(f"  → {added} added, {skipped} skipped")
        
        total_added += added
        total_skipped += skipped
        files_processed += 1
    
    logger.info("\n" + "=" * 60)
    logger.info("IMPORT COMPLETE")
    logger.info(f"  Files processed: {files_processed}")
    logger.info(f"  Records added: {total_added}")
    logger.info(f"  Records skipped: {total_skipped}")
    logger.info("=" * 60)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Import parsed meet files to database')
    parser.add_argument('--db', help='Path to database file')
    parser.add_argument('--no-clear', action='store_true', help='Do not clear existing data')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    import_all_parsed_meets(args.db, clear_db=not args.no_clear)


if __name__ == '__main__':
    main()
