#!/usr/bin/env python3
"""
Export photo GPS coordinates to GeoJSON format for QGIS snapping.

This script exports photo GPS coordinates from data/index.json to a GeoJSON file
that can be loaded into QGIS. After snapping to OSM in QGIS, use import_snapped_gps.py
to import the snapped coordinates back.

Usage:
    # Export all photos
    python scripts/export_photo_gps.py
    
    # Export specific date
    python scripts/export_photo_gps.py --date 2025-12-09
    
    # Export specific folder
    python scripts/export_photo_gps.py --folder IMG_20251209_125427_312_313_INTERVAL
    
    # Export to custom output file
    python scripts/export_photo_gps.py --output photos_to_snap.geojson
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


def load_index(index_path: Path) -> Dict:
    """Load the index.json file."""
    if not index_path.exists():
        print(f"Error: {index_path} not found")
        sys.exit(1)
    
    with open(index_path, 'r') as f:
        return json.load(f)


def filter_photos(index: Dict, date: Optional[str] = None, folder: Optional[str] = None) -> List[Dict]:
    """Filter photos from index based on date or folder."""
    photos = index.get('photos', [])
    
    if date:
        photos = [p for p in photos if p.get('date') == date]
    
    if folder:
        photos = [p for p in photos if p.get('folder') == folder]
    
    return photos


def create_geojson(photos: List[Dict]) -> Dict:
    """Create a GeoJSON FeatureCollection from photo data."""
    features = []
    
    for photo in photos:
        lat = photo.get('lat')
        lon = photo.get('lon')
        
        if lat is None or lon is None:
            continue
        
        # Create a unique ID for matching back
        photo_id = f"{photo.get('date')}/{photo.get('folder')}/{photo.get('filename')}"
        
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]  # GeoJSON uses [lon, lat]
            },
            "properties": {
                "photo_id": photo_id,
                "filename": photo.get('filename'),
                "folder": photo.get('folder'),
                "date": photo.get('date'),
                "path": photo.get('path'),
                "lat": lat,
                "lon": lon,
                "ele": photo.get('ele'),
                "timestamp": photo.get('timestamp'),
                "original_lat": lat,  # Keep original for reference
                "original_lon": lon   # Keep original for reference
            }
        }
        features.append(feature)
    
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
            }
        },
        "features": features
    }


def export_geojson(
    index_path: Path,
    output_path: Path,
    date: Optional[str] = None,
    folder: Optional[str] = None
):
    """Export photo GPS coordinates to GeoJSON."""
    print("="*60)
    print("Export Photo GPS Coordinates")
    print("="*60)
    print(f"Index file:  {index_path.absolute()}")
    print(f"Output file: {output_path.absolute()}")
    if date:
        print(f"Filter date: {date}")
    if folder:
        print(f"Filter folder: {folder}")
    print("="*60 + "\n")
    
    # Load index
    print("Loading index...")
    index = load_index(index_path)
    print(f"  Total photos in index: {index.get('total_photos', 0)}")
    
    # Filter photos
    photos = filter_photos(index, date=date, folder=folder)
    print(f"  Photos to export: {len(photos)}")
    
    if not photos:
        print("\nNo photos found matching criteria.")
        sys.exit(1)
    
    # Create GeoJSON
    print("\nCreating GeoJSON...")
    geojson = create_geojson(photos)
    
    # Save GeoJSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(geojson, f, indent=2)
    
    print(f"\n✓ Exported {len(geojson['features'])} photo locations to {output_path}")
    print(f"\nNext steps:")
    print(f"  1. Open {output_path} in QGIS")
    print(f"  2. Load OSM layer (Vector > QuickOSM or use QuickMapServices plugin)")
    print(f"  3. Use 'Snap geometries to layer' tool to snap points to OSM")
    print(f"  4. Export the snapped layer (right-click > Export > Save Features As...)")
    print(f"  5. Use import_snapped_gps.py to import the snapped coordinates back")
    print(f"\nNote: The 'photo_id' property is used to match photos back.")


def main():
    parser = argparse.ArgumentParser(
        description="Export photo GPS coordinates to GeoJSON for QGIS snapping"
    )
    parser.add_argument(
        '--date',
        type=str,
        help='Filter by date (format: YYYY-MM-DD)'
    )
    parser.add_argument(
        '--folder',
        type=str,
        help='Filter by folder name'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='photo_gps_export.geojson',
        help='Output GeoJSON file path (default: photo_gps_export.geojson)'
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
    if args.index:
        index_path = Path(args.index)
    else:
        index_path = repo_root / "data" / "index.json"
    
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    
    export_geojson(index_path, output_path, date=args.date, folder=args.folder)


if __name__ == "__main__":
    main()

