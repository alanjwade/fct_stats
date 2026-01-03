"""
Main scraper for Fort Collins Track Stats.
Orchestrates parsing meet YAML files and populating the database.
"""

import yaml
import logging
from pathlib import Path
from glob import glob

from .parsers import get_parser
from .school_matcher import is_fort_collins, get_school_matcher
from .event_matcher import get_event_matcher
from .database import get_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Scraper:
    """Main scraper orchestrator."""

    def __init__(self, data_dir: str = None, db_path: str = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / 'data'
        self.data_dir = Path(data_dir)
        
        self.db = get_database(db_path)
        self.event_matcher = get_event_matcher()
        self.school_matcher = get_school_matcher()
        self.current_name_mappings = {}  # Store name mappings for current meet
        
        # Initialize events in database
        self.db.initialize_events_from_config()

    def scrape_directory(self, directory: str):
        """Scrape all meet YAML files in a directory recursively."""
        dir_path = Path(directory)
        
        if not dir_path.exists():
            logger.error(f"Directory not found: {dir_path}")
            return
        
        yaml_files = glob(str(dir_path / '**' / '*.yaml'), recursive=True)
        yaml_files.extend(glob(str(dir_path / '**' / '*.yml'), recursive=True))
        
        logger.info(f"Found {len(yaml_files)} meet configuration files in {dir_path}")
        
        for yaml_file in yaml_files:
            try:
                self.scrape_meet(yaml_file)
            except Exception as e:
                logger.error(f"Error processing {yaml_file}: {e}")

    def scrape_all(self):
        """Scrape all meet YAML files in the data directory."""
        meets_dir = self.data_dir / 'meets'
        yaml_files = glob(str(meets_dir / '**' / '*.yaml'), recursive=True)
        yaml_files.extend(glob(str(meets_dir / '**' / '*.yml'), recursive=True))
        
        logger.info(f"Found {len(yaml_files)} meet configuration files")
        
        for yaml_file in yaml_files:
            try:
                self.scrape_meet(yaml_file)
            except Exception as e:
                logger.error(f"Error processing {yaml_file}: {e}")

    def scrape_meet(self, yaml_path: str):
        """Scrape a single meet from its YAML configuration."""
        logger.info(f"Processing meet: {yaml_path}")
        
        with open(yaml_path, 'r') as f:
            config = yaml.safe_load(f)
        
        meet_info = config.get('meet', {})
        meet_level = meet_info.get('level', 'varsity')  # Default to varsity
        meet_id = self.db.get_or_create_meet(
            name=meet_info.get('name', 'Unknown Meet'),
            meet_date=meet_info.get('date'),
            venue=meet_info.get('venue'),
            location=meet_info.get('location'),
            season=meet_info.get('season'),
            level=meet_level
        )
        
        logger.info(f"Meet ID: {meet_id} - {meet_info.get('name')} ({meet_level})")
        
        # Store name mappings for this meet
        self.current_name_mappings = config.get('name_mappings', {})
        
        # Process each source file
        for source in config.get('sources', []):
            self._process_source(source, meet_id, meet_level)

    def _process_source(self, source: dict, meet_id: int, meet_level: str):
        """Process a single source file with its events."""
        file_path = self.data_dir / source['file']
        
        if not file_path.exists():
            logger.warning(f"Source file not found: {file_path}")
            return
        
        parser_name = source.get('parser', 'generic_table')
        parser = get_parser(parser_name)
        
        logger.info(f"Processing source: {file_path} with parser: {parser_name}")
        
        # If events are specified, process each one
        events = source.get('events', [])
        if events:
            for event_config in events:
                self._process_event(parser, str(file_path), event_config, meet_id, source.get('gender'), meet_level)
        else:
            # Auto-detect events from file (for multi-event pages)
            self._process_auto_detect(parser, str(file_path), meet_id, source.get('gender'), meet_level)

    def _process_auto_detect(self, parser, file_path: str, meet_id: int, default_gender: str = None, meet_level: str = 'varsity'):
        """Auto-detect and process all events from a multi-event file."""
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check if this is a text file (HyTek format)
        if file_path.endswith('.txt'):
            # Text parsers handle everything internally
            all_results = parser.parse_all_events(content)
            logger.info(f"  Found {len(all_results)} total results from text parser")
            
            # Group by event
            events_dict = {}
            for result in all_results:
                if result.event_name not in events_dict:
                    events_dict[result.event_name] = []
                events_dict[result.event_name].append(result)
            
            logger.info(f"  Auto-detected {len(events_dict)} events in file")
            
            # Process each event
            for event_name, results in events_dict.items():
                logger.info(f"  Processing: {event_name}")
                
                # Determine gender from event name or first result
                if results and results[0].gender:
                    gender_code = results[0].gender
                elif event_name.lower().startswith('boys') or event_name.lower().startswith("men's"):
                    gender_code = 'M'
                elif event_name.lower().startswith('girls') or event_name.lower().startswith("women's"):
                    gender_code = 'F'
                elif default_gender:
                    gender_code = default_gender.upper()[0] if default_gender else None
                else:
                    gender_code = None
                
                # Try to match to canonical event
                matched_event = self.event_matcher.match(event_name, gender_code)
                if not matched_event:
                    logger.warning(f"    Could not match event: {event_name}")
                    continue
                
                event_info = self.event_matcher.get_event_info(matched_event)
                event_id = self.db.get_or_create_event(matched_event, event_info)
                
                logger.info(f"    Found {len(results)} results")
                
                # Filter to Fort Collins athletes and save
                fc_count = 0
                for result in results:
                    if self.school_matcher.is_target_school(result.school):
                        self._save_result(result, event_id, meet_id, gender_code or 'U', meet_level)
                        fc_count += 1
                
                logger.info(f"    Saved {fc_count} Fort Collins results")
            
            return
        
        # HTML parsing (original logic)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')
        
        # Look for MileSplit event name divs
        event_divs = soup.find_all('p', class_='eventName')
        
        logger.info(f"  Auto-detected {len(event_divs)} events in file")
        
        for event_div in event_divs:
            event_text = event_div.get_text(strip=True)
            logger.info(f"  Processing: {event_text}")
            
            # Determine gender from event name
            if event_text.lower().startswith('boys') or event_text.lower().startswith("men's"):
                gender_code = 'M'
            elif event_text.lower().startswith('girls') or event_text.lower().startswith("women's"):
                gender_code = 'F'
            elif default_gender:
                gender_code = default_gender.upper()[0] if default_gender else None
            else:
                gender_code = None
            
            # Try to match to canonical event
            matched_event = self.event_matcher.match(event_text, gender_code)
            if not matched_event:
                logger.warning(f"    Could not match event: {event_text}")
                continue
            
            event_info = self.event_matcher.get_event_info(matched_event)
            event_id = self.db.get_or_create_event(matched_event, event_info)
            
            # Extract the table following this event header
            results = self._extract_event_results(soup, event_div, event_info)
            
            logger.info(f"    Found {len(results)} results")
            
            # Filter to Fort Collins athletes and save
            fc_count = 0
            for result in results:
                if self.school_matcher.is_target_school(result.school):
                    self._save_result(result, event_id, meet_id, gender_code or 'U', meet_level)
                    fc_count += 1
            
            logger.info(f"    Saved {fc_count} Fort Collins results")

    def _extract_event_results(self, soup, event_div, event_info):
        """Extract results from the table following an event header."""
        from .parsers.base_parser import ParsedResult
        results = []
        
        # Find the next table after the event div
        current = event_div.parent
        while current:
            table = current.find_next('table', class_='eventTable')
            if table:
                break
            current = current.parent
        
        if not table:
            return results
        
        # Parse table rows
        rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 4:
                continue
            
            result = ParsedResult()
            
            # Common MileSplit structure:
            # Place | Video | Athlete | Grade | Team | Mark | Wind | Heat
            try:
                place_cell = cells[0]
                result.place = int(place_cell.get_text(strip=True)) if place_cell.get_text(strip=True).isdigit() else None
                
                # Athlete (usually has a link)
                athlete_cell = cells[2] if len(cells) > 2 else None
                if athlete_cell:
                    athlete_link = athlete_cell.find('a')
                    if athlete_link:
                        result.athlete_name = athlete_link.get_text(strip=True)
                
                # Team
                team_cell = cells[4] if len(cells) > 4 else None
                if team_cell:
                    team_link = team_cell.find('a')
                    if team_link:
                        result.school = team_link.get_text(strip=True)
                    else:
                        result.school = team_cell.get_text(strip=True)
                
                # Mark/time
                mark_cell = cells[5] if len(cells) > 5 else None
                if mark_cell:
                    mark_text = mark_cell.get_text(strip=True)
                    result.mark_display = mark_text
                    
                    # Convert to numeric value
                    if event_info and event_info.get('timed'):
                        result.mark = self._parse_time_to_seconds(mark_text)
                    else:
                        result.mark = self._parse_distance_to_meters(mark_text)
                
                # Wind (if present)
                if len(cells) > 6:
                    wind_text = cells[6].get_text(strip=True)
                    if wind_text and wind_text not in ['', 'NWI']:
                        try:
                            result.wind = float(wind_text)
                        except ValueError:
                            pass
                
                if result.athlete_name and result.mark:
                    results.append(result)
            except Exception as e:
                logger.debug(f"      Error parsing row: {e}")
                continue
        
        return results

    def _parse_time_to_seconds(self, time_str: str) -> float:
        """Convert time string to seconds."""
        if not time_str:
            return 0.0
        
        time_str = time_str.strip()
        
        # Handle MM:SS.ss format
        if ':' in time_str:
            parts = time_str.split(':')
            if len(parts) == 2:
                try:
                    minutes = float(parts[0])
                    seconds = float(parts[1])
                    return minutes * 60 + seconds
                except ValueError:
                    return 0.0
        
        # Handle SS.ss format
        try:
            return float(time_str)
        except ValueError:
            return 0.0

    def _parse_distance_to_meters(self, dist_str: str) -> float:
        """Convert distance string to meters."""
        if not dist_str:
            return 0.0
        
        dist_str = dist_str.strip()
        
        # Handle feet-inches format: 20-6.5 or 20'6.5"
        import re
        feet_inches = re.match(r"(\d+)['\-](\d+(?:\.\d+)?)", dist_str)
        if feet_inches:
            feet = float(feet_inches.group(1))
            inches = float(feet_inches.group(2))
            return (feet * 12 + inches) * 0.0254  # Convert to meters
        
        # Handle meters format: 45.23m or 45.23
        meters_match = re.match(r'(\d+(?:\.\d+)?)m?', dist_str)
        if meters_match:
            return float(meters_match.group(1))
        
        return 0.0

    def _process_event(self, parser, file_path: str, event_config: dict, meet_id: int, default_gender: str = None):
        """Process a single event from a source file."""
        canonical_event = event_config.get('canonical_event')
        gender = event_config.get('gender', default_gender or '').lower()
        level = event_config.get('level', 'varsity')
        
        # Convert gender to M/F
        gender_code = 'M' if gender in ['boys', 'male', 'm'] else 'F' if gender in ['girls', 'female', 'f'] else 'U'
        
        logger.info(f"  Processing event: {canonical_event} ({gender}, {level})")
        
        # Get or create event in database
        if not canonical_event:
            logger.warning("    No canonical event specified")
            return
            
        event_info = self.event_matcher.get_event_info(canonical_event)
        event_id = self.db.get_or_create_event(canonical_event, event_info)
        
        # Parse results
        try:
            results = parser.parse(file_path, event_config)
        except Exception as e:
            logger.error(f"    Error parsing: {e}")
            return
        
        logger.info(f"    Found {len(results)} results")
        
        # Filter to Fort Collins athletes and save
        fc_count = 0
        for result in results:
            if self.school_matcher.is_target_school(result.school):
                self._save_result(result, event_id, meet_id, gender_code, level)
                fc_count += 1
        
        logger.info(f"    Saved {fc_count} Fort Collins results")

    def _save_result(self, result, event_id: int, meet_id: int, gender: str, level: str):
        """Save a single result to the database."""
        # Apply name mappings if configured for this meet
        athlete_name = result.athlete_name
        if hasattr(self, 'current_name_mappings') and athlete_name in self.current_name_mappings:
            athlete_name = self.current_name_mappings[athlete_name]
            logger.info(f"    Applied name mapping: {result.athlete_name} -> {athlete_name}")
        
        # Split name
        first_name, last_name = self._split_name(athlete_name)
        
        if not first_name and not last_name:
            return
        
        # Get or create athlete
        athlete_id = self.db.get_or_create_athlete(
            first_name=first_name,
            last_name=last_name,
            gender=gender
        )
        
        # Build notes - include relay team if present
        notes = result.notes or ""
        if hasattr(result, 'relay_team') and result.relay_team:
            relay_note = f"Relay Team: {result.relay_team}"
            notes = f"{relay_note}; {notes}" if notes else relay_note
        
        # Add result
        self.db.add_result(
            athlete_id=athlete_id,
            event_id=event_id,
            meet_id=meet_id,
            mark=result.mark,
            mark_display=result.mark_display,
            place=result.place,
            level=level,
            wind=result.wind,
            heat=result.heat,
            lane=result.lane,
            flight=result.flight,
            notes=notes
        )

    def _split_name(self, full_name: str) -> tuple[str, str]:
        """Split a full name into first and last name."""
        if not full_name:
            return "", ""
        
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


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Scrape track meet results')
    parser.add_argument('meet', nargs='?', help='Path to specific meet YAML file')
    parser.add_argument('--meet-dir', help='Path to directory containing meet YAML files (searches recursively)')
    parser.add_argument('--data-dir', '-d', help='Path to data directory')
    parser.add_argument('--db', help='Path to database file')
    parser.add_argument('--clear-results', action='store_true', help='Clear all results before scraping')
    parser.add_argument('--clear-meets', action='store_true', help='Clear all meets and results before scraping')
    parser.add_argument('--clear-all', action='store_true', help='Clear entire database before scraping')
    parser.add_argument('--no-historical', action='store_true', help='Skip importing historical school records')
    
    args = parser.parse_args()
    
    scraper = Scraper(data_dir=args.data_dir, db_path=args.db)
    
    # Handle clear options
    if args.clear_all:
        logger.warning("Clearing entire database...")
        scraper.db.clear_all()
    elif args.clear_meets:
        logger.warning("Clearing all meets and results...")
        scraper.db.clear_meets()
    elif args.clear_results:
        logger.warning("Clearing all results...")
        scraper.db.clear_results()
    
    # Import historical records first (unless disabled)
    if not args.no_historical:
        try:
            from pathlib import Path
            import sys
            # Import the historical records module
            scripts_path = Path(__file__).parent.parent / 'scripts'
            sys.path.insert(0, str(scripts_path))
            from import_historical_records import import_historical_records
            import_historical_records(args.db)
        except Exception as e:
            logger.warning(f"Could not import historical records: {e}")
    
    if args.meet:
        scraper.scrape_meet(args.meet)
    elif args.meet_dir:
        scraper.scrape_directory(args.meet_dir)
    else:
        scraper.scrape_all()
    
    logger.info("Scraping complete!")


if __name__ == '__main__':
    main()
