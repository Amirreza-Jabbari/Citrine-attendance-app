# src/citrine_attendance/utils/time_utils.py
"""
Utility functions for time and duration conversions.
"""

def minutes_to_hhmm(minutes: int) -> str:
    """
    HEROIC FIX: Converts a total number of minutes into a more readable 'Xh Ym' format.
    For example, 75 minutes will be converted to "1h 15m".
    """
    if minutes is None or minutes < 0:
        return "0h 0m"
    hours, remainder = divmod(minutes, 60)
    return f"{int(hours)}h {int(remainder)}m"