#!/usr/bin/env python
"""
Blur faces and license plates in 360 photos.

This script:
- Detects human faces in equirectangular 360° photos
- Detects car license plates
- Applies blur to detected regions
- Preserves EXIF data
- Processes photos from photos/output/ by default
"""

from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageFilter
import subprocess
import json
import sys
from tqdm import tqdm
from typing import List, Tuple, Optional
import argparse

# =============================================================================
# CONFIGURATION
# =============================================================================

# Default input folder (geotagged photos)
PHOTOS_INPUT = Path("photos/output")

# Default output folder (if None, will overwrite originals)
PHOTOS_OUTPUT = Path("photos/blurred")  # Save blurred photos to separate folder

# Blur intensity (higher = more blur)
# Options: 'light' (15), 'medium' (25), 'heavy' (35)
BLUR_INTENSITY = 'medium'

# Minimum face size (as fraction of image width) - helps avoid false positives
MIN_FACE_SIZE = 0.02  # 2% of image width

# Maximum face size (as fraction of image width) - helps avoid false positives
MAX_FACE_SIZE = 0.3  # 30% of image width

# Padding around detected regions (as fraction of region size)
PADDING_FACTOR = 0.3  # 30% padding

# Process only specific date folders (None = process all)
DATE_FILTER = None  # e.g., "2025-12-09"

# Dry run mode (preview without making changes)
DRY_RUN = False

# =============================================================================
# FACE AND LICENSE PLATE DETECTION
# =============================================================================

def load_face_cascade():
    """Load OpenCV face detection cascade."""
    # Try multiple possible paths for the cascade file
    cascade_paths = [
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml',
        cv2.data.haarcascades + 'haarcascade_frontalface_alt.xml',
        '/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml',
    ]
    
    for path in cascade_paths:
        if Path(path).exists():
            return cv2.CascadeClassifier(path)
    
    # If not found, try to load from opencv data
    try:
        return cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    except:
        raise FileNotFoundError(
            "Could not find face detection cascade. "
            "Make sure opencv-python is properly installed."
        )


def detect_faces(image: np.ndarray, face_cascade) -> List[Tuple[int, int, int, int]]:
    """
    Detect faces in image.
    Returns list of (x, y, width, height) bounding boxes.
    """
    # Convert to grayscale for face detection
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Detect faces
    # scaleFactor: how much the image size is reduced at each scale
    # minNeighbors: how many neighbors each candidate rectangle should have
    # minSize: minimum face size
    # maxSize: maximum face size
    height, width = gray.shape
    min_size = (int(width * MIN_FACE_SIZE), int(height * MIN_FACE_SIZE))
    max_size = (int(width * MAX_FACE_SIZE), int(height * MAX_FACE_SIZE))
    
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=min_size,
        maxSize=max_size,
        flags=cv2.CASCADE_SCALE_IMAGE
    )
    
    return faces.tolist() if len(faces) > 0 else []


def detect_license_plates(image: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """
    Detect license plates using color and shape analysis.
    Returns list of (x, y, width, height) bounding boxes.
    
    License plates are typically:
    - Rectangular (aspect ratio ~2:1 to 3:1)
    - Light colored (white, yellow, etc.)
    - Have high contrast edges
    """
    height, width = image.shape[:2]
    plates = []
    
    # Convert to HSV for better color detection
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    
    # Create mask for light colors (white, light gray, yellow)
    # White/light colors have high value (brightness)
    lower_white = np.array([0, 0, 200])
    upper_white = np.array([180, 30, 255])
    mask_white = cv2.inRange(hsv, lower_white, upper_white)
    
    # Also detect yellow plates (common in some countries)
    lower_yellow = np.array([20, 100, 100])
    upper_yellow = np.array([30, 255, 255])
    mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
    
    # Combine masks
    mask = cv2.bitwise_or(mask_white, mask_yellow)
    
    # Apply morphological operations to clean up the mask
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    
    # Convert to grayscale for edge detection
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Filter contours by aspect ratio and size
    min_plate_width = int(width * 0.02)  # At least 2% of image width
    max_plate_width = int(width * 0.15)  # At most 15% of image width
    min_plate_height = int(height * 0.01)  # At least 1% of image height
    max_plate_height = int(height * 0.08)  # At most 8% of image height
    
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        
        # Filter by size
        if (min_plate_width <= w <= max_plate_width and 
            min_plate_height <= h <= max_plate_height):
            
            # Filter by aspect ratio (license plates are typically 2:1 to 4:1)
            aspect_ratio = w / h if h > 0 else 0
            if 1.5 <= aspect_ratio <= 5.0:
                # Check if region has high edge density (license plates have text)
                roi = gray[y:y+h, x:x+w]
                edges = cv2.Canny(roi, 50, 150)
                edge_density = np.sum(edges > 0) / (w * h)
                
                # License plates should have moderate to high edge density
                if edge_density > 0.1:  # At least 10% of pixels are edges
                    plates.append((x, y, w, h))
    
    return plates


def apply_blur_to_regions(
    image: np.ndarray, 
    regions: List[Tuple[int, int, int, int]],
    blur_intensity: str = BLUR_INTENSITY
) -> np.ndarray:
    """
    Apply blur to specified regions in the image.
    
    Args:
        image: Input image as numpy array
        regions: List of (x, y, width, height) bounding boxes
        blur_intensity: 'light', 'medium', or 'heavy'
    
    Returns:
        Image with blurred regions
    """
    if not regions:
        return image
    
    # Convert to PIL for better blur control
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    
    # Determine blur radius based on intensity
    blur_radii = {
        'light': 15,
        'medium': 25,
        'heavy': 35
    }
    radius = blur_radii.get(blur_intensity, 25)
    
    # Create a mask for blurring
    mask = Image.new('L', pil_image.size, 0)
    draw = Image.new('RGB', pil_image.size, (0, 0, 0))
    
    for x, y, w, h in regions:
        # Add padding
        padding_x = int(w * PADDING_FACTOR)
        padding_y = int(h * PADDING_FACTOR)
        
        x1 = max(0, x - padding_x)
        y1 = max(0, y - padding_y)
        x2 = min(pil_image.width, x + w + padding_x)
        y2 = min(pil_image.height, y + h + padding_y)
        
        # Draw white rectangle on mask
        region_mask = Image.new('L', (x2 - x1, y2 - y1), 255)
        mask.paste(region_mask, (x1, y1))
    
    # Apply blur to the entire image
    blurred = pil_image.filter(ImageFilter.GaussianBlur(radius=radius))
    
    # Composite: use blurred version where mask is white, original elsewhere
    result = Image.composite(blurred, pil_image, mask)
    
    # Convert back to OpenCV format
    result_array = cv2.cvtColor(np.array(result), cv2.COLOR_RGB2BGR)
    
    return result_array


def process_photo(
    photo_path: Path,
    face_cascade,
    output_path: Optional[Path],
    blur_intensity: str = BLUR_INTENSITY,
    dry_run: bool = False
) -> Tuple[int, int]:
    """
    Process a single photo: detect faces and license plates, then blur them.
    
    Returns:
        (num_faces, num_plates) detected
    """
    # Read image
    image = cv2.imread(str(photo_path))
    if image is None:
        print(f"  Warning: Could not read {photo_path.name}")
        return (0, 0)
    
    # Detect faces
    faces = detect_faces(image, face_cascade)
    
    # Detect license plates
    plates = detect_license_plates(image)
    
    if not faces and not plates:
        return (0, 0)
    
    if not dry_run:
        # Apply blur
        blurred_image = image.copy()
        if faces:
            blurred_image = apply_blur_to_regions(blurred_image, faces, blur_intensity)
        if plates:
            blurred_image = apply_blur_to_regions(blurred_image, plates, blur_intensity)
        
        # Save blurred image
        target_path = output_path if output_path else photo_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save with OpenCV (will lose EXIF, so we'll restore it)
        cv2.imwrite(str(target_path), blurred_image)
        
        # Restore EXIF data from original
        try:
            subprocess.run(
                ['exiftool', '-overwrite_original', '-tagsFromFile', str(photo_path), str(target_path)],
                capture_output=True,
                check=False
            )
        except Exception as e:
            print(f"  Warning: Could not restore EXIF data: {e}")
    
    return (len(faces), len(plates))


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Blur faces and license plates in 360 photos'
    )
    parser.add_argument(
        '--input',
        type=str,
        default=None,
        help='Input folder (default: photos/output)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output folder (default: overwrite originals)'
    )
    parser.add_argument(
        '--intensity',
        choices=['light', 'medium', 'heavy'],
        default=BLUR_INTENSITY,
        help='Blur intensity (default: medium)'
    )
    parser.add_argument(
        '--date',
        type=str,
        default=None,
        help='Process only specific date folder (e.g., 2025-12-09)'
    )
    parser.add_argument(
        '--folder',
        type=str,
        default=None,
        help='Process only specific photo folder (e.g., IMG_20251209_125427_312_313_INTERVAL)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview without making changes'
    )
    
    args = parser.parse_args()
    
    # Set paths
    input_base = Path(args.input) if args.input else PHOTOS_INPUT
    output_base = Path(args.output) if args.output else PHOTOS_OUTPUT
    date_filter = args.date or DATE_FILTER
    folder_filter = args.folder
    blur_intensity = args.intensity
    dry_run = args.dry_run or DRY_RUN
    
    print("="*60)
    print("Blur Faces and License Plates")
    print("="*60)
    print(f"Input folder:    {input_base.absolute()}")
    print(f"Output folder:   {output_base.absolute() if output_base else '(overwrite originals)'}")
    print(f"Blur intensity:  {blur_intensity}")
    print(f"Date filter:     {date_filter or '(all dates)'}")
    print(f"Folder filter:   {folder_filter or '(all folders)'}")
    print(f"Mode:            {'DRY RUN' if dry_run else 'LIVE'}")
    print("="*60 + "\n")
    
    # Check dependencies
    try:
        face_cascade = load_face_cascade()
        print("✓ Face detection cascade loaded\n")
    except Exception as e:
        print(f"✗ Error loading face detection: {e}\n")
        print("Make sure opencv-python is installed: pip install opencv-python")
        sys.exit(1)
    
    # Check exiftool
    result = subprocess.run(['which', 'exiftool'], capture_output=True, text=True)
    if result.returncode != 0:
        print("⚠️  exiftool not found. EXIF data will not be preserved.\n")
        print("Install with: brew install exiftool\n")
    
    # Find date folders
    if not input_base.exists():
        print(f"✗ Input folder does not exist: {input_base}")
        sys.exit(1)
    
    date_folders = sorted([
        d for d in input_base.iterdir() 
        if d.is_dir() and (not date_filter or d.name == date_filter)
    ])
    
    if not date_folders:
        print("No date folders found")
        sys.exit(0)
    
    print(f"Found {len(date_folders)} date folder(s)\n")
    
    # Scan for photos
    all_photos = []
    for date_folder in date_folders:
        for photo_folder in date_folder.iterdir():
            if photo_folder.is_dir():
                # Apply folder filter if specified
                if folder_filter and photo_folder.name != folder_filter:
                    continue
                
                photos = list(photo_folder.glob("*.jpg")) + list(photo_folder.glob("*.JPG"))
                for photo in photos:
                    output_path = None
                    if output_base:
                        # Mirror the folder structure
                        rel_path = photo.relative_to(input_base)
                        output_path = output_base / rel_path
                    all_photos.append((photo, output_path))
    
    total_photos = len(all_photos)
    if total_photos == 0:
        print("No photos found to process")
        sys.exit(0)
    
    print(f"Total photos to process: {total_photos}\n")
    
    # Process photos
    total_faces = 0
    total_plates = 0
    processed_count = 0
    
    with tqdm(total=total_photos, desc="Processing photos") as pbar:
        for photo_path, output_path in all_photos:
            num_faces, num_plates = process_photo(
                photo_path, face_cascade, output_path, blur_intensity, dry_run
            )
            total_faces += num_faces
            total_plates += num_plates
            if num_faces > 0 or num_plates > 0:
                processed_count += 1
            pbar.update(1)
    
    print("\n" + "="*60)
    print("Processing complete!")
    print("="*60)
    print(f"\nSUMMARY")
    print("="*60)
    print(f"Total photos processed:  {total_photos}")
    print(f"Photos with detections:  {processed_count}")
    print(f"Total faces detected:    {total_faces}")
    print(f"Total license plates:    {total_plates}")
    print("="*60)
    print("\n✓ Done!")


if __name__ == "__main__":
    main()

