"""
Generic table parser for various result formats.
Attempts to auto-detect column meanings from headers or patterns.
"""

import re
from bs4 import BeautifulSoup
from .base_parser import BaseParser, ParsedResult


class GenericTableParser(BaseParser):
    """
    Generic parser that tries to handle various table formats.
    Can work with HTML tables or tab/space-separated text.
    """

    def find_event_section(self, content: str, event_header: str) -> str:
        """Find event section by header text."""
        if not event_header:
            return content
        
        # Similar to milesplit_multi but more lenient
        escaped_header = re.escape(event_header)
        pattern = re.compile(rf'({escaped_header})', re.IGNORECASE)
        
        match = pattern.search(content)
        if not match:
            return content  # Return all if header not found
        
        start_pos = match.start()
        
        # Look for next section (double newline or similar header pattern)
        remaining = content[match.end():]
        
        # Find next event-like header or major separator
        next_section = re.search(
            r'\n\n\n|\n\s*(Boys|Girls|Men|Women)\s+\w+',
            remaining,
            re.IGNORECASE
        )
        
        if next_section:
            end_pos = match.end() + next_section.start()
            return content[start_pos:end_pos]
        
        return content[start_pos:]

    def parse(self, file_path: str, event_config: dict) -> list[ParsedResult]:
        """Parse results using generic detection."""
        content = self.read_file(file_path)
        section = self.find_event_section(content, event_config.get('event_header', ''))
        
        if not section:
            return []
        
        canonical_event = event_config.get('canonical_event', '')
        is_timed = self._is_timed_event(canonical_event)
        
        # Detect format and parse
        if '<table' in section.lower():
            return self._parse_html(section, is_timed)
        elif '\t' in section:
            return self._parse_tsv(section, is_timed)
        else:
            return self._parse_text(section, is_timed)

    def _is_timed_event(self, event_name: str) -> bool:
        """Determine if event is timed vs measured."""
        field_events = [
            'shot put', 'discus', 'javelin', 'high jump',
            'pole vault', 'long jump', 'triple jump',
            'decathlon', 'heptathlon'
        ]
        return not any(fe in event_name.lower() for fe in field_events)

    def _parse_html(self, section: str, is_timed: bool) -> list[ParsedResult]:
        """Parse HTML table with auto-detected columns."""
        results = []
        soup = BeautifulSoup(section, 'html.parser')
        
        for table in soup.find_all('table'):
            # Try to find header row
            headers = []
            header_row = table.find('tr')
            if header_row:
                headers = [th.get_text(strip=True).lower() 
                          for th in header_row.find_all(['th', 'td'])]
            
            # Map column indexes
            col_map = self._detect_columns(headers)
            
            # Parse data rows
            rows = table.find_all('tr')[1:] if headers else table.find_all('tr')
            
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(['td', 'th'])]
                result = self._extract_from_cells(cells, col_map, is_timed)
                if result and result.athlete_name:
                    results.append(result)
        
        return results

    def _parse_tsv(self, section: str, is_timed: bool) -> list[ParsedResult]:
        """Parse tab-separated values."""
        results = []
        lines = section.strip().split('\n')
        
        if not lines:
            return results
        
        # First non-empty line might be headers
        headers = []
        start_idx = 0
        
        for i, line in enumerate(lines):
            if line.strip():
                parts = line.split('\t')
                if self._looks_like_header(parts):
                    headers = [p.lower().strip() for p in parts]
                    start_idx = i + 1
                break
        
        col_map = self._detect_columns(headers)
        
        for line in lines[start_idx:]:
            if not line.strip():
                continue
            cells = [c.strip() for c in line.split('\t')]
            result = self._extract_from_cells(cells, col_map, is_timed)
            if result and result.athlete_name:
                results.append(result)
        
        return results

    def _parse_text(self, section: str, is_timed: bool) -> list[ParsedResult]:
        """Parse space-separated or fixed-width text."""
        results = []
        lines = section.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or self._looks_like_header([line]):
                continue
            
            result = self._parse_text_line(line, is_timed)
            if result and result.athlete_name:
                results.append(result)
        
        return results

    def _detect_columns(self, headers: list) -> dict:
        """Detect which columns contain which data."""
        col_map = {
            'place': None,
            'name': None,
            'school': None,
            'mark': None,
            'wind': None,
            'heat': None,
        }
        
        for i, header in enumerate(headers):
            header = header.lower()
            if header in ['pl', 'place', 'pos', 'position', '#']:
                col_map['place'] = i
            elif header in ['name', 'athlete', 'competitor']:
                col_map['name'] = i
            elif header in ['school', 'team', 'affiliation']:
                col_map['school'] = i
            elif header in ['time', 'mark', 'result', 'perf', 'performance']:
                col_map['mark'] = i
            elif header in ['wind', 'w']:
                col_map['wind'] = i
            elif header in ['heat', 'ht']:
                col_map['heat'] = i
        
        return col_map

    def _looks_like_header(self, parts: list) -> bool:
        """Check if a row looks like column headers."""
        header_words = [
            'place', 'name', 'school', 'team', 'time', 'mark',
            'athlete', 'result', 'wind', 'heat', 'lane', 'pl', 'pos'
        ]
        text = ' '.join(parts).lower()
        matches = sum(1 for w in header_words if w in text)
        return matches >= 2

    def _extract_from_cells(self, cells: list, col_map: dict, is_timed: bool) -> ParsedResult:
        """Extract result data from cells using column map."""
        result = ParsedResult()
        
        # Use mapped columns if available
        if col_map['place'] is not None and col_map['place'] < len(cells):
            try:
                result.place = int(cells[col_map['place']])
            except ValueError:
                pass
        
        if col_map['name'] is not None and col_map['name'] < len(cells):
            result.athlete_name = cells[col_map['name']]
        
        if col_map['school'] is not None and col_map['school'] < len(cells):
            result.school = cells[col_map['school']]
        
        if col_map['mark'] is not None and col_map['mark'] < len(cells):
            result.mark_display = cells[col_map['mark']]
            if is_timed:
                result.mark = self.parse_time_to_seconds(cells[col_map['mark']])
            else:
                result.mark = self.parse_distance_to_meters(cells[col_map['mark']])
        
        if col_map['wind'] is not None and col_map['wind'] < len(cells):
            result.wind = self.parse_wind(cells[col_map['wind']])
        
        # If columns weren't mapped, try auto-detection
        if not result.athlete_name:
            result = self._auto_detect_cells(cells, is_timed)
        
        return result

    def _auto_detect_cells(self, cells: list, is_timed: bool) -> ParsedResult:
        """Auto-detect cell meanings without headers."""
        result = ParsedResult()
        
        for i, cell in enumerate(cells):
            cell = cell.strip()
            if not cell:
                continue
            
            # Numeric at start = place
            if i == 0 and cell.isdigit():
                result.place = int(cell)
                continue
            
            # Time pattern
            if is_timed and re.match(r'^\d{1,2}:\d{2}', cell):
                result.mark_display = cell
                result.mark = self.parse_time_to_seconds(cell)
                continue
            
            # Seconds only
            if is_timed and re.match(r'^\d+\.\d+$', cell) and not result.mark:
                result.mark_display = cell
                result.mark = self.parse_time_to_seconds(cell)
                continue
            
            # Distance pattern
            if not is_timed and re.match(r"^\d+['\-]", cell):
                result.mark_display = cell
                result.mark = self.parse_distance_to_meters(cell)
                continue
            
            # Name (letters, spaces, common name chars)
            if re.match(r'^[A-Za-z][A-Za-z\s,.\'-]+$', cell):
                if not result.athlete_name:
                    result.athlete_name = cell
                elif not result.school:
                    result.school = cell
        
        return result

    def _parse_text_line(self, line: str, is_timed: bool) -> ParsedResult:
        """Parse a plain text line."""
        result = ParsedResult()
        
        # Extract place
        place_match = re.match(r'^(\d+)[.\s)\]]', line)
        if place_match:
            result.place = int(place_match.group(1))
            line = line[place_match.end():].strip()
        
        # Extract mark/time
        if is_timed:
            time_match = re.search(r'(\d{1,2}:\d{2}\.\d+|\d+\.\d{2})', line)
            if time_match:
                result.mark_display = time_match.group(1)
                result.mark = self.parse_time_to_seconds(time_match.group(1))
                line = line[:time_match.start()].strip()
        else:
            dist_match = re.search(r"(\d+['\-]\d+(?:\.\d+)?[\"']?)", line)
            if dist_match:
                result.mark_display = dist_match.group(1)
                result.mark = self.parse_distance_to_meters(dist_match.group(1))
                line = line[:dist_match.start()].strip()
        
        # Extract name and school from remaining
        paren_match = re.match(r'(.+?)\s*\(([^)]+)\)', line)
        if paren_match:
            result.athlete_name = paren_match.group(1).strip()
            result.school = paren_match.group(2).strip()
        else:
            parts = re.split(r'\s{2,}', line)
            if len(parts) >= 2:
                result.athlete_name = parts[0]
                result.school = parts[1]
            elif parts:
                result.athlete_name = parts[0]
        
        return result
