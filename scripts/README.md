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

# Delete multiple photos at once
python scripts/delete_individual_photos.py IMG_20251209_144524_00_554.jpg IMG_20251209_144525_00_555.jpg IMG_20251209_144526_00_556.jpg
```

# photos to delete
python scripts/delete_individual_photos.py IMG_20251209_144341_00_547.jpg IMG_20251209_144357_00_548.jpg IMG_20251209_144412_00_549.jpg IMG_20251209_144426_00_550.jpg IMG_20251209_144441_00_551.jpg IMG_20251209_144455_00_552.jpg IMG_20251209_144510_00_553.jpg IMG_20251209_144524_00_554.jpg

**What it does:**
- Finds the photos in `data/index.json` by filename
- Deletes photo files from `photos/output/`
- Removes photo entries from `data/index.json`
- Re-processes the folder(s) containing the deleted photos
- Re-matches remaining photos with GPX data
- Updates EXIF GPS tags for remaining photos
- Updates `data/index.json` with new GPS coordinates

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

python scripts/reassign_gpx.py IMG_20251209_133130_406_414_INTERVAL "2025-12-09-133410-Outdoor Walking-Chu’s Apple Watch.gpx"

# Preview changes without applying them
python scripts/reassign_gpx.py IMG_20251211_133133_966_972_INTERVAL "2025-12-11-133133-Outdoor Walking-Chu's Apple Watch.gpx" --dry-run
```

**What it does:**
- Re-processes all photos in the specified folder using the new GPX file
- Updates EXIF GPS tags in `photos/output/`
- Updates `data/index.json` with new GPS coordinates and GPX file reference
- Handles Unicode characters in filenames (like non-breaking spaces)

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

