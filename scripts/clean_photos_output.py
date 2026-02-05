#!/usr/bin/env python3
"""
Clean photos/output: remove .backup files and any files/folders not used by the web app.
Used = paths listed in data/index.json under photos[].path.

Usage:
    python scripts/clean_photos_output.py           # dry run
    python scripts/clean_photos_output.py --execute # actually delete
"""

import json
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "photos" / "output"
INDEX_PATH = REPO_ROOT / "data" / "index.json"


def main():
    ap = argparse.ArgumentParser(description="Clean photos/output: remove .backup and unused files.")
    ap.add_argument("--execute", action="store_true", help="Actually delete files (default is dry run)")
    args = ap.parse_args()
    dry_run = not args.execute

    with open(INDEX_PATH) as f:
        data = json.load(f)
    used_paths = {p["path"] for p in data["photos"]}

    to_delete_backup = []
    to_delete_unused = []
    for f in OUTPUT_DIR.rglob("*"):
        if not f.is_file():
            continue
        rel = str(f.relative_to(OUTPUT_DIR)).replace("\\", "/")
        if rel.endswith(".backup"):
            to_delete_backup.append(f)
        elif rel not in used_paths:
            to_delete_unused.append(f)

    print(f"Found {len(to_delete_backup)} .backup files and {len(to_delete_unused)} unused files.")
    if dry_run:
        print("DRY RUN — no files deleted. Use --execute to delete.")
    else:
        for p in to_delete_backup + to_delete_unused:
            p.unlink()
            print("Deleted:", p.relative_to(REPO_ROOT))
        # Remove empty directories (bottom-up)
        for d in sorted(OUTPUT_DIR.rglob("*"), key=lambda x: -len(x.parts)):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                print("Removed empty dir:", d.relative_to(REPO_ROOT))
    print("Done.")


if __name__ == "__main__":
    main()
