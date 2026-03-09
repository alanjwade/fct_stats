"""
Parser for the JSON format produced by scraper/web_scraper.py.

The input file looks like:
{
  "url": "https://co.milesplit.com/meets/.../results",
  "title": "...",
  "scraped_with": "playwright",
  "events": [
    {
      "event": "Boys 100 Meter Dash Finals",
      "headers": ["PLACE", "VIDEO", "ATHLETE", "", "TEAM", "MARK", "WIND", "HEAT"],
      "rows": [
        ["1", "", "Dj Ruff", "12", "Fort Collins High School", "11.10", "-1.2", "10"],
        ...
      ]
    },
    ...
  ]
}

Column layouts vary slightly by event type, but are inferred from the header row.
"""

import json
import re
from .base_parser import BaseParser, ParsedResult

# Events whose marks are distances rather than times
_FIELD_KEYWORDS = (
    'jump', 'vault', 'shot', 'discus', 'javelin', 'throw', 'hammer', 'weight'
)


def _is_relay(event_name: str) -> bool:
    name = event_name.lower()
    return 'relay' in name or bool(re.search(r'\d\s*x\s*\d', name))


def _is_field(event_name: str) -> bool:
    name = event_name.lower()
    return any(kw in name for kw in _FIELD_KEYWORDS)


class MilesplitWebParser(BaseParser):
    """
    Parses results from the JSON cache produced by the Playwright web scraper.
    Supports `parse_all_events(content)` for use in parse_new_meet.py.
    """

    # ── Detection ────────────────────────────────────────────────────────────

    def can_parse(self, content: str) -> bool:
        """Return True if *content* is a scraped MileSplit JSON payload."""
        stripped = content.strip()
        if not stripped.startswith('{'):
            return False
        try:
            data = json.loads(stripped)
            return (
                isinstance(data.get('events'), list)
                and data.get('scraped_with') == 'playwright'
            )
        except (json.JSONDecodeError, AttributeError):
            return False

    # ── Parsing entry-points ─────────────────────────────────────────────────

    def parse(self, file_path: str, event_config: dict) -> list[ParsedResult]:
        content = self.read_file(file_path)
        return self.parse_all_events(content)

    def parse_all_events(self, content: str) -> list[ParsedResult]:
        """Parse every event section in the scraped JSON."""
        data = json.loads(content)
        results = []
        for event_block in data.get('events', []):
            results.extend(self._parse_event_block(event_block))
        return results

    def find_event_section(self, content: str, event_header: str) -> str:
        # JSON format: the whole file is our "section".
        return content

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _parse_event_block(self, block: dict) -> list[ParsedResult]:
        """Convert one event dict from the scraped JSON into ParsedResult objects."""
        raw_name = block.get('event', '')
        headers = [h.upper().strip() for h in block.get('headers', [])]
        rows = block.get('rows', [])

        # Determine gender from event name prefix.
        gender = None
        name_lower = raw_name.lower()
        if name_lower.startswith(('boys', "men's", 'men ')):
            gender = 'M'
        elif name_lower.startswith(('girls', "women's", 'women ')):
            gender = 'F'

        # Strip gender prefix and trailing "Finals" / "Prelims".
        event_name = re.sub(
            r'^(boys|girls|men\'?s?|women\'?s?)\s+', '', raw_name, flags=re.IGNORECASE
        ).strip()
        event_name = re.sub(
            r'\s+(finals?|prelims?|heats?)\s*$', '', event_name, flags=re.IGNORECASE
        ).strip()

        relay = _is_relay(event_name)
        field = _is_field(event_name)

        # Build a mapping from semantic meaning → column index using headers.
        col = self._find_columns(headers)

        results = []
        for row in rows:
            result = self._parse_row(row, col, event_name, gender, relay, field)
            if result is not None:
                results.append(result)
        return results

    def _find_columns(self, headers: list[str]) -> dict:
        """
        Return a dict mapping semantic names to column indices.
        Handles the common MileSplit layout:
          PLACE | VIDEO | ATHLETE | (grade) | TEAM | MARK | WIND | HEAT/FLIGHT
        and falls back gracefully.
        """
        col = {}
        for i, h in enumerate(headers):
            if h in ('PLACE', 'PL', '#', 'RANK'):
                col.setdefault('place', i)
            elif h == 'ATHLETE' or h == 'NAME':
                col.setdefault('athlete', i)
                # The column immediately after ATHLETE with an empty (or blank)
                # header is the grade/year in school on MileSplit.
                if i + 1 < len(headers) and headers[i + 1] == '':
                    col['grade'] = i + 1
            elif h == 'TEAM' or h == 'SCHOOL':
                col.setdefault('team', i)
            elif h == 'MARK' or h == 'TIME' or h == 'RESULT':
                col.setdefault('mark', i)
            elif h == 'WIND':
                col.setdefault('wind', i)
            elif h in ('HEAT', 'FLIGHT', 'HT', 'FLT'):
                col.setdefault('heat', i)

        return col

    def _parse_row(
        self,
        row: list[str],
        col: dict,
        event_name: str,
        gender: str | None,
        relay: bool,
        field: bool,
    ) -> ParsedResult | None:
        """Convert one data row to a ParsedResult, or None if it looks empty/header."""

        def get(key):
            idx = col.get(key)
            if idx is None or idx >= len(row):
                return ''
            return row[idx].strip()

        place_str = get('place')
        athlete_raw = get('athlete')
        school = get('team')
        mark_str = get('mark')
        wind_str = get('wind')

        # Skip rows that have no meaningful data.
        if not mark_str and not athlete_raw:
            return None

        # Skip header-repeat rows (place column is non-numeric text like "PLACE").
        if place_str.upper() in ('PLACE', 'PL', '#', 'RANK', ''):
            pass  # fine — place will just be None

        place = None
        try:
            place = int(re.sub(r'\D', '', place_str)) if place_str else None
        except ValueError:
            pass

        wind = None
        try:
            wind = float(wind_str) if wind_str else None
        except ValueError:
            pass

        mark = (
            self.parse_distance_to_meters(mark_str)
            if field
            else self.parse_time_to_seconds(mark_str)
        )

        result = ParsedResult(
            event_name=event_name,
            gender=gender,
            place=place,
            athlete_name=athlete_raw,
            school=school,
            mark_display=mark_str,
            mark=mark,
            wind=wind,
        )

        if relay:
            result.relay_team = school

        return result
