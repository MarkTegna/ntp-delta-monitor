# NTP Delta Monitor - Release Notes v2.1.9

**Release Date:** January 7, 2026  
**Author:** Mark Oldham  
**Build Type:** PATCH Release (Bug Fix)

## Overview

Version 2.1.9 fixes a precision inconsistency between the threshold counting logic and Excel highlighting logic. The counting was using decimal precision while Excel highlighting used integer rounding, causing discrepancies where servers with values like 33.4ms would be counted but not highlighted.

## Bug Fix - Precision Consistency ✅

### Fixed Rounding Inconsistency Issue
- **Problem:** Counting logic used decimal precision, Excel highlighting used integer rounding
- **Root Cause:** Different precision handling between `abs(delta_seconds * 1000)` and `int(round(delta_seconds * 1000))`
- **Solution:** Standardized both counting and highlighting to use identical integer rounding logic
- **Impact:** Ensures perfect consistency between counts and visual highlighting

### Before vs After Examples

#### Before (v2.1.8) - Inconsistent Precision:
```
Server with 33.4ms delta:
- Counting Logic:    33.4 > 33 = TRUE  (counted)
- Excel Highlighting: int(round(33.4)) = 33 > 33 = FALSE (not highlighted)
- Result: Count shows 9 servers, Excel highlights 8 cells
```

#### After (v2.1.9) - Consistent Precision:
```
Server with 33.4ms delta:
- Counting Logic:    int(round(33.4)) = 33 > 33 = FALSE (not counted)
- Excel Highlighting: int(round(33.4)) = 33 > 33 = FALSE (not highlighted)  
- Result: Count shows 8 servers, Excel highlights 8 cells (consistent)
```

## Technical Changes

### Standardized Rounding Logic
- **Email Function:** Updated counting to use `int(round(abs(result.delta_seconds) * 1000))`
- **Summary Function:** Updated counting to use same integer rounding as Excel
- **Consistency:** Both functions now match Excel highlighting precision exactly
- **Logic Alignment:** All threshold comparisons use identical rounding methodology

### Precision Handling Details
```python
# Old logic (inconsistent)
delta_ms = abs(result.delta_seconds * 1000)  # Decimal precision

# New logic (consistent with Excel)
delta_ms = int(round(abs(result.delta_seconds) * 1000))  # Integer rounding like Excel
```

### Why This Issue Occurred
1. **Excel Formatting:** `format_delta_value()` uses `int(round(delta_seconds * 1000))` for milliseconds
2. **Excel Highlighting:** Uses `delta_cell.value` which contains the rounded integer value
3. **Counting Logic:** Was using `abs(result.delta_seconds * 1000)` with decimal precision
4. **Edge Cases:** Values like 33.4ms, 33.5ms caused counting/highlighting mismatches

## Files Modified

- `ntp_monitor.py`: Standardized rounding logic in both `send_email_notification()` and `format_summary()` functions
- Version incremented from 2.1.8 to 2.1.9

## Validation

### Test Scenarios
```
Test with 33ms threshold:
Server A: 32.6ms -> int(round(32.6)) = 33ms -> 33 > 33 = FALSE (not counted/highlighted)
Server B: 33.4ms -> int(round(33.4)) = 33ms -> 33 > 33 = FALSE (not counted/highlighted)  
Server C: 33.5ms -> int(round(33.5)) = 34ms -> 34 > 33 = TRUE (counted and highlighted)
Server D: 34.2ms -> int(round(34.2)) = 34ms -> 34 > 33 = TRUE (counted and highlighted)
```

### Consistency Verification
- **Email Subject:** Shows exact count matching Excel highlighting ✅
- **Text Report:** Shows same count as email subject ✅  
- **Excel Highlighting:** Highlights exact same number of cells as count ✅
- **Rounding Logic:** All use identical `int(round())` methodology ✅

## Benefits

### Perfect Consistency
- **Accurate Reporting:** Email subjects and text reports match Excel highlighting exactly
- **Predictable Behavior:** All threshold comparisons use identical rounding rules
- **Operational Clarity:** No confusion between different reporting mechanisms
- **Data Integrity:** Consistent precision across all output formats

### Improved Reliability
- **Edge Case Handling:** Properly handles values at threshold boundaries
- **Rounding Standards:** Uses standard mathematical rounding (0.5 rounds up)
- **Visual Alignment:** What you see highlighted matches what you count
- **Consistent Logic:** Same precision rules applied everywhere

## Upgrade Instructions

1. Replace existing `ntp_monitor.exe` with new version 2.1.9
2. No configuration changes required
3. Counts will now perfectly match Excel highlighting (may show slight differences from v2.1.8)
4. All existing functionality remains unchanged

## Known Issues

None identified in this release.

## Summary

**PRECISION BUG FIXED:** The threshold analysis now provides perfectly consistent counts and highlighting:
- ✅ Counting logic uses same integer rounding as Excel formatting
- ✅ Email subjects show exact count matching highlighted cells
- ✅ Text reports show same precise count as visual highlighting
- ✅ All threshold comparisons use identical mathematical rounding
- ✅ Eliminates precision-based discrepancies between reporting methods

Version 2.1.9 ensures perfect alignment between what administrators see highlighted in Excel and what they see counted in email subjects and text reports.

---

**Distribution Package:** `NTP-Delta-Monitor-v2.1.9.zip`  
**Executable:** `ntp_monitor.exe` (version 2.1.9)  
**Configuration:** Uses existing `variance_threshold_ms` setting  
**Dependencies:** All included in standalone executable  
**Status:** Precision consistency fix COMPLETE ✅