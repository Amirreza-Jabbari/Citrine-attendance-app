# src/citrine_attendance/services/export_service.py
"""Service for exporting attendance data."""
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any
import datetime

# Import jdatetime for Jalali date handling
import jdatetime

# For Excel export
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

# For PDF export (basic example)
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch

# Import config to get user settings
from ..config import config


class ExportServiceError(Exception):
    """Base exception for export service errors."""
    pass

class ExportService:
    """Handles exporting data to various formats."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def export_to_csv(self, data: List[Dict[str, Any]], filename: Path, delimiter: str = ',') -> Path:
        """Export data to a CSV file."""
        try:
            if not data:
                raise ExportServiceError("No data provided for CSV export.")

            fieldnames = data[0].keys() # Assumes all rows have the same keys

            with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile: # utf-8-sig for Excel
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=delimiter)
                writer.writeheader()
                # Process data for Jalali dates before writing
                processed_data = self._process_data_for_export(data)
                writer.writerows(processed_data)

            self.logger.info(f"Data exported to CSV: {filename}")
            return filename

        except Exception as e:
            self.logger.error(f"Error exporting to CSV: {e}", exc_info=True)
            raise ExportServiceError(f"Failed to export to CSV: {e}") from e

    def export_to_xlsx(self, data: List[Dict[str, Any]], filename: Path) -> Path:
        """Export data to an Excel (XLSX) file with formatting."""
        try:
            if not data:
                raise ExportServiceError("No data provided for XLSX export.")

            wb = Workbook()
            ws = wb.active
            ws.title = "Attendance Report"

            # Headers
            headers = list(data[0].keys())
            ws.append(headers)

            # Data rows
            processed_data = self._process_data_for_export(data)
            for row_dict in processed_data:
                # Maintain column order based on headers
                row_data = [row_dict.get(h, "") for h in headers]
                ws.append(row_data)

            # --- Basic Formatting ---
            header_font = Font(bold=True)
            header_fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
            center_alignment = Alignment(horizontal="center")

            for col_num, column_title in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num)
                cell.font = header_font
                cell.fill = header_fill
                # Try to auto-adjust column width
                column_letter = get_column_letter(col_num)
                # A simple way to set width based on header length
                adjusted_width = len(str(column_title)) + 2
                ws.column_dimensions[column_letter].width = min(adjusted_width, 50) # Cap width

            # Center Time/Duration columns
            time_cols = ["Time In", "Time Out", "Duration (Minutes)"]
            for col_title in time_cols:
                if col_title in headers:
                    col_idx = headers.index(col_title) + 1
                    for row in range(2, ws.max_row + 1): # Data rows
                        ws.cell(row=row, column=col_idx).alignment = center_alignment

            wb.save(filename)
            self.logger.info(f"Data exported to XLSX: {filename}")
            return filename

        except Exception as e:
            self.logger.error(f"Error exporting to XLSX: {e}", exc_info=True)
            raise ExportServiceError(f"Failed to export to XLSX: {e}") from e

    def export_to_pdf(self, data: List[Dict[str, Any]], filename: Path, title: str = "Attendance Report") -> Path:
        """Export data to a PDF file (basic table format)."""
        try:
            if not data:
                raise ExportServiceError("No data provided for PDF export.")

            # Create document
            # Use config for page size or default to A4
            page_size = A4 # or letter, or make configurable
            doc = SimpleDocTemplate(str(filename), pagesize=page_size)
            elements = []
            styles = getSampleStyleSheet()

            # Title
            title_para = Paragraph(title, styles['Title'])
            elements.append(title_para)
            elements.append(Spacer(1, 0.2*inch))

            # Date of report
            date_para = Paragraph(f"Report generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])
            elements.append(date_para)
            elements.append(Spacer(1, 0.2*inch))

            # Table Data
            processed_data = self._process_data_for_export(data)
            if not processed_data:
                 raise ExportServiceError("No processed data available for PDF table.")

            # Prepare table data (list of lists)
            headers = list(processed_data[0].keys())
            table_data = [headers] # First row is headers
            for row_dict in processed_data:
                row_list = [str(row_dict.get(h, "")) for h in headers]
                table_data.append(row_list)

            # Create table
            table = Table(table_data)

            # Style the table
            style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), # Header font
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ])
            table.setStyle(style)

            # Alternate row coloring (optional)
            for i in range(1, len(table_data)): # Start from 1 to skip header
                if i % 2 == 0:
                    bc = colors.lightgrey
                else:
                    bc = colors.whitesmoke
                ts = TableStyle([('BACKGROUND', (0, i), (-1, i), bc)])
                table.setStyle(ts)

            elements.append(table)
            doc.build(elements)

            self.logger.info(f"Data exported to PDF: {filename}")
            return filename

        except Exception as e:
            self.logger.error(f"Error exporting to PDF: {e}", exc_info=True)
            raise ExportServiceError(f"Failed to export to PDF: {e}") from e

    def _process_data_for_export(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process raw data dictionary to format dates, especially adding Jalali representation.
        This modifies the data dictionaries in place for export formats that need it.
        Handles both datetime.date objects and ISO date strings for the 'Date' key.
        """
        processed_data = []
        # Get date format preference from config
        date_format_preference = config.settings.get("date_format", "both")

        # Mapping for Persian digits
        digit_map = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')

        for row in data:
            # Create a copy to avoid modifying the original data passed in
            processed_row = row.copy()
            
            # --- Handle Date Conversion ---
            greg_date_value = row.get("Date")
            greg_date_obj = None

            if greg_date_value:
                try:
                    # Determine the type of the date value and convert to datetime.date if necessary
                    if isinstance(greg_date_value, datetime.date):
                        greg_date_obj = greg_date_value
                    elif isinstance(greg_date_value, str):
                        greg_date_obj = datetime.date.fromisoformat(greg_date_value)
                    else:
                        # If it's neither, log a warning and treat as string
                        self.logger.warning(f"Unexpected type for 'Date' in export data row: {type(greg_date_value)}. Attempting str conversion.")
                        greg_date_obj = datetime.date.fromisoformat(str(greg_date_value))

                    if greg_date_obj:
                        # --- Format Date for Export based on Preference using jdatetime ---
                        if date_format_preference == 'jalali':
                            # Only Jalali
                            jalali_date_obj = jdatetime.date.fromgregorian(date=greg_date_obj)
                            # Format: ۷ خرداد ۱۴۰۳
                            day_persian = ''.join(digit_map.get(d, d) for d in str(jalali_date_obj.day))
                            month_name = jalali_date_obj.j_months[jalali_date_obj.month - 1] # j_months is zero-indexed
                            year_persian = ''.join(digit_map.get(d, d) for d in str(jalali_date_obj.year))
                            jalali_display_str = f"{day_persian} {month_name} {year_persian}"
                            processed_row["Date"] = jalali_display_str
                        
                        elif date_format_preference == 'gregorian':
                            # Only Gregorian ISO
                            processed_row["Date"] = greg_date_obj.isoformat()
                        
                        elif date_format_preference == 'both':
                            # Both Gregorian and Jalali (default/fallback)
                            greg_iso_str = greg_date_obj.isoformat()
                            jalali_date_obj = jdatetime.date.fromgregorian(date=greg_date_obj)
                            # Format: ۷ خرداد ۱۴۰۳
                            day_persian = ''.join(digit_map.get(d, d) for d in str(jalali_date_obj.day))
                            month_name = jalali_date_obj.j_months[jalali_date_obj.month - 1]
                            year_persian = ''.join(digit_map.get(d, d) for d in str(jalali_date_obj.year))
                            jalali_display_str = f"{day_persian} {month_name} {year_persian}"
                            processed_row["Date"] = f"{jalali_display_str} — {greg_iso_str}"
                        
                        else:
                            # Default to 'both' if setting is unrecognized
                            greg_iso_str = greg_date_obj.isoformat()
                            jalali_date_obj = jdatetime.date.fromgregorian(date=greg_date_obj)
                            # Format: ۷ خرداد ۱۴۰۳
                            day_persian = ''.join(digit_map.get(d, d) for d in str(jalali_date_obj.day))
                            month_name = jalali_date_obj.j_months[jalali_date_obj.month - 1]
                            year_persian = ''.join(digit_map.get(d, d) for d in str(jalali_date_obj.year))
                            jalali_display_str = f"{day_persian} {month_name} {year_persian}"
                            processed_row["Date"] = f"{jalali_display_str} — {greg_iso_str}"

                    # --- Ensure Time fields are formatted correctly ---
                    # Excel/PDF writers usually handle time objects, but converting to string
                    # ensures consistency, especially for CSV.
                    time_in_val = processed_row.get("Time In")
                    if isinstance(time_in_val, datetime.time):
                        processed_row["Time In"] = time_in_val.strftime("%H:%M")

                    time_out_val = processed_row.get("Time Out")
                    if isinstance(time_out_val, datetime.time):
                        processed_row["Time Out"] = time_out_val.strftime("%H:%M")

                except (ValueError, TypeError) as e:
                    # If date processing fails, log error and leave the original value
                    self.logger.error(f"Error processing date '{greg_date_value}' for export: {e}")
                    # Keep the original value in the row (it's already copied)
            # If no 'Date' key or value is None/empty, it's copied as is.
            
            processed_data.append(processed_row)
        return processed_data


# Global instance
export_service = ExportService()