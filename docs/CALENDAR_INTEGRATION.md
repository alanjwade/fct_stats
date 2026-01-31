# Calendar Integration

## Overview
The FC Track & Field website now displays dynamic calendar events on the homepage, parsed from an exported calendar file.

## Files Changed

### 1. Calendar Parser Script
**File:** `scripts/parse_calendar.py`
- Parses calendar data from HTML accessibility tree JSON export
- Extracts event details: date, title, time, and location
- Outputs cleaned JSON to `config/calendar_events.json`

### 2. Calendar Data
**File:** `config/calendar_events.json`
- Contains parsed calendar events in JSON format
- Each event has: day, day_name, title, time, and optionally location
- Example:
  ```json
  {
    "day": "10",
    "day_name": "Saturday",
    "title": "Indoor HS Meet @ CO School of Mines",
    "time": "9:00 AM - 3:00 PM",
    "location": "Colorado School of Mines"
  }
  ```

### 3. Flask App
**File:** `webapp/app.py`
- Updated `index()` route to load calendar events from JSON file
- **Filters events to show only upcoming ones** (today or future dates)
- Parses dates in MM/DD/YYYY format
- Passes filtered events to template as `calendar_events` variable

### 4. Homepage Template  
**File:** `webapp/templates/index.html`
- Replaced hardcoded schedule with dynamic calendar events
- Shows up to 10 upcoming events in a responsive table
- **Displays actual date (MM/DD)** instead of just day number
- Shows event title, date, day of week, time, and location
- Mobile-friendly layout that adapts to screen size

## How to Update Calendar

### Method 1: Export from Calendar (Current Method)
1. Export calendar as HTML accessibility tree JSON
2. Save to `tmp/fct_calendar.json`
3. Run parser: `python3 scripts/parse_calendar.py`
4. Parser outputs to `config/calendar_events.json`
5. Restart webapp to see changes

### Method 2: Manual Edit (Quick Updates)
1. Edit `config/calendar_events.json` directly
2. Follow the JSON format shown above
3. Restart webapp to see changes

## Display Features

The homepage now shows:
- **Event Title**: Main event name (e.g., "Preseason Training", "Indoor HS Meet")
- **Date**: Actual date (MM/DD format) with day of week abbreviation
- **Time**: Event time or "All-day"
- **Location**: Venue name (desktop only, mobile shows in event cell)

**Important**: Only upcoming events (today or future) are displayed. Past events are automatically filtered out.

Events are displayed in chronological order, up to 10 upcoming events shown.

## Calendar Event Types

Currently displaying:
- **Winter Break** (All-day events)
- **Preseason Training** (Regular practice sessions)
- **Indoor HS Meets** (Competition events with location)
- **No School Days** (Holidays like MLK Day)

## Future Enhancements

Potential improvements:
1. Add actual dates (currently only showing day of month)
2. Parse multiple events on same day
3. Color-code event types (practice vs meets vs holidays)
4. Filter upcoming vs past events
5. Add iCal/.ics import support
6. Direct calendar API integration
