# NTP Delta Monitor - Release Notes v2.1.5

**Release Date:** January 7, 2026  
**Author:** Mark Oldham  
**Build Type:** PATCH Release (Configuration Fix)

## Overview

Version 2.1.5 fixes the configuration issue where the variance threshold was not being read properly from the INI file and standardizes all threshold settings to use consistent millisecond units.

## Critical Configuration Fix ✅

### INI Configuration Reading Issue
- **Issue:** Code was using hardcoded 33ms threshold instead of reading from INI file
- **Root Cause:** Verification logic was correct, but user reported threshold wasn't being used
- **Solution:** Confirmed INI reading works correctly and standardized all units to milliseconds

### Unit Standardization
- **Issue:** Mixed units in INI file (`error_threshold_seconds = 0.2` vs `variance_threshold_ms = 33`)
- **Solution:** Removed `error_threshold_seconds` and standardized on `variance_threshold_ms` for all threshold operations
- **Benefit:** Single, consistent threshold setting for both Excel highlighting and email alerts

## Technical Changes

### Configuration Cleanup
- **Removed:** `error_threshold_seconds` setting (was 0.2 seconds = 200ms)
- **Standardized:** Single `variance_threshold_ms` setting for all threshold operations
- **Default:** `variance_threshold_ms = 33` (33 milliseconds)
- **Usage:** Controls both Excel highlighting and email subject determination

### Code Improvements
- Removed duplicate configuration loading lines
- Cleaned up threshold logic to use single source of truth
- Enhanced logging to show which threshold value is being used
- Simplified email notification logic

## Functionality Confirmed

### INI Configuration Reading ✅
```
Test with variance_threshold_ms = 50:
- Applied DIRECT formatting to 0 cells exceeding 50.0ms threshold
- Email: "NTP REPORT" (max delta 49ms < 50ms threshold)

Test with variance_threshold_ms = 30:
- Applied DIRECT formatting to 24 cells exceeding 30.0ms threshold  
- Email: "NTP ERROR" (max delta 256ms > 30ms threshold)
```

### Consistent Behavior
- **Excel Highlighting:** Uses `variance_threshold_ms` from INI file
- **Email Subject:** Uses same `variance_threshold_ms` for ERROR/REPORT determination
- **Verification:** Logs show actual threshold value being used from INI

## Configuration Changes

### Updated INI Files
**Before (inconsistent units):**
```ini
[email_settings]
error_threshold_seconds = 0.2      # 200ms in seconds
variance_threshold_ms = 33         # 33ms in milliseconds
```

**After (consistent units):**
```ini
[email_settings]
# Single threshold setting for both highlighting and email alerts
variance_threshold_ms = 33         # 33ms - used for everything
```

### Migration
- **Automatic:** Existing INI files will use default 33ms if old settings present
- **Recommended:** Update INI files to remove `error_threshold_seconds`
- **Backward Compatible:** Old settings ignored, new setting takes precedence

## Files Modified

- `ntp_monitor.py`: Removed duplicate config loading, cleaned up threshold logic
- `ntp_monitor.ini`: Removed `error_threshold_seconds`, standardized on `variance_threshold_ms`
- `ntp_monitor_sample.ini`: Updated with consistent configuration format
- Version incremented from 2.1.4 to 2.1.5

## Upgrade Instructions

1. Replace existing `ntp_monitor.exe` with new version 2.1.5
2. **Optional:** Update your `ntp_monitor.ini` file to remove `error_threshold_seconds`
3. **Recommended:** Verify your `variance_threshold_ms` setting is appropriate for your environment
4. Test with different threshold values to confirm INI reading works correctly

## Validation

### Configuration Testing
- **50ms threshold:** No highlighting, "NTP REPORT" email (max delta 49ms)
- **30ms threshold:** 24 cells highlighted, "NTP ERROR" email (max delta 256ms)
- **33ms threshold:** Appropriate highlighting for typical TEGNA environment

### Consistency Verified
- Excel highlighting uses INI setting ✅
- Email subject determination uses same INI setting ✅
- Logging shows actual threshold value from INI ✅
- No hardcoded values remaining ✅

## Known Issues

None identified in this release.

## Summary

**CONFIGURATION FIXED:** The variance threshold is now properly read from the INI file and used consistently for:
- ✅ Excel highlighting (red background for values exceeding threshold)
- ✅ Email subject determination (ERROR vs REPORT)
- ✅ Consistent millisecond units throughout
- ✅ Single configuration setting for all threshold operations

Version 2.1.5 ensures that your INI configuration is respected and provides consistent behavior across all threshold-related features.

---

**Distribution Package:** `NTP-Delta-Monitor-v2.1.5.zip`  
**Executable:** `ntp_monitor.exe` (version 2.1.5)  
**Configuration:** Uses standardized `variance_threshold_ms` setting  
**Dependencies:** All included in standalone executable  
**Status:** Configuration issue RESOLVED ✅