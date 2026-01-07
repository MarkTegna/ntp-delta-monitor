# NTP Delta Monitor v2.1.0 Release Notes

**Release Date**: January 7, 2026  
**Build**: Windows x64 Standalone Executable  
**File Size**: ~10.4 MB  

## 🚨 New Variance Checking Features

### 1. Configurable Variance Threshold
- **Default Threshold**: 33ms variance detection
- **INI Configuration**: `variance_threshold_ms = 33` (customizable)
- **Automatic Detection**: Servers exceeding threshold trigger alerts
- **Real-time Testing**: Tested against live TEGNA servers

### 2. Enhanced Email Alerting
- **Subject Change**: "NTP REPORT" → "NTP ERROR" when variance exceeded
- **Intelligent Detection**: Based on absolute delta values vs threshold
- **Example**: `NTP ERROR tgna.tegna.com - Max Delta: 69ms - all servers responding`
- **Threshold-based**: Uses milliseconds for precise control

### 3. Excel Report Highlighting
- **Red Highlighting**: Cells exceeding variance threshold highlighted in bright red
- **White Text**: Bold white text on red background for visibility
- **Visual Priority**: Immediate identification of problematic servers
- **Automatic**: No manual configuration required

## 📊 Test Results (33ms Threshold)

**Live Test Results**:
- **Servers Tested**: 108 TEGNA NTP servers
- **Maximum Delta**: 69ms (exceeded 33ms threshold)
- **Email Subject**: Changed to "NTP ERROR" ✅
- **Excel Highlighting**: Values >33ms highlighted in red ✅
- **Sorting**: Error servers prioritized at top ✅

**Variance Distribution**:
```
Row 2: Delta = -69ms  (HIGHLIGHTED - exceeds 33ms)
Row 3: Delta = -62ms  (HIGHLIGHTED - exceeds 33ms)  
Row 4: Delta = -56ms  (HIGHLIGHTED - exceeds 33ms)
Row 5: Delta = -54ms  (HIGHLIGHTED - exceeds 33ms)
...
```

## 🔧 Configuration Updates

### New INI Settings
```ini
[email_settings]
variance_threshold_ms = 33    # NEW: Variance threshold in milliseconds
error_threshold_seconds = 0.2 # LEGACY: Still supported for compatibility
```

### Threshold Logic
- **Primary**: `variance_threshold_ms` (milliseconds) - used for variance detection
- **Secondary**: `error_threshold_seconds` (seconds) - maintained for compatibility
- **Priority**: Variance threshold takes precedence for email subject determination

## 📋 Distribution Contents

```
NTP-Delta-Monitor-v2.1.0.zip
├── ntp_monitor.exe              # Updated executable with variance checking
├── ntp_monitor_sample.ini       # Updated with variance_threshold_ms
├── README.md                    # Complete documentation
├── INSTALL.md                   # Installation guide
├── EXAMPLES.md                  # Usage examples
├── DEPLOYMENT.md                # Deployment guide
├── VERSION.txt                  # Updated version information
├── QUICK-START.txt              # Updated quick start guide
└── Reports/                     # Default output directory
```

## 🎯 Key Improvements

### Enhanced Problem Detection
1. **Immediate Visual Feedback**: Red highlighting in Excel for problem servers
2. **Proactive Alerting**: Email subject changes automatically when thresholds exceeded
3. **Precise Thresholds**: Millisecond-level control vs previous second-level
4. **Real-world Tested**: Validated against actual TEGNA infrastructure

### Better User Experience
- **Visual Priority**: Problem servers immediately visible in red
- **Clear Alerting**: Email subjects clearly indicate error conditions
- **Configurable**: Threshold adjustable for different environments
- **Backward Compatible**: Existing configurations continue to work

## 🚀 Quick Start

1. **Extract** the zip file to any directory
2. **Run** `ntp_monitor.exe` (detects variance automatically)
3. **Check Reports**: Look for red-highlighted cells in Excel
4. **Monitor Email**: "ERROR" subjects indicate variance issues
5. **Configure** (optional): Adjust `variance_threshold_ms` in INI file

## 📧 Email Alert Examples

### Normal Operation (≤33ms variance)
```
Subject: NTP REPORT tgna.tegna.com - Max Delta: 25ms - all servers responding
```

### High Variance (>33ms variance)  
```
Subject: NTP ERROR tgna.tegna.com - Max Delta: 69ms - all servers responding
```

### With Failed Servers
```
Subject: NTP ERROR tgna.tegna.com - Max Delta: 45ms - 3 servers not responding
```

## 🔄 Upgrade Notes

### From v2.0.x
- **Automatic**: New features enabled by default
- **Configuration**: Add `variance_threshold_ms = 33` to existing INI files
- **Compatibility**: All existing settings continue to work

### Recommended Actions
1. **Test Threshold**: Run against your servers to validate 33ms threshold
2. **Adjust if Needed**: Modify `variance_threshold_ms` for your environment
3. **Update Monitoring**: Expect "ERROR" emails when variance exceeded
4. **Train Users**: Red highlighting indicates servers needing attention

## 🐛 Bug Fixes

- Fixed duplicate configuration loading
- Improved error detection logic
- Enhanced Excel formatting reliability
- Better threshold comparison accuracy

## 📈 Performance

- **Same Performance**: No impact on monitoring speed
- **Enhanced Output**: Better visual feedback with minimal overhead
- **Efficient Highlighting**: Optimized Excel formatting
- **Smart Detection**: Precise threshold checking

## 🔗 Links

- **GitHub Repository**: https://github.com/MarkTegna/ntp-delta-monitor
- **Documentation**: See README.md in distribution
- **Support**: Create issues on GitHub repository

---

**System Requirements**: Windows 10/11, No additional dependencies required  
**Tested Environments**: Windows Server 2019/2022, Windows 10/11  
**Network Requirements**: UDP port 123 outbound, DNS resolution capability  
**Variance Testing**: Validated against 108 live TEGNA NTP servers