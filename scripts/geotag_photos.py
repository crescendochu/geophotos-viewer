#!/usr/bin/env python
"""
Geotag photos workflow:
- Reads photos from photos/input/
- Matches with GPS data from gps/
- Tags photos with EXIF GPS coordinates
- Outputs tagged photos to photos/output/
- Generates data/index.json
"""

from pathlib import Path
import os
import re
import subprocess
import shutil
import json
import gpxpy
from datetime import datetime, timezone, timedelta
from bisect import bisect_left
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from tqdm import tqdm

# =============================================================================
# CONFIGURATION
# =============================================================================

# Base folder containing date subfolders with GPX files
GPS_BASE = Path("gps")

# Base folder containing date subfolders with photo folders
PHOTOS_INPUT = Path("photos/input")

# Output folder (will mirror input structure)
PHOTOS_OUTPUT = Path("photos/output")

# Timezone offset from UTC (9 for Tokyo, -5 for EST, etc.)
TIMEZONE_OFFSET = 9

# How far outside the GPX track time range to still accept matches (seconds)
TIME_TOLERANCE_SECONDS = 120

# If True, only match folders to GPX tracks that start close to the folder time
# (prevents matching to long tracks that happen to cover the folder time)
# If False, will match if folder time is anywhere within the track
STRICT_MATCHING = True

# Set to True to preview without making changes, False to actually update files
DRY_RUN = False

# =============================================================================

# Data Classes
@dataclass
class GPXTrack:
    """Represents a parsed GPX track."""
    path: Path
    points: List[Tuple[datetime, float, float, float]]  # (time, lat, lon, ele)
    start_time: datetime
    end_time: datetime
    
    @property
    def duration_minutes(self) -> float:
        return (self.end_time - self.start_time).total_seconds() / 60


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


# Functions
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
    """
    Extract timestamp from Insta360 filename.
    Format: IMG_YYYYMMDD_HHMMSS_XX_XXX.jpg
    Returns datetime in UTC.
    """
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
    """
    Find GPS position for a given time by interpolating between track points.
    Extrapolates from the last two points if after track end, or first two if before track start.
    Returns (lat, lon, ele) or None if time is outside track range.
    """
    if not points:
        return None
    
    times = [p[0] for p in points]
    tolerance = timedelta(seconds=tolerance_seconds)
    
    if target_time < times[0] - tolerance or target_time > times[-1] + tolerance:
        return None
    
    idx = bisect_left(times, target_time)
    
    # Handle case where target_time is before the first point (extrapolate backwards)
    if idx == 0:
        if len(points) < 2:
            return (points[0][1], points[0][2], points[0][3])
        # Extrapolate from first two points
        p1 = points[0]
        p2 = points[1]
        t1, t2 = p1[0], p2[0]
        total_seconds = (t2 - t1).total_seconds()
        if total_seconds == 0:
            return (p1[1], p1[2], p1[3])
        # Negative fraction means extrapolating backwards
        fraction = (target_time - t1).total_seconds() / total_seconds
        lat = p1[1] + fraction * (p2[1] - p1[1])
        lon = p1[2] + fraction * (p2[2] - p1[2])
        ele = p1[3] + fraction * (p2[3] - p1[3]) if p1[3] and p2[3] else p1[3]
        return (lat, lon, ele)
    
    # Handle case where target_time is after the last point (extrapolate forwards)
    if idx >= len(points):
        if len(points) < 2:
            return (points[-1][1], points[-1][2], points[-1][3])
        # Extrapolate from last two points
        p1 = points[-2]
        p2 = points[-1]
        t1, t2 = p1[0], p2[0]
        total_seconds = (t2 - t1).total_seconds()
        if total_seconds == 0:
            return (p2[1], p2[2], p2[3])
        # Fraction > 1 means extrapolating forwards
        fraction = (target_time - t1).total_seconds() / total_seconds
        lat = p1[1] + fraction * (p2[1] - p1[1])
        lon = p1[2] + fraction * (p2[2] - p1[2])
        ele = p1[3] + fraction * (p2[3] - p1[3]) if p1[3] and p2[3] else p1[3]
        return (lat, lon, ele)
    
    # Normal interpolation case (target_time is between two points)
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
    """
    Find the single best GPX track for an entire folder.
    Uses the folder's timestamp (from folder name) to find the best match.
    Only matches if the folder time is within or very close to the GPX track time range.
    """
    # Extract timestamp from folder name (e.g., IMG_20251209_125427_312_313_INTERVAL)
    match = re.search(r'IMG_(\d{8})_(\d{6})', folder_path.name)
    if not match:
        return None
    
    date_str = match.group(1)
    time_str = match.group(2)
    
    local_dt = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
    local_tz = timezone(timedelta(hours=tz_offset))
    local_dt = local_dt.replace(tzinfo=local_tz)
    folder_start_time = local_dt.astimezone(timezone.utc)
    
    # Find GPX track that best matches the folder start time
    # Only match if folder time is within the track OR very close (within tolerance)
    best_track = None
    best_score = None  # Use None to track if we found any valid match
    
    for track in gpx_tracks:
        # Case 1: folder starts within the track (ideal case)
        if track.start_time <= folder_start_time <= track.end_time:
            # If strict matching is enabled, only match if folder is close to track start
            if STRICT_MATCHING:
                time_from_start = (folder_start_time - track.start_time).total_seconds()
                # Only match if folder is within tolerance of track start
                if time_from_start <= TIME_TOLERANCE_SECONDS:
                    score = (track.end_time - folder_start_time).total_seconds()
                    if best_score is None or score > best_score:
                        best_score = score
                        best_track = track
            else:
                # Original behavior: match if folder is anywhere within track
                score = (track.end_time - folder_start_time).total_seconds()
                if best_score is None or score > best_score:
                    best_score = score
                    best_track = track
        
        # Case 2: track ended before folder started, but within tolerance
        # Only match if the gap is small (within tolerance)
        elif track.end_time < folder_start_time:
            gap = (folder_start_time - track.end_time).total_seconds()
            if gap <= TIME_TOLERANCE_SECONDS:
                score = -gap  # Negative score, closer is better
                if best_score is None or score > best_score:
                    best_score = score
                    best_track = track
        
        # Case 3: track starts after folder (you started camera first), within tolerance
        # Only match if the gap is small (within tolerance)
        elif track.start_time > folder_start_time:
            gap = (track.start_time - folder_start_time).total_seconds()
            if gap <= TIME_TOLERANCE_SECONDS:
                score = -gap  # Negative score, closer is better
                if best_score is None or score > best_score:
                    best_score = score
                    best_track = track
    
    # Only return a track if we found a valid match
    # If best_score is None, no valid match was found (folder time is too far from any track)
    return best_track if best_score is not None else None


def process_photo_folder(
    folder_path: Path,
    gpx_tracks: List[GPXTrack],
    output_base: Path,
    date_str: str,
    dry_run: bool = False,
    progress_bar = None
) -> FolderResult:
    """Process all photos in a folder using a SINGLE GPX track."""
    
    folder_name = folder_path.name
    photos = sorted(list(folder_path.glob("*.jpg")) + list(folder_path.glob("*.JPG")))
    
    result = FolderResult(
        folder_name=folder_name,
        folder_path=str(folder_path),
        date=date_str,
        gpx_file=None,
        total_photos=len(photos),
        matched_photos=0,
        unmatched_photos=0
    )
    
    if not photos:
        return result
    
    # Find the SINGLE best GPX track for this entire folder
    gpx_track = find_best_gpx_for_folder(folder_path, gpx_tracks, TIMEZONE_OFFSET)
    
    if gpx_track:
        result.gpx_file = gpx_track.path.name
    
    # Create output folder
    output_folder = output_base / date_str / folder_name
    if not dry_run:
        output_folder.mkdir(parents=True, exist_ok=True)
    
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
            # Use the folder's assigned GPX track for ALL photos
            position = interpolate_position(gpx_track.points, timestamp)
            
            if position:
                match.lat, match.lon, match.ele = position
                match.matched = True
                match.gpx_file = gpx_track.path.name
                result.matched_photos += 1
                
                if not dry_run:
                    # Copy and geotag
                    dest = output_folder / photo.name
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
        
        if progress_bar:
            progress_bar.update(1)
    
    return result


def save_index(results: List[FolderResult], output_path: Path):
    """Save a JSON index of all processed photos with GPS data."""
    
    index = {
        "generated": datetime.now().isoformat(),
        "total_photos": sum(r.total_photos for r in results),
        "total_matched": sum(r.matched_photos for r in results),
        "folders": [],
        "photos": []
    }
    
    for result in results:
        index["folders"].append({
            "name": result.folder_name,
            "date": result.date,
            "total": result.total_photos,
            "matched": result.matched_photos,
            "gpx_file": result.gpx_file
        })
        
        for photo in result.photos:
            if photo.matched:
                index["photos"].append({
                    "filename": photo.filename,
                    "folder": result.folder_name,
                    "date": result.date,
                    "lat": photo.lat,
                    "lon": photo.lon,
                    "ele": photo.ele,
                    "timestamp": photo.timestamp.isoformat() if photo.timestamp else None,
                    "path": f"{result.date}/{result.folder_name}/{photo.filename}"
                })
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(index, f, indent=2)
    
    print(f"✓ Saved index to {output_path}")
    print(f"  - {len(index['folders'])} folders")
    print(f"  - {len(index['photos'])} geotagged photos")


# Main execution
if __name__ == "__main__":
    print("="*60)
    print("Geotag Photos Workflow")
    print("="*60)
    print(f"GPS folder:     {GPS_BASE.absolute()}")
    print(f"Photos input:   {PHOTOS_INPUT.absolute()}")
    print(f"Photos output:  {PHOTOS_OUTPUT.absolute()}")
    print(f"Timezone:       UTC{TIMEZONE_OFFSET:+d}")
    print(f"Mode:           {'DRY RUN' if DRY_RUN else 'LIVE'}")
    print("="*60 + "\n")
    
    # Check exiftool
    result = subprocess.run(['which', 'exiftool'], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✓ exiftool found: {result.stdout.strip()}\n")
    else:
        print("✗ exiftool not found! Install with: brew install exiftool\n")
        exit(1)
    
    # Find date folders
    date_folders = sorted([d for d in PHOTOS_INPUT.iterdir() if d.is_dir() and re.match(r'\d{4}-\d{2}-\d{2}', d.name)])
    
    if not date_folders:
        print("No date folders found in photos/input")
        exit(0)
    
    print(f"Found {len(date_folders)} date folder(s)\n")
    
    # Scan to get total count
    scan_results = []
    for date_folder in date_folders:
        date_str = date_folder.name
        photo_folders = [f for f in date_folder.iterdir() if f.is_dir()]
        total_photos = sum(
            len(list(f.glob("*.jpg")) + list(f.glob("*.JPG"))) 
            for f in photo_folders
        )
        scan_results.append({
            'date': date_str,
            'photo_folders': len(photo_folders),
            'total_photos': total_photos
        })
    
    total_photo_count = sum(r['total_photos'] for r in scan_results)
    print(f"Total photos to process: {total_photo_count}\n")
    
    # Process all folders
    all_results = []
    
    with tqdm(total=total_photo_count, desc="Processing photos") as pbar:
        for date_folder in date_folders:
            date_str = date_folder.name
            
            # Load GPX files for this date
            gpx_tracks = load_gpx_files_for_date(GPS_BASE, date_str)
            
            if not gpx_tracks:
                print(f"\n⚠️  {date_str}: No GPX files found, skipping...")
                # Still need to update progress bar
                photo_folders = [f for f in date_folder.iterdir() if f.is_dir()]
                for folder in photo_folders:
                    photo_count = len(list(folder.glob("*.jpg")) + list(folder.glob("*.JPG")))
                    pbar.update(photo_count)
                continue
            
            # Find photo folders for this date
            photo_folders = sorted([f for f in date_folder.iterdir() if f.is_dir()])
            
            for folder in photo_folders:
                result = process_photo_folder(
                    folder, gpx_tracks, PHOTOS_OUTPUT, date_str, DRY_RUN, pbar
                )
                all_results.append(result)
    
    print("\n" + "="*60)
    print("Processing complete!")
    print("="*60)
    
    # Summary statistics
    total_folders = len(all_results)
    total_photos = sum(r.total_photos for r in all_results)
    total_matched = sum(r.matched_photos for r in all_results)
    total_unmatched = sum(r.unmatched_photos for r in all_results)
    
    print(f"\nSUMMARY")
    print("="*60)
    print(f"Total folders processed: {total_folders}")
    print(f"Total photos:            {total_photos}")
    if total_photos > 0:
        print(f"Successfully matched:    {total_matched} ({100*total_matched/total_photos:.1f}%)")
    else:
        print(f"Successfully matched:    0")
    print(f"Unmatched:               {total_unmatched}")
    print("="*60)
    
    # Show any folders with issues
    problem_folders = [r for r in all_results if r.unmatched_photos > 0]
    if problem_folders:
        print(f"\n⚠️  Folders with unmatched photos:")
        for r in problem_folders:
            print(f"   {r.date}/{r.folder_name}: {r.unmatched_photos}/{r.total_photos} unmatched")
    
    # Save index
    if not DRY_RUN:
        print("\n" + "="*60)
        # Save to data/index.json (not photos/output/index.json)
        repo_root = Path(__file__).parent.parent
        index_path = repo_root / "data" / "index.json"
        save_index(all_results, index_path)
    
    print("\n✓ Done!")

