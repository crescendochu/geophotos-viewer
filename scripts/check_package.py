#!/usr/bin/env python3
"""
Quick script to check if a package is installed in the current Python environment.

Usage:
    python scripts/check_package.py <package_name>
    
Example:
    python scripts/check_package.py gpxpy
"""

import sys

if len(sys.argv) < 2:
    print("Usage: python scripts/check_package.py <package_name>")
    sys.exit(1)

package_name = sys.argv[1]

try:
    module = __import__(package_name)
    version = getattr(module, '__version__', 'unknown version')
    print(f"✓ {package_name} is installed (version: {version})")
    print(f"  Location: {module.__file__}")
    sys.exit(0)
except ImportError:
    print(f"✗ {package_name} is NOT installed")
    print(f"  Install with: pip install {package_name}")
    sys.exit(1)

