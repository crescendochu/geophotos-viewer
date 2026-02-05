# Scripts

## Workflow Scripts

### `geotag_photos.py`
Main workflow script that processes new photos:
1. Reads photos from `photos/input/`
2. Tags them with GPS data from `gps/`
3. Moves tagged photos to `photos/output/`
4. Generates/updates `data/index.json`

**Usage:**
```bash
python scripts/geotag_photos.py
```

**Configuration:**
Edit the constants at the top of the script to adjust:
- `TIMEZONE_OFFSET`: Your timezone offset from UTC
- `TIME_TOLERANCE_SECONDS`: How far outside GPX time range to accept matches
- `DRY_RUN`: Set to `True` to preview without making changes

### `delete_photos.py`
Deletes noisy/interrupted photo data from both the index and disk.

**Usage:**
```bash
# Delete by folder ID (removes entire folder)
python scripts/delete_photos.py IMG_20251211_120437_707_714_INTERVAL

### Deleted folders
python scripts/delete_photos.py IMG_20251211_103243_375_375_INTERVAL
python scripts/delete_photos.py IMG_20251211_131419_930_933_INTERVAL
python scripts/delete_photos.py IMG_20251211_122023_754_756_INTERVAL
python scripts/delete_photos.py IMG_20251211_130030_892_902_INTERVAL #(this one could be useful, same route with IMG_20251211_130643_903_913_INTERVAL)
python scripts/delete_photos.py IMG_20251211_111109_548_579_INTERVAL
python scripts/delete_photos.py IMG_20251211_110558_530_533_INTERVAL
python scripts/delete_photos.py IMG_20251211_124506_845_846_INTERVAL
python scripts/delete_photos.py IMG_20251210_134422_943_948_INTERVAL

python scripts/delete_photos.py IMG_20251210_151014_216_216_INTERVAL
python scripts/delete_photos.py IMG_20251210_160242_367_370_INTERVAL
python scripts/delete_photos.py IMG_20251210_140704_974_975_INTERVAL
python scripts/delete_photos.py IMG_20251210_155058_332_339_INTERVAL #(this one could be useful, same route with IMG_20251210_155957_359_366_INTERVAL)

python scripts/delete_photos.py IMG_20251209_143149_511_527_INTERVAL
python scripts/delete_photos.py IMG_20251209_145245_574_578_INTERVAL
python scripts/delete_photos.py IMG_20251209_150113_599_603_INTERVAL
python scripts/delete_photos.py IMG_20251209_145830_589_593_INTERVAL

python scripts/delete_photos.py IMG_20251209_141157_467_470_INTERVAL

python scripts/delete_photos.py IMG_20251209_133130_406_414_INTERVAL


python scripts/delete_photos.py IMG_20251209_125427_312_313_INTERVAL
python scripts/delete_photos.py IMG_20251209_150417_604_608_INTERVAL
python scripts/delete_photos.py IMG_20251211_113416_608_608_INTERVAL


# Delete multiple folders
python scripts/delete_photos.py folder1 folder2 folder3

# Delete specific photos by path
python scripts/delete_photos.py --paths "2025-12-11/IMG_.../IMG_20251211_120437_00_707.jpg"
```

**What it does:**
- Removes photo entries from `data/index.json`
- Updates folder counts
- Deletes photo files from `photos/output/` (optional, default: yes)
- Updates the `generated` timestamp in `index.json`

### `delete_individual_photos.py`
Deletes individual photos by filename and automatically re-matches GPX data for the remaining photos in the folder. Useful when you forgot to turn off the camera and want to remove specific photos.

**Usage:**
```bash
# Delete one or more individual photos by filename
python scripts/delete_individual_photos.py IMG_20251209_144524_00_554.jpg

python scripts/delete_individual_photos.py IMG_20251209_130548_00_355.jpg

# Delete multiple photos at once
python scripts/delete_individual_photos.py IMG_20251209_144524_00_554.jpg IMG_20251209_144525_00_555.jpg IMG_20251209_144526_00_556.jpg

# Delete without reassigning GPX
python scripts/delete_individual_photos.py --no-reassign IMG_20251209_144524_00_554.jpg
```

# photos to delete
python scripts/delete_individual_photos.py IMG_20251209_144341_00_547.jpg IMG_20251209_144357_00_548.jpg IMG_20251209_144412_00_549.jpg IMG_20251209_144426_00_550.jpg IMG_20251209_144441_00_551.jpg IMG_20251209_144455_00_552.jpg IMG_20251209_144510_00_553.jpg IMG_20251209_144524_00_554.jpg

python scripts/delete_individual_photos.py IMG_20251211_152024_00_098.jpg

**What it does:**
- Finds the photos in `data/index.json` by filename
- Deletes photo files from `photos/output/`
- Removes photo entries from `data/index.json`
- Re-processes the folder(s) containing the deleted photos (unless `--no-reassign`)
- Re-matches remaining photos with GPX data (unless `--no-reassign`)
- Updates EXIF GPS tags for remaining photos (unless `--no-reassign`)
- Updates `data/index.json` with new GPS coordinates (unless `--no-reassign`)

**Note:** The script will automatically find which folder each photo belongs to and re-process that entire folder to ensure all remaining photos are properly matched with GPX data.

### `reassign_gpx.py`
Reassigns a photo folder to a different GPX file. Useful for spot corrections when:
- GPX files are added later (you forgot to export one)
- A folder was incorrectly matched to the wrong GPX file

**Usage:**
```bash
python scripts/reassign_gpx.py <folder_name> <gpx_filename> [--dry-run]

# Example: Reassign folder to correct GPX file
python scripts/reassign_gpx.py IMG_20251211_133133_966_972_INTERVAL "2025-12-11-133133-Outdoor Walking-Chu's Apple Watch.gpx"

#reassigned folders
python scripts/reassign_gpx.py IMG_20251211_130030_892_902_INTERVAL "2025-12-11-130038-Outdoor Walking-Chu’s Apple Watch.gpx"

python scripts/reassign_gpx.py IMG_20251209_133130_406_414_INTERVAL "2025-12-09-133120-Outdoor Walking-Chu’s Apple Watch.gpx"

# Preview changes without applying them
python scripts/reassign_gpx.py IMG_20251211_133133_966_972_INTERVAL "2025-12-11-133133-Outdoor Walking-Chu's Apple Watch.gpx" --dry-run
```

**What it does:**
- Re-processes all photos in the specified folder using the new GPX file
- Updates EXIF GPS tags in `photos/output/`
- Updates `data/index.json` with new GPS coordinates and GPX file reference
- Handles Unicode characters in filenames (like non-breaking spaces)

### `blur_faces_plates.py`
Detects and blurs human faces and car license plates in 360° equirectangular photos. Useful for privacy protection before sharing photos publicly.

**Usage:**
```bash
# Blur faces and plates in all photos (saves to photos/blurred by default)
python scripts/blur_faces_plates.py

# Process only a specific photo folder (for testing)
python scripts/blur_faces_plates.py --folder IMG_20251209_125427_312_313_INTERVAL

python scripts/blur_faces_plates.py --folder IMG_20251210_101536_640_656_INTERVAL

# Process only a specific date
python scripts/blur_faces_plates.py --date 2025-12-09

# Adjust blur intensity (light, medium, heavy)
python scripts/blur_faces_plates.py --intensity heavy

# Preview without making changes
python scripts/blur_faces_plates.py --dry-run

# Overwrite originals instead of saving to photos/blurred
python scripts/blur_faces_plates.py --output photos/output

# Combine options
python scripts/blur_faces_plates.py --intensity medium --date 2025-12-09 --folder IMG_20251209_125427_312_313_INTERVAL
```

**What it does:**
- Detects human faces using OpenCV Haar cascades
- Detects license plates using color and shape analysis
- Applies Gaussian blur to detected regions
- Preserves EXIF data (GPS coordinates, timestamps, etc.)
- Processes photos from `photos/output/` by default
- Can overwrite originals or save to a separate folder

**Dependencies:**
```bash
pip install opencv-python numpy pillow tqdm
```

**Configuration:**
Edit the constants at the top of the script to adjust:
- `PHOTOS_INPUT`: Input folder (default: `photos/output`)
- `PHOTOS_OUTPUT`: Output folder (default: `photos/blurred`)
- `BLUR_INTENSITY`: `'light'`, `'medium'`, or `'heavy'` (default: `'medium'`)
- `MIN_FACE_SIZE`: Minimum face size as fraction of image width (default: 0.02)
- `MAX_FACE_SIZE`: Maximum face size as fraction of image width (default: 0.3)
- `PADDING_FACTOR`: Padding around detected regions (default: 0.3)

**Note:** The script works with equirectangular 360° images. Face detection may have some limitations with faces near the edges of the equirectangular projection due to distortion.

### `export_photo_db.py`
Exports a flat database of all photos to CSV and/or GeoJSON for easier management (spreadsheets, GIS, analysis). Assigns each photo to a neighborhood using the same date + `timeRange` logic as the web app. **Source:** `data/index.json` only; row count matches the index when no filter is used (~2000).

**Output columns / properties:**
- `photo_id` — Short unique ID: filename without `IMG_` or extension (e.g. `20251209_125542_00_314`)
- `neighborhood_id`, `neighborhood_name`, `neighborhood_name_ja` — Assigned neighborhood (empty if none)
- `lon`, `lat`, `ele` — Coordinates and elevation
- `date`, `timestamp` — Capture date and full ISO timestamp
- `filename`, `folder`, `path` — File location within `photos/output/`
- `gpx_file` — GPX track used for geotagging

**Usage:**
```bash
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
```

**What it does:**
- Reads `data/index.json` and `data/neighborhoods.json`
- Matches each photo to a neighborhood (date + optional `timeRange`)
- With no `--date` / `--neighborhood` filter, exports **all** index photos (row count = index size)
- Writes CSV (all columns above) and/or GeoJSON (point features with same properties)
- Skips photos without `lat`/`lon` in GeoJSON only; CSV includes every indexed photo

### `export_photo_gps.py` and `import_snapped_gps.py`
Export photo GPS coordinates to GeoJSON for snapping in QGIS, then import the snapped coordinates back. Useful for correcting GPS drift by snapping photo locations to OpenStreetMap features (roads, paths, etc.).

**Workflow:**

1. **Export GPS coordinates:**
   ```bash
   # Export all photos
   python scripts/export_photo_gps.py
   
   # Export specific date
   python scripts/export_photo_gps.py --date 2025-12-09
   
   # Export specific folder
   python scripts/export_photo_gps.py --folder IMG_20251209_125427_312_313_INTERVAL
   
   # Custom output file
   python scripts/export_photo_gps.py --output my_photos.geojson
   ```

2. **Snap to OSM in QGIS:**
   - Open the exported GeoJSON file in QGIS
   - Load OSM layer (Vector > QuickOSM or use QuickMapServices plugin)
   - Use "Snap geometries to layer" tool (Processing Toolbox > Vector geometry > Snap geometries to layer)
     - Input layer: your photo points
     - Reference layer: OSM layer (roads, paths, etc.)
     - Tolerance: set appropriate distance (e.g., 10-50 meters)
   - Export the snapped layer (right-click layer > Export > Save Features As... > GeoJSON)

3. **Import snapped coordinates:**
   ```bash
   # Import snapped coordinates
   python scripts/import_snapped_gps.py snapped_photos.geojson
   
   # Preview changes first
   python scripts/import_snapped_gps.py snapped_photos.geojson --dry-run
   
   # Only update EXIF, don't update index.json
   python scripts/import_snapped_gps.py snapped_photos.geojson --no-index
   ```

**What it does:**
- `export_photo_gps.py`: Exports photo GPS coordinates from `data/index.json` to GeoJSON format with photo identifiers
- `import_snapped_gps.py`: Reads snapped GeoJSON from QGIS and updates:
  - Photo EXIF GPS tags in `photos/output/`
  - GPS coordinates in `data/index.json`

**Note:** The `photo_id` property in the GeoJSON is used to match photos back. Make sure not to modify this property when working in QGIS.

### `clean_photos_output.py`
Removes clutter from `photos/output/`: deletes all `.backup` files and any files or folders not referenced in `data/index.json` (i.e. not used by the web app). Also removes empty directories.

**Usage:**
```bash
# Preview what would be deleted (dry run)
python scripts/clean_photos_output.py

# Actually delete
python scripts/clean_photos_output.py --execute
```

**What it does:**
- Deletes every `*.backup` file under `photos/output/`
- Deletes any file whose path is not in `data/index.json` → `photos[]` → `path`
- Removes empty directories

## Auto-Update Workflow

For auto-updating, you can:
- Use a file watcher (like `watchdog` in Python) to monitor `photos/input/`
- Set up a cron job or scheduled task
- Use a simple loop script that runs `geotag_photos.py` periodically

Example with `watchdog`:
```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class PhotoHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith(('.jpg', '.JPG')):
            # Run geotag_photos.py
            import subprocess
            subprocess.run(['python', 'scripts/geotag_photos.py'])
```

