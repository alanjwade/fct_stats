#!/usr/bin/env python3
"""
Consolidate existing parsed data into the central parsed_meets directory.

This is a one-time migration script that takes the existing parsed JSON files
and converts them into individual meet JSON files in data/parsed_meets/.

Structure:
  data/parsed_meets/
    historical_records.json     (all historical records, kept separate)
    2025/
      runners_roost_2025.json
      longmont_invite_2025.json
      ...
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def slugify(name: str) -> str:
    """Convert meet name to a safe filename slug."""
    # Remove special characters, replace spaces with underscores
    slug = re.sub(r'[^a-zA-Z0-9\s\-]', '', name)
    slug = re.sub(r'\s+', '_', slug.strip())
    slug = slug.lower()
    return slug


def consolidate_performance_list():
    """Split parsed_performance_list.json into individual meet files."""
    perf_path = Path(__file__).parent.parent / 'data' / 'snapshots' / '2025' / 'parsed_performance_list.json'
    output_dir = Path(__file__).parent.parent / 'data' / 'snapshots' / '2025' / 'meets'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not perf_path.exists():
        print(f"Performance list not found: {perf_path}")
        return
    
    print(f"Loading performance list from {perf_path}...")
    with open(perf_path, 'r') as f:
        all_results = json.load(f)
    
    print(f"Loaded {len(all_results)} total results")
    
    # Group results by meet
    meets = defaultdict(list)
    for result in all_results:
        meet_name = result.get('meet', 'Unknown')
        meets[meet_name].append(result)
    
    print(f"Found {len(meets)} unique meets")
    
    # Write each meet to its own file
    for meet_name, results in meets.items():
        slug = slugify(meet_name)
        if not slug:
            slug = 'unknown_meet'
        
        # Add year suffix if not present
        if '2025' not in slug:
            slug = f"{slug}_2025"
        
        output_file = output_dir / f"{slug}.json"
        
        # Create meet metadata wrapper
        meet_data = {
            "meet_name": meet_name,
            "year": 2025,
            "source": "performance_list_spreadsheet",
            "results": results
        }
        
        with open(output_file, 'w') as f:
            json.dump(meet_data, f, indent=2)
        
        print(f"  Wrote {len(results):4d} results to {output_file.name}")


def copy_historical_records():
    """Copy historical records to parsed_meets directory."""
    hist_path = Path(__file__).parent.parent / 'data' / 'snapshots' / 'historic' / 'historical_records.json'
    output_dir = Path(__file__).parent.parent / 'data' / 'snapshots'
    
    if not hist_path.exists():
        print(f"Historical records not found: {hist_path}")
        return
    
    print(f"\nCopying historical records from {hist_path}...")
    with open(hist_path, 'r') as f:
        records = json.load(f)
    
    # Wrap in metadata
    hist_data = {
        "meet_name": "Historical Records",
        "description": "All-time school records from various years",
        "source": "historical_records_markdown",
        "results": records
    }
    
    output_file = output_dir / 'historical_records.json'
    with open(output_file, 'w') as f:
        json.dump(hist_data, f, indent=2)
    
    print(f"  Wrote {len(records)} historical records to {output_file.name}")


def main():
    print("=" * 60)
    print("Consolidating parsed data to data/parsed_meets/")
    print("=" * 60)
    
    consolidate_performance_list()
    copy_historical_records()
    
    print("\n" + "=" * 60)
    print("Consolidation complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. New meets should be parsed into data/parsed_meets/YYYY/meet_name.json")
    print("2. Run scripts/import_from_parsed_meets.py to import all into database")


if __name__ == '__main__':
    main()
