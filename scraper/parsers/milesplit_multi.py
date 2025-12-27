"""
Parser for MileSplit pages containing multiple events.
Each event has a header followed by results, then the next event header.
"""

import re
from bs4 import BeautifulSoup
from .base_parser import BaseParser, ParsedResult


class MilesplitMultiParser(BaseParser):
    """
    Parses pages with multiple events.
    Looks for event headers to identify sections, then parses each section.
    """

    def find_event_section(self, content: str, event_header: str) -> str:
        """
        Find the section of content for a specific event.
        
        Looks for event_header text, then captures everything until
        the next similar header pattern or end of content.
        """
        if not event_header:
            return content
        
        # Escape special regex characters in the header
        escaped_header = re.escape(event_header)
        
        # Try to find the header
        header_pattern = re.compile(
            rf'({escaped_header})',
            re.IGNORECASE | re.MULTILINE
        )
        
        match = header_pattern.search(content)
        if not match:
            return ""
        
        start_pos = match.start()
        
        # Find the next event header (common patterns)
        # Look for patterns like "Boys 200 Meters", "Girls Shot Put", etc.
        next_event_pattern = re.compile(
            r'\n\s*((?:Boys|Girls|Men\'?s?|Women\'?s?)\s+\d*\s*(?:Meter|Mile|Shot|Discus|Javelin|High|Long|Triple|Pole|Hurdle|Relay|Steeplechase|Medley))',
            re.IGNORECASE
        )
        
        # Search for next event after our header
        remaining_content = content[match.end():]
        next_match = next_event_pattern.search(remaining_content)
        
        if next_match:
            end_pos = match.end() + next_match.start()
            return content[start_pos:end_pos]
        else:
            # No next event found, take everything to the end
            return content[start_pos:]

    def parse(self, file_path: str, event_config: dict) -> list[ParsedResult]:
        """Parse results from a multi-event file."""
        content = self.read_file(file_path)
        
        event_header = event_config.get('event_header', '')
        section = self.find_event_section(content, event_header)
        
        if not section:
            return []
        
        # Determine if this is a timed event or measured event
        canonical_event = event_config.get('canonical_event', '')
        is_timed = self._is_timed_event(canonical_event)
        
        # Try HTML parsing first
        if '<table' in section.lower() or '<tr' in section.lower():
            return self._parse_html_table(section, is_timed)
        else:
            return self._parse_text_results(section, is_timed)

    def _is_timed_event(self, event_name: str) -> bool:
        """Determine if event is timed (running) vs measured (field)."""
        field_events = [
            'shot put', 'discus', 'javelin', 'high jump', 
            'pole vault', 'long jump', 'triple jump',
            'decathlon', 'heptathlon'
        ]
        return not any(fe in event_name.lower() for fe in field_events)

    def _parse_html_table(self, section: str, is_timed: bool) -> list[ParsedResult]:
        """Parse results from an HTML table."""
        results = []
        soup = BeautifulSoup(section, 'html.parser')
        
        # Find all tables
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 3:
                    continue
                
                # Try to extract data from cells
                result = self._parse_table_row(cells, is_timed)
                if result and result.athlete_name:
                    results.append(result)
        
        return results

    def _parse_table_row(self, cells: list, is_timed: bool) -> ParsedResult:
        """Parse a single table row into a ParsedResult."""
        result = ParsedResult()
        
        # Common column patterns - try to detect
        cell_texts = [c.get_text(strip=True) for c in cells]
        
        for i, text in enumerate(cell_texts):
            # Place (usually first, numeric)
            if i == 0 and text.isdigit():
                result.place = int(text)
                continue
            
            # Name detection (contains letters, no numbers except maybe suffix)
            if re.match(r'^[A-Za-z\s,.\'-]+$', text) and len(text) > 2:
                if not result.athlete_name:
                    result.athlete_name = text
                elif not result.school:
                    result.school = text
                continue
            
            # Time/mark detection
            if re.match(r'^\d+[:.]\d+', text) or re.match(r"^\d+['\-]\d+", text):
                if not result.mark_display:
                    result.mark_display = text
                    if is_timed:
                        result.mark = self.parse_time_to_seconds(text)
                    else:
                        result.mark = self.parse_distance_to_meters(text)
                continue
            
            # Wind detection
            if re.match(r'^[+-]?\d+\.\d+$', text) and result.mark_display:
                result.wind = self.parse_wind(text)
        
        return result

    def _parse_text_results(self, section: str, is_timed: bool) -> list[ParsedResult]:
        """Parse results from plain text format."""
        results = []
        lines = section.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            result = self._parse_text_line(line, is_timed)
            if result and result.athlete_name:
                results.append(result)
        
        return results

    def _parse_text_line(self, line: str, is_timed: bool) -> ParsedResult:
        """Parse a single line of text results."""
        result = ParsedResult()
        
        # Common patterns:
        # "1  John Smith      Fort Collins    11.45  +1.2"
        # "1. Smith, John (Fort Collins) 11.45"
        
        # Try to extract place from start
        place_match = re.match(r'^(\d+)[.\s]', line)
        if place_match:
            result.place = int(place_match.group(1))
            line = line[place_match.end():].strip()
        
        # Try to extract time/mark (look for patterns)
        if is_timed:
            time_match = re.search(r'(\d{1,2}:\d{2}\.\d+|\d+\.\d+)\s*([+-]?\d+\.\d+)?', line)
            if time_match:
                result.mark_display = time_match.group(1)
                result.mark = self.parse_time_to_seconds(time_match.group(1))
                if time_match.group(2):
                    result.wind = self.parse_wind(time_match.group(2))
                line = line[:time_match.start()].strip()
        else:
            dist_match = re.search(r"(\d+['\-]\d+(?:\.\d+)?[\"']?|\d+\.\d+m?)", line)
            if dist_match:
                result.mark_display = dist_match.group(1)
                result.mark = self.parse_distance_to_meters(dist_match.group(1))
                line = line[:dist_match.start()].strip()
        
        # Remaining should be name and school
        # Try parentheses format: "John Smith (Fort Collins)"
        paren_match = re.match(r'(.+?)\s*\(([^)]+)\)', line)
        if paren_match:
            result.athlete_name = paren_match.group(1).strip()
            result.school = paren_match.group(2).strip()
        else:
            # Try to split by multiple spaces
            parts = re.split(r'\s{2,}', line)
            if len(parts) >= 2:
                result.athlete_name = parts[0].strip()
                result.school = parts[1].strip()
            elif len(parts) == 1:
                result.athlete_name = parts[0].strip()
        
        return result
