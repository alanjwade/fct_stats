"""
Parser for pages containing a single event's results.
The entire file is assumed to be results for one event.
"""

import re
from .base_parser import BaseParser, ParsedResult
from .milesplit_multi import MilesplitMultiParser


class MilesplitSingleParser(MilesplitMultiParser):
    """
    Parses pages with a single event.
    Inherits parsing logic from MilesplitMultiParser but
    doesn't need to find event sections.
    """

    def find_event_section(self, content: str, event_header: str) -> str:
        """
        For single-event files, the entire content is the event section.
        We may skip header lines but return most of the content.
        """
        lines = content.split('\n')
        
        # Skip initial blank lines and potential header
        start_idx = 0
        for i, line in enumerate(lines):
            line = line.strip()
            # Skip empty lines at start
            if not line:
                continue
            # Skip lines that look like headers (event titles, meet info, etc.)
            if self._is_header_line(line):
                start_idx = i + 1
                continue
            # Found data, stop skipping
            break
        
        return '\n'.join(lines[start_idx:])

    def _is_header_line(self, line: str) -> bool:
        """Check if a line looks like a header rather than results."""
        line = line.strip().lower()
        
        # Common header patterns
        header_patterns = [
            r'^(boys|girls|men|women)',  # Event gender prefix
            r'meters?$',                  # Event name ending
            r'(varsity|jv|junior varsity)',
            r'(finals?|prelim)',
            r'^(place|name|school|time|mark)',  # Column headers
            r'^-+$',                       # Separator lines
            r'^=+$',
        ]
        
        for pattern in header_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        
        return False

    def parse(self, file_path: str, event_config: dict) -> list[ParsedResult]:
        """Parse results from a single-event file."""
        content = self.read_file(file_path)
        section = self.find_event_section(content, event_config.get('event_header', ''))
        
        if not section:
            return []
        
        # Determine if this is a timed event
        canonical_event = event_config.get('canonical_event', '')
        is_timed = self._is_timed_event(canonical_event)
        
        # Use parent class parsing methods
        if '<table' in section.lower() or '<tr' in section.lower():
            return self._parse_html_table(section, is_timed)
        else:
            return self._parse_text_results(section, is_timed)
