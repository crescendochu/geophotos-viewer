# Tokyo 360° Street View - GeoPhotos Viewer

An immersive web viewer for 360° panoramic photos with GPS tracking, featuring interactive maps and neighborhood exploration.

## Project Structure

```
geophotos-viewer/
├── scripts/              # Python scripts for photo processing
│   ├── geotag_photos.py  # Main workflow: tag photos → generate index
│   ├── process_photos.py # Wrapper script (calls geotag_photos.py)
│   ├── delete_photos.py  # Delete noisy/interrupted data
│   └── README.md         # Script documentation
├── web/                  # Web viewer files
│   ├── css/              # Stylesheets
│   ├── js/               # JavaScript (app.js, viewer.js)
│   ├── index.html        # Home page (neighborhood grid)
│   └── viewer.html       # 360° panorama viewer
├── data/                 # Generated and config data
│   ├── index.json        # Auto-generated photo index (GPS, timestamps)
│   └── neighborhoods.json # Manual config: neighborhood definitions
├── photos/
│   ├── input/            # Drop raw photos here for processing
│   └── output/           # Tagged photos (organized by date/folder)
└── gps/                  # GPX track files (organized by date)
```

## Quick Start

### 1. Process New Photos

1. Copy raw photos to `photos/input/`
2. Ensure corresponding GPX files are in `gps/` (organized by date)
3. Run the processing script:
   ```bash
   python scripts/geotag_photos.py
   ```
4. Tagged photos will be in `photos/output/` and `data/index.json` will be updated

### 2. View in Browser

**Option 1: Run server from repo root** (recommended)
```bash
# From repo root
python3 -m http.server 8000

# Then open: http://localhost:8000
# (This will auto-redirect to web/index.html)
```

**Option 2: Run server from web directory**
```bash
# Navigate to web directory
cd web
python3 -m http.server 8000

# Then open: http://localhost:8000
```

**Option 3: Open directly**
Just open `web/index.html` in your browser (some features may not work due to CORS restrictions)

### 3. Delete Noisy Data

If you see interrupted or noisy recordings:

1. Note the folder ID from the viewer (shown in debug panel)
2. Delete it:
   ```bash
   python scripts/delete_photos.py IMG_20251211_120437_707_714_INTERVAL
   ```

## Workflow

### Adding New Photos

```
photos/input/          →  [process_photos.py]  →  photos/output/
gps/2025-12-XX/        →                        →  data/index.json
```

1. **Input**: Drop raw Insta360 photos into `photos/input/`
2. **Process**: Run `scripts/geotag_photos.py`
   - Tags photos with GPS from `gps/` files
   - Moves photos to `photos/output/` (organized by date/folder)
   - Generates/updates `data/index.json`
3. **View**: Open `web/index.html` - photos appear automatically!

### Cleaning Up

Use `scripts/delete_photos.py` to remove:
- Interrupted recordings
- Noisy data
- Test photos

It removes both the files and the index entries.

## Configuration

### Neighborhoods

Edit `data/neighborhoods.json` to define neighborhoods:
- `id`: Unique identifier
- `name` / `nameJa`: Display names
- `date`: Photo date filter
- `bounds`: Geographic bounds (optional)
- `timeRange`: Time window filter (optional)

### Mapbox Token

Update the Mapbox access token in:
- `js/app.js` (line 6)
- `js/viewer.js` (line 6)

Get your token from [mapbox.com](https://account.mapbox.com/access-tokens/)

## Development

### Scripts

See `scripts/README.md` for detailed script documentation.

**Note:** By default, you run `geotag_photos.py` manually when you add new photos. If you want automatic processing (optional), you can set up a file watcher or scheduled task, but this is not required.

## License

See LICENSE file.

