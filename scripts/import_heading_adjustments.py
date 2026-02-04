#!/usr/bin/env python3
"""
Import heading adjustments from exported browser JSON into index.json.

Usage:
    python scripts/import_heading_adjustments.py heading-adjustments-2026-02-03.json
    
    # Preview without making changes
    python scripts/import_heading_adjustments.py heading-adjustments.json --dry-run
    
    # Clear all heading adjustments from index.json
    python scripts/import_heading_adjustments.py --clear
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "data" / "index.json"


def load_index() -> dict:
    """Load the index.json file."""
    with open(INDEX_PATH, 'r') as f:
        return json.load(f)


def save_index(data: dict) -> None:
    """Save the index.json file."""
    with open(INDEX_PATH, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"✓ Saved {INDEX_PATH}")


def load_adjustments(adjustments_path: Path) -> dict:
    """Load the exported heading adjustments JSON."""
    with open(adjustments_path, 'r') as f:
        data = json.load(f)
    
    # Handle both formats: direct dict or wrapped in "adjustments" key
    if 'adjustments' in data:
        return data['adjustments']
    return data


def import_adjustments(adjustments_path: Path, dry_run: bool = False) -> None:
    """Import heading adjustments into index.json."""
    print("=" * 60)
    print("Import Heading Adjustments")
    print("=" * 60)
    
    # Load data
    index_data = load_index()
    adjustments = load_adjustments(adjustments_path)
    
    print(f"Adjustments file: {adjustments_path}")
    print(f"Photos in index: {len(index_data.get('photos', []))}")
    print(f"Adjustments to import: {len(adjustments)}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("=" * 60 + "\n")
    
    if not adjustments:
        print("No adjustments to import.")
        return
    
    # Build path -> photo index mapping
    photos = index_data.get('photos', [])
    path_to_idx = {p['path']: i for i, p in enumerate(photos)}
    
    # Import adjustments
    updated = 0
    not_found = 0
    
    for path, adj in adjustments.items():
        if path in path_to_idx:
            idx = path_to_idx[path]
            yaw = adj.get('yaw', 0)
            pitch = adj.get('pitch', 0)
            
            if not dry_run:
                photos[idx]['yaw'] = round(yaw, 2)
                photos[idx]['pitch'] = round(pitch, 2)
            
            print(f"  ✓ {path}")
            print(f"    yaw: {yaw:.1f}°, pitch: {pitch:.1f}°")
            updated += 1
        else:
            print(f"  ✗ Not found: {path}")
            not_found += 1
    
    print()
    print(f"Updated: {updated} photos")
    if not_found > 0:
        print(f"Not found: {not_found} photos")
    
    # Save
    if not dry_run and updated > 0:
        index_data['generated'] = datetime.now().isoformat()
        save_index(index_data)
        print("\n✓ Done!")
    elif dry_run:
        print("\n(Dry run - no changes made)")


def clear_adjustments(dry_run: bool = False) -> None:
    """Remove all heading adjustments from index.json."""
    print("=" * 60)
    print("Clear Heading Adjustments")
    print("=" * 60)
    
    index_data = load_index()
    photos = index_data.get('photos', [])
    
    print(f"Photos in index: {len(photos)}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("=" * 60 + "\n")
    
    cleared = 0
    for photo in photos:
        if 'yaw' in photo or 'pitch' in photo:
            if not dry_run:
                photo.pop('yaw', None)
                photo.pop('pitch', None)
            cleared += 1
    
    print(f"Cleared adjustments from: {cleared} photos")
    
    if not dry_run and cleared > 0:
        index_data['generated'] = datetime.now().isoformat()
        save_index(index_data)
        print("\n✓ Done!")
    elif dry_run:
        print("\n(Dry run - no changes made)")


def main():
    parser = argparse.ArgumentParser(
        description="Import heading adjustments from exported browser JSON into index.json"
    )
    parser.add_argument(
        "adjustments_file",
        nargs="?",
        help="Path to the exported heading adjustments JSON file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without making them"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear all heading adjustments from index.json"
    )
    
    args = parser.parse_args()
    
    if args.clear:
        clear_adjustments(args.dry_run)
    elif args.adjustments_file:
        adjustments_path = Path(args.adjustments_file)
        if not adjustments_path.is_absolute():
            adjustments_path = REPO_ROOT / adjustments_path
        
        if not adjustments_path.exists():
            print(f"Error: File not found: {adjustments_path}")
            sys.exit(1)
        
        import_adjustments(adjustments_path, args.dry_run)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
