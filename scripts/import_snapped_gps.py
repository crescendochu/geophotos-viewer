#!/usr/bin/env python3
"""
Import snapped GPS coordinates from QGIS and update photos.

This script reads a GeoJSON file exported from QGIS (after snapping to OSM)
and updates the photo EXIF data and index.json with the snapped coordinates.

Usage:
    # Import snapped coordinates
    python scripts/import_snapped_gps.py snapped_photos.geojson
    
    # Preview changes without applying
    python scripts/import_snapped_gps.py snapped_photos.geojson --dry-run
    
    # Only update EXIF, don't update index.json
    python scripts/import_snapped_gps.py snapped_photos.geojson --no-index
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple


TIMEZONE_OFFSET = 9  # Match geotag_photos.py


def load_geojson(geojson_path: Path) -> Dict:
    """Load the snapped GeoJSON file."""
    if not geojson_path.exists():
        print(f"Error: {geojson_path} not found")
        sys.exit(1)
    
    with open(geojson_path, 'r') as f:
        return json.load(f)


def load_index(index_path: Path) -> Dict:
    """Load the index.json file."""
    if not index_path.exists():
        print(f"Error: {index_path} not found")
        sys.exit(1)
    
    with open(index_path, 'r') as f:
        return json.load(f)


def write_exif(
    photo_path: Path,
    lat: float,
    lon: float,
    ele: Optional[float],
    timestamp: Optional[str],
    tz_offset: int = TIMEZONE_OFFSET
) -> Tuple[bool, str]:
    """Write GPS coordinates to photo EXIF."""
    from datetime import datetime, timezone, timedelta
    
    lat_ref = 'N' if lat >= 0 else 'S'
    lon_ref = 'E' if lon >= 0 else 'W'
    
    cmd = [
        'exiftool',
        '-overwrite_original',
        f'-GPSLatitude={abs(lat)}',
        f'-GPSLatitudeRef={lat_ref}',
        f'-GPSLongitude={abs(lon)}',
        f'-GPSLongitudeRef={lon_ref}',
    ]
    
    if ele is not None:
        ele_ref = 0 if ele >= 0 else 1
        cmd.extend([
            f'-GPSAltitude={abs(ele)}',
            f'-GPSAltitudeRef={ele_ref}',
        ])
    
    if timestamp:
        # Parse ISO timestamp
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            local_tz = timezone(timedelta(hours=tz_offset))
            local_dt = dt.astimezone(local_tz)
            exif_date = local_dt.strftime("%Y:%m:%d %H:%M:%S")
            tz_str = f"{tz_offset:+03d}:00"
            
            cmd.extend([
                f'-DateTimeOriginal={exif_date}',
                f'-CreateDate={exif_date}',
                f'-ModifyDate={exif_date}',
                f'-OffsetTimeOriginal={tz_str}',
                f'-OffsetTime={tz_str}',
            ])
        except Exception as e:
            print(f"  Warning: Could not parse timestamp {timestamp}: {e}")
    
    cmd.append(str(photo_path))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stderr


def process_snapped_coordinates(
    geojson_path: Path,
    index_path: Path,
    photos_output: Path,
    dry_run: bool = False,
    update_index: bool = True
):
    """Process snapped coordinates and update photos."""
    print("="*60)
    print("Import Snapped GPS Coordinates")
    print("="*60)
    print(f"GeoJSON file:  {geojson_path.absolute()}")
    print(f"Index file:    {index_path.absolute()}")
    print(f"Photos output: {photos_output.absolute()}")
    print(f"Mode:          {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"Update index:  {update_index}")
    print("="*60 + "\n")
    
    # Check exiftool
    result = subprocess.run(['which', 'exiftool'], capture_output=True, text=True)
    if result.returncode != 0:
        print("Error: exiftool not found! Install with: brew install exiftool")
        sys.exit(1)
    
    # Load GeoJSON
    print("Loading snapped GeoJSON...")
    geojson = load_geojson(geojson_path)
    features = geojson.get('features', [])
    print(f"  Found {len(features)} features")
    
    # Load index
    print("\nLoading index...")
    index = load_index(index_path)
    
    # Create lookup map: photo_id -> photo data
    photo_map = {}
    for photo in index.get('photos', []):
        photo_id = f"{photo.get('date')}/{photo.get('folder')}/{photo.get('filename')}"
        photo_map[photo_id] = photo
    
    print(f"  Found {len(photo_map)} photos in index")
    
    # Process each feature
    print("\nProcessing snapped coordinates...")
    updated_count = 0
    not_found_count = 0
    skipped_count = 0
    
    for feature in features:
        props = feature.get('properties', {})
        photo_id = props.get('photo_id')
        
        if not photo_id:
            print(f"  Warning: Feature missing 'photo_id', skipping")
            skipped_count += 1
            continue
        
        # Get coordinates from geometry
        geometry = feature.get('geometry', {})
        if geometry.get('type') != 'Point':
            print(f"  Warning: Feature {photo_id} is not a Point, skipping")
            skipped_count += 1
            continue
        
        coordinates = geometry.get('coordinates', [])
        if len(coordinates) < 2:
            print(f"  Warning: Feature {photo_id} has invalid coordinates, skipping")
            skipped_count += 1
            continue
        
        lon, lat = coordinates[0], coordinates[1]
        
        # Check if coordinates changed
        original_lat = props.get('original_lat')
        original_lon = props.get('original_lon')
        
        if original_lat is not None and original_lon is not None:
            if abs(lat - original_lat) < 1e-9 and abs(lon - original_lon) < 1e-9:
                # Coordinates didn't change, skip
                continue
        
        # Find photo in index
        if photo_id not in photo_map:
            print(f"  Warning: Photo {photo_id} not found in index")
            not_found_count += 1
            continue
        
        photo_data = photo_map[photo_id]
        
        # Find photo file
        photo_path = photos_output / photo_data.get('path')
        
        if not photo_path.exists():
            print(f"  Warning: Photo file not found: {photo_path}")
            not_found_count += 1
            continue
        
        # Update EXIF
        print(f"  Updating {photo_data.get('filename')}...")
        print(f"    Old: ({photo_data.get('lat')}, {photo_data.get('lon')})")
        print(f"    New: ({lat}, {lon})")
        
        if not dry_run:
            ele = props.get('ele') or photo_data.get('ele')
            timestamp = props.get('timestamp') or photo_data.get('timestamp')
            
            success, err = write_exif(
                photo_path,
                lat,
                lon,
                ele,
                timestamp,
                TIMEZONE_OFFSET
            )
            
            if not success:
                print(f"    Error: Failed to update EXIF: {err}")
                continue
            
            # Update index
            if update_index:
                photo_data['lat'] = lat
                photo_data['lon'] = lon
                if ele is not None:
                    photo_data['ele'] = ele
        
        updated_count += 1
    
    print(f"\n" + "="*60)
    print("Summary")
    print("="*60)
    print(f"Updated:     {updated_count}")
    print(f"Not found:   {not_found_count}")
    print(f"Skipped:     {skipped_count}")
    print("="*60)
    
    # Save updated index
    if not dry_run and update_index:
        index['generated'] = datetime.now().isoformat()
        
        with open(index_path, 'w') as f:
            json.dump(index, f, indent=2)
        
        print(f"\n✓ Updated {index_path}")
    
    print("\n✓ Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Import snapped GPS coordinates from QGIS GeoJSON"
    )
    parser.add_argument(
        'geojson',
        type=str,
        help='Path to snapped GeoJSON file from QGIS'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without applying them'
    )
    parser.add_argument(
        '--no-index',
        action='store_true',
        help='Only update EXIF, do not update index.json'
    )
    parser.add_argument(
        '--index',
        type=str,
        default=None,
        help='Path to index.json (default: data/index.json)'
    )
    
    args = parser.parse_args()
    
    # Determine paths
    repo_root = Path(__file__).parent.parent
    geojson_path = Path(args.geojson)
    if not geojson_path.is_absolute():
        geojson_path = repo_root / geojson_path
    
    if args.index:
        index_path = Path(args.index)
    else:
        index_path = repo_root / "data" / "index.json"
    
    photos_output = repo_root / "photos" / "output"
    
    process_snapped_coordinates(
        geojson_path,
        index_path,
        photos_output,
        dry_run=args.dry_run,
        update_index=not args.no_index
    )


if __name__ == "__main__":
    main()


