# Add New Meet Results - AI Assistant Prompt

This prompt guides the AI assistant through parsing a new track meet results file for Fort Collins High School athletes.

## Input Required

You should have:
1. A meet results file (HTML or text) **OR a URL** to the results page — either provide the path/URL or paste the content
2. The meet name (e.g., "Longmont Invitational")
3. The meet date (YYYY-MM-DD format)
4. The level (varsity/jv/open)

## Process

### Step 0: Check If the Meet Already Exists

Before asking the user for meet details, read `config/meets_2026.json` (or the relevant year's file) and check whether the meet is already listed. If it is, you already have the name, date, level, and URL — use them directly and skip asking the user for those fields.

```python
import json
with open("config/meets_2026.json") as f:
    meets = json.load(f)["meets"]
# Check if any entry matches the meet the user mentioned
```

Only ask for missing information that isn't already in the config.

### Step 1: Analyze the Input

Determine whether the user gave a **URL** or a **local file**:

- **URL** (starts with `https://` or `http://`): use the web scraping path below.
- **Local file**: read it and proceed to Step 2.

```
I have a new meet to add.
Source: [URL or PATH]
Meet name: [NAME]
Date: [DATE]
Level: [LEVEL]

Please analyze the source and determine:
1. Is this a URL or a local file?
2. What format is the data? (HyTek, MileSplit web page, HTML file, etc.)
3. Are there Fort Collins athletes visible in the results?
```

### Step 1a: If the Input is a URL — Web Scraping

Pass the URL directly to `parse_new_meet.py`. The script will:
1. Check for a cached scrape at `data/sources/current/pages/<year>/<meet-slug>.json`
2. If no cache exists, launch Playwright/Chromium headlessly, render the page, extract all result tables, and save the JSON cache.
3. Parse the cached JSON with the `milesplit_web` parser.

```bash
python scripts/parse_new_meet.py "https://co.milesplit.com/meets/.../results" \
    --meet "Meet Name" \
    --date 2026-03-07 \
    --level varsity
```

The page is only fetched **once**; subsequent runs load from the cache. To force a fresh fetch:
```bash
python scripts/parse_new_meet.py "https://..." --meet "..." --date ... --rescrape
```

**Also add the URL to `data/sources/current/<year>/meets_<year>.json`** so it's recorded with the meet:
```json
{
  "name": "Meet Name",
  "date": "2026-03-07",
  "level": "varsity",
  "url": "https://co.milesplit.com/meets/.../results"
}
```

### Step 2: Try Existing Parsers (for local files)

The existing parsers are in `scraper/parsers/`:
- **milesplit_web.py** - JSON produced by the Playwright web scraper (auto-selected for scraped URLs)
- **hytek_text.py** - HyTek Meet Manager text output (look for "HY-TEK's Meet Manager" or "Event X Boys/Girls")
- **milesplit_multi.py** - MileSplit multi-event HTML pages
- **milesplit_single.py** - MileSplit single-event HTML pages
- **generic_table.py** - Generic HTML tables with results

Each parser has a `can_parse(content)` method that detects if it can handle the format.

**Run the parser script (local file):**
```bash
python scripts/parse_new_meet.py "path/to/results.html" \
    --meet "Meet Name" \
    --date 2025-04-15 \
    --level varsity
```

If multiple parsers can handle the format, try all of them and compare results to pick the best option.

### Step 3: Compare & Validate Results

When multiple parsers succeed, evaluate them with these metrics:
- **Total results**: Count of all results parsed
- **Fort Collins athletes**: How many FC results were found
- **Event coverage**: How many unique events are represented
- **Gender balance**: Are both boys and girls represented
- **Result quality**: Do times/distances look reasonable for the event

**Example comparison output:**
```
Parser Results:
- hytek_text: 156 total results, 34 FC athletes, 16 events
- generic_table: 142 total results, 28 FC athletes, 14 events

Recommendation: hytek_text (best FC coverage, most events)
```

If multiple options are equally valid, ask the user which source looks more trustworthy or complete.

A successful parse should have:
- [ ] **Reasonable count**: 20-200 results for a typical varsity meet
- [ ] **Multiple events**: At least 5-10 different events
- [ ] **Both genders**: Results for boys AND girls
- [ ] **Expected events**: Common events like 100m, 200m, 400m, 800m, 1600m, 3200m, hurdles, relays, field events
- [ ] **Valid marks**: Times and distances that look correct

**Fort Collins school name patterns to match:**
- "Fort Collins", "Ft Collins", "Ft. Collins"
- "FCHS"
- "Lambkins", "Lambkin"

### Step 4: If Parsing Fails

If no existing parser works, create a new one:

1. **Analyze the format**: Look at the HTML/text structure and identify distinctive characteristics
2. **Name the parser**: Use clear, generic names that describe what makes it different:
   - Include the primary format source (e.g., `hytek_`, `milesplit_`, `generic_`)
   - Describe the input type or structure (e.g., `_text`, `_html`, `_multi`, `_single`, `_table`)
   - Use suffix variants if multiple similar parsers exist: `_a`, `_b`, etc. (don't make names unreasonably long)
   - Example: `hytek_text.py`, `milesplit_multi.py`, `generic_table.py`, `generic_table_a.py`
3. **Create parser class** in `scraper/parsers/new_parser.py`
4. **Inherit from BaseParser**: Use the utilities in base_parser.py
5. **Implement required methods**:
   - `can_parse(content: str) -> bool`
   - `parse(file_path: str, event_config: dict) -> list[ParsedResult]`
   - `find_event_section(content: str, event_header: str) -> str`
6. **Register in `__init__.py`**: Add to PARSERS dict

**Relay Event Handling:**
For relay results, always capture the relay time with these fields:
- `is_relay: true` — Mark the record as a relay
- `athlete_first` and `athlete_last` — Populate with actual names if available; can be empty  
- `relay_members` — List of team members if names are available in the source; can be omitted  

**Important**: Even if the source file doesn't include individual athlete names, the relay time should still be recorded. The import script will use "Fort Collins" as a placeholder name if needed, so the relay time appears in the season-bests leaderboard. This is critical for tracking team performance.

**Parser template:**
```python
from .base_parser import BaseParser, ParsedResult

class NewFormatParser(BaseParser):
    """Parser for [format description]."""
    
    def can_parse(self, content: str) -> bool:
        """Check if this parser can handle the content."""
        # Look for distinctive markers in the content
        return 'SOME_MARKER' in content
    
    def parse(self, file_path: str, event_config: dict) -> list:
        content = self.read_file(file_path)
        return self.parse_all_events(content)
    
    def parse_all_events(self, content: str) -> list:
        results = []
        # Parse logic here
        return results
    
    def find_event_section(self, content: str, event_header: str) -> str:
        # Extract section for specific event
        pass
```

### Step 5: Save Results

Once parsing succeeds, the script saves to:
```
data/generated/parsed/meets/YYYY/meet_name.json
```

Example structure:
```json
{
  "meet_name": "Longmont Invitational",
  "date": "2025-04-25",
  "year": 2025,
  "level": "varsity",
  "source": "longmont_results.html",
  "parser": "hytek_text",
  "results": [
    {
      "event": "100m",
      "athlete_first": "John",
      "athlete_last": "Smith",
      "gender": "M",
      "mark": 11.45,
      "mark_display": "11.45",
      "place": 3,
      "meet": "Longmont Invitational",
      "date": "2025-04-25",
      "year": 2025,
      "level": "varsity"
    }
  ]
}
```

### Step 6: Update Configuration

Add the meet to `data/sources/current/<year>/meets_<year>.json`.
Include the `url` field if the source was a web page:
```json
{
  "name": "Meet Name",
  "date": "2025-04-25",
  "level": "varsity",
  "url": "https://co.milesplit.com/meets/.../results"
}
```
Omit `url` for meets that came from a local HTML/text file.

### Step 7: Import to Database

Import just this meet (or all meets):
```bash
# Add to existing data
python scripts/import_from_parsed_meets.py --no-clear

# Or reimport everything
python scripts/import_from_parsed_meets.py
```

### Step 8: Display Best Performances

After successful import, display the best Fort Collins performances from this meet, organized by event:

```
Best Fort Collins Performances - Longmont Invitational (2025-04-25)

100m:
  Boys: John Smith - 11.45 (4th place)
  Girls: Sarah Johnson - 12.89 (3rd place)

200m:
  Boys: Marcus Davis - 23.12 (5th place)
  Girls: Emily Chen - 26.34 (2nd place)

[continues for all events with Fort Collins results]
```

Grouped by event with top performers for each gender. This confirms:
- Parse was successful
- Fort Collins athletes were properly identified
- Results are reasonable for their meet placements

---

## Quick Reference

### Directory Structure
```
data/
├── generated/
│   └── parsed/
│       └── meets/           # Central parsed results location
│           ├── historical_records.json
│           └── 2025/
│               ├── runners_roost_2025.json
│               ├── longmont_invite_2025.json
│               └── [new_meet]_2025.json
└── sources/
    └── current/
        ├── 2025/
        │   └── meets_2025.json   # Meet list (name/date/level/url)
        ├── 2026/
        │   └── meets_2026.json
        ├── pages/               # Raw meet result files & scraped JSON cache
        │   ├── 2025/
        │   │   └── [meet-slug].html  (or .json for web-scraped meets)
        │   └── 2026/
        │       └── [meet-id]-[meet-slug].json   ← Playwright cache
        └── meets/               # Meet YAML configurations (legacy)
            └── 2025/
```

### Common Issues

**No Fort Collins athletes found:**
- Check school name matching in `is_fort_collins()` function
- The source might use different spelling

**Event names not matching:**
- Check `config/canonical_events.yaml` for aliases
- Add new aliases if needed

**Marks not parsing correctly:**
- Check time format (MM:SS.ss vs SS.ss)
- Check distance format (feet-inches vs meters)

**Wrong gender assignment:**
- Event header should include "Boys/Girls" or "Men/Women"
- May need to parse from event section headers

### Useful Commands

```bash
# Scrape a URL (cached automatically)
python scripts/parse_new_meet.py "https://co.milesplit.com/meets/.../results" \
    -m "Meet Name" -d 2026-03-07

# Force re-scrape even if cached
python scripts/parse_new_meet.py "https://..." -m "Meet" -d 2026-03-07 --rescrape

# Parse a local HTML/text file
python scripts/parse_new_meet.py file.html -m "Meet" -d 2025-04-15

# Save even if validation warns
python scripts/parse_new_meet.py ... --force

# Use a specific parser
python scripts/parse_new_meet.py file.html -m "Meet" -d 2025-04-15 --parser hytek_text

# List available parsers
python -c "from scraper.parsers import PARSERS; print(list(PARSERS.keys()))"

# Test school matching
python -c "
from scripts.parse_new_meet import is_fort_collins
test_names = ['Fort Collins', 'Ft Collins', 'FCHS', 'Lambkins', 'Poudre']
for name in test_names:
    print(f'{name}: {is_fort_collins(name)}')"
```

---

## Example Session

```
User: I have a new meet to add. The results are in tmp/spring_classic_2025.html
      Meet name: Spring Classic
      Date: 2025-04-12
      Level: varsity

AI: Let me analyze that file...
    [reads file, detects format]
    
    This appears to be HyTek Meet Manager format. I'll try the hytek_text parser.
    
    [runs parser]
    
    Found 45 Fort Collins results across 12 events:
    - Boys: 100m (3), 200m (4), 400m (2), ...
    - Girls: 100m (2), 200m (3), ...
    
    Validation passed! Saving to data/generated/parsed/meets/2025/spring_classic.json
    
    Next: Add meet to config/meets_2025.json and run import.
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `scripts/parse_new_meet.py` | Main script for parsing new meets |
| `scripts/import_from_parsed_meets.py` | Import parsed JSON to database |
| `scraper/parsers/*.py` | Parser implementations |
| `config/meets_2025.json` | Meet dates and levels |
| `data/generated/parsed/meets/` | Central parsed results storage |
