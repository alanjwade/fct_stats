# Scraping Track Meet Results

This prompt helps you run the scraper to populate the FCT Stats database with meet results.

## Overview

The scraper processes meet result files and imports Fort Collins athlete data into the database. There are several ways to run the scraper depending on your needs:

- **Scrape all meets**: Process all configured YAML files in `data/meets/`
- **Scrape specific meet**: Process a single meet YAML file
- **Scrape directory**: Process all meet files in a specific directory
- **Clear and rebuild**: Clear existing data before scraping

## Quick Start

**Important:** The scraper has its own virtual environment at `scraper/venv/`. Always use it for scraper commands.

### Scrape All Meets (Most Common)
```bash
scraper/venv/bin/python -m scraper.scraper
```

This will:
1. Import historical school records
2. Process all YAML files in `data/meets/`
3. Parse results and save Fort Collins athletes to database
4. Show progress for each meet

### Scrape a Single Meet
```bash
scraper/venv/bin/python -m scraper.scraper data/meets/2025/longmont_invitational_2025.yaml
```

## Detailed Usage

### Option 1: Scrape Everything
**Use when:** Starting fresh, syncing all meets, or doing a full rebuild

```bash
scraper/venv/bin/python -m scraper.scraper
```

**Output:**
```
- Imports historical records
- Processes all YAML files in data/meets/ (recursively)
- Shows progress for each meet
- Logs Fort Collins athlete counts
```

### Option 2: Scrape Specific Meet File
**Use when:** You've updated one meet YAML and want to re-import just that meet

```bash
scraper/venv/bin/python -m scraper.scraper data/meets/2025/longmont_invitational_2025.yaml
```

**Output:**
```
- Imports historical records
- Processes only the specified YAML file
- Updates results for that meet
```

### Option 3: Scrape a Directory
**Use when:** You've added multiple new meets in a specific directory

```bash
scraper/venv/bin/python -m scraper.scraper --meet-dir data/meets/2025
```

**Output:**
```
- Imports historical records
- Recursively finds all .yaml and .yml files in the directory
- Processes each file
```

### Option 4: Scrape with Clear Options
**Use when:** You need to rebuild data from scratch

#### Clear Results Only (Keep athletes and events)
```bash
scraper/venv/bin/python -m scraper.scraper --clear-results
```

#### Clear Meets and Results (Keep historical records and athletes)
```bash
scraper/venv/bin/python -m scraper.scraper --clear-meets
```

#### Clear Entire Database (Nuclear option)
```bash
scraper/venv/bin/python -m scraper.scraper --clear-all
```

**⚠️ Warning:** `--clear-all` removes everything. Historical records must be re-imported.

## Advanced Options

### Skip Historical Records Import
If historical records are already in the database and you just want to add new meets:

```bash
scraper/venv/bin/python -m scraper.scraper --no-historical
```

### Specify Custom Data Directory
```bash
scraper/venv/bin/python -m scraper.scraper --data-dir /path/to/data
```

### Specify Custom Database Path
```bash
scraper/venv/bin/python -m scraper.scraper --db /path/to/database.db
```

### Combine Options
```bash
scraper/venv/bin/python -m scraper.scraper data/meets/2025/my_meet.yaml --db /path/to/db.db --no-historical
```

## Fallback: No YAML Meet Files Available

If there are no YAML meet files in `data/meets/` (check with `find data/meets -name "*.yaml"`), use the parsed JSON data pipeline instead. This is the standard approach for the current setup.

### Step 1: Check for YAML files
```bash
find data/meets -name "*.yaml" -o -name "*.yml" 2>/dev/null | head -20
```

### Step 2: If none found, re-import from parsed JSON meets and historical records
```bash
# Import school records from data/sources/historic/*.md
./.venv/bin/python scripts/import_historical_records.py

# Import all parsed meet JSON files from data/generated/parsed/meets/
./.venv/bin/python scripts/import_from_parsed_meets.py
```

This covers:
- Historical school records (`data/sources/historic/FCHS *.md`)
- All parsed 2025 meet JSON files (`data/generated/parsed/meets/2025/*.json`)

### When to use this fallback
- No YAML meet configs exist (pages haven't been downloaded/configured yet)
- You've added new meets via `scripts/parse_new_meet.py` and want to import results
- You want a quick full rebuild without configuring YAML files

---

## Common Workflows

### Workflow 1: Update Single Meet After Editing YAML
1. **Edit the meet YAML:**
   ```bash
   nano data/meets/2025/my_meet.yaml
   ```

2. **Clear previous results for that meet:**
   ```bash
   sqlite3 data/fct_stats.db "DELETE FROM results WHERE meet_id = (SELECT id FROM meets WHERE name = 'My Meet');"
   ```

3. **Re-scrape everything to apply changes:**
   ```bash
   scraper/venv/bin/python -m scraper.scraper
   ```

### Workflow 2: Import New Season Meets
1. **Create YAML files for new meets in `data/meets/2025/`**

2. **Run scraper for all meets:**
   ```bash
   scraper/venv/bin/python -m scraper.scraper
   ```

3. **Verify results:**
   ```bash
   sqlite3 data/fct_stats.db "SELECT name, COUNT(*) as results FROM meets JOIN results ON meets.id = results.meet_id GROUP BY meet_id;"
   ```

### Workflow 3: Fresh Database Build
1. **Clear everything:**
   ```bash
   scraper/venv/bin/python -m scraper.scraper --clear-all
   ```

2. **Scrape all meets:**
   ```bash
   scraper/venv/bin/python -m scraper.scraper
   ```

3. **Verify:**
   ```bash
   sqlite3 data/fct_stats.db "SELECT COUNT(*) as total_results FROM results;"
   ```

### Workflow 4: Rebuild Without Touching Historical Records
1. **Clear meets and results only:**
   ```bash
   scraper/venv/bin/python -m scraper.scraper --clear-meets --no-historical
   ```

2. **Re-scrape current meets:**
   ```bash
   scraper/venv/bin/python -m scraper.scraper --no-historical
   ```

This keeps historical school records while rebuilding meet results.

### Workflow 5: Re-import from Parsed Meets (No YAML Files)
Use this when no YAML meet configs exist but parsed JSON meet files are available.

1. **Import historical school records:**
   ```bash
   ./.venv/bin/python scripts/import_historical_records.py
   ```

2. **Import all parsed meet JSON files:**
   ```bash
   ./.venv/bin/python scripts/import_from_parsed_meets.py
   ```

3. **Verify:**
   ```bash
   ./.venv/bin/python -c "import sqlite3; conn = sqlite3.connect('data/generated/db/fct_stats.db'); print('Results:', conn.execute('SELECT COUNT(*) FROM results').fetchone()[0])"
   ```

## Understanding YAML Meet Files

Meet files are in `data/meets/YYYY/` format:

```yaml
meet:
  name: "Longmont Invitational"
  date: "2025-04-25"
  venue: "Longmont High School"
  location: "Longmont, CO"
  season: 2025
  level: "varsity"

sources:
  - file: "../../pages/2025/Longmont Invitational 2025.html"
    format: "hytek"
    default_gender: "boys"
    events:
      - canonical_event: "100m"
        gender: "boys"
      - canonical_event: "200m"
        gender: "boys"
      - canonical_event: "100m"
        gender: "girls"
```

## Data Source Organization

All data sources are now organized under `/data`:

- **2025 Performance List**: `data/2025/2025 Track & Field Performance List.xlsx.ods`
  - Parsed by: `scripts/parse_performance_list.py`
  - Output: `data/parsed_performance_list.json`

- **Meet Configuration**: `data/2025/meets_2025.json`
  - Contains meet names, dates, and levels for 2025

- **Historical Records**: `data/historic/*.md`
  - `data/historic/FCHS Boys Track & Field Records.docx.md`
  - `data/historic/FCHS Girls Track & Field Records.docx.md`
  - Parsed by: `scripts/parse_historical_records.py`
  - Output: `data/historical_records.json`

**Key fields:**
- `meet.name`: Display name of the meet
- `meet.date`: Date in YYYY-MM-DD format
- `meet.level`: "varsity" or "jv"
- `sources`: List of files to parse
- `sources[].file`: Path to results file (relative to YAML location)
- `sources[].format`: Parser to use ("hytek", "milesplit_multi", etc.)
- `sources[].events`: Events to extract from this source

## Database Verification Commands

### Check total results
```bash
sqlite3 data/fct_stats.db "SELECT COUNT(*) FROM results;"
```

### Check results by meet
```bash
sqlite3 data/fct_stats.db "SELECT meets.name, COUNT(*) FROM results JOIN meets ON results.meet_id = meets.id GROUP BY meet_id ORDER BY meets.date DESC;"
```

### Check specific meet results
```bash
sqlite3 data/fct_stats.db "SELECT * FROM results WHERE meet_id = (SELECT id FROM meets WHERE name = 'Longmont Invite') LIMIT 5;"
```

### Count Fort Collins athletes
```bash
sqlite3 data/fct_stats.db "SELECT COUNT(DISTINCT athlete_id) FROM results;"
```

### Check most recent meets
```bash
sqlite3 data/fct_stats.db "SELECT name, date, COUNT(*) as results FROM meets LEFT JOIN results ON meets.id = results.meet_id GROUP BY meets.id ORDER BY meets.date DESC LIMIT 10;"
```

## Troubleshooting

### "No meet files found"
- Check that YAML files exist in `data/meets/`
- Verify directory structure: `data/meets/YYYY/meet_name.yaml`
- Use `find data/meets -name "*.yaml"` to list files

### "Error parsing: file not found"
- YAML references file paths relative to the YAML location
- Example: `file: "../../pages/2025/Results.html"` relative to `data/meets/2025/meet.yaml`
- Check that the path is correct

### "Could not match event"
- Event name in YAML must match canonical events in `config/canonical_events.yaml`
- Check spelling and case
- Use `canonical_event: "100m"` format

### "School matcher not finding Fort Collins"
- Check `scraper/school_matcher.py` for patterns
- Fort Collins patterns: "Fort Collins", "FCHS", "Lambkins", etc.
- Add new patterns if results aren't being captured

### Results not showing up in database
1. **Check scraper logs:** Look for errors or warnings
2. **Verify database:**
   ```bash
   sqlite3 data/fct_stats.db ".tables"
   ```
3. **Check results exist:**
   ```bash
   sqlite3 data/fct_stats.db "SELECT COUNT(*) FROM results;"
   ```
4. **Check specific meet:**
   ```bash
   sqlite3 data/fct_stats.db "SELECT * FROM meets WHERE name LIKE '%Longmont%';"
   ```

## Related Scripts

### Parse New Meet
For parsing new meet files that don't have a YAML config yet:
```bash
scraper/venv/bin/python scripts/parse_new_meet.py data/pages/2025/NewMeet.html --meet "New Meet" --date 2025-05-15
```

### Import from Parsed Meets
For importing from the centralized `data/parsed_meets/` directory:
```bash
scraper/venv/bin/python scripts/import_from_parsed_meets.py
```

### Parse Historical Records
To import/update school records only:
```bash
scraper/venv/bin/python scripts/import_historical_records.py
```

## Performance Notes

- **Scraping all meets** typically takes 2-5 minutes depending on file sizes
- **Scraping single meet** typically takes 10-30 seconds
- **Database size** grows with each meet added (~1-2KB per result)

## Environment Variables

Optional environment variables:
```bash
DATABASE_PATH=/path/to/database.db
CONFIG_PATH=/path/to/config
DATA_DIR=/path/to/data
```

Example usage:
```bash
DATABASE_PATH=data/fct_stats.db scraper/venv/bin/python -m scraper.scraper
```

## Using the Scraper Virtual Environment

The scraper has its own dedicated virtual environment at `scraper/venv/`. This environment has all required dependencies pre-installed:
- beautifulsoup4
- PyYAML
- rapidfuzz
- lxml

### Why Use the Dedicated Venv?
- No need to create a separate venv or install packages
- All commands just use `scraper/venv/bin/python` instead of `python`
- Dependencies are already configured and ready to use

### Verify the Environment
```bash
scraper/venv/bin/python -c "import rapidfuzz; print('✓ Environment ready')"
```

### If You Need to Add Dependencies
If new packages are needed, install them in the scraper venv:
```bash
scraper/venv/bin/pip install package_name
# Then update scraper/requirements.txt
scraper/venv/bin/pip freeze > scraper/requirements.txt
```

## Pre-Scrape Checklist

**If using YAML-based scraper (`scraper/venv/bin/python -m scraper.scraper`):**
- [ ] Meet YAML files created in `data/meets/YYYY/`
- [ ] Result files exist (HTML/TXT) referenced in YAML
- [ ] Canonical events are correct in `config/canonical_events.yaml`
- [ ] School matcher patterns include all needed schools

**If using parsed JSON pipeline (no YAML files):**
- [ ] Parsed JSON files exist in `data/generated/parsed/meets/`
- [ ] Historical records markdown files exist in `data/sources/historic/`
- [ ] Use: `./.venv/bin/python scripts/import_historical_records.py`
- [ ] Use: `./.venv/bin/python scripts/import_from_parsed_meets.py`

**Always:**
- [ ] Database path is accessible
- [ ] No other processes are accessing the database

## Post-Scrape Verification

- [ ] No errors in console output
- [ ] Results count increased: `sqlite3 data/fct_stats.db "SELECT COUNT(*) FROM results;"`
- [ ] Meets show up in database: `sqlite3 data/fct_stats.db "SELECT COUNT(*) FROM meets;"`
- [ ] Fort Collins athletes are present: `sqlite3 data/fct_stats.db "SELECT DISTINCT school FROM results LIMIT 10;"`
- [ ] Can export to JSON: `python scripts/parse_new_meet.py` or import workflow
