"""
School matching utility for identifying Fort Collins High School athletes.
Uses fuzzy matching to handle variations in school names.
"""

import yaml
from pathlib import Path
from rapidfuzz import fuzz, process


class SchoolMatcher:
    """Matches school names to identify Fort Collins athletes."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'schools.yaml'
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        self.target = config['target_school']
        self.target_aliases = [a.lower() for a in self.target['aliases']]
        self.threshold = self.target.get('match_threshold', 80)
        
        # Build exclusion list
        self.excluded_aliases = []
        for school in config.get('exclude_schools', []):
            self.excluded_aliases.extend([a.lower() for a in school['aliases']])

    def is_target_school(self, school_name: str) -> bool:
        """
        Determine if a school name matches Fort Collins High School.
        
        Returns True only if:
        1. It matches one of our target aliases above threshold
        2. It does NOT match any excluded school aliases
        """
        if not school_name:
            return False
        
        school_lower = school_name.lower().strip()
        
        # First, check for exact matches with our target aliases
        # This prevents "Fort Collins" from being excluded by "Fort Collins Christian"
        if school_lower in self.target_aliases:
            return True
        
        # Then check if it matches an excluded school
        for excluded in self.excluded_aliases:
            score = fuzz.ratio(school_lower, excluded)
            if score >= 85:  # Higher threshold for exclusions
                return False
            # Check if excluded is a substring of school name
            if excluded in school_lower and fuzz.partial_ratio(school_lower, excluded) >= 90:
                return False
        
        # Now check fuzzy matches with target school
        for alias in self.target_aliases:
            score = fuzz.ratio(school_lower, alias)
            if score >= self.threshold:
                return True
            # Check partial match for abbreviations
            if fuzz.partial_ratio(school_lower, alias) >= 90:
                # Verify it's not a false positive
                if len(school_lower) >= 4:  # Avoid matching "FC" alone
                    return True
        
        return False

    def get_canonical_name(self) -> str:
        """Return the canonical school name."""
        return self.target['canonical_name']


# Singleton instance
_matcher = None


def get_school_matcher(config_path: str = None) -> SchoolMatcher:
    """Get or create the school matcher singleton."""
    global _matcher
    if _matcher is None:
        _matcher = SchoolMatcher(config_path)
    return _matcher


def is_fort_collins(school_name: str) -> bool:
    """Convenience function to check if a school is Fort Collins."""
    return get_school_matcher().is_target_school(school_name)
