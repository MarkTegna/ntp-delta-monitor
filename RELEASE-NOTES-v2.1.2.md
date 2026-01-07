# NTP Delta Monitor - Release Notes v2.1.2

**Release Date:** January 7, 2026  
**Author:** Mark Oldham  
**Build Type:** PATCH Release (Bug Fix)

## Overview

Version 2.1.2 addresses a critical compatibility issue with Excel highlighting in email attachments and distribution executables. This release replaces direct cell formatting with Excel's built-in conditional formatting rules for maximum compatibility across different Excel versions and email clients.

## Critical Bug Fix

### Excel Highlighting Compatibility Issue
- **Issue:** Red highlighting for variance threshold violations was not visible in Excel files when sent as email attachments or when using the distribution executable
- **Root Cause:** Direct cell formatting (PatternFill/Font) was not preserved when Excel files were transmitted via email or opened in different Excel environments
- **Solution:** Implemented Excel conditional formatting rules using FormulaRule and DifferentialStyle for robust cross-platform compatibility

## Technical Changes

### Excel Report Generation
- Replaced direct cell formatting with Excel conditional formatting rules
- Added `openpyxl.formatting.rule.FormulaRule` for variance threshold highlighting
- Added `openpyxl.styles.differential.DifferentialStyle` for consistent formatting
- Enhanced PyInstaller spec with additional openpyxl conditional formatting dependencies

### Conditional Formatting Rules
- **Status Column:** Green for OK, Red for ERROR/TIMEOUT/UNSYNCHRONIZED, Yellow for UNREACHABLE
- **Delta Value Column:** Bright red background with white text for values exceeding variance threshold
- **Formula-Based:** Uses `ABS(cell_value) > threshold` formula for dynamic highlighting

### Dependencies Updated
- Added `openpyxl.styles.differential` to hidden imports
- Added `openpyxl.utils.cell` to hidden imports  
- Added `openpyxl.formatting.formatting` to hidden imports
- Added `get_column_letter` import for column reference calculations

## Compatibility Improvements

### Email Attachment Compatibility
- Conditional formatting rules are preserved when Excel files are sent as email attachments
- Highlighting now visible in Outlook, Gmail, and other email clients
- Compatible with Excel 2016, 2019, 2021, and Office 365

### Distribution Executable
- All Excel formatting functionality now works identically in distribution executable
- No difference between development and production highlighting behavior
- Comprehensive openpyxl module inclusion in PyInstaller build

## Configuration

### Variance Threshold
- Continues to use `variance_threshold_ms = 33` from INI configuration
- Threshold applies to absolute delta values for highlighting determination
- Email subject changes from "REPORT" to "ERROR" when threshold exceeded

## Files Modified

- `ntp_monitor.py`: Replaced direct cell formatting with conditional formatting rules
- `ntp_monitor.spec`: Added conditional formatting dependencies to hidden imports
- Version incremented from 2.1.1 to 2.1.2

## Testing Verification

### Functionality Confirmed
- Conditional formatting rules apply correctly to variance threshold violations
- Status column formatting works for all status types (OK, ERROR, TIMEOUT, etc.)
- Email notifications include properly formatted Excel attachments
- Distribution executable generates identical formatting to development version

### Compatibility Tested
- Excel files open correctly with visible highlighting in email attachments
- Conditional formatting persists across different Excel versions
- No regression in existing functionality (email, statistics, reporting)

## Upgrade Instructions

1. Replace existing `ntp_monitor.exe` with new version 2.1.2
2. No configuration changes required - existing INI files remain compatible
3. Test Excel highlighting by running with variance threshold violations
4. Verify email attachments show red highlighting for out-of-range values

## Known Issues

None identified in this release.

## Next Steps

This release resolves the Excel highlighting compatibility issue. Future enhancements may include:
- Additional conditional formatting options
- Customizable highlighting colors via INI configuration
- Enhanced Excel report formatting features

---

**Distribution Package:** `NTP-Delta-Monitor-v2.1.2.zip`  
**Executable:** `ntp_monitor.exe` (version 2.1.2)  
**Configuration:** Compatible with existing INI files  
**Dependencies:** All included in standalone executable