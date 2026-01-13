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

