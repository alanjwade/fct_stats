"""
Parser for MileSplit plain-text export format.

This format is produced when copying MileSplit meet results as text, e.g.:
    https://co.milesplit.com/meets/.../results

Each result spans multiple lines:
  3-line (athlete has a recorded grade):
    "{place} {school}"
    "{athlete_name}"
    " {grade} {school} {mark} [{wind}] {heat}"

  2-line (athlete has no recorded grade):
    "{place} {school} {athlete_name}"
    " {school} {mark} [{wind}] {heat}"

  Relay (3-line):
    "{place} {school}"
    "{school}"
    " {mark} {heat}"

Event section headers look like:  "Boys 100 Meter Dash Finals"
Column headers look like:         "Place Video Athlete Team Mark Wind Heat"
"""

import re
from .base_parser import BaseParser, ParsedResult


class MilesplitTextParser(BaseParser):
    """Parser for MileSplit plain-text export format."""

    FIELD_EVENT_MARKERS = [
        'high jump', 'pole vault', 'long jump', 'triple jump',
        'shot put', 'discus', 'javelin', 'hammer', 'weight throw',
    ]

    def can_parse(self, content: str) -> bool:
        """Detect MileSplit text export by its column-header and event-header patterns."""
        has_column_header = (
            'Place Video Athlete Team Mark' in content
            or 'Place Video Team Mark' in content
        )
        has_event_header = bool(
            re.search(r'^(Boys|Girls)\s+.+?\s+Finals\s*$', content, re.MULTILINE)
        )
        return has_column_header and has_event_header

    def parse(self, file_path: str, event_config: dict) -> list:
        """Parse all events from the file."""
        content = self.read_file(file_path)
        return self.parse_all_events(content)

    def find_event_section(self, content: str, event_header: str) -> str:
        """Find the content section for a specific event."""
        pattern = re.compile(re.escape(event_header), re.IGNORECASE)
        match = pattern.search(content)
        if not match:
            return ''
        next_event = re.search(r'\n(Boys|Girls)\s+\d', content[match.end():])
        if next_event:
            return content[match.start():match.end() + next_event.start()]
        return content[match.start():]

    def parse_all_events(self, content: str) -> list:
        """Parse every event section found in the full file content."""
        results = []
        event_pattern = re.compile(
            r'^(Boys|Girls)\s+(.+?)\s+Finals\s*$',
            re.MULTILINE,
        )
        matches = list(event_pattern.finditer(content))

        for idx, match in enumerate(matches):
            gender = 'M' if match.group(1) == 'Boys' else 'F'
            event_name = match.group(2).strip()

            section_start = match.end()
            section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
            section = content[section_start:section_end]

            results.extend(self._parse_event_section(section, event_name, gender))

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_field_event(self, event_name: str) -> bool:
        name_lower = event_name.lower()
        return any(marker in name_lower for marker in self.FIELD_EVENT_MARKERS)

    def _parse_event_section(self, section: str, event_name: str, gender: str) -> list:
        """Parse all results from one event section."""
        results = []
        lines = section.split('\n')
        is_relay = 'relay' in event_name.lower()
        is_timed = not self._is_field_event(event_name)

        i = 0
        while i < len(lines):
            line = lines[i]

            # Skip blank lines and column-header lines
            if not line.strip() or 'Place Video' in line:
                i += 1
                continue

            # A result block begins with a place number
            place_match = re.match(r'^(\d+)\s+(.+)$', line)
            if not place_match:
                i += 1
                continue

            place = int(place_match.group(1))
            line1_rest = place_match.group(2).strip()

            # The mark line is the first subsequent line that starts with whitespace
            j = i + 1
            while j < len(lines):
                if lines[j].startswith((' ', '\t')):
                    break
                j += 1

            if j >= len(lines):
                i += 1
                continue

            mark_line = lines[j].strip()
            middle_lines = [
                lines[k].strip()
                for k in range(i + 1, j)
                if lines[k].strip()
            ]

            result = ParsedResult(
                event_name=event_name,
                gender=gender,
                place=place,
                relay_team=line1_rest if is_relay else None,
            )

            self._parse_mark_line(result, mark_line, is_timed)

            if is_relay:
                result.school = result.school or line1_rest
                result.athlete_name = ''
            elif middle_lines:
                # 3-line format: line1_rest = school, middle_lines[0] = name
                result.school = result.school or line1_rest
                result.athlete_name = middle_lines[0]
            else:
                # 2-line format: line1_rest = "{school} {athlete_name}"
                school_from_mark = result.school
                if school_from_mark and line1_rest.startswith(school_from_mark):
                    leftover = line1_rest[len(school_from_mark):].strip()
                    result.athlete_name = leftover
                else:
                    result.school = result.school or line1_rest
                    result.athlete_name = ''

            results.append(result)
            i = j + 1

        return results

    def _parse_mark_line(self, result: ParsedResult, mark_line: str, is_timed: bool) -> None:
        """
        Parse the mark line and populate result.mark, mark_display, school, wind, heat.

        Mark line formats (all begin with leading whitespace, stripped before entry):
          "{grade} {school} {mark} {wind} {heat}"  — individual, with grade
          "{school} {mark} {wind} {heat}"           — individual, no grade
          "{mark} {heat}"                           — relay
          "{mark} {wind} {heat}"                    — relay with wind
        """
        tokens = mark_line.split()
        if not tokens:
            return

        # Locate the mark token (time or feet-inches distance)
        mark_idx = None
        for idx, token in enumerate(tokens):
            # Time with colon: "1:23.45" or "10:58.98"
            if re.match(r'^\d+:\d{2}\.\d{2}$', token):
                mark_idx = idx
                break
            # Seconds with exactly 2 decimal places: "11.10", "41.61"
            if re.match(r'^\d+\.\d{2}$', token):
                mark_idx = idx
                break
            # Feet-inches: "21-11.50", "5-10.00", "138-5.00"
            if re.match(r'^\d+-\d+\.\d+$', token):
                mark_idx = idx
                break

        if mark_idx is None:
            return

        result.mark_display = tokens[mark_idx]
        if is_timed:
            result.mark = self.parse_time_to_seconds(tokens[mark_idx])
        else:
            result.mark = self.parse_distance_to_meters(tokens[mark_idx])

        # Tokens after the mark: optional wind (decimal) then optional heat (integer)
        for token in tokens[mark_idx + 1:]:
            if '.' in token:
                try:
                    result.wind = float(token)
                except ValueError:
                    pass
            elif token.isdigit():
                result.heat = int(token)

        # Tokens before the mark: optional grade then school name
        before = tokens[:mark_idx]
        if before:
            grade_offset = 0
            if re.match(r'^\d{1,2}$', before[0]):
                try:
                    grade = int(before[0])
                    if 7 <= grade <= 12:
                        grade_offset = 1
                except ValueError:
                    pass
            school_tokens = before[grade_offset:]
            if school_tokens:
                result.school = ' '.join(school_tokens)
