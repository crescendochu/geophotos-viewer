#!/usr/bin/env python3
"""
Delete individual photos and optionally re-match GPX for remaining photos.

Usage:
    python scripts/delete_individual_photos.py <photo_filename1> [photo_filename2] ...
    python scripts/delete_individual_photos.py --no-reassign <photo_filename1> [photo_filename2] ...
    
Example:
    python scripts/delete_individual_photos.py IMG_20251209_144524_00_554.jpg IMG_20251209_144525_00_555.jpg
    python scripts/delete_individual_photos.py --no-reassign IMG_20251209_144524_00_554.jpg
"""

import sys
import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from bisect import bisect_left
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

try:
    import gpxpy
except ImportError:
    print("Error: gpxpy module not found. Install it with: pip install gpxpy")
    sys.exit(1)

# Import configuration from geotag_photos.py
TIMEZONE_OFFSET = 9
TIME_TOLERANCE_SECONDS = 120
STRICT_MATCHING = True

# Paths
GPS_BASE = Path("gps")
PHOTOS_INPUT = Path("photos/input")
PHOTOS_OUTPUT = Path("photos/output")

# Data Classes
@dataclass
class GPXTrack:
    """Represents a parsed GPX track."""
    path: Path
    points: List[Tuple[datetime, float, float, float]]  # (time, lat, lon, ele)
    start_time: datetime
    end_time: datetime


@dataclass
class PhotoMatch:
    """Result of matching a photo to GPS coordinates."""
    filename: str
    timestamp: Optional[datetime]
    lat: Optional[float]
    lon: Optional[float]
    ele: Optional[float]
    matched: bool
    gpx_file: Optional[str] = None


@dataclass 
class FolderResult:
    """Result of processing a photo folder."""
    folder_name: str
    folder_path: str
    date: str
    gpx_file: Optional[str]
    total_photos: int
    matched_photos: int
    unmatched_photos: int
    photos: List[PhotoMatch] = field(default_factory=list)


# Functions (reused from geotag_photos.py)
def parse_gpx(gpx_path: Path) -> Optional[GPXTrack]:
    """Parse a GPX file and return a GPXTrack object."""
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
        
        return GPXTrack(
            path=gpx_path,
            points=points,
            start_time=points[0][0],
            end_time=points[-1][0]
        )
    except Exception as e:
        print(f"  Warning: Could not parse {gpx_path.name}: {e}")
        return None


def load_gpx_files_for_date(gps_base: Path, date_str: str) -> List[GPXTrack]:
    """Load all GPX files for a given date."""
    date_folder = gps_base / date_str
    
    if not date_folder.exists():
        return []
    
    tracks = []
    for gpx_file in date_folder.glob("*.gpx"):
        track = parse_gpx(gpx_file)
        if track:
            tracks.append(track)
    
    # Sort by start time
    tracks.sort(key=lambda t: t.start_time)
    return tracks


def extract_timestamp_from_filename(filename: str, tz_offset: int = TIMEZONE_OFFSET) -> Optional[datetime]:
    """Extract timestamp from Insta360 filename."""
    import re
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


def interpolate_position(
    points: List[Tuple[datetime, float, float, float]], 
    target_time: datetime,
    tolerance_seconds: int = TIME_TOLERANCE_SECONDS
) -> Optional[Tuple[float, float, float]]:
    """Find GPS position for a given time by interpolating between track points."""
    if not points:
        return None
    
    times = [p[0] for p in points]
    tolerance = timedelta(seconds=tolerance_seconds)
    
    if target_time < times[0] - tolerance or target_time > times[-1] + tolerance:
        return None
    
    idx = bisect_left(times, target_time)
    
    # Handle case where target_time is before the first point
    if idx == 0:
        if len(points) < 2:
            return (points[0][1], points[0][2], points[0][3])
        p1 = points[0]
        p2 = points[1]
        t1, t2 = p1[0], p2[0]
        total_seconds = (t2 - t1).total_seconds()
        if total_seconds == 0:
            return (p1[1], p1[2], p1[3])
        fraction = (target_time - t1).total_seconds() / total_seconds
        lat = p1[1] + fraction * (p2[1] - p1[1])
        lon = p1[2] + fraction * (p2[2] - p1[2])
        ele = p1[3] + fraction * (p2[3] - p1[3]) if p1[3] and p2[3] else p1[3]
        return (lat, lon, ele)
    
    # Handle case where target_time is after the last point
    if idx >= len(points):
        if len(points) < 2:
            return (points[-1][1], points[-1][2], points[-1][3])
        p1 = points[-2]
        p2 = points[-1]
        t1, t2 = p1[0], p2[0]
        total_seconds = (t2 - t1).total_seconds()
        if total_seconds == 0:
            return (p2[1], p2[2], p2[3])
        fraction = (target_time - t1).total_seconds() / total_seconds
        lat = p1[1] + fraction * (p2[1] - p1[1])
        lon = p1[2] + fraction * (p2[2] - p1[2])
        ele = p1[3] + fraction * (p2[3] - p1[3]) if p1[3] and p2[3] else p1[3]
        return (lat, lon, ele)
    
    # Normal interpolation case
    p1 = points[idx - 1]
    p2 = points[idx]
    
    t1, t2 = p1[0], p2[0]
    total_seconds = (t2 - t1).total_seconds()
    
    if total_seconds == 0:
        return (p1[1], p1[2], p1[3])
    
    fraction = (target_time - t1).total_seconds() / total_seconds
    
    lat = p1[1] + fraction * (p2[1] - p1[1])
    lon = p1[2] + fraction * (p2[2] - p1[2])
    ele = p1[3] + fraction * (p2[3] - p1[3]) if p1[3] and p2[3] else p1[3]
    
    return (lat, lon, ele)


def write_exif(
    photo_path: Path, 
    lat: float, 
    lon: float, 
    ele: Optional[float],
    timestamp: Optional[datetime],
    tz_offset: int = TIMEZONE_OFFSET
) -> Tuple[bool, str]:
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


def find_best_gpx_for_folder(
    folder_path: Path,
    gpx_tracks: List[GPXTrack],
    tz_offset: int = TIMEZONE_OFFSET
) -> Optional[GPXTrack]:
    """Find the single best GPX track for an entire folder."""
    import re
    match = re.search(r'IMG_(\d{8})_(\d{6})', folder_path.name)
    if not match:
        return None
    
    date_str = match.group(1)
    time_str = match.group(2)
    
    local_dt = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
    local_tz = timezone(timedelta(hours=tz_offset))
    local_dt = local_dt.replace(tzinfo=local_tz)
    folder_start_time = local_dt.astimezone(timezone.utc)
    
    best_track = None
    best_score = None
    
    for track in gpx_tracks:
        if track.start_time <= folder_start_time <= track.end_time:
            if STRICT_MATCHING:
                time_from_start = (folder_start_time - track.start_time).total_seconds()
                if time_from_start <= TIME_TOLERANCE_SECONDS:
                    score = (track.end_time - folder_start_time).total_seconds()
                    if best_score is None or score > best_score:
                        best_score = score
                        best_track = track
            else:
                score = (track.end_time - folder_start_time).total_seconds()
                if best_score is None or score > best_score:
                    best_score = score
                    best_track = track
        
        elif track.end_time < folder_start_time:
            gap = (folder_start_time - track.end_time).total_seconds()
            if gap <= TIME_TOLERANCE_SECONDS:
                score = -gap
                if best_score is None or score > best_score:
                    best_score = score
                    best_track = track
        
        elif track.start_time > folder_start_time:
            gap = (track.start_time - folder_start_time).total_seconds()
            if gap <= TIME_TOLERANCE_SECONDS:
                score = -gap
                if best_score is None or score > best_score:
                    best_score = score
                    best_track = track
    
    return best_track if best_score is not None else None


def reprocess_folder(
    folder_name: str,
    date_str: str,
    repo_root: Path
) -> FolderResult:
    """Re-process a folder: re-match remaining photos with GPX."""
    
    # Find photos in input and output folders
    input_folder = repo_root / PHOTOS_INPUT / date_str / folder_name
    output_folder = repo_root / PHOTOS_OUTPUT / date_str / folder_name
    
    # Use output folder if it exists and has photos (current state after deletions)
    # Otherwise use input folder (photos haven't been processed yet)
    if output_folder.exists():
        photos_in_output = list(output_folder.glob("*.jpg")) + list(output_folder.glob("*.JPG"))
        if photos_in_output:
            source_folder = output_folder
            use_input_as_source = False
        elif input_folder.exists():
            source_folder = input_folder
            use_input_as_source = True
        else:
            print(f"  Warning: Folder {folder_name} has no photos in output or input")
            return FolderResult(
                folder_name=folder_name,
                folder_path="",
                date=date_str,
                gpx_file=None,
                total_photos=0,
                matched_photos=0,
                unmatched_photos=0
            )
    elif input_folder.exists():
        source_folder = input_folder
        use_input_as_source = True
    else:
        print(f"  Warning: Folder {folder_name} not found in input or output")
        return FolderResult(
            folder_name=folder_name,
            folder_path="",
            date=date_str,
            gpx_file=None,
            total_photos=0,
            matched_photos=0,
            unmatched_photos=0
        )
    
    photos = sorted(list(source_folder.glob("*.jpg")) + list(source_folder.glob("*.JPG")))
    
    result = FolderResult(
        folder_name=folder_name,
        folder_path=str(source_folder),
        date=date_str,
        gpx_file=None,
        total_photos=len(photos),
        matched_photos=0,
        unmatched_photos=0
    )
    
    if not photos:
        return result
    
    # Load GPX files for this date
    gpx_tracks = load_gpx_files_for_date(repo_root / GPS_BASE, date_str)
    
    if not gpx_tracks:
        print(f"  Warning: No GPX files found for {date_str}")
        return result
    
    # Find the best GPX track for this folder
    gpx_track = find_best_gpx_for_folder(source_folder, gpx_tracks, TIMEZONE_OFFSET)
    
    if gpx_track:
        result.gpx_file = gpx_track.path.name
    else:
        print(f"  Warning: No matching GPX track found for {folder_name}")
        return result
    
    # Ensure output folder exists
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # Process each photo
    for photo in photos:
        timestamp = extract_timestamp_from_filename(photo.name, TIMEZONE_OFFSET)
        
        match = PhotoMatch(
            filename=photo.name,
            timestamp=timestamp,
            lat=None,
            lon=None,
            ele=None,
            matched=False
        )
        
        if timestamp and gpx_track:
            position = interpolate_position(gpx_track.points, timestamp)
            
            if position:
                match.lat, match.lon, match.ele = position
                match.matched = True
                match.gpx_file = gpx_track.path.name
                result.matched_photos += 1
                
                # Copy to output and geotag
                dest = output_folder / photo.name
                if not use_input_as_source:
                    # Already in output, just update EXIF
                    success, err = write_exif(
                        dest, match.lat, match.lon, match.ele,
                        timestamp, TIMEZONE_OFFSET
                    )
                else:
                    # Copy from input to output
                    shutil.copy2(photo, dest)
                    success, err = write_exif(
                        dest, match.lat, match.lon, match.ele,
                        timestamp, TIMEZONE_OFFSET
                    )
                
                if not success:
                    print(f"    Warning: EXIF write failed for {photo.name}: {err}")
            else:
                result.unmatched_photos += 1
        else:
            result.unmatched_photos += 1
        
        result.photos.append(match)
    
    return result


def update_folder_counts(index: dict, folders_to_update: set):
    """Update folder totals/matched and drop empty folders."""
    remaining_by_folder = {}
    for photo in index.get('photos', []):
        folder_name = photo.get('folder')
        if not folder_name:
            continue
        if folder_name not in remaining_by_folder:
            remaining_by_folder[folder_name] = {'total': 0, 'matched': 0}
        remaining_by_folder[folder_name]['total'] += 1
        if photo.get('lat') and photo.get('lon'):
            remaining_by_folder[folder_name]['matched'] += 1

    updated_folders = []
    for folder in index.get('folders', []):
        folder_name = folder.get('name')
        if folder_name in folders_to_update:
            counts = remaining_by_folder.get(folder_name)
            if counts:
                folder['total'] = counts['total']
                folder['matched'] = counts['matched']
                updated_folders.append(folder)
            # Drop empty folders
        else:
            updated_folders.append(folder)

    index['folders'] = updated_folders


def delete_individual_photos(photo_filenames: List[str], repo_root: Path, reassign_gpx: bool = True):
    """Delete individual photos and optionally re-process their folders."""
    
    index_file = repo_root / "data" / "index.json"
    output_dir = repo_root / PHOTOS_OUTPUT
    
    # Load index
    if not index_file.exists():
        print(f"Error: {index_file} not found")
        sys.exit(1)
    
    with open(index_file, 'r') as f:
        index = json.load(f)
    
    # Find photos to delete and group by folder
    photos_to_delete = {}
    folders_to_reprocess = set()
    
    for photo_filename in photo_filenames:
        # Find photo in index
        found = False
        for photo in index['photos']:
            if photo.get('filename') == photo_filename:
                folder_name = photo.get('folder')
                date_str = photo.get('date')
                
                if folder_name and date_str:
                    if folder_name not in photos_to_delete:
                        photos_to_delete[folder_name] = {
                            'date': date_str,
                            'photos': []
                        }
                    photos_to_delete[folder_name]['photos'].append(photo_filename)
                    folders_to_reprocess.add((folder_name, date_str))
                    found = True
                    break
        
        if not found:
            print(f"  Warning: Photo {photo_filename} not found in index")
    
    if not photos_to_delete:
        print("No photos found to delete")
        return
    
    # Delete photos from disk and index
    deleted_count = 0
    for folder_name, folder_data in photos_to_delete.items():
        date_str = folder_data['date']
        photo_filenames_in_folder = folder_data['photos']
        
        print(f"\nDeleting {len(photo_filenames_in_folder)} photo(s) from folder {folder_name}:")
        
        for photo_filename in photo_filenames_in_folder:
            # Delete from index
            index['photos'] = [
                p for p in index['photos']
                if not (p.get('filename') == photo_filename and p.get('folder') == folder_name)
            ]
            
            # Delete from disk
            photo_path = output_dir / date_str / folder_name / photo_filename
            if photo_path.exists():
                photo_path.unlink()
                print(f"  ✓ Deleted: {photo_filename}")
                deleted_count += 1
            else:
                print(f"  ⚠ File not found: {photo_path}")
    
    print(f"\n✓ Deleted {deleted_count} photo(s) from disk")
    print(f"✓ Removed {deleted_count} photo entry/entries from index")
    
    if reassign_gpx:
        # Re-process folders
        print(f"\nRe-processing {len(folders_to_reprocess)} folder(s)...")
        
        for folder_name, date_str in folders_to_reprocess:
            print(f"\n  Re-processing folder: {folder_name}")
            result = reprocess_folder(folder_name, date_str, repo_root)
            
            # Update folder entry in index
            folder_entry = None
            for folder in index['folders']:
                if folder.get('name') == folder_name:
                    folder_entry = folder
                    break
            
            if folder_entry:
                folder_entry['total'] = result.total_photos
                folder_entry['matched'] = result.matched_photos
                folder_entry['gpx_file'] = result.gpx_file
            else:
                # Add new folder entry
                index['folders'].append({
                    "name": folder_name,
                    "date": date_str,
                    "total": result.total_photos,
                    "matched": result.matched_photos,
                    "gpx_file": result.gpx_file
                })
            
            # Remove old photo entries for this folder
            index['photos'] = [
                p for p in index['photos']
                if p.get('folder') != folder_name
            ]
            
            # Add new photo entries
            for photo_match in result.photos:
                if photo_match.matched:
                    index['photos'].append({
                        "filename": photo_match.filename,
                        "folder": folder_name,
                        "date": date_str,
                        "lat": photo_match.lat,
                        "lon": photo_match.lon,
                        "ele": photo_match.ele,
                        "timestamp": photo_match.timestamp.isoformat() if photo_match.timestamp else None,
                        "path": f"{date_str}/{folder_name}/{photo_match.filename}"
                    })
            
            print(f"    ✓ Re-matched {result.matched_photos}/{result.total_photos} photos")
    else:
        update_folder_counts(index, {name for name, _ in folders_to_reprocess})
    
    # Update totals
    index['total_photos'] = len(index['photos'])
    index['total_matched'] = len([p for p in index['photos'] if p.get('lat') and p.get('lon')])
    index['generated'] = datetime.now().isoformat()
    
    # Save index
    with open(index_file, 'w') as f:
        json.dump(index, f, indent=2)
    
    print(f"\n✓ Updated {index_file}")


def main():
    args = sys.argv[1:]
    reassign_gpx = True
    if '--no-reassign' in args:
        reassign_gpx = False
        args = [a for a in args if a != '--no-reassign']

    if len(args) < 1:
        print("Usage: python scripts/delete_individual_photos.py [--no-reassign] <photo_filename1> [photo_filename2] ...")
        print("\nExamples:")
        print("  python scripts/delete_individual_photos.py IMG_20251209_144524_00_554.jpg IMG_20251209_144525_00_555.jpg")
        print("  python scripts/delete_individual_photos.py --no-reassign IMG_20251209_144524_00_554.jpg")
        sys.exit(1)
    
    if reassign_gpx:
        # Check exiftool
        result = subprocess.run(['which', 'exiftool'], capture_output=True, text=True)
        if result.returncode != 0:
            print("Error: exiftool not found! Install with: brew install exiftool")
            sys.exit(1)
    
    photo_filenames = args
    repo_root = Path(__file__).parent.parent
    
    print("="*60)
    print("Delete Individual Photos")
    print("="*60)
    print(f"Photos to delete: {len(photo_filenames)}")
    if not reassign_gpx:
        print("Reassign GPX: no")
    print("="*60 + "\n")
    
    delete_individual_photos(photo_filenames, repo_root, reassign_gpx=reassign_gpx)
    
    print("\n✓ Done!")


if __name__ == "__main__":
    main()

