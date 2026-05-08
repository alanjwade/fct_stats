#!/usr/bin/env python3
"""
Import 2026 season results from the parsed Google Sheet JSON into the database.

Usage:
    # Fetch fresh from sheet and import immediately:
    python scripts/import_from_gsheet.py --fetch \
        --url "https://docs.google.com/spreadsheets/d/1avGZOoj0we3cyuMSTWbBQGdJ-i7XGmZa"

    # Import from already-saved JSON (faster, no network):
    python scripts/import_from_gsheet.py --input data/snapshots/2026/gsheet_2026.json

    # Dry run (no DB writes):
    python scripts/import_from_gsheet.py --input data/snapshots/2026/gsheet_2026.json --dry-run

    # Re-fetch, save, then import:
    python scripts/import_from_gsheet.py --fetch --url "..." \
        --save data/snapshots/2026/gsheet_2026.json

This script is the SOURCE OF TRUTH for 2026 season data.
Do NOT also run import_from_parsed_meets.py for 2026, as that data is now
superseded by the Google Sheet. The scraped source files in
  data/sources/2026/pages/
are kept on disk for reference but are NOT imported.
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.database import get_database
from scraper.event_matcher import get_event_matcher

logger = logging.getLogger(__name__)

SEASON = "2026"
GENDER_MAP = {"girls": "F", "boys": "M"}

# ──────────────────────────────────────────────────────────────
# Athlete name aliases: (first, last) → (canonical_first, canonical_last)
# Use when coaches enter a nickname instead of the athlete's full name.
# ──────────────────────────────────────────────────────────────
NAME_ALIASES: dict[tuple[str, str], tuple[str, str]] = {
    ("Addy", "Timock"): ("Addyson", "Timock"),
}

# ──────────────────────────────────────────────────────────────
# Per-athlete meet overrides: (sheet_athlete_name, canonical_event, canonical_source_meet) → canonical_target_meet
# Use when an athlete competed at a different venue than the rest of the team
# but their result is recorded under the team's main meet column in the sheet.
# ──────────────────────────────────────────────────────────────
ATHLETE_MEET_OVERRIDES: dict[tuple[str, str, str], str] = {
    # Cadel Ruthven, Will Johns, Sean Giles competed at Arcadia Invite (CA)
    # on 2026-04-11 while the team was at Pomona Invite.
    ("Cadel Ruthven", "1600m", "Pomona Invite"): "Arcadia Invite",
    ("Will Johns",    "1600m", "Pomona Invite"): "Arcadia Invite",
    ("Sean Giles",    "3200m", "Pomona Invite"): "Arcadia Invite",
}

# ──────────────────────────────────────────────────────────────
# Meet name → (canonical_name, date, level)
# "canonical_name" is how it will appear in the DB meets table.
# Add entries here as new meets are completed.
# ──────────────────────────────────────────────────────────────
MEET_INFO: dict[str, dict] = {
    # Calendar: "Fort Collins JV Scrimmage" 2026-03-04
    "FCHS JV Scrimmage": {
        "canonical": "Fort Collins JV Scrimmage",
        "date": "2026-03-04",
        "level": "jv",
    },
    "Fort Collins JV Scrimmage": {
        "date": "2026-03-04",
        "level": "jv",
    },
    "John Martin Early Bird Invite": {
        "date": "2026-03-07",
        "level": "varsity",
    },
    "Poudre JV Meet": {
        "date": "2026-03-10",
        "level": "jv",
    },
    "Thunder Ridge Invite": {
        "date": "2026-03-14",
        "level": "varsity",
    },
    # Spreadsheet sometimes spells it "Thurder Ridge" — normalise below
    "Thurder Ridge Invite": {
        "canonical": "Thunder Ridge Invite",
        "date": "2026-03-14",
        "level": "varsity",
    },
    "Runners Roost": {
        "canonical": "Runners Roost Invite",
        "date": "2026-03-21",
        "level": "varsity",
    },
    "Runners Roost Invite": {
        "date": "2026-03-21",
        "level": "varsity",
    },
    "PSD JV Invite #1": {
        "canonical": "Rocky JV Meet",
        "date": "2026-03-25",
        "level": "jv",
    },
    "PSD JV Invite #1 (FA)": {
        "canonical": "Rocky JV Meet",
        "date": "2026-03-25",
        "level": "jv",
    },
    "PSD JV Invite #2": {
        "date": "2026-04-01",
        "level": "jv",
    },
    "PSD JV Invite #2 (FA)": {
        "canonical": "PSD JV Invite #2",
        "date": "2026-04-01",
        "level": "jv",
    },
    "PSD JV Invite #3": {
        "date": "2026-04-15",
        "level": "jv",
    },
    "PSD JV Invite #3 (FA)": {
        "canonical": "PSD JV Invite #3",
        "date": "2026-04-15",
        "level": "jv",
    },
    "Roosevelt Power Invite": {
        "date": "2026-03-27",
        "level": "varsity",
    },
    "Altitude Invite": {
        "date": "2026-04-04",
        "level": "varsity",
    },
    "Randi Yaussi Meet": {
        "date": "2026-04-08",
        "level": "varsity",
    },
    "Randy Yaussi Meet": {
        "canonical": "Randi Yaussi Meet",
        "date": "2026-04-08",
        "level": "varsity",
    },
    "Rand Yaussi PSD Meet": {
        "canonical": "Randi Yaussi Meet",
        "date": "2026-04-08",
        "level": "varsity",
    },
    "Thunder Ridge": {
        "canonical": "Thunder Ridge Invite",
        "date": None,
        "level": "varsity",
    },
    "Cherry Creek Invite": {
        "date": "2026-04-18",
        "level": "varsity",
    },
    "Randall Hess Invite": {
        "date": "2026-04-18",
        "level": "varsity",
    },
    "Longmont Invite": {
        "date": None,
        "level": "varsity",
    },
    "Northern League Championships": {
        "date": "2026-05-01",      # finals
        "prelims_date": "2026-04-29",  # prelims
        "level": "varsity",
    },
    "St. Vrain Hoka / Teddy's Last Chance": {
        "date": None,
        "level": "varsity",
    },
    "Pomona Invite": {
        "date": "2026-04-11",       # finals (Saturday)
        "prelims_date": "2026-04-10",  # prelims (Friday)
        "level": "varsity",
    },
    "Pomona Invite / Arcadia Invite": {
        "canonical": "Pomona Invite",
        "date": "2026-04-11",
        "level": "varsity",
    },
    "Arcadia Invite": {
        "date": "2026-04-11",
        "level": "varsity",
    },
    "JV Northern League Champs": {
        "date": "2026-04-23",
        "level": "jv",
    },
    "JV Championships": {
        "canonical": "JV Northern League Champs",
        "date": "2026-04-23",
        "level": "jv",
    },
    "Stutler Twilight Invite": {
        "date": "2026-04-23",
        "level": "varsity",
    },
    "Stutler Bowl Invite": {
        "canonical": "Stutler Twilight Invite",
        "date": "2026-04-23",
        "level": "varsity",
    },
    "State Championships": {
        "date": None,
        "level": "varsity",
    },
}


def resolve_meet(raw_name: str) -> tuple[str, str | None, str]:
    """
    Returns (canonical_name, date, level) for a meet name as written in the sheet.
    Unknown meets get a warning and sensible defaults.
    """
    info = MEET_INFO.get(raw_name)
    if info is None:
        logger.warning(f"Unknown meet name: {raw_name!r} — importing with no date")
        return raw_name, None, "varsity"

    canonical = info.get("canonical", raw_name)
    # If there's a canonical alias, look up that entry for date/level
    if canonical != raw_name:
        canon_info = MEET_INFO.get(canonical, info)
        return canonical, canon_info.get("date"), canon_info.get("level", "varsity")

    return canonical, info.get("date"), info.get("level", "varsity")


# ──────────────────────────────────────────────────────────────
# Mark conversion
# ──────────────────────────────────────────────────────────────

def parse_time(s: str) -> float | None:
    """
    Convert a display time string to total seconds.
      "12.33"     → 12.33
      "1:54.18"   → 114.18
      "4:22.77"   → 262.77
      "10:30.0"   → 630.0
    Returns None for unparseable strings.
    """
    s = s.strip()
    if not s or s in ('-', 'NT', 'DNS', 'DNF', 'DQ', 'SCR', 'NH', 'ND', 'NM'):
        return None
    # Handles both M:SS.XX and M:SS (whole seconds, no decimal)
    m = re.match(r'^(\d+):(\d{2})(?:\.(\d+))?$', s)
    if m:
        mins = int(m.group(1))
        secs = int(m.group(2))
        frac = m.group(3) or '0'
        return mins * 60 + secs + float('0.' + frac)
    try:
        return float(s)
    except ValueError:
        return None


def parse_feet_inches(s: str) -> float | None:
    """
    Convert feet-inches display marks to meters.
      "5'10"      → 1.7780
      "21'11.5"   → 6.6929
      "44'9.75"   → 13.6525
    Also handles plain decimal feet ("55.25" → 16.84m) — but that should not
    appear in this sheet since coaches use feet-inches.
    Returns None for unparseable strings.
    """
    s = s.strip()
    if not s or s in ('-', 'NT', 'DNS', 'DNF', 'DQ', 'SCR', 'NH', 'ND', 'NM'):
        return None
    # Feet-inches: N'M or N'M.XX or N'M" or N'M.XX"
    m = re.match(r"^(\d+)'([\d.]+)\"?$", s)
    if m:
        feet = int(m.group(1))
        inches = float(m.group(2))
        total_inches = feet * 12 + inches
        return round(total_inches * 0.0254, 4)
    # Plain decimal (fallback — treat as feet and convert)
    try:
        return round(float(s) * 0.3048, 4)
    except ValueError:
        return None


def parse_mark(mark_str: str, is_timed: bool) -> tuple[float | None, str]:
    """
    Parse a mark from the sheet.
    Returns (numeric_mark, display_string).
    """
    display = mark_str.strip()
    if not display:
        return None, ''
    if is_timed:
        numeric = parse_time(display)
    else:
        numeric = parse_feet_inches(display)
    return numeric, display


# ──────────────────────────────────────────────────────────────
# Name parsing
# ──────────────────────────────────────────────────────────────

def split_name(full_name: str) -> tuple[str, str]:
    """Split 'First Last' into (first, last). Handles middle names / suffixes.

    Parenthetical nicknames like 'Jacob (Denny) Richter' are dropped so that
    'Richter' becomes the last name and the entry sorts correctly.
    """
    # Remove any parenthetical segment, e.g. "(Denny)" or "(nickname)"
    import re as _re
    cleaned = _re.sub(r'\s*\([^)]*\)', '', full_name).strip()
    parts = cleaned.split()
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], ' '.join(parts[1:])


# ──────────────────────────────────────────────────────────────
# Core importer
# ──────────────────────────────────────────────────────────────

def import_sheet(db, event_matcher, sheet: dict, dry_run: bool = False) -> dict:
    """
    Import one sheet's worth of parsed data.  Returns counts dict.
    """
    gender_str = sheet["gender"]         # 'girls' or 'boys'
    gender = GENDER_MAP.get(gender_str, "M")
    is_relay_sheet = sheet["type"] == "relays"
    counts = {"added": 0, "skipped": 0, "errors": 0, "no_mark": 0}

    for event_block in sheet["events"]:
        raw_event = event_block["event"]

        # Map to canonical event name
        canonical_event = event_matcher.match(raw_event, gender)
        if not canonical_event:
            logger.warning(f"  Cannot match event: {raw_event!r} — skipping block")
            counts["errors"] += len(event_block["athletes"])
            continue

        event_info = event_matcher.get_event_info(canonical_event)
        is_timed = event_info.get("timed", True) if event_info else True
        is_relay = event_info.get("is_relay", False) if event_info else is_relay_sheet

        if not dry_run:
            event_id = db.get_or_create_event(canonical_event, event_info)

        for athlete_entry in event_block["athletes"]:
            name = athlete_entry["name"]
            meet_results = athlete_entry.get("meet_results", {})

            if not meet_results:
                counts["no_mark"] += 1
                continue

            # Parse athlete name
            if is_relay:
                # Relay entries are "A Team", "B Team" etc.
                # Store as a placeholder athlete: "Fort Collins" + event + team label
                first_name = "Fort Collins"
                last_name = f"{canonical_event} {name}"
            else:
                first_name, last_name = split_name(name)
                if not first_name:
                    counts["errors"] += 1
                    continue

            # Normalize name aliases (e.g. nicknames entered by coaches)
            first_name, last_name = NAME_ALIASES.get(
                (first_name, last_name), (first_name, last_name)
            )

            if not dry_run:
                athlete_id = db.get_or_create_athlete(
                    first_name=first_name,
                    last_name=last_name,
                    gender=gender,
                    graduation_year=None,
                )

            # One result per meet (or two if mark is "prelim/final" slash format)
            for raw_meet_name, mark_display in meet_results.items():
                # Skip computed/reference columns that leaked in as meets
                # e.g. "2024 SB", "2025 SB" — these are prior-year SB columns,
                # not actual competitions.
                if re.match(r'^20\d\d\s*SB$', raw_meet_name.strip(), re.IGNORECASE):
                    continue

                canonical_meet, meet_date, level = resolve_meet(raw_meet_name)

                # Per-athlete venue override (e.g. athlete at Arcadia while team was at Pomona)
                override_target = ATHLETE_MEET_OVERRIDES.get((name, canonical_event, canonical_meet))
                if override_target:
                    logger.info(f"  Override: {name} / {canonical_event} / {canonical_meet} → {override_target}")
                    canonical_meet, meet_date, level = resolve_meet(override_target)

                # Expand slash marks: "prelim/final" means two results.
                # If the meet has a prelims_date, store each under a separate meet name.
                # Otherwise both marks go to the same meet (second will be silently
                # dropped by the UNIQUE constraint if the event has no prelims round).
                if isinstance(mark_display, str) and '/' in mark_display:
                    slash_parts = [p.strip() for p in mark_display.split('/')]
                    slash_parsed = [parse_mark(p, is_timed) for p in slash_parts]
                    if all(n is not None for n, _ in slash_parsed):
                        prelims_date = MEET_INFO.get(canonical_meet, {}).get("prelims_date")
                        if prelims_date and len(slash_parts) == 2:
                            # First mark → prelims meet; second mark → finals meet
                            mark_meet_list = [
                                (slash_parts[0], f"{canonical_meet} Prelims", prelims_date, level),
                                (slash_parts[1], canonical_meet, meet_date, level),
                            ]
                        else:
                            mark_meet_list = [(m, canonical_meet, meet_date, level) for m in slash_parts]
                    else:
                        mark_meet_list = [(mark_display, canonical_meet, meet_date, level)]
                else:
                    mark_meet_list = [(mark_display, canonical_meet, meet_date, level)]

                for mark_str, m_name, m_date, m_level in mark_meet_list:
                    numeric_mark, display = parse_mark(mark_str, is_timed)
                    if numeric_mark is None:
                        counts["no_mark"] += 1
                        logger.debug(f"  Unparseable mark {mark_str!r} for "
                                     f"{name} / {canonical_event} / {raw_meet_name}")
                        continue

                    if dry_run:
                        counts["added"] += 1
                        logger.debug(
                            f"  [DRY] {name} | {canonical_event} | {m_name} "
                            f"| {display} ({numeric_mark})"
                        )
                        continue

                    meet_id = db.get_or_create_meet(
                        name=m_name,
                        meet_date=m_date,
                        venue=m_name,
                        location=m_name,
                        season=SEASON,
                    )

                    result_id = db.add_result(
                        athlete_id=athlete_id,
                        event_id=event_id,
                        meet_id=meet_id,
                        mark=numeric_mark,
                        mark_display=display,
                        level=m_level,
                    )

                    if result_id:
                        counts["added"] += 1
                    else:
                        counts["skipped"] += 1

    return counts


def import_all(gsheet_data: list[dict], db_path: str = None,
               dry_run: bool = False) -> None:
    """Import all sheets into the database."""
    db = get_database(db_path)
    event_matcher = get_event_matcher()

    total = {"added": 0, "skipped": 0, "errors": 0, "no_mark": 0}

    for sheet in gsheet_data:
        sheet_name = sheet["sheet"]
        logger.info(f"\nProcessing: {sheet_name}")
        counts = import_sheet(db, event_matcher, sheet, dry_run=dry_run)
        logger.info(
            f"  added={counts['added']}  skipped={counts['skipped']}  "
            f"errors={counts['errors']}  no_mark={counts['no_mark']}"
        )
        for k in total:
            total[k] += counts[k]

    mode = "[DRY RUN] " if dry_run else ""
    logger.info(f"\n{'='*60}")
    logger.info(f"{mode}GSHEET IMPORT COMPLETE")
    logger.info(f"  Added:   {total['added']}")
    logger.info(f"  Skipped: {total['skipped']} (already in DB)")
    logger.info(f"  No mark: {total['no_mark']} (blank cells / non-numeric)")
    logger.info(f"  Errors:  {total['errors']}")
    logger.info(f"{'='*60}")


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Import 2026 season results from Google Sheet into the database"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--input", metavar="FILE",
        help="Path to already-saved gsheet JSON (e.g. data/snapshots/2026/gsheet_2026.json)"
    )
    source.add_argument(
        "--fetch", action="store_true",
        help="Fetch fresh data from Google Sheets (requires --url)"
    )
    parser.add_argument(
        "--url",
        help="Google Sheets URL (required with --fetch; sheet must be publicly viewable)"
    )
    parser.add_argument(
        "--save", metavar="FILE",
        help="When using --fetch, also save the parsed JSON to this path"
    )
    parser.add_argument("--db", help="Path to database file (default: auto-detected)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and report without writing to the database")
    parser.add_argument("--debug", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(message)s"
    )

    if args.fetch:
        if not args.url:
            parser.error("--fetch requires --url")
        # Reuse the exploration script's fetch+parse logic
        sys.path.insert(0, str(Path(__file__).parent))
        import explore_gsheet as eg

        sheet_id = eg.sheet_id_from_url(args.url)
        gsheet_data = []
        import time
        for i, sheet_name in enumerate(eg.SHEET_NAMES):
            if i > 0:
                time.sleep(2)
            logger.info(f"Fetching {sheet_name} ...")
            rows = eg.fetch_sheet_as_csv(sheet_id, sheet_name, eg.DEFAULT_GIDS)
            parsed = eg.parse_sheet(rows, sheet_name)
            gsheet_data.append(parsed)

        if args.save:
            save_path = Path(args.save)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w") as f:
                json.dump(gsheet_data, f, indent=2)
            logger.info(f"Saved to {save_path}")
    else:
        input_path = Path(args.input)
        if not input_path.exists():
            sys.exit(f"File not found: {input_path}")
        with open(input_path) as f:
            gsheet_data = json.load(f)

    import_all(gsheet_data, db_path=args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
