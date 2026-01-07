# NTP Delta Monitor v2.1.1 Release Notes

**Release Date**: January 7, 2026  
**Build**: Windows x64 Standalone Executable  
**File Size**: ~10.4 MB  

## 🔧 **CRITICAL FIX: Excel Highlighting Now Working**

### Issue Resolved
- **Problem**: Excel highlighting was not working in the standalone executable distribution
- **Root Cause**: Missing openpyxl style imports in PyInstaller build
- **Solution**: Enhanced PyInstaller spec with comprehensive openpyxl style dependencies

### ✅ **Verified Working Features**

**Excel Highlighting:**
- ✅ Red background highlighting for values exceeding variance threshold
- ✅ White bold text on red background for maximum visibility
- ✅ Automatic threshold detection (default: 33ms)
- ✅ Configurable via `variance_threshold_ms` in INI file

**Email Notifications:**
- ✅ Subject changes from "NTP REPORT" to "NTP ERROR" when threshold exceeded
- ✅ Variance-based detection working correctly
- ✅ Email delivery with XLSX attachments

**Test Results:**
- **Servers Tested**: 108 TEGNA NTP servers
- **Highlighted Cells**: 17 cells with values >33ms (57ms, 51ms, 49ms, etc.)
- **Email Subject**: Correctly shows "NTP ERROR" when variance exceeded
- **Verification**: Programmatic verification confirms highlighting is present

## 🛠 **Technical Improvements**

### Enhanced PyInstaller Configuration
```python
# Added comprehensive openpyxl imports
'openpyxl.styles.fonts',
'openpyxl.styles.fills', 
'openpyxl.styles.colors',
'openpyxl.styles.alignment',
'openpyxl.formatting',
'openpyxl.formatting.rule',
```

### Improved Error Handling
- Added comprehensive debugging for Excel formatting operations
- Enhanced error reporting for highlighting failures
- Better logging of variance threshold application

### Version Update
- Updated version string to 2.1.1
- Enhanced debugging capabilities for troubleshooting

## 📋 **Distribution Contents**

```
NTP-Delta-Monitor-v2.1.1.zip
├── ntp_monitor.exe              # FIXED executable with working highlighting
├── ntp_monitor_sample.ini       # Configuration with variance_threshold_ms
├── README.md                    # Complete documentation
├── INSTALL.md                   # Installation guide
├── EXAMPLES.md                  # Usage examples
├── DEPLOYMENT.md                # Deployment guide
├── VERSION.txt                  # Updated version information
├── QUICK-START.txt              # Updated quick start guide
└── Reports/                     # Default output directory
```

## 🎯 **Verification Steps**

To confirm highlighting is working:

1. **Run the executable**: `ntp_monitor.exe`
2. **Open the Excel report**: Check `Reports\ntp_monitor_report_*.xlsx`
3. **Look for red cells**: Values >33ms should have red background with white text
4. **Check email**: Subject should show "ERROR" if variance exceeded

## 🔄 **Upgrade from v2.1.0**

- **Automatic**: Simply replace the executable - no configuration changes needed
- **Immediate**: Highlighting will work immediately in new reports
- **Backward Compatible**: All existing settings and configurations preserved

## 🐛 **Bug Fixes**

- **FIXED**: Excel highlighting now works correctly in standalone executable
- **FIXED**: PyInstaller missing openpyxl style dependencies
- **FIXED**: Variance threshold detection and highlighting reliability
- **IMPROVED**: Error handling and debugging capabilities

## 📈 **Performance**

- **Same Performance**: No impact on monitoring speed or functionality
- **Enhanced Reliability**: Better error handling and recovery
- **Improved Debugging**: More detailed logging for troubleshooting

## 🔗 **Links**

- **GitHub Repository**: https://github.com/MarkTegna/ntp-delta-monitor
- **Documentation**: See README.md in distribution
- **Support**: Create issues on GitHub repository

---

**System Requirements**: Windows 10/11, No additional dependencies required  
**Tested Environments**: Windows Server 2019/2022, Windows 10/11  
**Network Requirements**: UDP port 123 outbound, DNS resolution capability  
**Verification**: Tested against 108 live TEGNA NTP servers with confirmed highlighting