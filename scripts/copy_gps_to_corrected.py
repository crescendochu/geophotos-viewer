#!/usr/bin/env python3
"""
Copy GPS EXIF data from a source photo to a corrected photo, then replace the source.

Usage:
    python scripts/copy_gps_to_corrected.py \
        --corrected photos/corrected/IMG_20251209_125610_00_316.jpg \
        --source photos/output/2025-12-09/IMG_20251209_125542_314_343_INTERVAL/IMG_20251209_125610_00_316.jpg
"""

import sys
import subprocess
import argparse
from pathlib import Path
import shutil


def read_exif_gps(photo_path: Path) -> dict:
    """Read GPS coordinates from photo EXIF using exiftool."""
    cmd = [
        'exiftool',
        '-GPSLatitude',
        '-GPSLatitudeRef',
        '-GPSLongitude',
        '-GPSLongitudeRef',
        '-GPSAltitude',
        '-GPSAltitudeRef',
        '-j',  # JSON output
        str(photo_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error reading EXIF from {photo_path}: {result.stderr}")
        return None
    
    try:
        import json
        data = json.loads(result.stdout)
        if data and len(data) > 0:
            return data[0]
        return None
    except json.JSONDecodeError:
        print(f"Error parsing exiftool output: {result.stdout}")
        return None


def write_exif_gps(photo_path: Path, gps_data: dict) -> bool:
    """Write GPS coordinates to photo EXIF using exiftool."""
    if not gps_data:
        print("No GPS data to write")
        return False
    
    cmd = [
        'exiftool',
        '-overwrite_original',
    ]
    
    # Add GPS fields if they exist
    if 'GPSLatitude' in gps_data and gps_data['GPSLatitude']:
        cmd.append(f"-GPSLatitude={gps_data['GPSLatitude']}")
    if 'GPSLatitudeRef' in gps_data and gps_data['GPSLatitudeRef']:
        cmd.append(f"-GPSLatitudeRef={gps_data['GPSLatitudeRef']}")
    if 'GPSLongitude' in gps_data and gps_data['GPSLongitude']:
        cmd.append(f"-GPSLongitude={gps_data['GPSLongitude']}")
    if 'GPSLongitudeRef' in gps_data and gps_data['GPSLongitudeRef']:
        cmd.append(f"-GPSLongitudeRef={gps_data['GPSLongitudeRef']}")
    if 'GPSAltitude' in gps_data and gps_data['GPSAltitude']:
        cmd.append(f"-GPSAltitude={gps_data['GPSAltitude']}")
    if 'GPSAltitudeRef' in gps_data and gps_data['GPSAltitudeRef'] is not None:
        cmd.append(f"-GPSAltitudeRef={gps_data['GPSAltitudeRef']}")
    
    cmd.append(str(photo_path))
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error writing EXIF to {photo_path}: {result.stderr}")
        return False
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Copy GPS EXIF data from source photo to corrected photo, then replace source"
    )
    parser.add_argument(
        '--corrected',
        type=str,
        required=True,
        help='Path to corrected photo (without GPS)'
    )
    parser.add_argument(
        '--source',
        type=str,
        required=True,
        help='Path to source photo (with GPS) that will be replaced'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without making them'
    )
    
    args = parser.parse_args()
    
    corrected_path = Path(args.corrected)
    source_path = Path(args.source)
    
    # Check if files exist
    if not corrected_path.exists():
        print(f"Error: Corrected photo not found: {corrected_path}")
        sys.exit(1)
    
    if not source_path.exists():
        print(f"Error: Source photo not found: {source_path}")
        sys.exit(1)
    
    print("="*60)
    print("Copy GPS to Corrected Photo")
    print("="*60)
    print(f"Corrected photo: {corrected_path.absolute()}")
    print(f"Source photo:    {source_path.absolute()}")
    print(f"Mode:            {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("="*60 + "\n")
    
    # Check exiftool
    result = subprocess.run(['which', 'exiftool'], capture_output=True, text=True)
    if result.returncode != 0:
        print("✗ exiftool not found! Install with: brew install exiftool")
        sys.exit(1)
    print(f"✓ exiftool found: {result.stdout.strip()}\n")
    
    # Read GPS data from source
    print("Reading GPS data from source photo...")
    gps_data = read_exif_gps(source_path)
    
    if not gps_data:
        print("✗ No GPS data found in source photo")
        sys.exit(1)
    
    print("✓ GPS data found:")
    if 'GPSLatitude' in gps_data:
        print(f"  Latitude:  {gps_data.get('GPSLatitude')} {gps_data.get('GPSLatitudeRef', '')}")
    if 'GPSLongitude' in gps_data:
        print(f"  Longitude: {gps_data.get('GPSLongitude')} {gps_data.get('GPSLongitudeRef', '')}")
    if 'GPSAltitude' in gps_data:
        print(f"  Altitude:  {gps_data.get('GPSAltitude')} (ref: {gps_data.get('GPSAltitudeRef', '0')})")
    print()
    
    if args.dry_run:
        print("DRY RUN: Would write GPS data to corrected photo and replace source")
        return
    
    # Write GPS data to corrected photo
    print("Writing GPS data to corrected photo...")
    success = write_exif_gps(corrected_path, gps_data)
    
    if not success:
        print("✗ Failed to write GPS data")
        sys.exit(1)
    
    print("✓ GPS data written to corrected photo\n")
    
    # Replace source with corrected
    print(f"Replacing source photo with corrected photo...")
    try:
        # Create backup of original
        backup_path = source_path.with_suffix(source_path.suffix + '.backup')
        shutil.copy2(source_path, backup_path)
        print(f"  Created backup: {backup_path}")
        
        # Replace source with corrected
        shutil.copy2(corrected_path, source_path)
        print(f"✓ Source photo replaced with corrected photo")
        
        # Optionally remove backup (uncomment if desired)
        # backup_path.unlink()
        # print(f"  Removed backup")
        
    except Exception as e:
        print(f"✗ Error replacing file: {e}")
        sys.exit(1)
    
    print("\n✓ Done!")


if __name__ == "__main__":
    main()

