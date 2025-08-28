# src/citrine_attendance/utils/time_utils.py
"""Utility functions for time formatting."""
from typing import Optional

def minutes_to_hhmm(minutes: Optional[int]) -> str:
    """
    Converts a total number of minutes into a formatted string "HH:MM".
    
    Args:
        minutes (int, optional): The total minutes. Can be None.
        
    Returns:
        str: The formatted time string (e.g., "01:30") or an empty string if input is None or invalid.
    """
    if minutes is None or minutes < 0:
        return ""
    
    try:
        hours, remainder_minutes = divmod(int(minutes), 60)
        return f"{hours:02d}:{remainder_minutes:02d}"
    except (ValueError, TypeError):
        return ""