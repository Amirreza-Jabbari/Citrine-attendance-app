# src/citrine_attendance/services/export_service.py
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any
import datetime
import jdatetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from ..config import config
from ..utils.time_utils import minutes_to_hhmm # <-- Import the utility


class ExportServiceError(Exception):
    pass

class ExportService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _process_data_for_export(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process data for export, formatting dates and converting all minute fields to HH:MM.
        """
        processed_data = []
        date_format_pref = config.settings.get("date_format", "both")

        for row in data:
            processed_row = row.copy()
            
            # Format Date
            greg_date = processed_row.get("Date")
            if isinstance(greg_date, datetime.date):
                if date_format_pref == 'jalali':
                    processed_row["Date"] = jdatetime.date.fromgregorian(date=greg_date).strftime("%Y/%m/%d")
                elif date_format_pref == 'gregorian':
                    processed_row["Date"] = greg_date.isoformat()
                else: # both
                    j_date_str = jdatetime.date.fromgregorian(date=greg_date).strftime("%Y/%m/%d")
                    g_date_str = greg_date.isoformat()
                    processed_row["Date"] = f"{j_date_str} | {g_date_str}"
            
            # Format Times (e.g., Time In, Time Out)
            for key in ["Time In", "Time Out"]:
                time_val = processed_row.get(key)
                if isinstance(time_val, datetime.time):
                    processed_row[key] = time_val.strftime("%H:%M")

            # --- Convert all minute fields to HH:MM strings and update headers ---
            minute_keys = [
                "Tardiness (min)", "Main Work (min)", "Overtime (min)", 
                "Launch Time (min)", "Total Duration (min)", "Leave (min)"
            ]
            for key in minute_keys:
                if key in processed_row:
                    new_key = key.replace("(min)", "(H:M)").strip()  # Create new header name like "Tardiness (H:M)"
                    # Pop the old key and value, and add the new key with the formatted value
                    processed_row[new_key] = minutes_to_hhmm(processed_row.pop(key))
            
            processed_data.append(processed_row)
        return processed_data

    def export_to_csv(self, data: List[Dict[str, Any]], filename: Path, delimiter: str = ',') -> Path:
        """Export data to a CSV file."""
        try:
            if not data:
                raise ExportServiceError("No data provided for CSV export.")
            
            processed_data = self._process_data_for_export(data)
            if not processed_data:
                raise ExportServiceError("No data available after processing.")

            fieldnames = processed_data[0].keys()
            
            with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=delimiter)
                writer.writeheader()
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
            
            processed_data = self._process_data_for_export(data)
            if not processed_data:
                raise ExportServiceError("No data available after processing.")

            wb = Workbook()
            ws = wb.active
            ws.title = "Attendance Report"

            headers = list(processed_data[0].keys())
            ws.append(headers)
            
            for row_dict in processed_data:
                row_data = [row_dict.get(h, "") for h in headers]
                ws.append(row_data)

            # Formatting
            header_font = Font(bold=True)
            center_alignment = Alignment(horizontal="center", vertical="center")
            for col_num, column_title in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num)
                cell.font = header_font
                
                max_length = len(str(column_title))
                for row_idx in range(2, ws.max_row + 1):
                    cell_value = ws.cell(row=row_idx, column=col_num).value
                    if cell_value is not None:
                        max_length = max(max_length, len(str(cell_value)))
                adjusted_width = max_length + 4 # Add a bit more padding
                ws.column_dimensions[get_column_letter(col_num)].width = min(adjusted_width, 40)
                
                # Center columns with time data
                if "(h:m)" in column_title.lower() or "time" in column_title.lower():
                    for row in range(1, ws.max_row + 1): # Include header
                        ws.cell(row=row, column=col_num).alignment = center_alignment

            wb.save(filename)
            self.logger.info(f"Data exported to XLSX: {filename}")
            return filename
        except Exception as e:
            self.logger.error(f"Error exporting to XLSX: {e}", exc_info=True)
            raise ExportServiceError(f"Failed to export to XLSX: {e}") from e

    def export_to_pdf(self, data: List[Dict[str, Any]], filename: Path, title: str = "Attendance Report") -> Path:
        """Export data to a PDF file."""
        try:
            if not data:
                raise ExportServiceError("No data provided for PDF export.")

            doc = SimpleDocTemplate(str(filename), pagesize=landscape(A4))
            elements = []
            styles = getSampleStyleSheet()
            
            elements.append(Paragraph(title, styles['Title']))
            elements.append(Spacer(1, 0.2*inch))
            
            processed_data = self._process_data_for_export(data)
            if not processed_data:
                raise ExportServiceError("No data available after processing.")
                
            headers = list(processed_data[0].keys())
            table_data = [headers] + [[str(row.get(h, "")) for h in headers] for row in processed_data]
            
            table = Table(table_data, repeatRows=1)
            style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ])
            table.setStyle(style)

            for i, row in enumerate(table_data[1:], start=1):
                if i % 2 == 0:
                    table.setStyle(TableStyle([('BACKGROUND', (0, i), (-1, i), colors.lightgrey)]))
            
            elements.append(table)
            doc.build(elements)

            self.logger.info(f"Data exported to PDF: {filename}")
            return filename
        except Exception as e:
            self.logger.error(f"Error exporting to PDF: {e}", exc_info=True)
            raise ExportServiceError(f"Failed to export to PDF: {e}") from e

# Global instance
export_service = ExportService()