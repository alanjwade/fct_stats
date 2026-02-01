#!/usr/bin/env python3
"""
Parse a new meet results file and save to the parsed_meets directory.

This script:
1. Detects which parser can handle the input file
2. Extracts all results for Fort Collins athletes
3. Validates the results (reasonable count, expected events)
4. Saves to data/parsed_meets/YYYY/meet_name.json

Usage:
    python parse_new_meet.py <input_file> --meet "Meet Name" --date 2025-04-15 [--level varsity]
"""

import json
import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.parsers import PARSERS, ParsedResult
from scraper.event_matcher import get_event_matcher
from scraper.school_matcher import SchoolMatcher

# Expected events that Fort Collins typically competes in
EXPECTED_EVENTS = {
    'track': ['100m', '200m', '400m', '800m', '1600m', '3200m'],
    'hurdles': ['100m Hurdles', '110m Hurdles', '300m Hurdles'],
    'relays': ['4x100m Relay', '4x200m Relay', '4x400m Relay', '4x800m Relay'],
    'field': ['High Jump', 'Pole Vault', 'Long Jump', 'Triple Jump', 'Shot Put', 'Discus']
}


def slugify(name: str) -> str:
    """Convert meet name to a safe filename slug."""
    slug = re.sub(r'[^a-zA-Z0-9\s\-]', '', name)
    slug = re.sub(r'\s+', '_', slug.strip())
    slug = slug.lower()
    return slug


def detect_parser(content: str) -> tuple[str, any]:
    """
    Try each parser to see which can handle this content.
    Returns (parser_name, parser) or (None, None).
    """
    for name, parser in PARSERS.items():
        if hasattr(parser, 'can_parse') and parser.can_parse(content):
            return name, parser
    return None, None


def is_fort_collins(school_name: str) -> bool:
    """Check if school name matches Fort Collins."""
    if not school_name:
        return False
    school_lower = school_name.lower().strip()
    return any(pattern in school_lower for pattern in [
        'fort collins', 'ft collins', 'ft. collins', 'fchs',
        'lambkins', 'lambkin'
    ])


def extract_fc_results(all_results: list, event_matcher) -> list:
    """
    Filter results to only Fort Collins athletes and convert to our format.
    """
    fc_results = []
    
    for result in all_results:
        if isinstance(result, ParsedResult):
            result_dict = result.to_dict()
        else:
            result_dict = result
        
        school = result_dict.get('school', '')
        if not is_fort_collins(school):
            continue
        
        # Convert to our standard format
        event_name = result_dict.get('event_name', '')
        gender = result_dict.get('gender')
        
        # Try to get gender from event name if not set
        if not gender and event_name:
            if 'Girls' in event_name or 'Women' in event_name:
                gender = 'F'
                event_name = re.sub(r'^(Girls|Women)\s+', '', event_name)
            elif 'Boys' in event_name or 'Men' in event_name:
                gender = 'M'
                event_name = re.sub(r'^(Boys|Men)\s+', '', event_name)
        
        # Match to canonical event
        if event_name and gender:
            canonical = event_matcher.match(event_name, gender)
            if canonical:
                event_name = canonical
        
        # Parse athlete name
        athlete_name = result_dict.get('athlete_name', '')
        first_name, last_name = '', ''
        if athlete_name:
            if ',' in athlete_name:
                parts = athlete_name.split(',', 1)
                last_name = parts[0].strip()
                first_name = parts[1].strip() if len(parts) > 1 else ''
            else:
                parts = athlete_name.split()
                if len(parts) >= 2:
                    first_name = parts[0]
                    last_name = ' '.join(parts[1:])
                elif parts:
                    first_name = parts[0]
        
        fc_result = {
            'event': event_name,
            'athlete_first': first_name,
            'athlete_last': last_name,
            'gender': gender,
            'mark': result_dict.get('mark'),
            'mark_display': result_dict.get('mark_display', ''),
            'place': result_dict.get('place'),
            'level': 'varsity',  # Will be updated from meet config
        }
        
        # Handle relay
        relay_team = result_dict.get('relay_team')
        if relay_team:
            fc_result['is_relay'] = True
            # Parse relay members if available
            if isinstance(relay_team, list):
                fc_result['relay_members'] = relay_team
        
        fc_results.append(fc_result)
    
    return fc_results


def validate_results(results: list) -> tuple[bool, list[str]]:
    """
    Validate that the parsed results look reasonable.
    Returns (is_valid, list_of_issues).
    """
    issues = []
    
    # Check we have a reasonable number of results
    if len(results) < 5:
        issues.append(f"Only {len(results)} results found - expected more for a typical meet")
    
    if len(results) > 500:
        issues.append(f"Found {len(results)} results - unusually high, may have parsing issues")
    
    # Check we have results in multiple events
    events = set(r.get('event', '') for r in results)
    if len(events) < 3:
        issues.append(f"Only {len(events)} different events found - expected more variety")
    
    # Check for both genders
    genders = set(r.get('gender') for r in results)
    if 'M' not in genders:
        issues.append("No boys results found")
    if 'F' not in genders:
        issues.append("No girls results found")
    
    # Check we have some expected events
    found_expected = 0
    all_expected = []
    for category, event_list in EXPECTED_EVENTS.items():
        all_expected.extend(event_list)
    
    for event in events:
        if event in all_expected:
            found_expected += 1
    
    if found_expected < 3:
        issues.append(f"Only {found_expected} expected event types found - check event name mapping")
    
    # Check for athletes with names
    athletes_with_names = sum(1 for r in results if r.get('athlete_first') or r.get('athlete_last'))
    if athletes_with_names < len(results) * 0.8:
        issues.append(f"Only {athletes_with_names}/{len(results)} results have athlete names")
    
    is_valid = len(issues) == 0
    return is_valid, issues


def print_summary(results: list, parser_name: str):
    """Print a summary of parsed results."""
    events_by_gender = defaultdict(lambda: defaultdict(int))
    
    for r in results:
        gender = r.get('gender', '?')
        event = r.get('event', 'Unknown')
        events_by_gender[gender][event] += 1
    
    print(f"\n{'='*60}")
    print(f"Parser used: {parser_name}")
    print(f"Total Fort Collins results: {len(results)}")
    print(f"{'='*60}")
    
    for gender in ['M', 'F']:
        if gender not in events_by_gender:
            continue
        label = "Boys" if gender == 'M' else "Girls"
        print(f"\n{label}:")
        for event, count in sorted(events_by_gender[gender].items()):
            print(f"  {event}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description='Parse a new meet results file for Fort Collins athletes'
    )
    parser.add_argument('input_file', help='Path to meet results file (HTML or text)')
    parser.add_argument('--meet', '-m', required=True, help='Meet name')
    parser.add_argument('--date', '-d', required=True, help='Meet date (YYYY-MM-DD)')
    parser.add_argument('--level', '-l', default='varsity', 
                       choices=['varsity', 'jv', 'open'], help='Competition level')
    parser.add_argument('--year', '-y', type=int, help='Year (defaults to date year)')
    parser.add_argument('--output', '-o', help='Output file path (auto-generated if not specified)')
    parser.add_argument('--force', '-f', action='store_true', 
                       help='Save even if validation fails')
    parser.add_argument('--parser', '-p', help='Force use of specific parser')
    
    args = parser.parse_args()
    
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1
    
    # Read input file
    print(f"Reading {input_path}...")
    with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # Detect or use specified parser
    if args.parser:
        if args.parser not in PARSERS:
            print(f"Error: Unknown parser '{args.parser}'")
            print(f"Available parsers: {list(PARSERS.keys())}")
            return 1
        parser_name = args.parser
        selected_parser = PARSERS[parser_name]
    else:
        parser_name, selected_parser = detect_parser(content)
        if not selected_parser:
            print("Error: Could not detect appropriate parser for this file format")
            print("Available parsers:")
            for name, p in PARSERS.items():
                print(f"  {name}")
            print("\nTry specifying a parser with --parser or create a new parser")
            return 1
    
    print(f"Using parser: {parser_name}")
    
    # Parse all results
    try:
        if hasattr(selected_parser, 'parse_all_events'):
            all_results = selected_parser.parse_all_events(content)
        else:
            # Fall back to parsing with empty config
            all_results = selected_parser.parse(str(input_path), {})
    except Exception as e:
        print(f"Error parsing file: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print(f"Parsed {len(all_results)} total results from file")
    
    # Filter to Fort Collins athletes
    event_matcher = get_event_matcher()
    fc_results = extract_fc_results(all_results, event_matcher)
    
    if not fc_results:
        print("Error: No Fort Collins athletes found in results!")
        print("Check that the school name matching is correct")
        return 1
    
    # Add meet info to results
    year = args.year or int(args.date[:4])
    for result in fc_results:
        result['meet'] = args.meet
        result['date'] = args.date
        result['year'] = year
        result['level'] = args.level
    
    # Print summary
    print_summary(fc_results, parser_name)
    
    # Validate results
    is_valid, issues = validate_results(fc_results)
    
    if issues:
        print(f"\n{'!'*60}")
        print("VALIDATION ISSUES:")
        for issue in issues:
            print(f"  ⚠ {issue}")
        print(f"{'!'*60}")
    
    if not is_valid and not args.force:
        print("\nUse --force to save anyway")
        return 1
    
    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_dir = Path(__file__).parent.parent / 'data' / 'generated' / 'parsed' / 'meets' / str(year)
        output_dir.mkdir(parents=True, exist_ok=True)
        slug = slugify(args.meet)
        output_path = output_dir / f"{slug}.json"
    
    # Create meet data structure
    meet_data = {
        "meet_name": args.meet,
        "date": args.date,
        "year": year,
        "level": args.level,
        "source": str(input_path.name),
        "parser": parser_name,
        "results": fc_results
    }
    
    # Save to file
    with open(output_path, 'w') as f:
        json.dump(meet_data, f, indent=2)
    
    print(f"\n✓ Saved {len(fc_results)} results to {output_path}")
    
    # Remind to update meets config if needed
    print(f"\nNext steps:")
    print(f"1. Review the output file: {output_path}")
    print(f"2. Ensure meet is in config/meets_2025.json with correct date/level")
    print(f"3. Run: python scripts/import_from_parsed_meets.py --no-clear")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
