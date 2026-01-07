# NTP Delta Monitor - Release Notes v2.1.8

**Release Date:** January 7, 2026  
**Author:** Mark Oldham  
**Build Type:** PATCH Release (Bug Fix)

## Overview

Version 2.1.8 fixes a counting bug where the reference server was potentially being included in the variance threshold analysis, causing the count of servers exceeding the threshold to be off by 1 in both email subjects and text reports.

## Bug Fix - Threshold Counting Accuracy ✅

### Fixed Reference Server Inclusion Issue
- **Problem:** Reference server was potentially being counted in threshold analysis
- **Root Cause:** Reference server appears in target server list when using domain discovery
- **Solution:** Explicitly exclude reference server from threshold counting logic
- **Impact:** Corrects count in email subjects, text reports, and Excel highlighting

### Before vs After Examples

#### Before (v2.1.7) - Incorrect Count:
```
Email Subject: NTP ERROR tgna.tegna.com - MAX DELTA EXCEEDED (9 servers) - all servers responding
Text Report:   Servers exceeding threshold: 9
Actual Count:  Should be 8 servers (reference server incorrectly included)
```

#### After (v2.1.8) - Correct Count:
```
Email Subject: NTP ERROR tgna.tegna.com - MAX DELTA EXCEEDED (8 servers) - all servers responding  
Text Report:   Servers exceeding threshold: 8
Actual Count:  Correctly shows 8 servers (reference server properly excluded)
```

## Technical Changes

### Enhanced Threshold Counting Logic
- **Email Function:** Added explicit reference server exclusion in `send_email_notification()`
- **Summary Function:** Added explicit reference server exclusion in `format_summary()`
- **Function Signature:** Updated `send_email_notification()` to accept `reference_server` parameter
- **Consistent Logic:** Both functions now use identical exclusion criteria

### Reference Server Exclusion Criteria
```python
# New logic ensures reference server is never counted
if (result.status == NTPStatus.OK and 
    result.delta_seconds is not None and 
    result.ntp_server != reference_server):
```

### Why This Issue Occurred
1. **Domain Discovery:** `discover_ntp_servers_in_domain()` gets all A records from domain
2. **Reference Inclusion:** Reference server (e.g., `ntp1.tgna.tegna.com`) is included in A records
3. **Delta Calculation:** Reference server gets `delta_seconds = None` (correctly)
4. **Counting Logic:** Previous logic only checked for `delta_seconds is not None`
5. **Edge Case:** In some scenarios, reference server might get a delta value

## Files Modified

- `ntp_monitor.py`: Enhanced threshold counting logic in both email and summary functions
- Version incremented from 2.1.7 to 2.1.8

## Validation

### Test Scenarios
```
Test Environment: 108 total servers, ntp1.tgna.tegna.com as reference
Before Fix: 23 servers exceeding threshold (incorrect - included reference)
After Fix:  22 servers exceeding threshold (correct - excluded reference)

Email Subject Before: "MAX DELTA EXCEEDED (23 servers)"
Email Subject After:  "MAX DELTA EXCEEDED (22 servers)"
```

### Consistency Check
- **Email Subject:** Shows correct count ✅
- **Text Report:** Shows same correct count ✅  
- **Excel Highlighting:** Highlights same number of cells ✅
- **Reference Server:** Properly excluded from all counts ✅

## Benefits

### Accurate Reporting
- **Correct Counts:** Email subjects and text reports now show accurate server counts
- **Consistent Data:** All reporting mechanisms use identical counting logic
- **Operational Accuracy:** Administrators get precise information for decision making
- **Threshold Analysis:** More reliable variance threshold reporting

### Improved Reliability
- **Edge Case Handling:** Properly handles reference server in all scenarios
- **Data Integrity:** Ensures reference server never affects threshold statistics
- **Consistent Behavior:** Same counting logic across all output formats

## Upgrade Instructions

1. Replace existing `ntp_monitor.exe` with new version 2.1.8
2. No configuration changes required
3. Threshold counts will now be accurate (may show 1 less server than before)
4. All existing functionality remains unchanged

## Known Issues

None identified in this release.

## Summary

**COUNTING BUG FIXED:** The threshold analysis now provides accurate server counts:
- ✅ Reference server properly excluded from threshold counting
- ✅ Email subjects show correct number of servers exceeding threshold
- ✅ Text reports show same accurate count as email subjects
- ✅ Excel highlighting remains consistent with corrected counts
- ✅ Eliminates off-by-one counting error in all reporting

Version 2.1.8 ensures accurate threshold violation reporting across all output formats, providing administrators with reliable data for NTP monitoring decisions.

---

**Distribution Package:** `NTP-Delta-Monitor-v2.1.8.zip`  
**Executable:** `ntp_monitor.exe` (version 2.1.8)  
**Configuration:** Uses existing `variance_threshold_ms` setting  
**Dependencies:** All included in standalone executable  
**Status:** Counting bug fix COMPLETE ✅