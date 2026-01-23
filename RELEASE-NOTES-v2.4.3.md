# NTP Delta Monitor - Release Notes v2.4.3

**Release Date:** January 23, 2026  
**Author:** Mark Oldham

## Overview
Version 2.4.3 enhances XLSX report formatting by highlighting the reference server row for improved visibility and report readability.

## New Features

### Reference Server Highlighting in XLSX Reports
- **Reference server row now highlighted in bold blue** throughout the entire row
- Reference server appears in its natural sorted position (not as a separate header)
- Makes it easy to identify which server was used as the time reference
- Applies to all columns in the reference server row

## Technical Details

### XLSX Report Enhancements
- Reference server detection during data writing
- Bold blue font formatting (`color="0000FF"`) applied to all cells in reference server row
- Maintains existing variance highlighting (red background for deltas exceeding threshold)
- Maintains existing status column color coding (green=OK, red=ERROR, yellow=UNREACHABLE)

## Bug Fixes
- Fixed row number calculations in XLSX formatting logic (data rows now correctly start at row 2)
- Corrected verification loop to check proper row range

## Compatibility
- Fully backward compatible with v2.4.2
- No changes to INI configuration format
- No changes to CSV input/output formats
- XLSX reports maintain all existing columns and formatting

## Upgrade Notes
- No configuration changes required
- Existing INI files work without modification
- XLSX reports will automatically include reference server highlighting

## Testing Recommendations
After upgrading to v2.4.3:
1. Run a test query with your configured reference server
2. Open the generated XLSX report
3. Verify the reference server row is highlighted in bold blue
4. Confirm variance highlighting still works for high-delta servers
5. Verify status column colors are correct (green/red/yellow)

## Known Issues
None

## Distribution Files
- `ntp_monitor.exe` - Windows executable (no version in filename)
- `NTP-Delta-Monitor-v2.4.3.zip` - Complete distribution package

---

For questions or issues, contact Mark Oldham.
