"""
Event matching utility for normalizing event names to canonical forms.
Uses fuzzy matching to handle variations in event naming.
"""

import yaml
from pathlib import Path
from rapidfuzz import fuzz, process
from typing import Optional


class EventMatcher:
    """Matches event names to canonical event names."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'canonical_events.yaml'
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        self.events = config['events']
        
        # Build lookup dictionary: alias -> canonical name
        self.alias_map = {}
        for event in self.events:
            canonical = event['name']
            self.alias_map[canonical.lower()] = canonical
            for alias in event.get('aliases', []):
                self.alias_map[alias.lower()] = canonical

    def match(self, event_name: str, gender: str = None) -> Optional[str]:
        """
        Match an event name to its canonical form.
        
        Args:
            event_name: The event name to match
            gender: 'M' or 'F' to help disambiguate gender-specific events
            
        Returns:
            Canonical event name or None if no match
        """
        if not event_name:
            return None
        
        event_lower = event_name.lower().strip()
        
        # Strip common prefixes and suffixes
        import re
        event_lower = re.sub(r'^(boys?|girls?|mens?|womens?)\s+', '', event_lower)
        event_lower = re.sub(r'\s+(finals?|prelims?|preliminaries?|heats?)$', '', event_lower)
        event_lower = event_lower.strip()
        
        # Direct match
        if event_lower in self.alias_map:
            return self.alias_map[event_lower]
        
        # Fuzzy match
        aliases = list(self.alias_map.keys())
        result = process.extractOne(
            event_lower,
            aliases,
            scorer=fuzz.ratio,
            score_cutoff=75
        )
        
        if result:
            matched_alias, score, _ = result
            canonical = self.alias_map[matched_alias]
            
            # Check gender-specific events
            event_info = self.get_event_info(canonical)
            if event_info and event_info.get('gender_specific'):
                if gender and event_info['gender_specific'] != gender:
                    # Try to find gender-appropriate alternative
                    return self._find_gender_alternative(event_lower, gender)
            
            return canonical
        
        return None

    def _find_gender_alternative(self, event_name: str, gender: str) -> Optional[str]:
        """Find a gender-appropriate alternative event."""
        # Common case: 100m hurdles (F) vs 110m hurdles (M)
        for event in self.events:
            if event.get('gender_specific') == gender:
                if event['category'] == 'hurdles':
                    # Check if the event name contains hurdles
                    if 'hurdle' in event_name:
                        return event['name']
        return None

    def get_event_info(self, canonical_name: str) -> Optional[dict]:
        """Get full event info by canonical name."""
        for event in self.events:
            if event['name'] == canonical_name:
                return event
        return None

    def get_all_events(self) -> list[dict]:
        """Get all canonical events."""
        return self.events

    def is_timed_event(self, canonical_name: str) -> bool:
        """Check if an event is timed (vs measured)."""
        event_info = self.get_event_info(canonical_name)
        if event_info:
            return event_info.get('timed', True)
        return True

    def is_lower_better(self, canonical_name: str) -> bool:
        """Check if lower marks are better for this event."""
        event_info = self.get_event_info(canonical_name)
        if event_info:
            return event_info.get('lower_is_better', True)
        return True


# Singleton instance
_matcher = None


def get_event_matcher(config_path: str = None) -> EventMatcher:
    """Get or create the event matcher singleton."""
    global _matcher
    if _matcher is None:
        _matcher = EventMatcher(config_path)
    return _matcher


def match_event(event_name: str, gender: str = None) -> Optional[str]:
    """Convenience function to match an event name."""
    return get_event_matcher().match(event_name, gender)
