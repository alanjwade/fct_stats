#!/usr/bin/env python3
"""
Parse historical school records from markdown files and generate JSON.
"""

import json
import re
from pathlib import Path


def parse_imperial_to_meters(mark_str):
    """Convert feet/inches marks to meters."""
    # Clean up the string - handle both regular and curly quotes
    mark_str = mark_str.strip()
    # Replace all variants of curly quotes with straight quotes
    mark_str = mark_str.replace("'", "'").replace("'", "'").replace("‛", "'").replace("′", "'")
    mark_str = mark_str.replace(""", '"').replace(""", '"').replace("″", '"')
    # Also handle Unicode characters by code point
    mark_str = mark_str.replace(chr(8217), "'")  # RIGHT SINGLE QUOTATION MARK
    mark_str = mark_str.replace(chr(8216), "'")  # LEFT SINGLE QUOTATION MARK
    mark_str = mark_str.replace(chr(8221), '"')  # RIGHT DOUBLE QUOTATION MARK
    mark_str = mark_str.replace(chr(8220), '"')  # LEFT DOUBLE QUOTATION MARK
    
    # Pattern: 14'6" or 24'0.25" or 6'8.5" or 38' 6" (with space)
    match = re.match(r"(\d+)'\s*(\d+\.?\d*)\"?", mark_str)
    if match:
        feet = int(match.group(1))
        inches = float(match.group(2))
        total_inches = feet * 12 + inches
        meters = total_inches * 0.0254
        return round(meters, 4)
    
    return None


def parse_time_to_seconds(mark_str):
    """Convert time string to seconds."""
    mark_str = mark_str.strip()
    
    # Handle times with periods instead of colons (e.g., 1.27.09 or 9.06.06)
    # Pattern: M.MM.SS format
    period_count = mark_str.count('.')
    if period_count == 2:
        # This is M.MM.SS format - replace periods with colons appropriately
        parts = mark_str.split('.')
        mark_str = f"{parts[0]}:{parts[1]}.{parts[2]}"
    
    # Pattern: HH:MM:SS.ss or MM:SS.ss or M:SS.ss
    if ':' in mark_str:
        parts = mark_str.split(':')
        
        # Handle H:MM:SS.ss or HH:MM:SS.ss format (e.g., 1:27:09 or 12:43:15)
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return round(hours * 3600 + minutes * 60 + seconds, 2)
        elif len(parts) == 2:
            minutes = int(parts[0])
            seconds = float(parts[1])
            return round(minutes * 60 + seconds, 2)
    
    # Pattern: SS.ss (just seconds)
    try:
        return round(float(mark_str), 2)
    except ValueError:
        return None


def infer_year_from_location(location_str):
    """Extract year from location string like 'State 2012'."""
    match = re.search(r'(\d{4})', location_str)
    if match:
        return int(match.group(1))
    return None


def parse_event_type(event_name):
    """Determine if event is timed (True) or distance/height (False)."""
    timed_events = ['100m', '200m', '400m', '800m', '1600m', '3200m', 
                    '110m High Hurdles', '100M High Hurdles', 
                    '300m Int. Hurdles', '300M Low Hurdles',
                    'Relay', 'relay', 'Medley', 'medley']
    
    for timed in timed_events:
        if timed.lower() in event_name.lower():
            return True
    return False


def parse_boys_records():
    """Parse boys track records from markdown."""
    records = []
    
    file_path = Path(__file__).parent.parent / 'tmp' / 'FCHS Boys Track & Field Records.docx.md'
    with open(file_path, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('**') or 'EVENT' in line or 'ATHLETE' in line:
            continue
        
        # Parse individual events
        # Pattern: EVENT    ATHLETE    MARK    LOCATION
        parts = re.split(r'\t+', line)
        if len(parts) < 4:
            continue
        
        event = parts[0].strip()
        athlete = parts[1].strip()
        mark_str = parts[2].strip()
        location = parts[3].strip()
        
        if not event or not athlete or not mark_str:
            continue
        
        # Check if this is a relay event
        is_relay = 'relay' in event.lower() or '4x' in event.lower()
        
        # Parse mark based on event type
        is_timed = parse_event_type(event)
        
        if is_timed:
            mark_value = parse_time_to_seconds(mark_str)
        else:
            mark_value = parse_imperial_to_meters(mark_str)
        
        if mark_value is None:
            print(f"Warning: Could not parse mark '{mark_str}' for {event}")
            continue
        
        year = infer_year_from_location(location)
        
        record = {
            'event': event,
            'athlete': athlete,
            'mark': mark_value,
            'mark_display': mark_str,
            'location': location,
            'year': year,
            'gender': 'M',
            'is_relay': is_relay,
            'relay_members': []
        }
        
        records.append(record)
    
    # Now find relay team members in subsequent lines
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Check if this line contains relay designation like (4x100)
        # and possibly the first relay member
        if re.match(r'^\([0-9x-]+\)', line_stripped):
            # Parse out any athlete name on this line
            parts = re.split(r'\t+', line)
            additional_member = None
            if len(parts) >= 2:
                additional_member = parts[1].strip()
            
            # Find the most recent relay record (should be immediately before this line)
            for record in reversed(records):
                if record['is_relay'] and not record['relay_members']:
                    members = []
                    
                    # Add the primary athlete from the main event line
                    if record['athlete']:
                        members.append(record['athlete'])
                    
                    # Add additional member from this (4x100) line if present
                    if additional_member and len(additional_member) > 1:
                        members.append(additional_member)
                    
                    # Get the remaining team members from following lines
                    for j in range(i+1, min(i+5, len(lines))):
                        raw_line = lines[j]
                        member_line = raw_line.strip()
                        
                        # Skip empty lines and header lines
                        if not member_line or member_line.startswith('**'):
                            continue
                        
                        # Stop if we hit another event
                        # Events have text before the first tab, member lines start with tabs
                        if not raw_line.startswith('\t') and not raw_line.startswith(' '):
                            break
                        
                        # Add the member
                        if member_line and len(member_line) > 1 and not member_line.startswith('('):
                            members.append(member_line)
                        if len(members) >= 4:
                            break
                    
                    record['relay_members'] = members
                    break
    
    return records


def parse_girls_records():
    """Parse girls track records from markdown."""
    records = []
    
    file_path = Path(__file__).parent.parent / 'tmp' / 'FCHS Girls Track & Field Records.docx.md'
    with open(file_path, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('**') or 'EVENT' in line or 'ATHLETE' in line:
            continue
        
        # Parse individual events - handle variable whitespace
        # Split on multiple spaces (at least 2)
        parts = re.split(r'\s{2,}', line)
        if len(parts) < 4:
            continue
        
        event = parts[0].strip()
        athlete = parts[1].strip()
        mark_str = parts[2].strip()
        location = parts[3].strip()
        
        if not event or not athlete or not mark_str:
            continue
        
        # Check if this is a relay event
        is_relay = 'relay' in event.lower() or '4x' in event.lower()
        
        # Parse mark based on event type
        is_timed = parse_event_type(event)
        
        if is_timed:
            mark_value = parse_time_to_seconds(mark_str)
        else:
            mark_value = parse_imperial_to_meters(mark_str)
        
        if mark_value is None:
            print(f"Warning: Could not parse mark '{mark_str}' for {event}")
            continue
        
        year = infer_year_from_location(location)
        
        record = {
            'event': event,
            'athlete': athlete,
            'mark': mark_value,
            'mark_display': mark_str,
            'location': location,
            'year': year,
            'gender': 'F',
            'is_relay': is_relay,
            'relay_members': []
        }
        
        records.append(record)
    
    # Find relay team members
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Check if this line contains relay info like (4x100)
        # and possibly the first relay member after the primary athlete
        if re.match(r'^\([0-9x-]+\)', line_stripped):
            # Parse out any athlete name on this line (girls format uses spaces not tabs)
            parts = re.split(r'\s{2,}', line)
            additional_member = None
            if len(parts) >= 2:
                # First part is (4x100), second might be athlete name
                additional_member = parts[1].strip() if len(parts[1].strip()) > 3 else None
            
            # Find the previous relay record
            for record in reversed(records):
                if record['is_relay'] and not record['relay_members']:
                    members = []
                    
                    # Add the primary athlete from the main event line
                    if record['athlete']:
                        members.append(record['athlete'])
                    
                    # Add additional member from this line if present
                    if additional_member and len(additional_member) > 1:
                        members.append(additional_member)
                    
                    # Get the remaining team members from following lines
                    for j in range(i+1, min(i+5, len(lines))):
                        member_line = lines[j].strip()
                        # Skip empty lines and header lines
                        if not member_line or member_line.startswith('**'):
                            continue
                        # Stop if we hit another event (has multiple spaces indicating columns)
                        if re.search(r'\s{2,}', lines[j]) and not lines[j].startswith(' '):
                            break
                        # Add the member
                        if member_line and len(member_line) > 1 and not member_line.startswith('('):
                            members.append(member_line)
                        if len(members) >= 4:
                            break
                    
                    record['relay_members'] = members
                    break
    
    return records


def main():
    """Main entry point."""
    print("Parsing historical records...")
    
    boys_records = parse_boys_records()
    girls_records = parse_girls_records()
    
    all_records = {
        'boys': boys_records,
        'girls': girls_records,
        'total_count': len(boys_records) + len(girls_records)
    }
    
    # Save to JSON
    output_path = Path(__file__).parent.parent / 'data' / 'historical_records.json'
    with open(output_path, 'w') as f:
        json.dump(all_records, f, indent=2)
    
    print(f"Parsed {len(boys_records)} boys records")
    print(f"Parsed {len(girls_records)} girls records")
    print(f"Total: {all_records['total_count']} records")
    print(f"Saved to: {output_path}")
    
    # Print summary
    print("\nSummary:")
    print(f"Boys relays: {sum(1 for r in boys_records if r['is_relay'])}")
    print(f"Girls relays: {sum(1 for r in girls_records if r['is_relay'])}")


if __name__ == '__main__':
    main()
