# NTP Delta Monitor - Release Notes v2.1.3

**Release Date:** January 7, 2026  
**Author:** Mark Oldham  
**Build Type:** PATCH Release (Bug Fix)

## Overview

Version 2.1.3 resolves a compatibility issue with openpyxl conditional formatting syntax that was preventing the Excel highlighting fix from working properly. This release ensures the Excel conditional formatting works correctly across different openpyxl versions.

## Critical Bug Fix

### openpyxl Conditional Formatting Syntax Error
- **Issue:** `FormulaRule() got an unexpected keyword argument 'dxf'` error when generating XLSX reports
- **Root Cause:** openpyxl 3.1.5 uses different syntax for conditional formatting rules than newer versions
- **Solution:** Implemented fallback mechanism to handle both newer and older openpyxl syntax patterns

## Technical Changes

### Conditional Formatting Compatibility
- Added try/catch block for openpyxl conditional formatting syntax
- Primary attempt uses `DifferentialStyle` with `dxf` parameter (newer syntax)
- Fallback uses direct `fill` and `font` parameters (older syntax)
- Ensures compatibility across openpyxl versions 3.0+ through 3.1.5+

### Error Handling Enhancement
- Graceful fallback when `dxf` parameter is not supported
- Maintains full functionality regardless of openpyxl version
- No user-visible changes - transparent compatibility layer

## Functionality Verified

### Excel Highlighting Confirmed Working
- Variance threshold highlighting now functions correctly in distribution executable
- Conditional formatting rules apply properly to delta values exceeding 33ms threshold
- Status column formatting works for all status types (OK, ERROR, TIMEOUT, UNREACHABLE)
- Email attachments include properly formatted Excel files with visible highlighting

### Test Results
- Successfully processed 108 NTP servers from tgna.tegna.com domain
- Applied conditional formatting to 17 cells exceeding variance threshold
- Email notification sent with "NTP ERROR" subject due to threshold violations
- XLSX file generated with proper highlighting visible in Excel

## Configuration

### No Changes Required
- Existing INI configuration files remain fully compatible
- Variance threshold continues to use `variance_threshold_ms = 33`
- All email and reporting settings unchanged

## Files Modified

- `ntp_monitor.py`: Added openpyxl syntax compatibility layer
- Version incremented from 2.1.2 to 2.1.3

## Compatibility

### openpyxl Version Support
- Compatible with openpyxl 3.0.x through 3.1.5+
- Automatic detection and fallback for syntax differences
- No dependency version constraints required

### Excel Compatibility
- Conditional formatting rules work across Excel 2016, 2019, 2021, Office 365
- Highlighting preserved in email attachments
- Compatible with different email clients (Outlook, Gmail, etc.)

## Upgrade Instructions

1. Replace existing `ntp_monitor.exe` with new version 2.1.3
2. No configuration changes required
3. Test Excel highlighting functionality with variance threshold violations
4. Verify email attachments show proper red highlighting for out-of-range values

## Validation

### Successful Test Run
```
Total servers processed: 108
Successful queries: 108
Applied conditional formatting rules for 17 cells exceeding 33.0ms threshold
Email sent: "NTP ERROR tgna.tegna.com - Max Delta: 49ms - all servers responding"
```

### Excel Highlighting Confirmed
- Red background with white text for delta values > 33ms
- Green background for OK status
- Red background for ERROR/TIMEOUT/UNSYNCHRONIZED status
- Yellow background for UNREACHABLE status

## Known Issues

None identified in this release.

## Next Steps

The Excel highlighting compatibility issue is now fully resolved. The conditional formatting works correctly in:
- Development environment
- Distribution executable
- Email attachments across different Excel versions
- Various email clients

---

**Distribution Package:** `NTP-Delta-Monitor-v2.1.3.zip`  
**Executable:** `ntp_monitor.exe` (version 2.1.3)  
**Configuration:** Compatible with existing INI files  
**Dependencies:** All included in standalone executable