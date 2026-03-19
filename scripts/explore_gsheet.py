#!/usr/bin/env python3
"""
Exploration and parsing script for the FCT track/field Google Sheet.

Usage:
    # Public sheet (view-only link shared) - no auth needed
    python scripts/explore_gsheet.py --url "https://docs.google.com/spreadsheets/d/SHEET_ID/..." --dump

    # Auth with your Google account (OAuth, opens browser once):
    python scripts/explore_gsheet.py --id SHEET_ID --dump

    # Parse and output JSON:
    python scripts/explore_gsheet.py --url "..." --output data/snapshots/2026/gsheet_results.json

Flags:
    --dump          Print raw cell dump for each sheet (great for debugging structure)
    --sheet NAME    Only process one sheet (e.g. "2026 Girls Track")
    --output FILE   Write parsed JSON to file
"""

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import gspread
    HAS_GSPREAD = True
except ImportError:
    HAS_GSPREAD = False


# ──────────────────────────────────────────────────────────────
# Known event names for detection (add more as needed)
# ──────────────────────────────────────────────────────────────
KNOWN_TRACK_EVENTS = {
    '100m', '200m', '400m', '800m', '1500m', '1600m', '1000m',
    '3000m', '3200m', '5000m', '5k', '110m hurdles', '100m hurdles',
    '300m hurdles', '300m ih', '110m ih', '100m ih',
    '400m hurdles', '400m ih',
    '100mh', '110mh', '110hh', '300mh', '300h',
    '4x100', '4x200', '4x400', '4x800', '4x100m', '4x400m', '4x800m',
    'sprint medley', 'distance medley',
}

KNOWN_FIELD_EVENTS = {
    'high jump', 'long jump', 'triple jump', 'pole vault',
    'shot put', 'discus', 'javelin', 'hammer',
    'pentathlon', 'heptathlon', 'decathlon',
}

ALL_KNOWN_EVENTS = KNOWN_TRACK_EVENTS | KNOWN_FIELD_EVENTS

SHEET_NAMES = [
    '2026 Girls Track',
    '2026 Girls Field',
    '2026 Boys Track',
    '2026 Boys Field',
    '2026 Girls Relays',
    '2026 Boys Relays',
]

# Known GIDs for the FCT spreadsheet (find by clicking each tab in the browser
# and reading #gid= from the URL). Only needed when two sheets have the same
# row count and the gviz endpoint can't differentiate them.
DEFAULT_GIDS: dict[str, str] = {
    '2026 Girls Track': '730601561',
    '2026 Boys Track':  '253493446',
}


# ──────────────────────────────────────────────────────────────
# Data access helpers
# ──────────────────────────────────────────────────────────────

def sheet_id_from_url(url: str) -> str:
    """Extract the spreadsheet ID from a Google Sheets URL."""
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url)
    if not m:
        sys.exit(f"Could not extract sheet ID from URL: {url}")
    return m.group(1)


_sheet_gid_cache: dict[str, dict[str, str]] = {}  # sheet_id -> {sheet_name -> gid}


def get_sheet_gids(sheet_id: str) -> dict[str, str]:
    """
    Fetch the spreadsheet HTML page and extract {sheet_name: gid} for all tabs.
    Falls back gracefully if scraping fails.
    """
    if sheet_id in _sheet_gid_cache:
        return _sheet_gid_cache[sheet_id]

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    gids = {}

    # Pattern in server-rendered Sheets HTML:
    # id="docs-sheet-tab-NNN" ... <div ...>SHEETNAME</div>
    # or: href="#gid=NNN" ... SHEETNAME
    for m in re.finditer(r'"sheetId"\s*:\s*(\d+)\s*,\s*"title"\s*:\s*"([^"]+)"', resp.text):
        gids[m.group(2)] = m.group(1)
    if not gids:
        # Try compact format: [NNN,"SHEETNAME",...]
        for m in re.finditer(r'\[(\d{6,}),\s*"([^"]{4,60})"', resp.text):
            gids[m.group(2)] = m.group(1)

    _sheet_gid_cache[sheet_id] = gids
    return gids


def fetch_sheet_as_csv(sheet_id: str, sheet_name: str,
                       manual_gids: dict[str, str] | None = None) -> list[list[str]]:
    """
    Download a single worksheet as CSV.
    Tries GID-based export (reliable) then falls back to gviz (unreliable for
    sheets with similar dimensions).  Pass manual_gids={sheet_name: gid} to
    bypass auto-detection.
    """
    if not HAS_REQUESTS:
        sys.exit("requests library not installed. Run: pip install requests")

    import time

    # Resolve GID: manual override > auto-scraped > unknown
    gid = None
    if manual_gids:
        gid = manual_gids.get(sheet_name)
    if gid is None:
        gids = get_sheet_gids(sheet_id)
        gid = gids.get(sheet_name)

    if gid is not None:
        url = (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}"
            f"/export?format=csv&gid={gid}"
        )
    else:
        # Fall back to gviz — works for sheets with unique dimensions
        # but may return wrong data when two sheets have the same row count
        url = (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}"
            f"/gviz/tq?tqx=out:csv&sheet={requests.utils.quote(sheet_name)}"
        )
        print(f"\n  WARNING: Could not determine GID for '{sheet_name}'. "
              f"Falling back to gviz (may return wrong sheet if dimensions match another sheet).\n"
              f"  To fix: run with --gids or use --id for OAuth access.\n"
              f"  Get GIDs: open the sheet in your browser, click each tab, read #gid= from the URL.",
              file=sys.stderr)

    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            reader = csv.reader(io.StringIO(resp.text))
            return list(reader)
        except Exception as e:
            last_err = e
            wait = 2 ** attempt
            print(f"  (attempt {attempt+1} failed: {e}; retrying in {wait}s...)")
            time.sleep(wait)
    raise last_err


def open_with_gspread(sheet_id: str) -> 'gspread.Spreadsheet':
    """
    Open the spreadsheet using gspread + OAuth (your Google account).
    On first run this opens a browser to authenticate.
    Credentials are cached in ~/.config/gspread/authorized_user.json.
    """
    if not HAS_GSPREAD:
        sys.exit("gspread not installed. Run: pip install gspread google-auth")

    gc = gspread.oauth(
        credentials_filename=str(
            Path.home() / '.config' / 'gspread' / 'credentials.json'
        )
    )
    return gc.open_by_key(sheet_id)


# ──────────────────────────────────────────────────────────────
# Structure inspection
# ──────────────────────────────────────────────────────────────

def dump_rows(rows: list[list[str]], sheet_name: str, max_rows: int = 60):
    """Print a readable dump of the first N rows with column labels."""
    print(f"\n{'='*70}")
    print(f"  SHEET: {sheet_name}")
    print(f"{'='*70}")
    col_labels = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    for r_idx, row in enumerate(rows[:max_rows], start=1):
        for c_idx, val in enumerate(row):
            if val.strip():
                col = col_labels[c_idx] if c_idx < 26 else f'col{c_idx+1}'
                print(f"  [{r_idx},{col}] {repr(val)}")
    print()


def _pad_row(row: list[str], width: int = 25) -> list[str]:
    return (row or []) + [''] * max(0, width - len(row or []))


def detect_columns(header_row: list[str]) -> dict:
    """
    Given a header row, figure out which columns hold what.
    Handles three formats:
      - Field:   B="PR", C="2025 SB", D="SB", E+=meets
      - Track:   B="School Record: X.XX (Name) PR", C="2025 SB", D="SB", E+=meets
      - Relays:  B="SB" (or "School Record: X.XX"), C="2025 SB", D+=meets
    Returns: { 'pr': col_idx, 'sb_2025': col_idx, 'sb_2026': col_idx,
                'meets': [(col_idx, meet_name), ...] }
    """
    info = {}
    meets = []
    for i, val in enumerate(header_row):
        v = val.strip()
        vl = v.lower()
        if i == 0 or not v:
            continue

        # "School Record: ..." rows — only useful if they contain "PR"
        if 'school record' in vl:
            if re.search(r'\bPR\b', v):
                info['pr'] = i   # e.g. "School Record: 11.91 (Name) PR"
            # else: school record without PR = metadata (e.g. "School Record: 47.97 SB")
            continue

        # Plain "PR" column header (Field events)
        if re.match(r'^PR$', v, re.IGNORECASE):
            info['pr'] = i
            continue

        # Previous-year SB (C column labelled "2025 SB", "2024 SB", etc.)
        if re.search(r'20\d\d\s*(SB|season)', v, re.IGNORECASE):
            if 'sb_2025' not in info:
                info['sb_2025'] = i
            continue

        # "SB" or "Season Best" alone = current-year (2026) SB column
        if re.match(r'^SB$', v, re.IGNORECASE) or re.match(r'^Season Best$', v, re.IGNORECASE):
            if 'sb_2026' not in info:  # first one wins (manual "SB" beats formula column)
                info['sb_2026'] = i
            continue

        # Helper/sort columns — skip
        if re.search(r'Season Best Sort|Sort$', v, re.IGNORECASE):
            continue

        # Skip annotation cells ("18th in 5A...", "=...", etc.)
        if re.search(r'\d+(th|rd|st|nd)\s+in\s+\d+A|=\s*(Pomona|Arcadia|Cherry)', v, re.IGNORECASE):
            continue

        # Everything else is a meet name
        meets.append((i, v))
    info['meets'] = meets
    return info


def is_header_row(padded: list[str]) -> bool:
    """
    Returns True if this row appears to contain column headers
    (not athlete data). Handles all three sheet formats.
    """
    b = padded[1].strip() if len(padded) > 1 else ''
    c = padded[2].strip() if len(padded) > 2 else ''

    # B contains "PR" as a word: "PR" or "School Record: ... PR"
    if re.search(r'\bPR\b', b):
        return True

    # B is "SB" alone (Relay sub-header: B="SB", C="2025 SB", D+=meets)
    if re.match(r'^SB$', b, re.IGNORECASE):
        return True

    # C is "2025 SB" — Track sub-header (after event-only row, B is blank)
    if re.match(r'^2025\s*(SB|season)', c, re.IGNORECASE):
        return True

    # B is "School Record: ..." AND C is "2025 SB" (Relay first-event header)
    if re.search(r'school record', b, re.IGNORECASE) and re.match(r'^2025\s*(SB|season)', c, re.IGNORECASE):
        return True

    return False


# ──────────────────────────────────────────────────────────────
# Event detection
# ──────────────────────────────────────────────────────────────

def extract_event_name(cell_a: str) -> str:
    """
    Extract a clean event name from col A, which may have notes appended.
    e.g. "100m (JV hand held times are converted...)" → "100m"
         "4 x 100 Relay " → "4 x 100 Relay"
    """
    # Strip content after the first '(' or extra whitespace
    name = re.sub(r'\s*\(.*', '', cell_a).strip()
    return name


def is_event_cell(cell_a: str) -> bool:
    """
    Returns True if the value in column A looks like an event name
    rather than an athlete/team name.
    """
    v = cell_a.strip().lower()
    if not v:
        return False
    # Trim any notes in parens for matching
    clean = re.sub(r'\s*\(.*', '', v).strip()
    # Direct match against known events
    if clean in ALL_KNOWN_EVENTS:
        return True
    # "100m", "200m", "3200m", etc.
    if re.match(r'^\d+\s*m\b', clean):
        return True
    # Abbreviated hurdle forms: 100mH, 110HH, 300mH, 110mHH, etc.
    if re.match(r'^\d+\s*m?h+\b', clean):
        return True
    # "4 x 100", "4x400", etc.
    if re.match(r'^4\s*x\s*\d', clean):
        return True
    if any(kw in clean for kw in ('hurdles', 'relay', 'jump', 'vault', 'put', 'discus', 'javelin')):
        return True
    return False


# ──────────────────────────────────────────────────────────────
# Parser
# ──────────────────────────────────────────────────────────────

def parse_sheet(rows: list[list[str]], sheet_name: str) -> dict:
    """
    Parse one worksheet into structured data.

    Handles three sheet layouts found in this workbook:
      Field:   row 1 = event + B="PR" + C="2025 SB" + D="SB" + meets
      Track:   row 1 = event + B="School Record: X (Name) PR" + C="2025 SB" + D="SB" + meets
               subsequent events: event-only row, then sub-header row (C="2025 SB", E+=meets)
      Relays:  row 1 = event + B="School Record: X SB" (metadata) + C="2025 SB" + meets
               subsequent events: event-only row, then sub-header row (B="SB", C="2025 SB", D+=meets)

    Returns:
      {
        'sheet': sheet_name,
        'gender': 'girls'|'boys',
        'type': 'track'|'field'|'relays',
        'column_map': { 'pr': col, 'sb_2025': col, 'sb_2026': col,
                        'meets': [(col, name), ...] },
        'events': [
          { 'event': '100m',
            'athletes': [
              { 'name': '...', 'pr': '...', 'sb_2025': '...', 'sb_2026': '...',
                'meet_results': { meet_name: result, ... } },
              ...
            ]
          }, ...
        ]
      }
    """
    gender = 'girls' if 'girls' in sheet_name.lower() else 'boys'
    if 'track' in sheet_name.lower():
        event_type = 'track'
    elif 'field' in sheet_name.lower():
        event_type = 'field'
    else:
        event_type = 'relays'

    result = {
        'sheet': sheet_name,
        'gender': gender,
        'type': event_type,
        'column_map': {},
        'events': [],
    }

    if not rows:
        return result

    def safe_get(r, i):
        return r[i].strip() if i is not None and i < len(r) else ''

    # ── Step 1: Find the first header row and build the initial column map ──
    header_row_idx = None
    col_map = {}
    for r_idx, row in enumerate(rows):
        padded = _pad_row(row)
        if is_header_row(padded):
            header_row_idx = r_idx
            col_map = detect_columns(padded)
            result['column_map'] = col_map
            break

    if header_row_idx is None:
        print(f"  WARNING: Could not find header row in {sheet_name}")
        return result

    # ── Step 2: Extract the first event name (from col A at/before header row) ──
    first_event_name = ''
    for r_idx in range(0, header_row_idx + 1):
        if r_idx < len(rows) and rows[r_idx] and rows[r_idx][0].strip():
            candidate = rows[r_idx][0].strip()
            if is_event_cell(candidate):
                first_event_name = extract_event_name(candidate)
                break

    current_event = {'event': first_event_name, 'athletes': []} if first_event_name else None

    # ── Step 3: Process remaining rows ──
    for r_idx in range(header_row_idx + 1, len(rows)):
        row = rows[r_idx]
        padded = _pad_row(row)
        cell_a = padded[0].strip()

        # Skip fully blank rows
        if not any(v.strip() for v in padded):
            continue

        # Sub-header row: no event name in A, but has column-header content
        # (e.g. Track sub-header after each event, or Relay B="SB" row)
        if not cell_a and is_header_row(padded):
            new_map = detect_columns(padded)
            # Merge new column info:
            # - For pr/sb columns: take new value if not already set
            # - For meets: ADD new columns; do NOT remove original meets
            #   (sub-header rows often list fewer meets than the first header row)
            for key in ('pr', 'sb_2025', 'sb_2026'):
                if key in new_map and key not in col_map:
                    col_map[key] = new_map[key]
            if new_map.get('meets'):
                existing_cols = {c for c, _ in col_map.get('meets', [])}
                for col_idx, meet_name in new_map['meets']:
                    if col_idx not in existing_cols:
                        col_map.setdefault('meets', []).append((col_idx, meet_name))
            result['column_map'] = col_map
            continue

        # New event row
        if cell_a and is_event_cell(cell_a):
            if current_event and current_event['athletes']:
                result['events'].append(current_event)
            current_event = {'event': extract_event_name(cell_a), 'athletes': []}
            continue

        # Skip rows with no athlete name
        if not cell_a:
            continue

        # Athlete / team row
        if current_event is None:
            current_event = {'event': 'Unknown', 'athletes': []}

        # Strip PR annotations appended to name: "Dj Ruff (10.54)" → "Dj Ruff"
        clean_name = re.sub(r'\s*\([\d.:\'"-]+\)\s*$', '', cell_a).strip()

        athlete = {
            'name': clean_name,
            'pr':      safe_get(padded, col_map.get('pr')),
            'sb_2025': safe_get(padded, col_map.get('sb_2025')),
            'sb_2026': safe_get(padded, col_map.get('sb_2026')),
        }
        athlete['meet_results'] = {
            meet_name: v
            for col_idx, meet_name in col_map.get('meets', [])
            if (v := safe_get(padded, col_idx))
        }
        current_event['athletes'].append(athlete)

    # Save the last event
    if current_event and current_event['athletes']:
        result['events'].append(current_event)

    return result


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Explore/parse FCT Google Sheet")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--url', help="Full Google Sheets URL (sheet must be publicly viewable)")
    group.add_argument('--id', dest='sheet_id', help="Spreadsheet ID (uses OAuth via gspread)")
    parser.add_argument('--sheet', help="Only process this sheet name (default: all 6)")
    parser.add_argument('--dump', action='store_true',
                        help="Print raw cell dump to help understand structure")
    parser.add_argument('--output', help="Write parsed JSON to this file path")
    parser.add_argument('--max-dump-rows', type=int, default=80,
                        help="Max rows to print in --dump mode (default 80)")
    parser.add_argument('--list-sheets', action='store_true',
                        help="List all sheet tabs in the spreadsheet and exit")
    parser.add_argument(
        '--gids',
        help=(
            'Comma-separated sheet_name=GID pairs to bypass auto-detection. '
            'Example: --gids "2026 Boys Track=1234567890,2026 Girls Track=0". '
            'Find GIDs by opening the sheet in your browser and reading #gid= from the URL.'
        )
    )
    args = parser.parse_args()

    if args.url:
        sheet_id = sheet_id_from_url(args.url)
        use_public = True
    else:
        sheet_id = args.sheet_id
        use_public = False

    target_sheets = [args.sheet] if args.sheet else SHEET_NAMES

    # Build GID map: start with known defaults, then layer on any --gids overrides
    manual_gids: dict[str, str] = dict(DEFAULT_GIDS)
    if args.gids:
        for part in args.gids.split(','):
            part = part.strip()
            if '=' in part:
                name, gid = part.split('=', 1)
                manual_gids[name.strip()] = gid.strip()

    if args.list_sheets and use_public:
        gids = get_sheet_gids(sheet_id)
        if gids:
            print("Sheets found in spreadsheet HTML:")
            for name, gid in gids.items():
                print(f"  [{gid}] {name}")
        else:
            print(
                "Could not auto-detect sheet GIDs from the page HTML.\n"
                "To find GIDs manually: open the spreadsheet in your browser,\n"
                "click each sheet tab, and read the #gid= value from the URL.\n"
                "Then pass them with:  --gids \"Sheet Name=GID,...\""
            )
        return

    all_parsed = []

    for i, sheet_name in enumerate(target_sheets):
        if i > 0:
            import time; time.sleep(2)  # be polite to Google's servers
        print(f"\nFetching: {sheet_name} ...", end=' ', flush=True)
        try:
            if use_public:
                rows = fetch_sheet_as_csv(sheet_id, sheet_name, manual_gids or None)
            else:
                spreadsheet = open_with_gspread(sheet_id)
                ws = spreadsheet.worksheet(sheet_name)
                rows = ws.get_all_values()
            print(f"OK ({len(rows)} rows)")
        except Exception as e:
            print(f"FAILED: {e}")
            continue

        if args.dump:
            dump_rows(rows, sheet_name, max_rows=args.max_dump_rows)

        parsed = parse_sheet(rows, sheet_name)
        all_parsed.append(parsed)

        # Quick summary
        event_count = len(parsed['events'])
        athlete_count = sum(len(e['athletes']) for e in parsed['events'])
        print(f"  → {event_count} events, {athlete_count} athlete entries")
        print(f"  Column map: {parsed['column_map']}")
        for ev in parsed['events']:
            names = [a['name'] for a in ev['athletes'][:3]]
            print(f"    {ev['event']}: {len(ev['athletes'])} athletes  {names}{'...' if len(ev['athletes'])>3 else ''}")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w') as f:
            json.dump(all_parsed, f, indent=2)
        print(f"\nWrote {out_path}")
    else:
        print("\n(Use --output FILE to save parsed JSON)")


if __name__ == '__main__':
    main()
