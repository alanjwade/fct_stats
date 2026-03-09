# Add New Meet Results - AI Assistant Prompt

This prompt guides the AI assistant through parsing a new track meet results file for Fort Collins High School athletes.

## Input Required

You should have:
1. A meet results file (HTML or text) - either provide the path or paste the content
2. The meet name (e.g., "Longmont Invitational")
3. The meet date (YYYY-MM-DD format)
4. The level (varsity/jv/open)

## Process

### Step 1: Analyze the Input File

First, examine the results file to understand its format:

```
I have a new meet results file to parse. The file is at: [PATH]
Meet name: [NAME]
Date: [DATE]
Level: [LEVEL]

Please analyze this file and determine:
1. What format is it? (HyTek, Milesplit, generic HTML table, etc.)
2. Do we have an existing parser that can handle it?
3. Are there Fort Collins athletes visible in the results?
```

### Step 2: Try Existing Parsers

The existing parsers are in `scraper/parsers/`:
- **hytek_text.py** - HyTek Meet Manager text output (look for "HY-TEK's Meet Manager" or "Event X Boys/Girls")
- **milesplit_multi.py** - Milesplit multi-event pages
- **milesplit_single.py** - Milesplit single event pages  
- **generic_table.py** - Generic HTML tables with results

Each parser has a `can_parse(content)` method that detects if it can handle the format.

**Run the parser script:**
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

Add the meet to `config/meets_2025.json`:
```json
{
  "name": "Meet Name",
  "date": "2025-04-25",
  "level": "varsity"
}
```

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
        ├── pages/           # Raw meet result files
        │   └── 2025/
        └── meets/           # Meet YAML configurations
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
# Analyze file without saving
python scripts/parse_new_meet.py file.html -m "Meet" -d 2025-04-15 --force

# Use specific parser
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
