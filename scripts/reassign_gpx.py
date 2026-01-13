#!/usr/bin/env python3
"""
Reassign a photo folder to a different GPX file.
Useful for spot corrections when GPX files are added later or incorrect matches.

Usage:
    python scripts/reassign_gpx.py <folder_name> <gpx_filename>
    
Example:
    python scripts/reassign_gpx.py IMG_20251211_133133_966_972_INTERVAL "2025-12-11-133133-Outdoor Walking-Chu's Apple Watch.gpx"
"""

import sys
import json
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from bisect import bisect_left
import subprocess
import shutil

try:
    import gpxpy
except ImportError:
    print("Error: gpxpy module not found. Install it with: pip install gpxpy")
    sys.exit(1)

# Import functions from geotag_photos.py
# We'll duplicate the key functions here to keep it standalone
TIMEZONE_OFFSET = 9
TIME_TOLERANCE_SECONDS = 120

def parse_gpx(gpx_path: Path):
    """Parse a GPX file and return track data."""
    try:
        with open(gpx_path, 'r') as f:
            gpx = gpxpy.parse(f)
        
        points = []
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    if point.time:
                        points.append((
                            point.time,
                            point.latitude,
                            point.longitude,
                            point.elevation
                        ))
        
        if not points:
            return None
        
        points.sort(key=lambda x: x[0])
        return {
            'points': points,
            'start_time': points[0][0],
            'end_time': points[-1][0]
        }
    except Exception as e:
        print(f"Error parsing GPX file: {e}")
        return None


def extract_timestamp_from_filename(filename: str, tz_offset: int = TIMEZONE_OFFSET):
    """Extract timestamp from Insta360 filename."""
    match = re.search(r'IMG_(\d{8})_(\d{6})', filename)
    if not match:
        return None
    
    date_str = match.group(1)
    time_str = match.group(2)
    
    local_dt = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
    local_tz = timezone(timedelta(hours=tz_offset))
    local_dt = local_dt.replace(tzinfo=local_tz)
    utc_dt = local_dt.astimezone(timezone.utc)
    
    return utc_dt


def interpolate_position(points, target_time, tolerance_seconds=TIME_TOLERANCE_SECONDS):
    """Find GPS position for a given time by interpolating between track points."""
    if not points:
        return None
    
    times = [p[0] for p in points]
    tolerance = timedelta(seconds=tolerance_seconds)
    
    if target_time < times[0] - tolerance or target_time > times[-1] + tolerance:
        return None
    
    idx = bisect_left(times, target_time)
    
    # Handle extrapolation before first point
    if idx == 0:
        if len(points) < 2:
            return (points[0][1], points[0][2], points[0][3])
        p1, p2 = points[0], points[1]
        t1, t2 = p1[0], p2[0]
        total_seconds = (t2 - t1).total_seconds()
        if total_seconds == 0:
            return (p1[1], p1[2], p1[3])
        fraction = (target_time - t1).total_seconds() / total_seconds
        lat = p1[1] + fraction * (p2[1] - p1[1])
        lon = p1[2] + fraction * (p2[2] - p1[2])
        ele = p1[3] + fraction * (p2[3] - p1[3]) if p1[3] and p2[3] else p1[3]
        return (lat, lon, ele)
    
    # Handle extrapolation after last point
    if idx >= len(points):
        if len(points) < 2:
            return (points[-1][1], points[-1][2], points[-1][3])
        p1, p2 = points[-2], points[-1]
        t1, t2 = p1[0], p2[0]
        total_seconds = (t2 - t1).total_seconds()
        if total_seconds == 0:
            return (p2[1], p2[2], p2[3])
        fraction = (target_time - t1).total_seconds() / total_seconds
        lat = p1[1] + fraction * (p2[1] - p1[1])
        lon = p1[2] + fraction * (p2[2] - p1[2])
        ele = p1[3] + fraction * (p2[3] - p1[3]) if p1[3] and p2[3] else p1[3]
        return (lat, lon, ele)
    
    # Normal interpolation
    p1, p2 = points[idx - 1], points[idx]
    t1, t2 = p1[0], p2[0]
    total_seconds = (t2 - t1).total_seconds()
    
    if total_seconds == 0:
        return (p1[1], p1[2], p1[3])
    
    fraction = (target_time - t1).total_seconds() / total_seconds
    lat = p1[1] + fraction * (p2[1] - p1[1])
    lon = p1[2] + fraction * (p2[2] - p1[2])
    ele = p1[3] + fraction * (p2[3] - p1[3]) if p1[3] and p2[3] else p1[3]
    
    return (lat, lon, ele)


def write_exif(photo_path: Path, lat: float, lon: float, ele, timestamp, tz_offset=TIMEZONE_OFFSET):
    """Write GPS coordinates and timestamp to photo EXIF."""
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
        local_tz = timezone(timedelta(hours=tz_offset))
        local_dt = timestamp.astimezone(local_tz)
        exif_date = local_dt.strftime("%Y:%m:%d %H:%M:%S")
        tz_str = f"{tz_offset:+03d}:00"
        
        cmd.extend([
            f'-DateTimeOriginal={exif_date}',
            f'-CreateDate={exif_date}',
            f'-ModifyDate={exif_date}',
            f'-OffsetTimeOriginal={tz_str}',
            f'-OffsetTime={tz_str}',
        ])
    
    cmd.append(str(photo_path))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stderr


def find_folder_in_input(folder_name: str, photos_input: Path):
    """Find the folder in photos/input by searching all date folders."""
    for date_folder in photos_input.iterdir():
        if not date_folder.is_dir():
            continue
        folder_path = date_folder / folder_name
        if folder_path.exists() and folder_path.is_dir():
            return folder_path, date_folder.name
    return None, None


def normalize_filename(filename: str) -> str:
    """Normalize filename for comparison (handles Unicode spaces, smart quotes, etc.)"""
    # 1. Handle smart quotes (replace curly with straight)
    normalized = filename.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"')
    # 2. Handle Unicode spaces
    normalized = normalized.replace('\xa0', ' ').replace('\u2009', ' ').replace('\u202f', ' ')
    # 3. Normalize multiple spaces and lowercase
    normalized = ' '.join(normalized.split())
    return normalized.lower().strip()


def find_gpx_file(gpx_input: str, gps_base: Path, date_hint: str = None):
    """Find the GPX file even if a full path is provided."""
    # Extract just the filename if a path was provided
    gpx_filename = Path(gpx_input).name
    normalized_input = normalize_filename(gpx_filename)
    
    # First, try using the date hint if provided
    if date_hint:
        date_folder = gps_base / date_hint
        if date_folder.exists():
            # Try exact match first
            gpx_path = date_folder / gpx_filename
            if gpx_path.exists():
                return gpx_path, date_hint
            # Try normalized match (handles Unicode spaces, smart quotes, case differences)
            for file in date_folder.glob("*.gpx"):
                if normalize_filename(file.name) == normalized_input:
                    return file, date_hint
    
    # Try to extract date from filename (format: YYYY-MM-DD-...)
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', gpx_filename)
    if date_match:
        date_str = date_match.group(1)
        date_folder = gps_base / date_str
        if date_folder.exists():
            # Try exact match first
            gpx_path = date_folder / gpx_filename
            if gpx_path.exists():
                return gpx_path, date_str
            # Try normalized match
            for file in date_folder.glob("*.gpx"):
                if normalize_filename(file.name) == normalized_input:
                    return file, date_str
    
    # If date extraction failed, search all date folders
    for date_folder in sorted(gps_base.iterdir()):
        if not date_folder.is_dir():
            continue
        # Try exact match
        gpx_path = date_folder / gpx_filename
        if gpx_path.exists():
            return gpx_path, date_folder.name
        # Try normalized match
        for file in date_folder.glob("*.gpx"):
            if normalize_filename(file.name) == normalized_input:
                return file, date_folder.name
    
    return None, None


def reassign_folder(folder_name: str, gpx_filename: str, dry_run: bool = False):
    """Reassign a folder to a different GPX file."""
    repo_root = Path(__file__).parent.parent
    photos_input = repo_root / "photos" / "input"
    photos_output = repo_root / "photos" / "output"
    gps_base = repo_root / "gps"
    index_file = repo_root / "data" / "index.json"
    
    # Find the folder
    folder_path, date_str = find_folder_in_input(folder_name, photos_input)
    if not folder_path:
        print(f"Error: Folder '{folder_name}' not found in photos/input/")
        return False
    
    print(f"Found folder: {folder_path}")
    print(f"Date: {date_str}")
    
    # Find the GPX file (use date from folder as hint)
    gpx_path, gpx_date = find_gpx_file(gpx_filename, gps_base, date_hint=date_str)
    if not gpx_path:
        print(f"Error: GPX file '{gpx_filename}' not found in gps/")
        print(f"  Searched in: gps/{date_str}/")
        print(f"  Also searched all date folders in gps/")
        return False
    
    print(f"Found GPX: {gpx_path}")
    
    # Parse GPX
    track_data = parse_gpx(gpx_path)
    if not track_data:
        print(f"Error: Could not parse GPX file")
        return False
    
    print(f"GPX track: {track_data['start_time']} to {track_data['end_time']}")
    print(f"Points: {len(track_data['points'])}")
    
    # Get photos
    photos = sorted(list(folder_path.glob("*.jpg")) + list(folder_path.glob("*.JPG")))
    if not photos:
        print(f"Error: No photos found in folder")
        return False
    
    print(f"Photos to process: {len(photos)}")
    
    # Process photos
    output_folder = photos_output / date_str / folder_name
    if not dry_run:
        output_folder.mkdir(parents=True, exist_ok=True)
    
    matched_count = 0
    unmatched_count = 0
    
    for photo in photos:
        timestamp = extract_timestamp_from_filename(photo.name, TIMEZONE_OFFSET)
        
        if timestamp:
            position = interpolate_position(track_data['points'], timestamp)
            if position:
                lat, lon, ele = position
                matched_count += 1
                
                if not dry_run:
                    # Copy and geotag
                    dest = output_folder / photo.name
                    shutil.copy2(photo, dest)
                    success, err = write_exif(dest, lat, lon, ele, timestamp, TIMEZONE_OFFSET)
                    if not success:
                        print(f"  Warning: EXIF write failed for {photo.name}: {err}")
            else:
                unmatched_count += 1
        else:
            unmatched_count += 1
    
    print(f"\nMatched: {matched_count}/{len(photos)}")
    if unmatched_count > 0:
        print(f"Unmatched: {unmatched_count}")
    
    # Update index.json
    if not dry_run:
        # Load index
        if not index_file.exists():
            print(f"Error: {index_file} not found")
            return False
        
        with open(index_file, 'r') as f:
            index = json.load(f)
        
        # Remove old entries for this folder
        index['photos'] = [p for p in index['photos'] if p.get('folder') != folder_name]
        index['folders'] = [f for f in index['folders'] if f.get('name') != folder_name]
        
        # Add new entries
        folder_entry = {
            "name": folder_name,
            "date": date_str,
            "total": len(photos),
            "matched": matched_count,
            "gpx_file": gpx_filename
        }
        index['folders'].append(folder_entry)
        
        # Add photo entries
        for photo in photos:
            timestamp = extract_timestamp_from_filename(photo.name, TIMEZONE_OFFSET)
            if timestamp:
                position = interpolate_position(track_data['points'], timestamp)
                if position:
                    lat, lon, ele = position
                    index['photos'].append({
                        "filename": photo.name,
                        "folder": folder_name,
                        "date": date_str,
                        "lat": lat,
                        "lon": lon,
                        "ele": ele,
                        "timestamp": timestamp.isoformat(),
                        "path": f"{date_str}/{folder_name}/{photo.name}"
                    })
        
        # Update totals
        index['total_photos'] = len(index['photos'])
        index['total_matched'] = len([p for p in index['photos'] if p.get('lat') and p.get('lon')])
        index['generated'] = datetime.now().isoformat()
        
        # Save index
        with open(index_file, 'w') as f:
            json.dump(index, f, indent=2)
        
        print(f"\n✓ Updated {index_file}")
    
    return True


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/reassign_gpx.py <folder_name> <gpx_filename> [--dry-run]")
        print("\nExample:")
        print('  python scripts/reassign_gpx.py IMG_20251211_133133_966_972_INTERVAL "2025-12-11-133133-Outdoor Walking-Chu\'s Apple Watch.gpx"')
        sys.exit(1)
    
    folder_name = sys.argv[1]
    gpx_filename = sys.argv[2]
    dry_run = '--dry-run' in sys.argv
    
    if dry_run:
        print("DRY RUN MODE - No files will be modified\n")
    
    # Check exiftool
    result = subprocess.run(['which', 'exiftool'], capture_output=True, text=True)
    if result.returncode != 0:
        print("Error: exiftool not found! Install with: brew install exiftool")
        sys.exit(1)
    
    success = reassign_folder(folder_name, gpx_filename, dry_run=dry_run)
    
    if success:
        print("\n✓ Done!")
    else:
        print("\n✗ Failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()

