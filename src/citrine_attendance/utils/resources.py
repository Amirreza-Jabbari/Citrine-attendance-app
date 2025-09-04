# src/citrine_attendance/utils/resources.py
import os
from pathlib import Path

def get_resource_path(relative_path: str) -> Path:
    """
    Get the absolute path to a resource file. This function is crucial for
    reliably locating resources (like icons, fonts) regardless of where the
    application is run from.
    """
    # Assumes this file is in src/citrine_attendance/utils.
    # We go up two levels to get to the 'src/citrine_attendance' directory.
    base_path = Path(__file__).resolve().parent.parent
    
    # Join with the 'resources' directory and the specific relative path.
    resource_path = base_path / "resources" / relative_path
    
    if not resource_path.exists():
        # Add a warning if the file doesn't exist to make debugging easier.
        print(f"Warning: Resource not found at path: {resource_path}")

    return resource_path

def get_icon_path(icon_name: str) -> str:
    """
    A convenience function to get the full, absolute path for an icon.
    It now correctly points to the 'icon' (singular) subfolder.
    """
    # CORRECTED: Changed "icons" to "icon" to match your project structure.
    return str(get_resource_path(f"icon/{icon_name}"))

def get_font_path(font_name: str) -> str:
    """
    A convenience function to get the full, absolute path for a font.
    """
    return str(get_resource_path(f"fonts/{font_name}"))

