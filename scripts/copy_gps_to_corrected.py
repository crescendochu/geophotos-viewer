#!/usr/bin/env python3
"""
Copy GPS EXIF data from a source photo to a corrected photo, then replace the source.

Usage (single pair):
    python scripts/copy_gps_to_corrected.py \
        --corrected photos/corrected/IMG_20251209_125610_00_316.jpg \
        --source photos/output/2025-12-09/IMG_20251209_125542_314_343_INTERVAL/IMG_20251209_125610_00_316.jpg

Usage (folder of corrected photos; sources are found under photos/output by filename):
    python scripts/copy_gps_to_corrected.py --corrected-dir photos/corrected
    python scripts/copy_gps_to_corrected.py --corrected-dir photos/corrected/my_batch --dry-run
"""

import sys
import subprocess
import argparse
from pathlib import Path
import shutil

REPO_ROOT = Path(__file__).resolve().parent.parent
PHOTOS_OUTPUT = REPO_ROOT / "photos" / "output"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".JPG", ".JPEG"}


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


def build_source_map(output_dir: Path) -> dict:
    """Build filename -> source path for all photos under output_dir."""
    source_by_name = {}
    if not output_dir.is_dir():
        return source_by_name
    for path in output_dir.rglob("*"):
        if path.is_file() and path.suffix in IMAGE_SUFFIXES:
            name = path.name
            if name not in source_by_name:
                source_by_name[name] = path
    return source_by_name


def process_one(corrected_path: Path, source_path: Path, dry_run: bool) -> bool:
    """Copy GPS from source to corrected, then replace source with corrected. Returns True on success."""
    gps_data = read_exif_gps(source_path)
    if not gps_data:
        print(f"  ✗ No GPS in source: {source_path}")
        return False
    if dry_run:
        print(f"  Would copy GPS to {corrected_path.name} and replace {source_path}")
        return True
    if not write_exif_gps(corrected_path, gps_data):
        print(f"  ✗ Failed to write GPS to {corrected_path}")
        return False
    try:
        backup_path = source_path.with_suffix(source_path.suffix + ".backup")
        shutil.copy2(source_path, backup_path)
        shutil.copy2(corrected_path, source_path)
        print(f"  ✓ {corrected_path.name} → replaced source (backup: {backup_path.name})")
        return True
    except Exception as e:
        print(f"  ✗ Replace failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Copy GPS EXIF data from source photo to corrected photo, then replace source"
    )
    parser.add_argument(
        "--corrected",
        type=str,
        default=None,
        help="Path to corrected photo (use with --source for single pair)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Path to source photo (with GPS) that will be replaced",
    )
    parser.add_argument(
        "--corrected-dir",
        type=str,
        default=None,
        metavar="DIR",
        help="Folder of corrected photos; each file is matched to photos/output by filename",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        metavar="DIR",
        help="Where to find source photos (default: photos/output). Used with --corrected-dir.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without making them",
    )
    args = parser.parse_args()

    use_dir = args.corrected_dir is not None
    if use_dir and (args.corrected is not None or args.source is not None):
        print("Error: Use either --corrected-dir OR --corrected + --source, not both.")
        sys.exit(1)
    if not use_dir and (args.corrected is None or args.source is None):
        print("Error: Use --corrected and --source for one photo, or --corrected-dir for a folder.")
        sys.exit(1)

    result = subprocess.run(["which", "exiftool"], capture_output=True, text=True)
    if result.returncode != 0:
        print("✗ exiftool not found! Install with: brew install exiftool")
        sys.exit(1)

    if use_dir:
        corrected_dir = Path(args.corrected_dir)
        if not corrected_dir.is_dir():
            print(f"Error: Corrected folder not found: {corrected_dir}")
            sys.exit(1)
        output_dir = Path(args.output_dir) if args.output_dir else PHOTOS_OUTPUT
        if not output_dir.is_absolute():
            output_dir = REPO_ROOT / output_dir
        source_map = build_source_map(output_dir)
        # Collect all image files in corrected dir (no recursion: only direct children and one level of subdirs)
        corrected_files = []
        for p in corrected_dir.rglob("*"):
            if p.is_file() and p.suffix in IMAGE_SUFFIXES:
                corrected_files.append(p)
        corrected_files.sort(key=lambda p: p.name)
        if not corrected_files:
            print(f"No image files found in {corrected_dir}")
            sys.exit(0)
        print("=" * 60)
        print("Copy GPS to Corrected (folder mode)")
        print("=" * 60)
        print(f"Corrected folder: {corrected_dir.absolute()}")
        print(f"Source folder:    {output_dir.absolute()}")
        print(f"Photos to process: {len(corrected_files)}")
        print(f"Mode:            {'DRY RUN' if args.dry_run else 'LIVE'}")
        print("=" * 60 + "\n")
        ok = 0
        skip = 0
        for corrected_path in corrected_files:
            source_path = source_map.get(corrected_path.name)
            if source_path is None:
                print(f"  ⊘ No source for {corrected_path.name} (skipped)")
                skip += 1
                continue
            if process_one(corrected_path, source_path, args.dry_run):
                ok += 1
        print()
        print(f"Done: {ok} updated, {skip} skipped (no source).")
        return

    # Single-pair mode
    corrected_path = Path(args.corrected)
    source_path = Path(args.source)
    if not corrected_path.is_absolute():
        corrected_path = REPO_ROOT / corrected_path
    if not source_path.is_absolute():
        source_path = REPO_ROOT / source_path
    if not corrected_path.exists():
        print(f"Error: Corrected photo not found: {corrected_path}")
        sys.exit(1)
    if not source_path.exists():
        print(f"Error: Source photo not found: {source_path}")
        sys.exit(1)
    print("=" * 60)
    print("Copy GPS to Corrected Photo")
    print("=" * 60)
    print(f"Corrected photo: {corrected_path.absolute()}")
    print(f"Source photo:    {source_path.absolute()}")
    print(f"Mode:            {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60 + "\n")
    if not process_one(corrected_path, source_path, args.dry_run):
        sys.exit(1)
    print("\n✓ Done!")


if __name__ == "__main__":
    main()

