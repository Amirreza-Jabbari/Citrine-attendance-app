import jdatetime
import datetime
from typing import Union

# --- Date Conversion Utilities ---
def gregorian_to_jalali(greg_date: Union[datetime.date, datetime.datetime]) -> jdatetime.date:
    """Convert Gregorian date/datetime to Jalali date."""
    if isinstance(greg_date, datetime.datetime):
        greg_date = greg_date.date()
    if not isinstance(greg_date, datetime.date):
         raise TypeError("Input must be a datetime.date or datetime.datetime object")
    return jdatetime.date.fromgregorian(date=greg_date)

def jalali_to_gregorian(jalali_date: jdatetime.date) -> datetime.date:
    """Convert Jalali date to Gregorian date."""
    if not isinstance(jalali_date, jdatetime.date):
         raise TypeError("Input must be a jdatetime.date object")
    return jalali_date.togregorian()

# --- Date Formatting Utilities ---
def format_jalali_date(jalali_date: jdatetime.date, include_time: bool = False, gregorian_dt: datetime.datetime = None) -> str:
    """
    Format a Jalali date for display.
    Example: ۷ خرداد ۱۴۰۳
    If include_time and gregorian_dt provided: ۷ خرداد ۱۴۰۳ — ساعت ۰۹:۰۵
    """
    # Use Persian digits and month names from jdatetime
    day_str = str(jalali_date.day).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
    month_name = jalali_date.j_months[jalali_date.month - 1] # j_months is zero-indexed
    year_str = str(jalali_date.year).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))

    formatted_date = f"{day_str} {month_name} {year_str}"

    if include_time and gregorian_dt:
         time_str = gregorian_dt.strftime("%H:%M").translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))
         formatted_date += f" — ساعت {time_str}"

    return formatted_date

def format_gregorian_date_iso(gregorian_date: Union[datetime.date, datetime.datetime]) -> str:
    """Format Gregorian date as ISO string for tooltips/hover."""
    if isinstance(gregorian_date, datetime.datetime):
        return gregorian_date.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(gregorian_date, datetime.date):
        return gregorian_date.isoformat()
    else:
         raise TypeError("Input must be a datetime.date or datetime.datetime object")

# --- Combined Display Formatting ---
def format_date_for_display(gregorian_date: Union[datetime.date, datetime.datetime],
                            gregorian_dt: datetime.datetime = None, # Needed for time if datetime.date passed for gregorian_date
                            format_preference: str = 'both') -> str:
    """
    Format date for display based on user preference.
    format_preference: 'jalali', 'gregorian', 'both'
    """
    if isinstance(gregorian_date, datetime.datetime):
        greg_date_obj = gregorian_date.date()
        greg_dt_obj = gregorian_date
    elif isinstance(gregorian_date, datetime.date):
        greg_date_obj = gregorian_date
        greg_dt_obj = gregorian_dt if gregorian_dt else datetime.datetime.combine(gregorian_date, datetime.time.min)
    else:
         raise TypeError("Input must be a datetime.date or datetime.datetime object")

    jalali_date_obj = gregorian_to_jalali(greg_date_obj)

    if format_preference == 'jalali':
        return format_jalali_date(jalali_date_obj, include_time=isinstance(gregorian_date, datetime.datetime), gregorian_dt=greg_dt_obj)
    elif format_preference == 'gregorian':
        return format_gregorian_date_iso(gregorian_date)
    elif format_preference == 'both':
        jalali_part = format_jalali_date(jalali_date_obj, include_time=isinstance(gregorian_date, datetime.datetime), gregorian_dt=greg_dt_obj)
        iso_part = format_gregorian_date_iso(gregorian_date)
        return f"{jalali_part} — {iso_part}"
    else: # Default to both
        jalali_part = format_jalali_date(jalali_date_obj, include_time=isinstance(gregorian_date, datetime.datetime), gregorian_dt=greg_dt_obj)
        iso_part = format_gregorian_date_iso(gregorian_date)
        return f"{jalali_part} — {iso_part}"