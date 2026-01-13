#!/usr/bin/env python3
"""
Delete noisy/interrupted photo data:
- Removes photos from photos/output/
- Removes entries from data/index.json
- Updates folder counts in index.json
"""

import json
import sys
from pathlib import Path
from datetime import datetime

def load_index(index_file):
    """Load index.json"""
    if not index_file.exists():
        print(f"Error: {index_file} not found")
        sys.exit(1)
    
    with open(index_file, 'r') as f:
        return json.load(f)

def save_index(index_file, data):
    """Save index.json with updated timestamp"""
    data['generated'] = datetime.now().isoformat()
    with open(index_file, 'w') as f:
        json.dump(data, f, indent=2)

def delete_photos_by_ids(index_file, photo_ids, delete_files=True):
    """
    Delete photos by their IDs (folder names or specific photo paths)
    
    Args:
        index_file: Path to index.json
        photo_ids: List of folder names (e.g., "IMG_20251211_120437_707_714_INTERVAL")
                   or specific photo paths
        delete_files: If True, also delete photo files from disk
    """
    repo_root = Path(index_file).parent.parent
    output_dir = repo_root / "photos" / "output"
    
    data = load_index(index_file)
    
    # Track what we're deleting
    deleted_folders = set()
    deleted_photos = []
    
    # Filter photos - remove matching entries
    original_count = len(data['photos'])
    data['photos'] = [
        photo for photo in data['photos']
        if not any(
            photo.get('folder') == folder_id or 
            photo.get('path', '').endswith(folder_id) or
            folder_id in photo.get('path', '')
            for folder_id in photo_ids
        )
    ]
    
    deleted_count = original_count - len(data['photos'])
    
    # Update folder entries
    folders_to_remove = []
    for folder in data['folders']:
        folder_name = folder['name']
        
        # Count remaining photos for this folder
        remaining_photos = [
            p for p in data['photos']
            if p.get('folder') == folder_name
        ]
        
        if folder_name in photo_ids or len(remaining_photos) == 0:
            folders_to_remove.append(folder_name)
            deleted_folders.add(folder_name)
        else:
            # Update counts
            folder['total'] = len(remaining_photos)
            folder['matched'] = len([p for p in remaining_photos if p.get('lat') and p.get('lon')])
    
    # Remove empty folders
    data['folders'] = [f for f in data['folders'] if f['name'] not in folders_to_remove]
    
    # Update totals
    data['total_photos'] = len(data['photos'])
    data['total_matched'] = len([p for p in data['photos'] if p.get('lat') and p.get('lon')])
    
    # Delete files from disk if requested
    if delete_files:
        for folder_name in deleted_folders:
            folder_path = output_dir / folder_name
            if folder_path.exists():
                import shutil
                shutil.rmtree(folder_path)
                print(f"  Deleted folder: {folder_path}")
    
    # Save updated index
    save_index(index_file, data)
    
    print(f"\n✓ Deleted {deleted_count} photo entries")
    print(f"✓ Removed {len(folders_to_remove)} folder entries")
    if delete_files:
        print(f"✓ Deleted {len(deleted_folders)} photo folders from disk")
    print(f"✓ Updated {index_file}")

def delete_photos_by_paths(index_file, photo_paths, delete_files=True):
    """
    Delete specific photos by their paths
    
    Args:
        index_file: Path to index.json
        photo_paths: List of photo paths (e.g., "2025-12-11/IMG_.../IMG_20251211_120437_00_707.jpg")
        delete_files: If True, also delete photo files from disk
    """
    repo_root = Path(index_file).parent.parent
    output_dir = repo_root / "photos" / "output"
    
    data = load_index(index_file)
    
    # Normalize paths (remove 'photos/' prefix if present)
    normalized_paths = {
        p.replace('photos/', '').replace('output/', '') if 'photos/' in p or 'output/' in p else p
        for p in photo_paths
    }
    
    # Filter photos
    original_count = len(data['photos'])
    deleted_photos = [
        photo for photo in data['photos']
        if photo.get('path') in normalized_paths
    ]
    
    data['photos'] = [
        photo for photo in data['photos']
        if photo.get('path') not in normalized_paths
    ]
    
    deleted_count = original_count - len(data['photos'])
    
    # Update folder counts
    folder_counts = {}
    for photo in data['photos']:
        folder = photo.get('folder')
        if folder:
            if folder not in folder_counts:
                folder_counts[folder] = {'total': 0, 'matched': 0}
            folder_counts[folder]['total'] += 1
            if photo.get('lat') and photo.get('lon'):
                folder_counts[folder]['matched'] += 1
    
    # Update folder entries
    for folder in data['folders']:
        if folder['name'] in folder_counts:
            folder['total'] = folder_counts[folder['name']]['total']
            folder['matched'] = folder_counts[folder['name']]['matched']
        else:
            # Folder is now empty, but we'll keep it (or remove if you prefer)
            pass
    
    # Delete files from disk if requested
    if delete_files:
        for photo_path in normalized_paths:
            full_path = output_dir / photo_path
            if full_path.exists():
                full_path.unlink()
                print(f"  Deleted: {full_path}")
    
    # Update totals
    data['total_photos'] = len(data['photos'])
    data['total_matched'] = len([p for p in data['photos'] if p.get('lat') and p.get('lon')])
    
    # Save updated index
    save_index(index_file, data)
    
    print(f"\n✓ Deleted {deleted_count} photo entries")
    if delete_files:
        print(f"✓ Deleted {deleted_count} photo files from disk")
    print(f"✓ Updated {index_file}")

def main():
    """Interactive deletion tool"""
    repo_root = Path(__file__).parent.parent
    index_file = repo_root / "data" / "index.json"
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/delete_photos.py <folder_id1> [folder_id2] ...")
        print("  python scripts/delete_photos.py --paths <photo_path1> [photo_path2] ...")
        print("\nExamples:")
        print("  python scripts/delete_photos.py IMG_20251211_120437_707_714_INTERVAL")
        print("  python scripts/delete_photos.py --paths '2025-12-11/IMG_.../IMG_20251211_120437_00_707.jpg'")
        sys.exit(1)
    
    if sys.argv[1] == '--paths':
        photo_paths = sys.argv[2:]
        delete_photos_by_paths(index_file, photo_paths, delete_files=True)
    else:
        folder_ids = sys.argv[1:]
        delete_photos_by_ids(index_file, folder_ids, delete_files=True)

if __name__ == "__main__":
    main()

