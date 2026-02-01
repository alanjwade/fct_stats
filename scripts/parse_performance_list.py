#!/usr/bin/env python3
"""
Parse the ODS performance list file and convert to database-ready JSON.
"""

import json
import re
import sys
from pathlib import Path
from odf import opendocument, table, text
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from scraper.event_matcher import get_event_matcher


def get_row_cells(row):
    """Extract cells from a row, handling repeated cells and returning dict with column indices.
    
    Returns a dict mapping column_index -> cell object.
    Properly handles numbercolumnsrepeated to track actual Excel column positions.
    """
    cells = row.getElementsByType(table.TableCell)
    cell_dict = {}
    current_col_index = 0
    
    for cell in cells:
        # Check if cell is repeated
        repeat_count = cell.getAttribute('numbercolumnsrepeated')
        repeat = int(repeat_count) if repeat_count else 1
        
        # This cell occupies columns from current_col_index to current_col_index + repeat - 1
        for offset in range(repeat):
            col_index = current_col_index + offset
            cell_dict[col_index] = cell
        
        current_col_index += repeat
    
    return cell_dict


def get_cell_text(cell):
    """Extract text from an ODS cell."""
    try:
        text_content = []
        for p in cell.getElementsByType(text.P):
            for node in p.childNodes:
                if node.nodeType == node.TEXT_NODE:
                    text_content.append(str(node.data))
        return ' '.join(text_content).strip()
    except:
        return ''


def parse_name(name_str):
    """Parse athlete name into first and last name."""
    if not name_str or not name_str.strip():
        return None, None
    
    # Remove any extra whitespace
    name_str = ' '.join(name_str.split())
    
    # Handle "Last, First" format
    if ',' in name_str:
        parts = name_str.split(',')
        last_name = parts[0].strip()
        first_name = parts[1].strip() if len(parts) > 1 else ''
        return first_name, last_name
    
    # Handle "First Last" format
    parts = name_str.split()
    if len(parts) >= 2:
        first_name = parts[0]
        last_name = ' '.join(parts[1:])
        return first_name, last_name
    elif len(parts) == 1:
        return parts[0], ''
    
    return None, None


def parse_mark(mark_str):
    """Parse a performance mark and convert to seconds for timed events.
    
    Returns: (mark_value, mark_display, is_wind_assisted)
    """
    if not mark_str or mark_str.strip() in ['', '-', 'DNS', 'DNF', 'DQ', 'ND', 'NH', 'FOUL']:
        return None, mark_str.strip() if mark_str else None, False
    
    mark_str = mark_str.strip()
    is_wind_assisted = False
    
    # Check for wind-assisted marks (e.g., "12.42w" or "12.42w/12.48")
    # Extract just the first part before any '/' or trailing 'w'
    if '/' in mark_str:
        mark_str = mark_str.split('/')[0].strip()
    
    if mark_str.endswith('w') or mark_str.endswith('W'):
        is_wind_assisted = True
        mark_display = mark_str  # Keep the 'w' in display
        mark_str = mark_str[:-1].strip()  # Remove 'w' for parsing
    else:
        mark_display = mark_str
    
    # Check if it contains time format (minutes:seconds or just seconds)
    if ':' in mark_str:
        # Format: M:SS.ss or MM:SS.ss
        try:
            parts = mark_str.split(':')
            minutes = float(parts[0])
            seconds = float(parts[1])
            total_seconds = minutes * 60 + seconds
            return total_seconds, mark_display, is_wind_assisted
        except ValueError:
            return None, mark_display, is_wind_assisted
    
    # Try to parse as a plain number (seconds or distance)
    try:
        mark_value = float(mark_str.replace('"', '').replace("'", ''))
        return mark_value, mark_display, is_wind_assisted
    except ValueError:
        return None, mark_display, is_wind_assisted


def infer_event_from_record(record_text, gender):
    """Infer event name from school record text."""
    # Extract the mark from "School Record: XX.XX (Athlete)" format
    match = re.search(r'School Record:\s*([\d:.-]+)', record_text)
    if not match:
        return None
    
    mark_str = match.group(1)
    
    # Known school records to help identify events
    # Based on historical_records.json and the spreadsheet
    boys_records = {
        '10.27': '100m',
        '20.84': '200m',
        '20.87': '200m',  # Updated record
        '47.14': '400m',
        '1:54.18': '800m',
        '114.18': '800m',  # in seconds
        '4:16.91': '1600m',
        '4:12.96': '1600m',  # Updated record
        '256.91': '1600m',  # in seconds
        '252.96': '1600m',  # in seconds
        '9:17.20': '3200m',
        '9:15.58': '3200m',  # Updated record
        '557.20': '3200m',  # in seconds
        '555.58': '3200m',  # in seconds
        '14.45': '110m Hurdles',
        '14.21': '110m Hurdles',  # Updated record
        '37.92': '300m Hurdles',
        '37.85': '300m Hurdles',  # Updated record
        '6-6': 'High Jump',
        '6-08.50': 'High Jump',  # Updated record
        '14-0': 'Pole Vault',
        '14-06.00': 'Pole Vault',  # Updated record
        '22-10.5': 'Long Jump',
        '24-00.75': 'Long Jump',  # Updated record
        '45-6': 'Triple Jump',
        '49-09.25': 'Triple Jump',  # Updated record
        '56-5.5': 'Shot Put',
        '60-04.50': 'Shot Put',  # Updated record
        '170-9': 'Discus',
        '174-08.00': 'Discus',  # Updated record
        '41.81': '4x100m Relay',
        '1:27.91': '4x200m Relay',
        '1:27.09': '4x200m Relay',  # Updated record
        '3:21.24': '4x400m Relay',
        '3:15.38': '4x400m Relay',  # Updated record
        '7:54.67': '4x800m Relay',
        '7:53.81': '4x800m Relay',  # Updated record
    }
    
    girls_records = {
        '11.91': '100m',
        '24.13': '200m',
        '55.82': '400m',
        '53.64': '400m',  # Updated record
        '2:12.57': '800m',
        '2:10.94': '800m',  # Updated record
        '5:04.59': '1600m',
        '4:50.77': '1600m',  # Updated record
        '11:00.20': '3200m',
        '10:16.43': '3200m',  # Updated record
        '15.11': '100m Hurdles',
        '15.07': '100m Hurdles',  # Updated record
        '45.87': '300m Hurdles',
        '42.91': '300m Hurdles',  # Updated record
        '5-2': 'High Jump',
        '5-09.00': 'High Jump',  # Updated record
        '11-6': 'Pole Vault',
        '10-00.00': 'Pole Vault',  # Updated record
        '18-5.25': 'Long Jump',
        '19-08.50': 'Long Jump',  # Updated record
        '37-5.75': 'Triple Jump',
        '39-07.00': 'Triple Jump',  # Updated record
        '40-7.5': 'Shot Put',
        '50-04.50': 'Shot Put',  # Updated record
        '126-7': 'Discus',
        '161-01.00': 'Discus',  # Updated record
        '48.72': '4x100m Relay',
        '47.97': '4x100m Relay',  # Updated record
        '1:43.40': '4x200m Relay',
        '1:40.20': '4x200m Relay',  # Updated record
        '3:56.48': '4x400m Relay',
        '3:49.52': '4x400m Relay',  # Updated record
        '9:16.75': '4x800m Relay',
        '9:06.06': '4x800m Relay',  # Updated record
    }
    
    records = boys_records if gender == 'M' else girls_records
    
    # Direct lookup
    if mark_str in records:
        return records[mark_str]
    
    # Try to match by converting time formats
    # If mark contains ':', it's a time
    if ':' in mark_str:
        # Try converting to seconds
        parts = mark_str.split(':')
        if len(parts) == 2:
            try:
                minutes = int(parts[0])
                seconds = float(parts[1])
                total_seconds = minutes * 60 + seconds
                sec_str = f"{total_seconds:.2f}"
                if sec_str in records:
                    return records[sec_str]
            except:
                pass
    
    return None


def extract_event_name(cell_text):
    """Extract event name from cell text that may have extra information."""
    if not cell_text:
        return None
    
    # Handle "School Record: 10.27 (Raymond Bozmans)" format
    # The event name is not in this text, so return None for this pattern
    if 'School Record' in cell_text or 'Record:' in cell_text:
        # Try to extract a number pattern that might indicate the event
        # e.g., "10.27" suggests 100m
        return None  # We'll need to look elsewhere for the event name
    
    # Common patterns: "100m - Sprint" or "100M DASH" or "100m (some text)"
    # Look for event patterns
    patterns = [
        r'(\d+m)',  # Distance events like 100m, 200m, 800m, etc.
        r'(\d+M)',  # Same but uppercase
        r'(Mile)',  # Mile
        r'(Shot Put)',
        r'(Discus)',
        r'(Javelin)',
        r'(High Jump)',
        r'(Long Jump)',
        r'(Triple Jump)',
        r'(Pole Vault)',
        r'(\d+m Hurdles)',
        r'(\d+M Hurdles)',
        r'(\d+m Relay)',
        r'(\d+M Relay)',
        r'(\d+x\d+m?)',  # Relay format like 4x100m
        r'(\d+x\d+M?)',  # Relay format uppercase
    ]
    
    # Try to find a match
    cell_text_lower = cell_text.lower()
    for pattern in patterns:
        match = re.search(pattern, cell_text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return cell_text.strip()


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


def parse_sheet(sheet, event_matcher, gender, meet_dates):
    """Parse a single sheet from the ODS file."""
    results = []
    rows = sheet.getElementsByType(table.TableRow)
    
    current_event = None
    event_id = None
    meet_columns = {}  # Map column index to meet name
    event_row_idx = -1
    
    for row_idx, row in enumerate(rows):
        cells = get_row_cells(row)
        if not cells:
            continue
        
        # Check if column A contains an event name (e.g., "100m" or "100m (text)")
        # This handles merged cells where A1:A2 contains the event
        cell_a = cells.get(0)
        cell_a_text = get_cell_text(cell_a) if cell_a else ''
        
        # Try to extract event from column A first
        event_from_a = None
        if cell_a_text:
            # Look for event patterns like "100m", "100m Hurdles", etc.
            # Match things like "100m", "100m (other text)", "110m Hurdles", etc.
            event_match = re.match(r'^(\d+m(?:\s+Hurdles)?|High Jump|Long Jump|Triple Jump|Pole Vault|Shot Put|Discus|Javelin)', cell_a_text, re.IGNORECASE)
            if event_match:
                event_from_a = event_match.group(1)
        
        # Also check if this row contains an event header in column B (old method)
        cell_b = cells.get(1)
        cell_b_text = get_cell_text(cell_b) if cell_b else ''
        
        if event_from_a or (cell_b_text and ('School Record' in cell_b_text or 'Record:' in cell_b_text)):
            # This is likely an event header row
            # Prefer event from column A if available, otherwise infer from school record
            potential_event = event_from_a
            
            if not potential_event and cell_b_text:
                # Infer event from the school record
                potential_event = infer_event_from_record(cell_b_text, gender)
            
            if potential_event:
                # Try to match to canonical event
                canonical_event = event_matcher.match(potential_event, gender)
                if canonical_event:
                    current_event = canonical_event
                    event_row_idx = row_idx
                    meet_columns = {}
                    
                    # Parse meet headers from next row (row_idx + 1)
                    # Meets start at column D (index 3) based on the actual spreadsheet layout
                    if row_idx + 1 < len(rows):
                        header_row = rows[row_idx + 1]
                        header_cells = get_row_cells(header_row)
                        
                        # DEBUG: Print the headers we're finding
                        debug_headers = []
                        
                        for col_idx in range(3, 100):  # Check columns D through CV
                            if col_idx in header_cells:
                                meet_name = get_cell_text(header_cells[col_idx])
                                if meet_name and meet_name.strip() and meet_name.strip() not in ['PR', '2024 SB', 'SB', 'Season Best']:
                                    meet_columns[col_idx] = meet_name.strip()
                    
                    print(f"  Found event: {current_event} with {len(meet_columns)} meets")
                    continue
                else:
                    print(f"  Warning: Could not match inferred event '{potential_event}' to canonical event")
            else:
                if cell_b_text:
                    print(f"  Warning: Could not infer event from: {cell_b_text[:60]}")
        
        # If we have a current event and we're past the header row, parse athlete data
        # Data starts at row event_row_idx + 2 (event header, then column header, then data)
        if current_event and event_row_idx >= 0 and row_idx > event_row_idx + 1:
            # Column A (index 0) should have athlete name
            cell_a = cells.get(0)
            athlete_name = get_cell_text(cell_a) if cell_a else ''
            
            # If no name or it looks like another event header, we're done with this event
            if not athlete_name or 'School Record' in athlete_name or 'Record:' in athlete_name:
                current_event = None
                event_row_idx = -1
                meet_columns = {}
                continue
            
            first_name, last_name = parse_name(athlete_name)
            if not first_name and not last_name:
                # Not a valid athlete row
                continue
            
            # Parse column B (all-time PR), C (2024 SB), D (2025 SB)
            # Note: The indices are 0-based, so A=0, B=1, C=2, D=3
            all_time_pr = get_cell_text(cells.get(1)) if 1 in cells else ''
            sb_2024 = get_cell_text(cells.get(2)) if 2 in cells else ''
            sb_2025 = get_cell_text(cells.get(3)) if 3 in cells else ''
            
            # Parse meet results from columns D onwards
            for col_idx, meet_name in meet_columns.items():
                if col_idx in cells:
                    mark_str = get_cell_text(cells[col_idx])
                    mark_value, mark_display, is_wind = parse_mark(mark_str)
                    
                    if mark_value is not None:
                        result = {
                            'event': current_event,
                            'athlete_first': first_name,
                            'athlete_last': last_name,
                            'gender': gender,
                            'meet': meet_name,
                            'mark': mark_value,
                            'mark_display': mark_display,
                            'year': 2025,  # Assuming this is 2025 data
                            'level': 'varsity'
                        }
                        # Add date and level from meet_info if available
                        if meet_name in meet_dates:
                            result['date'] = meet_dates[meet_name]['date']
                            result['level'] = meet_dates[meet_name]['level']
                        if is_wind:
                            result['wind_assisted'] = True
                        results.append(result)
    
    return results


def parse_ods_file(ods_path, meet_dates):
    """Parse the ODS file and extract all results."""
    print(f"Opening {ods_path}...")
    doc = opendocument.load(str(ods_path))
    
    event_matcher = get_event_matcher()
    all_results = []
    
    sheets = doc.spreadsheet.getElementsByType(table.Table)
    print(f"Found {len(sheets)} sheets")
    
    for sheet_idx, sheet in enumerate(sheets):
        sheet_name = sheet.getAttribute('name')
        print(f"\nProcessing sheet {sheet_idx + 1}: {sheet_name}")
        
        # Try to determine gender from sheet name
        gender = None
        if 'boy' in sheet_name.lower() or 'men' in sheet_name.lower() or 'male' in sheet_name.lower():
            gender = 'M'
        elif 'girl' in sheet_name.lower() or 'women' in sheet_name.lower() or 'female' in sheet_name.lower():
            gender = 'F'
        
        if not gender:
            print(f"  Warning: Could not determine gender from sheet name '{sheet_name}', skipping")
            continue
        
        print(f"  Detected gender: {'Male' if gender == 'M' else 'Female'}")
        sheet_results = parse_sheet(sheet, event_matcher, gender, meet_dates)
        all_results.extend(sheet_results)
        print(f"  Extracted {len(sheet_results)} results from this sheet")
    
    return all_results


def main():
    """Main entry point."""
    # Load meet info (dates and levels) from config
    meet_info = load_meet_dates()
    print(f"Loaded {len(meet_info)} meets from config/meets_2025.json")
    
    # Find the ODS file
    ods_path = Path(__file__).parent.parent / 'data' / 'sources' / 'current' / '2025' / '2025 Track & Field Performance List.xlsx.ods'
    
    if not ods_path.exists():
        print(f"Error: ODS file not found at {ods_path}")
        return 1
    
    # Parse the file
    results = parse_ods_file(ods_path, meet_info)
    
    print(f"\n{'='*60}")
    print(f"Total results extracted: {len(results)}")
    
    # Save to JSON
    output_path = Path(__file__).parent.parent / 'data' / 'generated' / 'parsed' / 'parsed_performance_list.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to: {output_path}")
    
    # Print summary statistics
    events = set(r['event'] for r in results)
    athletes = set((r['athlete_first'], r['athlete_last']) for r in results)
    meets = set(r['meet'] for r in results)
    
    print(f"\nSummary:")
    print(f"  Unique events: {len(events)}")
    print(f"  Unique athletes: {len(athletes)}")
    print(f"  Unique meets: {len(meets)}")
    
    print(f"\nEvents found:")
    for event in sorted(events):
        count = sum(1 for r in results if r['event'] == event)
        print(f"  {event}: {count} results")
    
    # Check if import_historical_records.py structure could work
    print(f"\n{'='*60}")
    print("Analysis for import compatibility:")
    print("\nThe import_historical_records.py script expects this JSON structure:")
    print("""
    {
      "boys": [
        {
          "event": "100m",
          "athlete": "First Last",
          "mark": 10.27,
          "mark_display": "10.27",
          "location": "Meet Name",
          "year": 2025,
          "gender": "M",
          "is_relay": false,
          "relay_members": []
        }
      ],
      "girls": [...]
    }
    """)
    print("\nOur parsed data has a different structure:")
    print("""
    [
      {
        "event": "100m",
        "athlete_first": "First",
        "athlete_last": "Last",
        "gender": "M",
        "meet": "Meet Name",
        "mark": 10.27,
        "mark_display": "10.27",
        "year": 2025,
        "level": "varsity"
      }
    ]
    """)
    print("\nConclusion:")
    print("The import_historical_records.py script COULD be adapted to import")
    print("these results, but it would need modifications:")
    print("  1. Accept the new JSON format (or convert it first)")
    print("  2. Handle multiple results per athlete per event (different meets)")
    print("  3. The current script assumes one record per athlete per event")
    print("\nRecommendation: Create a new import script specifically for")
    print("performance list data, or create a converter to transform this")
    print("data into individual meet files that the scraper can process.")
    
    return 0


if __name__ == '__main__':
    exit(main())
