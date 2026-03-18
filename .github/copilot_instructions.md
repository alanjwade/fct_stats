# Fort Collins Track Stats - Copilot Instructions

This document provides context for AI assistants (like GitHub Copilot) working on the Fort Collins High School Track & Field statistics website.

## Project Overview

A Flask-based web application for displaying track & field statistics, personal records, and meet results for Fort Collins High School athletes. The project has **two distinct components**:

1. **Data Pipeline** (scraper + scripts): Parses meet results and populates database
2. **Web Application** (webapp): Read-only Flask app that displays statistics

**Critical: The webapp NEVER writes to the database. Only scripts do.**

---

## Architecture

### Directory Structure

```
fct_stats/
├── config/                    # Configuration files
│   ├── canonical_events.yaml # Event definitions and aliases
│   ├── meets_2025.json       # 2025 meet dates and levels
│   ├── calendar_events.json  # Calendar integration
│   └── schools.yaml          # School matching
├── data/                      # Data files
│   ├── sources/              # Source data (raw inputs)
│   │   ├── current/          # Current season data
│   │   │   ├── 2025/        # 2025 spreadsheets and configs
│   │   │   ├── pages/       # Raw HTML/TXT meet results
│   │   │   └── meets/       # Meet configuration YAMLs
│   │   └── historic/        # Historical records (markdown)
│   └── generated/            # Generated outputs (regenerable)
│       ├── db/
│       │   └── fct_stats.db  # SQLite database
│       └── parsed/           # Parsed JSON results
│           ├── meets/       # Individual meet JSON files
│           ├── historical_records.json
│           └── parsed_performance_list.json
├── database/
│   └── schema.sql            # Database schema definition
├── scraper/                   # Core parsing library
│   ├── database.py           # Database write operations (used by scripts only)
│   ├── event_matcher.py      # Event name canonicalization
│   ├── school_matcher.py     # School name matching
│   └── parsers/              # HTML parsing modules
├── scripts/                   # Data import/parsing scripts
│   ├── parse_performance_list.py    # Parse ODS performance spreadsheet
│   ├── parse_historical_records.py  # Parse markdown historical records
│   └── import_all_records.py        # Import all data to database
├── webapp/                    # Flask web application (READ-ONLY)
│   ├── app.py                # Main Flask app
│   ├── templates/            # Jinja2 templates
│   └── static/               # CSS, JS, images
└── docker/                    # Docker deployment configs
```

### Database Schema

SQLite database (`data/generated/db/fct_stats.db`) with tables:

- **athletes**: Athlete information (name, gender, graduation year)
- **events**: Canonical event definitions (100m, Long Jump, etc.)
- **meets**: Meet information (name, date, venue, level)
- **results**: Individual performance results
- **relay_members**: Relay team composition

**Key constraint**: `results` table has `UNIQUE(athlete_id, event_id, meet_id)` - one result per athlete per event per meet.

### Data Flow

```
Raw Data Sources
    ↓
[parse_performance_list.py] ← ODS: data/sources/current/2025/*.ods
[parse_historical_records.py] ← Markdown: data/sources/historic/*.md
    ↓
JSON Files (data/generated/parsed/)
    ↓
[import_all_records.py] ← meets config: data/sources/current/2025/meets_2025.json
    ↓
SQLite Database (data/generated/db/fct_stats.db)
    ↓
[Flask Webapp] → HTML Views
```

**The webapp only READS from the database. It never writes.**

---

## Key Components

### 1. Event Matching System

**Location**: `scraper/event_matcher.py`

- Canonicalizes event names from various formats
- Uses `config/canonical_events.yaml` for mappings
- Example: "100 Meters" → "100m", "Long Jump" → "Long Jump"
- Gender-specific events: "110m Hurdles" (M), "100m Hurdles" (F)

**When editing**:
- All event names in database must match canonical form
- Add aliases to `canonical_events.yaml` for new variations
- Event properties: `category`, `timed`, `lower_is_better`, `is_relay`

### 2. Meet Date Configuration

**Location**: `config/meets_2025.json`

Structure:
```json
{
  "meets": [
    {
      "name": "Longmont Invite",
      "date": "2025-04-25",
      "level": "varsity"
    }
  ]
}
```

- **Priority order** for date matching:
  1. `meets_2025.json` (highest priority)
  2. `calendar_events.json` (word matching)
  3. Embedded year in meet name ("State 2012" → 2012-03-15)
  4. Record year → YYYY-03-15

- **Level values**: `"varsity"`, `"jv"`, `"open"`
- JV meets: Names containing "JV" should have `level: "jv"`

### 3. Data Parsing Scripts

#### `parse_performance_list.py`

Parses ODS spreadsheet (`data/sources/current/2025/2025 Track & Field Performance List.xlsx.ods`):

- 6 sheets: Girls Track, Girls Field, Girls Relays, Boys Track, Boys Field, Boys Relays
- Event headers in column A, meets starting in column D
- Skips columns: `['PR', '2024 SB', 'SB', 'Season Best']`
- Loads dates/levels from `data/sources/current/2025/meets_2025.json`
- Outputs: `data/generated/parsed/parsed_performance_list.json`

**Critical**: Uses dict-based cell mapping to handle merged cells correctly.

#### `parse_historical_records.py`

Parses markdown historical records files:

- Handles variable whitespace/tabs in markdown tables
- Parses relay team members (comma-separated names)
- Outputs same JSON format as performance list
- Outputs: `data/generated/parsed/historical_records.json`

#### `import_all_records.py`

Main import script that:

1. Clears database (if `--no-clear` not specified)
2. Loads `meets_2025.json` for date/level mapping
3. Imports historical records
4. Imports performance records
5. Uses `scraper/database.py` for all writes

**Usage**:
```bash
python3 scripts/import_all_records.py          # Clear and reimport all
python3 scripts/import_all_records.py --no-clear  # Add without clearing
```

### 4. Flask Web Application

**Location**: `webapp/app.py`

**READ-ONLY APPLICATION** - Never modifies database.

Key routes:
- `/` - Home page with overview
- `/stats` - Performance statistics and charts
- `/athletes` - Athletes list with filtering
- `/athlete/<id>` - Individual athlete statistics
- `/events` - Events list
- `/event/<name>` - Event leaderboard and records
- `/team-bests` - Team records (historical best per event)
- `/season-bests-2025` - 2025 season bests per athlete per event

**Database Access Pattern**:
```python
def get_db_connection():
    """Context manager for read-only database access."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Access by column name
    return conn

# Usage in routes
with get_db_connection() as conn:
    cursor = conn.cursor()
    results = cursor.execute("SELECT ...").fetchall()
```

**Template System**:
- Base template: `templates/base.html` (FC purple/gold theme)
- FC Colors: `--fc-purple: #4B286D`, `--fc-gold: #C4A000`
- Bootstrap 5 + bootstrap-icons
- Responsive design with mobile support

### 5. Scraper Library

**Location**: `scraper/database.py`

Database write operations used by scripts:

```python
db = get_database()  # Creates/connects to database

# Core methods
db.get_or_create_athlete(first_name, last_name, gender, graduation_year)
db.get_or_create_event(name, event_info)
db.get_or_create_meet(name, meet_date, venue, location, season, level)
db.add_result(athlete_id, event_id, meet_id, mark, mark_display, ...)
db.add_relay_member(result_id, athlete_id, leg_order)
db.clear_all()  # Clears all data
```

**Important**: Returns `None` if duplicate exists (violates UNIQUE constraint).

---

## Common Workflows

### Adding New 2025 Meet Data

1. **Update meets config**:
   ```bash
   # Edit config/meets_2025.json
   # Add meet with name, date, level
   ```

2. **Update ODS spreadsheet**:
   ```
   Update: tmp/2025 Track & Field Performance List.xlsx.ods
   Add meet column with results
   ```

3. **Re-parse and import**:
   ```bash
   python3 scripts/parse_performance_list.py
   python3 scripts/import_all_records.py
   ```

### Adding Historical Records

1. **Update markdown file** in `tmp/` (or create JSON directly)

2. **Parse markdown**:
   ```bash
   python3 scripts/parse_historical_records.py
   ```

3. **Import**:
   ```bash
   python3 scripts/import_all_records.py
   ```

### Adding New Event Type

1. **Add to canonical events**:
   ```yaml
   # config/canonical_events.yaml
   - name: "Javelin"
     aliases: ["Javelin Throw"]
     category: "throws"
     timed: false
     lower_is_better: false
   ```

2. **Re-import data** (event matcher will apply new mappings)

### Modifying Meet Dates

1. **Edit** `config/meets_2025.json`
2. **Re-import**: `python3 scripts/import_all_records.py`

---

## Design Patterns & Best Practices

### DO:

- **Use meet config for dates**: Always prioritize `meets_2025.json`
- **Read-only webapp**: Webapp queries database, never writes
- **Canonical events**: Use `event_matcher.match()` for all event names
- **Context managers**: Use `with get_db_connection()` pattern
- **Parameterized queries**: Always use `?` placeholders for SQL
- **Gender specification**: Explicitly specify 'M' or 'F' for all results
- **Level specification**: Use 'varsity', 'jv', or 'open' consistently

### DON'T:

- **Don't modify database from webapp**: All writes happen in scripts
- **Don't hardcode event names**: Always use canonical form
- **Don't duplicate results**: Check UNIQUE constraints before insert
- **Don't skip date config**: Maintain `meets_2025.json` for accuracy
- **Don't mix data sources**: Keep historical vs performance separate
- **Don't run `publish-and-restart.sh` unless explicitly asked**: The user controls when to deploy. Never run `./scripts/publish-and-restart.sh` (or any of the `publish-*.sh` / `homelab-*.sh` scripts) as part of a fix or investigation unless the user specifically requests it.

### Database Queries

**Good Pattern**:
```python
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.first_name, a.last_name, r.mark_display
        FROM results r
        JOIN athletes a ON r.athlete_id = a.id
        WHERE a.gender = ? AND r.event_id = ?
        ORDER BY r.mark ASC
    """, (gender, event_id))
    results = cursor.fetchall()
```

**Bad Pattern**:
```python
# DON'T: No context manager, string formatting
conn = sqlite3.connect(DATABASE_PATH)
query = f"SELECT * FROM results WHERE gender = '{gender}'"  # SQL injection risk!
```

---

## Testing & Debugging

### Verify Data Import

```bash
# Check record counts
python3 -c "
from scraper.database import get_database
db = get_database()
with db.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM results')
    print(f'Total results: {cursor.fetchone()[0]}')
"
```

### Check Athlete Results

```bash
python3 -c "
from scraper.database import get_database
db = get_database()
with db.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute('''
        SELECT e.name, m.name, m.meet_date, r.mark_display
        FROM results r
        JOIN events e ON r.event_id = e.id
        JOIN meets m ON r.meet_id = m.id
        JOIN athletes a ON r.athlete_id = a.id
        WHERE a.first_name = 'FirstName' AND a.last_name = 'LastName'
        ORDER BY e.name, m.meet_date
    ''')
    for row in cursor.fetchall():
        print(row)
"
```

### Validate Meet Dates

Check that meets are using config dates vs defaults:

```python
import json
from scraper.database import get_database

config = json.load(open('config/meets_2025.json'))
config_meets = {m['name']: m['date'] for m in config['meets']}

db = get_database()
with db.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT name, meet_date FROM meets WHERE meet_date LIKE '2025%'")
    
    for name, db_date in cursor.fetchall():
        config_date = config_meets.get(name)
        if config_date and db_date != config_date:
            print(f"Mismatch: {name} - DB: {db_date}, Config: {config_date}")
```

---

## Deployment

### Docker Setup

Two environments:

1. **Development** (`docker-compose.dev.yml`):
   - Flask debug mode enabled
   - Volume mounts for live editing
   - Port 5000 exposed

2. **Production** (`docker-compose.yml`):
   - Nginx reverse proxy
   - Gunicorn WSGI server
   - Port 80/443

**Commands**:
```bash
# Development
docker-compose -f docker/docker-compose.dev.yml up --build

# Production
./scripts/homelab-start.sh
./scripts/homelab-stop.sh
./scripts/homelab-restart.sh
```

### Environment Variables

```bash
DATABASE_PATH=/path/to/fct_stats.db  # Database location
ANALYTICS_SECRET=secret-key           # Analytics page access
```

---

## Common Issues & Solutions

### Issue: Meet dates showing as 2025-03-15 (default)

**Cause**: Meet name not in `meets_2025.json` or different name used

**Solution**:
1. Check exact meet name in database
2. Add to `meets_2025.json` with correct date
3. Re-run import script

### Issue: Event not recognized

**Cause**: Event name variation not in aliases

**Solution**:
1. Add alias to `config/canonical_events.yaml`
2. Re-run import script

### Issue: Duplicate result error

**Cause**: Trying to insert duplicate (athlete, event, meet) combination

**Solution**:
- Normal behavior - script skips duplicates
- If intentional, clear database first with `--clear`

### Issue: Gender-specific events incorrect

**Cause**: Wrong hurdles event (110m vs 100m)

**Solution**:
- Boys: 110m Hurdles
- Girls: 100m Hurdles
- Check gender in source data

### Issue: Relay members not showing

**Cause**: Relay not marked as relay in canonical events

**Solution**:
- Ensure event has `is_relay: true` in `canonical_events.yaml`
- Verify relay_members data in JSON

---

## Code Style & Conventions

### Python

- **Docstrings**: All functions should have docstrings
- **Type hints**: Use for function signatures where practical
- **Logging**: Use `logger` instead of `print()` in scripts
- **SQL**: Use triple-quoted strings for multi-line queries

### Templates

- **Indentation**: 2 spaces for HTML
- **CSS**: Inline in `<style>` blocks or `base.html`
- **Colors**: Use CSS variables (`var(--fc-purple)`)
- **Icons**: Bootstrap Icons (`bi-*` classes)

### File Naming

- **Scripts**: `lowercase_with_underscores.py`
- **Templates**: `lowercase_with_underscores.html`
- **Config**: `lowercase_or_camelCase.yaml/json`

---

## Future Enhancements

Potential areas for expansion:

1. **Real-time meet results**: Auto-import from athletic.net
2. **Photo gallery**: Athlete/meet photos
3. **Workout tracking**: Training log integration
4. **Comparison tools**: Compare athletes side-by-side
5. **Export features**: PDF reports, CSV downloads
6. **Mobile app**: Native iOS/Android app
7. **Social features**: Comments, athlete profiles
8. **Analytics dashboard**: Trend analysis, predictions

---

## Contact & Maintenance

- **Database location**: `data/generated/db/fct_stats.db`
- **Backup strategy**: Git tracks all JSON source files
- **Update frequency**: After each meet during season
- **Owner contact**: alan.j.wade@gmail.com

---

## Quick Reference

### Common Commands

```bash
# Parse new data
python3 scripts/parse_performance_list.py
python3 scripts/parse_historical_records.py

# Import to database
python3 scripts/import_all_records.py

# Run webapp locally
cd webapp && python3 app.py

# Docker development
docker-compose -f docker/docker-compose.dev.yml up

# Check database
sqlite3 data/generated/db/fct_stats.db "SELECT COUNT(*) FROM results;"
```

### Key Files to Check First

- `config/meets_2025.json` - Meet dates and levels
- `config/canonical_events.yaml` - Event definitions
- `scripts/import_all_records.py` - Main import logic
- `webapp/app.py` - Web routes and queries
- `scraper/database.py` - Database write operations

### File Paths in Code

All paths should be absolute from project root:

```python
from pathlib import Path

# Good
data_dir = Path(__file__).parent.parent / 'data'

# Bad
data_dir = '../data'  # Relative paths break in different contexts
```

---

**Remember**: The webapp is READ-ONLY. All database modifications happen through scripts.

## Important Note

Do not publish the webapp or database unless explicitly requested. Always confirm with the user before initiating any publish-related actions.

## Guidelines
- Ensure all changes are tested locally before suggesting a publish.
- Provide clear communication about the impact of publishing.
- Wait for explicit user approval before proceeding with any publish commands.

## Additional Notes
- Follow the user's instructions carefully.
- Document any changes made during the session.
