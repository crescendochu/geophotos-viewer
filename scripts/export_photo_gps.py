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


def filter_photos(
    index: Dict, 
    date: Optional[str] = None, 
    folder: Optional[str] = None,
    neighborhood: Optional[Dict] = None
) -> List[Dict]:
    """Filter photos from index based on date, folder, or neighborhood."""
    photos = index.get('photos', [])
    
    if neighborhood:
        # Filter by neighborhood criteria
        if neighborhood.get('date'):
            photos = [p for p in photos if p.get('date') == neighborhood['date']]
        
        # Filter by bounds if available
        if neighborhood.get('bounds'):
            bounds = neighborhood['bounds']
            photos = [
                p for p in photos 
                if (p.get('lat') and p.get('lon') and
                    bounds['minLat'] <= p['lat'] <= bounds['maxLat'] and
                    bounds['minLon'] <= p['lon'] <= bounds['maxLon'])
            ]
        
        # Filter by time range if available
        if neighborhood.get('timeRange'):
            time_range = neighborhood['timeRange']
            try:
                start_time = datetime.fromisoformat(time_range['start'].replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(time_range['end'].replace('Z', '+00:00'))
                
                filtered = []
                for p in photos:
                    if p.get('timestamp'):
                        try:
                            photo_time = datetime.fromisoformat(p['timestamp'].replace('Z', '+00:00'))
                            if start_time <= photo_time <= end_time:
                                filtered.append(p)
                        except:
                            pass
                photos = filtered
            except Exception as e:
                print(f"  Warning: Could not parse time range: {e}")
    
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


def load_neighborhoods(neighborhoods_path: Path) -> Dict:
    """Load the neighborhoods.json file."""
    if not neighborhoods_path.exists():
        print(f"Error: {neighborhoods_path} not found")
        sys.exit(1)
    
    with open(neighborhoods_path, 'r') as f:
        return json.load(f)


def export_geojson(
    index_path: Path,
    output_path: Path,
    date: Optional[str] = None,
    folder: Optional[str] = None,
    neighborhood: Optional[Dict] = None
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
    if neighborhood:
        print(f"Filter neighborhood: {neighborhood.get('name', 'Unknown')} ({neighborhood.get('id', 'unknown')})")
    print("="*60 + "\n")
    
    # Load index
    print("Loading index...")
    index = load_index(index_path)
    print(f"  Total photos in index: {index.get('total_photos', 0)}")
    
    # Filter photos
    photos = filter_photos(index, date=date, folder=folder, neighborhood=neighborhood)
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
    parser.add_argument(
        '--neighborhood',
        type=str,
        help='Filter by neighborhood ID (e.g., shinjuku, kinshicho)'
    )
    
    args = parser.parse_args()
    
    # Determine paths
    repo_root = Path(__file__).parent.parent
    if args.index:
        index_path = Path(args.index)
    else:
        index_path = repo_root / "data" / "index.json"
    
    neighborhoods_path = repo_root / "data" / "neighborhoods.json"
    
    # Load neighborhood if specified
    neighborhood = None
    if args.neighborhood:
        neighborhoods_data = load_neighborhoods(neighborhoods_path)
        neighborhood = next(
            (n for n in neighborhoods_data.get('neighborhoods', []) if n.get('id') == args.neighborhood),
            None
        )
        if not neighborhood:
            print(f"Error: Neighborhood '{args.neighborhood}' not found")
            print(f"Available neighborhoods: {', '.join(n.get('id') for n in neighborhoods_data.get('neighborhoods', []))}")
            sys.exit(1)
    
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    
    export_geojson(index_path, output_path, date=args.date, folder=args.folder, neighborhood=neighborhood)


if __name__ == "__main__":
    main()

