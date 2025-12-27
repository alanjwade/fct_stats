"""
Parser for HyTek text format results (used by Rapid Results Timing).
"""

import re
from .base_parser import BaseParser, ParsedResult


class HyTekTextParser(BaseParser):
    """Parser for HyTek Meet Manager text output format."""
    
    def can_parse(self, content: str) -> bool:
        """Check if this parser can handle the content."""
        return 'HY-TEK\'s Meet Manager' in content or re.search(r'Event \d+\s+(Girls|Boys)', content) is not None
    
    def parse(self, file_path: str, event_config: dict) -> list:
        """Parse specific event from HyTek text format."""
        content = self.read_file(file_path)
        
        # For HyTek text files, we parse all events at once
        # This is different from other parsers that parse one event at a time
        all_results = self.parse_all_events(content)
        
        # Filter to the requested event if specified
        if 'canonical_event' in event_config:
            canonical = event_config['canonical_event']
            gender = event_config.get('gender', '')
            all_results = [r for r in all_results if r.event_name == f"{gender} {canonical}"]
        
        return all_results
    
    def find_event_section(self, content: str, event_header: str) -> str:
        """Extract the section of content for a specific event."""
        # Find the event header
        event_pattern = re.compile(rf'^Event \d+\s+{re.escape(event_header)}$', re.MULTILINE)
        match = event_pattern.search(content)
        
        if not match:
            return ""
        
        start = match.start()
        
        # Find next event or end of file
        next_match = re.search(r'^Event \d+\s+', content[start + 1:], re.MULTILINE)
        if next_match:
            end = start + 1 + next_match.start()
        else:
            end = len(content)
        
        return content[start:end]
    
    def parse_all_events(self, content: str) -> list:
        """Parse all events from HyTek text format."""
        events = []
        
        # Split content into events using the Event header pattern
        event_pattern = re.compile(r'^Event \d+\s+(Girls|Boys)\s+(.+?)$', re.MULTILINE)
        
        # Find all event headers
        matches = list(event_pattern.finditer(content))
        
        for i, match in enumerate(matches):
            event_start = match.start()
            event_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            
            event_text = content[event_start:event_end]
            gender = match.group(1)
            event_name = match.group(2).strip()
            
            # Determine if this is a relay
            is_relay = 'relay' in event_name.lower()
            
            # Parse this event
            if is_relay:
                event_results = self._parse_relay_event(event_text, gender, event_name)
            else:
                event_results = self._parse_individual_event(event_text, gender, event_name)
            
            events.extend(event_results)
        
        return events
    
    def _parse_individual_event(self, event_text: str, gender: str, event_name: str) -> list:
        """Parse individual (non-relay) event."""
        results = []
        
        # Normalize gender
        gender_code = 'M' if gender == 'Boys' else 'F'
        
        # Add gender prefix to event name
        full_event_name = f"{gender} {event_name}"
        
        # Pattern for individual results
        # Example: " 1 # 3155 Tortorelli Cruz, 12 Riverdale Ri 12.23S 0.1 13 10"
        # or: " 6 # 696 Folkestad, Ava 10 Fort Collins 12.71 0.1 13 3"
        # or: " 23 # 814 Wade, Joseph 12 Fort Collins x4:38.45 4" (x prefix = non-scoring)
        # or: " 3 # 692 Dodd, Chloe 12 Fort Collins J10-04.00 6" (J prefix = tied on countback)
        result_pattern = re.compile(
            r'^\s+(\d+)\s+#\s*(\d+)\s+(.+?),\s+(.+?)\s+(\d+)\s+([A-Za-z ]+?)\s+([a-zA-Z]?[\d:\.\-]+[a-zA-Z]*)\s+'
        )
        
        for line in event_text.split('\n'):
            match = result_pattern.match(line)
            if not match:
                continue
            
            place = int(match.group(1))
            athlete_number = match.group(2)
            last_name = match.group(3).strip()
            first_name = match.group(4).strip()
            year = match.group(5)
            school = match.group(6).strip()
            mark_str = match.group(7).strip()
            
            # Skip if mark is DNS, DNF, SCR, etc.
            if re.match(r'^[A-Z]{2,}$', mark_str):
                continue
            
            # Check if mark contains 'x' prefix (non-scoring)
            mark_clean = mark_str
            if mark_str.startswith('x'):
                mark_clean = mark_str[1:]
            
            # Remove letter prefixes (J for tie, S for stadium record, etc.)
            mark_clean = re.sub(r'^[a-zA-Z]', '', mark_clean)
            
            # Convert mark to float
            if ':' in mark_clean:
                # Time format MM:SS.ss - remove any trailing letters
                mark_clean = re.sub(r'[a-zA-Z]+$', '', mark_clean)
                parts = mark_clean.split(':')
                try:
                    minutes = int(parts[0])
                    seconds = float(parts[1])
                    mark = minutes * 60 + seconds
                except (ValueError, IndexError):
                    continue
            elif '-' in mark_clean and not mark_clean.startswith('-'):
                # Feet-inches format (e.g., "10-04.00" or "19-08.25")
                # Remove any trailing letters
                mark_clean = re.sub(r'[a-zA-Z]+$', '', mark_clean)
                # Convert to meters
                parts = mark_clean.split('-')
                try:
                    feet = int(parts[0])
                    inches = float(parts[1])
                    total_inches = feet * 12 + inches
                    mark = total_inches * 0.0254  # Convert inches to meters
                except (ValueError, IndexError):
                    continue
            else:
                # Plain number - remove any remaining letters
                mark_clean = re.sub(r'[a-zA-Z]', '', mark_clean)
                try:
                    mark = float(mark_clean)
                except ValueError:
                    continue
            
            # Determine if this is a timed event or field event
            is_timed = 'Meter' in event_name or 'Relay' in event_name
            
            results.append(ParsedResult(
                event_name=full_event_name,
                athlete_name=f"{first_name} {last_name}",
                school=school,
                mark=mark,
                mark_display=mark_str,
                place=place,
                gender=gender_code,
                year=int(year) if year.isdigit() else None
            ))
        
        return results
    
    def _parse_relay_event(self, event_text: str, gender: str, event_name: str) -> list:
        """Parse relay event with team members."""
        results = []
        
        # Normalize gender
        gender_code = 'M' if gender == 'Boys' else 'F'
        
        # Add gender prefix to event name
        full_event_name = f"{gender} {event_name}"
        
        # Pattern for relay team header
        # Example: " 8 Fort Collins 'A' 10:56.50 1"
        team_pattern = re.compile(
            r'^\s+(\d+)\s+(.+?)\s+\'([A-Z])\'\s+([\d:\.]+[a-zA-Z]*)\s+(\d+)?'
        )
        
        # Pattern for relay team members
        # Example: " 1) #702 Hoppin, Macie 10 2) #725 Sullivan, Sarah 9"
        member_pattern = re.compile(
            r'(\d+)\)\s+#(\d+)\s+(.+?),\s+(.+?)\s+(\d+)'
        )
        
        lines = event_text.split('\n')
        current_team = None
        current_school = None
        current_relay_team = None
        current_mark = None
        current_place = None
        team_members = []
        
        for line in lines:
            team_match = team_pattern.match(line)
            member_match = member_pattern.search(line)
            
            if team_match:
                # Save previous team if exists
                if current_school and current_mark and team_members:
                    # Create result for each team member
                    for member in team_members:
                        results.append(ParsedResult(
                            event_name=full_event_name,
                            athlete_name=member['name'],
                            school=current_school,
                            mark=current_mark,
                            mark_display=current_mark_str,
                            place=current_place,
                            gender=gender_code,
                            year=member.get('year'),
                            relay_team=current_relay_team  # Track which relay team (A, B, etc.)
                        ))
                
                # Start new team
                current_place = int(team_match.group(1))
                current_school = team_match.group(2).strip()
                current_relay_team = team_match.group(3)  # A, B, C, etc.
                current_mark_str = team_match.group(4).strip()
                
                # Parse mark
                mark_clean = re.sub(r'[a-zA-Z]', '', current_mark_str)
                if ':' in mark_clean:
                    parts = mark_clean.split(':')
                    minutes = int(parts[0])
                    seconds = float(parts[1])
                    current_mark = minutes * 60 + seconds
                else:
                    try:
                        current_mark = float(mark_clean)
                    except ValueError:
                        current_mark = None
                
                team_members = []
            
            elif member_match and current_school:
                # Add member to current team
                last_name = member_match.group(3).strip()
                first_name = member_match.group(4).strip()
                year = member_match.group(5)
                
                team_members.append({
                    'name': f"{first_name} {last_name}",
                    'year': int(year) if year.isdigit() else None
                })
        
        # Save last team
        if current_school and current_mark and team_members:
            for member in team_members:
                results.append(ParsedResult(
                    event_name=full_event_name,
                    athlete_name=member['name'],
                    school=current_school,
                    mark=current_mark,
                    mark_display=current_mark_str,
                    place=current_place,
                    gender=gender_code,
                    year=member.get('year'),
                    relay_team=current_relay_team
                ))
        
        return results
