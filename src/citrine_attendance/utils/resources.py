# src/citrine_attendance/utils/resources.py
"""Utility functions for managing application resources."""
import sys
from pathlib import Path

def get_resource_path(relative_path: str) -> Path:
    """
    Get absolute path to resource, works for dev and for PyInstaller.
    Assumes resources are in a 'resources' folder relative to the package root.
    """
    # Get the directory of the current file (this utils module)
    base_path = Path(__file__).parent.parent # Go up two levels to 'citrine_attendance' package root
    resources_path = base_path / "resources" / relative_path
    return resources_path.resolve() # Return absolute path

def get_font_path(font_filename: str) -> Path:
    """Get the path to a font file."""
    return get_resource_path(f"fonts/{font_filename}")

def get_icon_path(icon_filename: str) -> Path:
    """Get the path to an icon file."""
    return get_resource_path(f"icons/{icon_filename}") # Create resources/icons/ folder if needed

# Example usage (if run directly):
# if __name__ == '__main__':
#     print("Font path:", get_font_path("Vazir-Regular.ttf"))
#     print("Icon path:", get_icon_path("app_icon.png"))