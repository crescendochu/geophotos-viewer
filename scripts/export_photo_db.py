#!/usr/bin/env python3
"""
Export a database of photos to CSV and/or GeoJSON for easier management.

Reads data/index.json and data/neighborhoods.json, assigns each photo to a
neighborhood (using the same date + timeRange logic as the web app), and
writes photo_id, neighbourhood, lon/lat, date captured, and related fields.

Usage:
    # Export both CSV and GeoJSON (default: data/photos_db.csv, data/photos_db.geojson)
    python scripts/export_photo_db.py

    # CSV only
    python scripts/export_photo_db.py --csv-only

    # GeoJSON only
    python scripts/export_photo_db.py --geojson-only

    # Filter by date or neighborhood
    python scripts/export_photo_db.py --date 2025-12-09
    python scripts/export_photo_db.py --neighborhood kinshicho

    # Custom output paths
    python scripts/export_photo_db.py --csv my_photos.csv --geojson my_photos.geojson
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "data" / "index.json"
NEIGHBORHOODS_PATH = REPO_ROOT / "data" / "neighborhoods.json"
PHOTOS_OUTPUT = REPO_ROOT / "photos" / "output"
SNAPPED_POINTS_DIR = REPO_ROOT / "data" / "snapped-points"
DEFAULT_CSV_PATH = REPO_ROOT / "data" / "photos_db.csv"
DEFAULT_GEOJSON_PATH = REPO_ROOT / "data" / "photos_db.geojson"

# -----------------------------------------------------------------------------
# Load data
# -----------------------------------------------------------------------------


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_index(path: Path) -> Dict[str, Any]:
    return load_json(path)


def load_neighborhoods(path: Path) -> List[Dict[str, Any]]:
    data = load_json(path)
    return data.get("neighborhoods", [])


def load_snapped_coords(snapped_dir: Path) -> Dict[str, Tuple[float, float]]:
    """
    Load path -> (lat, lon) from all snapped-points GeoJSON files.
    Geometry coordinates are [lon, lat]; we return (lat, lon).
    Match key: properties.path or properties.photo_id (full path).
    """
    out: Dict[str, Tuple[float, float]] = {}
    if not snapped_dir.is_dir():
        return out
    for gj_path in snapped_dir.glob("*.geojson"):
        try:
            data = load_json(gj_path)
        except Exception:
            continue
        for feat in data.get("features", []):
            geom = feat.get("geometry")
            props = feat.get("properties") or {}
            if geom and geom.get("type") == "Point":
                coords = geom.get("coordinates")
                if coords and len(coords) >= 2:
                    lon, lat = float(coords[0]), float(coords[1])
                    key = props.get("path") or props.get("photo_id") or ""
                    if key:
                        out[key] = (lat, lon)
    return out


# -----------------------------------------------------------------------------
# Neighborhood matching (same logic as web app)
# -----------------------------------------------------------------------------


def get_neighborhood_for_photo(
    photo: Dict[str, Any],
    neighborhoods: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return the neighborhood this photo belongs to, or None."""
    photo_date = photo.get("date")
    if not photo_date:
        return None
    if not photo.get("lat") or not photo.get("lon"):
        return None

    ts = photo.get("timestamp")
    if not ts:
        photo_time_ms = None
    else:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            photo_time_ms = dt.timestamp() * 1000
        except Exception:
            photo_time_ms = None

    for nb in neighborhoods:
        if nb.get("date") != photo_date:
            continue
        tr = nb.get("timeRange")
        if not tr:
            return nb
        if photo_time_ms is None:
            continue
        try:
            start_ms = datetime.fromisoformat(
                tr["start"].replace("Z", "+00:00")
            ).timestamp() * 1000
            end_ms = datetime.fromisoformat(
                tr["end"].replace("Z", "+00:00")
            ).timestamp() * 1000
        except Exception:
            continue
        if start_ms <= photo_time_ms <= end_ms:
            return nb

    return None


# -----------------------------------------------------------------------------
# Build photo database rows
# -----------------------------------------------------------------------------


def photo_id(photo: Dict[str, Any]) -> str:
    """Short unique id: filename without IMG_ prefix or extension (e.g. 20251209_125542_00_314)."""
    fn = photo.get("filename") or ""
    if fn.upper().startswith("IMG_"):
        fn = fn[4:]
    if "." in fn:
        fn = fn.rsplit(".", 1)[0]
    return fn or f"{photo.get('date', '')}/{photo.get('folder', '')}/{photo.get('filename', '')}"


def build_db_rows(
    index: Dict[str, Any],
    neighborhoods: List[Dict[str, Any]],
    *,
    date_filter: Optional[str] = None,
    neighborhood_filter: Optional[str] = None,
    snapped_map: Optional[Dict[str, Tuple[float, float]]] = None,
    photos_output: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Build list of photo DB rows (flat dicts for CSV/GeoJSON props).
    Skips photos whose image file does not exist under photos_output.
    Adds lat_current, lon_current from snapped_map when available.
    Returns (rows, n_skipped_missing_file).
    """
    photos = index.get("photos", [])
    folders_by_name: Dict[str, Dict[str, Any]] = {}
    for f in index.get("folders", []):
        folders_by_name[f["name"]] = f

    if date_filter:
        photos = [p for p in photos if p.get("date") == date_filter]
    if neighborhood_filter:
        nb_ids = {nb["id"] for nb in neighborhoods if nb["id"] == neighborhood_filter}
        if not nb_ids:
            print(f"Error: Unknown neighborhood '{neighborhood_filter}'")
            sys.exit(1)

    snapped = snapped_map or {}
    out_dir = photos_output or PHOTOS_OUTPUT
    n_skipped_missing = 0

    rows: List[Dict[str, Any]] = []
    for p in sorted(photos, key=lambda x: (x.get("timestamp") or "", x.get("path") or "")):
        path_val = p.get("path") or ""
        if path_val and not out_dir.joinpath(path_val).exists():
            n_skipped_missing += 1
            continue

        nb = get_neighborhood_for_photo(p, neighborhoods)
        nb_id = nb["id"] if nb else ""
        nb_name = nb.get("name", "") if nb else ""
        nb_name_ja = nb.get("nameJa", "") if nb else ""

        if neighborhood_filter and nb_id != neighborhood_filter:
            continue

        folder_data = folders_by_name.get(p.get("folder") or "", {})
        gpx_file = folder_data.get("gpx_file") or ""

        lat_cur, lon_cur = snapped.get(path_val, (None, None)) if path_val else (None, None)

        row = {
            "photo_id": photo_id(p),
            "filename": p.get("filename") or "",
            "folder": p.get("folder") or "",
            "path": path_val,
            "date": p.get("date") or "",
            "timestamp": p.get("timestamp") or "",
            "lat": p.get("lat"),
            "lon": p.get("lon"),
            "lat_current": lat_cur,
            "lon_current": lon_cur,
            "ele": p.get("ele"),
            "neighborhood_id": nb_id,
            "neighborhood_name": nb_name,
            "neighborhood_name_ja": nb_name_ja,
            "gpx_file": gpx_file,
        }
        rows.append(row)

    return rows, n_skipped_missing


# -----------------------------------------------------------------------------
# Export CSV
# -----------------------------------------------------------------------------

CSV_COLUMNS = [
    "photo_id",
    "neighborhood_id",
    "neighborhood_name",
    "neighborhood_name_ja",
    "lon",
    "lat",
    "lon_current",
    "lat_current",
    "ele",
    "date",
    "timestamp",
    "filename",
    "folder",
    "path",
    "gpx_file",
]


def write_csv(rows: List[Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            # CSV can't store None nicely; use empty string
            out = {k: ("" if v is None else v) for k, v in r.items()}
            w.writerow(out)


# -----------------------------------------------------------------------------
# Export GeoJSON
# -----------------------------------------------------------------------------


def build_geojson(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    features = []
    for r in rows:
        lat, lon = r.get("lat"), r.get("lon")
        if lat is None or lon is None:
            continue
        props = {k: v for k, v in r.items() if v != "" and v is not None}
        # Ensure numeric types for lat/lon in properties; geometry has the coords
        if "lat" in props:
            props["lat"] = float(props["lat"])
        if "lon" in props:
            props["lon"] = float(props["lon"])
        if "lat_current" in props:
            props["lat_current"] = float(props["lat_current"])
        if "lon_current" in props:
            props["lon_current"] = float(props["lon_current"])
        if "ele" in props:
            props["ele"] = float(props["ele"])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": props,
        })
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }


def write_geojson(rows: List[Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gj = build_geojson(rows)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(gj, f, indent=2, ensure_ascii=False)


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Export photo database to CSV and/or GeoJSON"
    )
    ap.add_argument("--csv", type=str, default=None, help="Output CSV path")
    ap.add_argument("--geojson", type=str, default=None, help="Output GeoJSON path")
    ap.add_argument(
        "--csv-only",
        action="store_true",
        help="Write only CSV (default: both if no --csv/--geojson)",
    )
    ap.add_argument(
        "--geojson-only",
        action="store_true",
        help="Write only GeoJSON",
    )
    ap.add_argument("--date", type=str, help="Filter by date (YYYY-MM-DD)")
    ap.add_argument(
        "--neighborhood",
        type=str,
        help="Filter by neighborhood id (e.g. kinshicho)",
    )
    ap.add_argument(
        "--index",
        type=str,
        default=None,
        help="Path to index.json (default: data/index.json)",
    )
    ap.add_argument(
        "--neighborhoods",
        type=str,
        default=None,
        help="Path to neighborhoods.json (default: data/neighborhoods.json)",
    )
    args = ap.parse_args()

    index_path = Path(args.index) if args.index else INDEX_PATH
    nb_path = Path(args.neighborhoods) if args.neighborhoods else NEIGHBORHOODS_PATH

    index = load_index(index_path)
    neighborhoods = load_neighborhoods(nb_path)
    index_count = len(index.get("photos", []))

    snapped_map = load_snapped_coords(SNAPPED_POINTS_DIR)
    if snapped_map:
        print(f"  Loaded {len(snapped_map)} snapped coordinates from data/snapped-points/")

    rows, n_skipped_missing = build_db_rows(
        index,
        neighborhoods,
        date_filter=args.date,
        neighborhood_filter=args.neighborhood,
        snapped_map=snapped_map,
        photos_output=PHOTOS_OUTPUT,
    )

    if n_skipped_missing > 0:
        print(f"  Skipped {n_skipped_missing} photos (image file no longer exists).")

    if not rows:
        print("No photos match the given filters (or all were skipped).")
        sys.exit(1)

    if not args.date and not args.neighborhood and len(rows) + n_skipped_missing != index_count:
        print(f"Warning: index has {index_count} photos but export has {len(rows)} (+ {n_skipped_missing} skipped). Check for bugs.")

    write_csv_flag = not args.geojson_only
    write_geojson_flag = not args.csv_only
    if args.csv_only:
        write_geojson_flag = False
    if args.geojson_only:
        write_csv_flag = False

    csv_path = Path(args.csv) if args.csv else DEFAULT_CSV_PATH
    if not csv_path.is_absolute():
        csv_path = REPO_ROOT / csv_path
    geojson_path = Path(args.geojson) if args.geojson else DEFAULT_GEOJSON_PATH
    if not geojson_path.is_absolute():
        geojson_path = REPO_ROOT / geojson_path

    print("Exporting photo database")
    print(f"  Index photos: {index_count}")
    print(f"  Exporting:    {len(rows)}")
    if args.date:
        print(f"  Date filter: {args.date}")
    if args.neighborhood:
        print(f"  Neighborhood filter: {args.neighborhood}")
    print()

    if write_csv_flag:
        write_csv(rows, csv_path)
        print(f"  CSV:     {csv_path}")
    if write_geojson_flag:
        write_geojson(rows, geojson_path)
        n_geo = len([r for r in rows if r.get("lat") is not None and r.get("lon") is not None])
        print(f"  GeoJSON: {geojson_path} ({n_geo} features)")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
