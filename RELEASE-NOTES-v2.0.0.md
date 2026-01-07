# NTP Delta Monitor v2.0.0 Release Notes

**Release Date**: January 7, 2026  
**Build**: Windows x64 Standalone Executable  
**File Size**: ~10.4 MB  

## 🚀 New Features

### 1. Configurable Output Directory
- **Default Location**: `.\Reports` directory
- **Automatic Creation**: Directory created automatically if it doesn't exist
- **INI Configuration**: Customizable via `output_directory` setting
- **Organized Storage**: All XLSX and TXT files saved to configured location

### 2. Error Server Prioritization
- **Top Priority**: Error servers now appear at the top of all reports
- **Severity Sorting**: Errors sorted by severity (ERROR > TIMEOUT > UNSYNCHRONIZED > UNREACHABLE)
- **Immediate Visibility**: Critical issues are always visible first
- **Enhanced Troubleshooting**: Faster problem identification and resolution

### 3. Improved Statistics
- **Absolute Values**: Min/Max/Average now use absolute values for meaningful variance analysis
- **Better Metrics**: Statistics represent actual time differences regardless of direction
- **Enhanced Email Alerts**: Subject line shows maximum absolute delta value

### 4. Enhanced Default Configuration
- **Milliseconds Format**: Now default format for better readability
- **Optimized Settings**: Improved defaults for typical enterprise environments
- **Better Documentation**: Enhanced configuration examples and explanations

## 📋 Distribution Contents

```
NTP-Delta-Monitor-v2.0.0.zip
├── ntp_monitor.exe              # Main executable (10.4 MB)
├── ntp_monitor_sample.ini       # Configuration template
├── README.md                    # Complete documentation
├── INSTALL.md                   # Installation guide
├── EXAMPLES.md                  # Usage examples
├── DEPLOYMENT.md                # Deployment guide
├── VERSION.txt                  # Version information
├── QUICK-START.txt              # Quick start guide
└── Reports/                     # Default output directory
```

## 🔧 Configuration Changes

### New INI Settings
```ini
[report_settings]
output_directory = .\Reports     # NEW: Configurable output location
default_format = milliseconds    # CHANGED: From seconds to milliseconds
```

### Backward Compatibility
- All existing configurations continue to work
- New settings have sensible defaults
- No breaking changes to command-line interface

## 📊 Report Improvements

### Enhanced Sorting Priority
1. **Error Servers** (ERROR, TIMEOUT, UNSYNCHRONIZED, UNREACHABLE)
2. **Successful Servers** (sorted by highest absolute time variance)
3. **Servers without Delta** (reference servers, etc.)

### Better Statistics Display
```
Time delta statistics (successful measurements):
  Minimum delta: 8 milliseconds      # Now absolute values
  Maximum delta: 106 milliseconds    # Highest variance regardless of direction
  Average delta: 26 milliseconds     # Average of absolute values
```

## 🚀 Quick Start

1. **Extract** the zip file to any directory
2. **Run** `ntp_monitor.exe` (no installation required)
3. **Check** the `Reports` folder for output files
4. **Configure** by copying `ntp_monitor_sample.ini` to `ntp_monitor.ini`

## 📧 Email Notifications

Enhanced email subject format:
- **Normal**: `NTP REPORT tgna.tegna.com - Max Delta: 106ms - all servers responding`
- **Error**: `NTP ERROR tgna.tegna.com - Max Delta: 312ms - 2 servers not responding`

## 🔄 Upgrade Notes

### From v1.x
- **No Action Required**: Existing installations continue to work
- **New Features**: Automatically enabled with default settings
- **Configuration**: Optional - copy sample INI for new features

### Recommended Actions
1. Update any automation scripts to expect files in `Reports` directory
2. Review new configuration options in `ntp_monitor_sample.ini`
3. Test email notifications with new subject format

## 🐛 Bug Fixes

- Fixed time delta drift issues with fresh reference queries
- Improved error handling and recovery
- Enhanced DNS resolution reliability
- Better concurrent processing stability

## 📈 Performance Improvements

- Optimized sorting algorithms for large server lists
- Improved memory usage for concurrent processing
- Faster XLSX generation with enhanced formatting
- Better error recovery and processing continuity

## 🔗 Links

- **GitHub Repository**: https://github.com/MarkTegna/ntp-delta-monitor
- **Documentation**: See README.md in distribution
- **Support**: Create issues on GitHub repository

---

**System Requirements**: Windows 10/11, No additional dependencies required  
**Tested Environments**: Windows Server 2019/2022, Windows 10/11  
**Network Requirements**: UDP port 123 outbound, DNS resolution capability