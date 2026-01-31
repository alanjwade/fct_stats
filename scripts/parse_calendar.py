#!/usr/bin/env python3
"""
Parse calendar data from HTML accessibility tree JSON export.
"""
import json
import re
from datetime import datetime

def extract_calendar_events(json_file):
    """Extract calendar events from accessibility tree JSON."""
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    events = []
    
    # Navigate to the list items
    if 'children' in data:
        for item in data['children']:
            if item.get('role') == 'listitem':
                event = parse_list_item(item)
                if event:
                    events.append(event)
    
    return events

def parse_list_item(item):
    """Parse a single calendar list item."""
    event = {}
    
    # Extract the name which contains: "DAY DayName Title Time Location Details"
    name = item.get('name', '')
    
    # Look for time element for date - search recursively
    def find_datetime(node):
        """Recursively search for datetime attribute."""
        if isinstance(node, dict):
            attrs = node.get('attributes', {})
            if 'datetime' in attrs:
                return attrs['datetime']
            # Search children
            for child in node.get('children', []):
                result = find_datetime(child)
                if result:
                    return result
        return None
    
    for child in item.get('children', []):
        if child.get('role') == 'time':
            datetime_val = find_datetime(child)
            if datetime_val:
                event['date'] = datetime_val
    
    # Parse the name to extract event details
    # Format: "DAY DayName Title Time Location Details"
    parts = name.split(' ')
    
    if len(parts) >= 2:
        # First part is day number
        event['day'] = parts[0]
        event['day_name'] = parts[1]
        
        # Extract title (text before time)
        # Look for time patterns like "4:20 PM - 5:45 PM" or "All-day"
        time_match = re.search(r'(\d{1,2}:\d{2}\s*[AP]M\s*-\s*\d{1,2}:\d{2}\s*[AP]M|All-day)', name)
        
        if time_match:
            time_start = time_match.start()
            # Title is everything between day name and time
            title_start = len(parts[0]) + len(parts[1]) + 2  # +2 for spaces
            title = name[title_start:time_start].strip()
            event['title'] = title
            event['time'] = time_match.group(1)
            
            # Rest after time is location/description
            remaining = name[time_match.end():].strip()
            # Remove the #color codes and "Group Calendar · Jeff Brennan"
            remaining = re.sub(r'#[0-9A-F]{6}\s*', '', remaining)
            remaining = re.sub(r'Group Calendar\s*·\s*Jeff Brennan\s*', '', remaining)
            if remaining:
                event['location'] = remaining.strip()
        else:
            # No time pattern found, title is everything after day name
            event['title'] = ' '.join(parts[2:])
    
    return event if event else None

def main():
    json_file = '/home/alan/Documents/code/fct_stats/tmp/fct_calendar.json'
    
    events = extract_calendar_events(json_file)
    
    print(f"Found {len(events)} calendar events:\n")
    
    for event in events:
        print(f"Date: {event.get('date', 'N/A')}")
        print(f"  Day: {event.get('day_name', 'N/A')}, {event.get('day', 'N/A')}")
        print(f"  Title: {event.get('title', 'N/A')}")
        print(f"  Time: {event.get('time', 'N/A')}")
        if 'location' in event:
            print(f"  Location: {event['location']}")
        print()
    
    # Save to a clean JSON file
    output_file = '/home/alan/Documents/code/fct_stats/tmp/parsed_calendar.json'
    with open(output_file, 'w') as f:
        json.dump(events, f, indent=2)
    
    print(f"\nSaved parsed events to {output_file}")

if __name__ == '__main__':
    main()
