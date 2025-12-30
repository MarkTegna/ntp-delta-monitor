# Installation Guide - NTP Delta Monitor

## Quick Start (Recommended)

### Download and Run Executable

1. **Download**: Get the `ntp_monitor.exe` file
2. **Place**: Put it in any directory (e.g., `C:\Tools\`)
3. **Run**: Open Command Prompt and run:
   ```cmd
   ntp_monitor.exe -r time.windows.com -s your_servers.txt
   ```

**That's it!** No installation required - all dependencies are included.

## Detailed Installation Options

### Option 1: Standalone Executable (No Python Required)

**Best for**: Production use, deployment across multiple systems

1. **Download the executable**:
   - Get `ntp_monitor.exe` from the releases
   - File size: ~15MB (includes all dependencies)

2. **Choose installation location**:
   ```cmd
   # System-wide installation (requires admin)
   C:\Program Files\NTPMonitor\ntp_monitor.exe
   
   # User installation
   C:\Users\%USERNAME%\Tools\ntp_monitor.exe
   
   # Portable installation
   D:\PortableApps\NTPMonitor\ntp_monitor.exe
   ```

3. **Optional: Add to PATH**:
   - Right-click "This PC" → Properties → Advanced System Settings
   - Click "Environment Variables"
   - Edit "Path" variable and add your installation directory
   - Now you can run `ntp_monitor` from anywhere

4. **Test installation**:
   ```cmd
   ntp_monitor.exe --version
   ntp_monitor.exe --help
   ```

### Option 2: Python Source Installation

**Best for**: Development, customization, or systems with Python already installed

#### Prerequisites

- **Python 3.8 or higher**
- **Windows operating system**
- **Internet connection** (for package installation)

#### Step-by-Step Installation

1. **Verify Python installation**:
   ```cmd
   python --version
   # Should show Python 3.8.x or higher
   ```

2. **Create project directory**:
   ```cmd
   mkdir C:\NTPMonitor
   cd C:\NTPMonitor
   ```

3. **Create virtual environment** (recommended):
   ```cmd
   python -m venv .venv
   .venv\Scripts\activate
   ```

4. **Install dependencies**:
   ```cmd
   pip install ntplib dnspython
   ```

5. **Download source files**:
   - Get `ntp_monitor.py`
   - Place in your project directory

6. **Test installation**:
   ```cmd
   python ntp_monitor.py --version
   python ntp_monitor.py --help
   ```

## Building from Source (Advanced)

### Prerequisites for Building

- Python 3.8+
- PyInstaller
- All runtime dependencies

### Build Process

1. **Setup environment**:
   ```cmd
   git clone <repository>
   cd ntp-delta-monitor
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. **Install build dependencies**:
   ```cmd
   pip install pyinstaller ntplib dnspython
   ```

3. **Build executable**:
   ```cmd
   pyinstaller ntp_monitor.spec
   ```

4. **Find executable**:
   ```cmd
   # Built executable will be in:
   dist\ntp_monitor.exe
   ```

## Deployment Scenarios

### Single User Installation

```cmd
# Create user tools directory
mkdir %USERPROFILE%\Tools
copy ntp_monitor.exe %USERPROFILE%\Tools\

# Add to user PATH (optional)
setx PATH "%PATH%;%USERPROFILE%\Tools"
```

### System-Wide Installation

```cmd
# Requires administrator privileges
mkdir "C:\Program Files\NTPMonitor"
copy ntp_monitor.exe "C:\Program Files\NTPMonitor\"

# Add to system PATH (optional)
setx PATH "%PATH%;C:\Program Files\NTPMonitor" /M
```

### Network Share Deployment

```cmd
# Copy to network share
copy ntp_monitor.exe \\server\share\Tools\

# Create batch file for easy access
echo @echo off > run_ntp_monitor.bat
echo \\server\share\Tools\ntp_monitor.exe %* >> run_ntp_monitor.bat
```

### Portable Installation

```cmd
# Create portable directory structure
mkdir D:\PortableApps\NTPMonitor
copy ntp_monitor.exe D:\PortableApps\NTPMonitor\
copy README.md D:\PortableApps\NTPMonitor\
mkdir D:\PortableApps\NTPMonitor\examples
```

## Verification and Testing

### Basic Functionality Test

1. **Create test server list**:
   ```cmd
   echo time.windows.com > test_servers.txt
   echo pool.ntp.org >> test_servers.txt
   ```

2. **Run basic test**:
   ```cmd
   ntp_monitor.exe -r time.windows.com -s test_servers.txt -v
   ```

3. **Expected output**:
   - Should show successful NTP queries
   - Generate CSV report file
   - Display summary statistics
   - Exit with code 0

### Network Connectivity Test

```cmd
# Test with verbose logging
ntp_monitor.exe -r pool.ntp.org -s test_servers.txt -v -t 10

# Check for:
# - DNS resolution success
# - NTP query completion
# - No timeout errors
```

### Performance Test

```cmd
# Test concurrent processing
ntp_monitor.exe -r time.windows.com -s large_server_list.txt -p 20 -t 30
```

## Troubleshooting Installation

### Common Installation Issues

#### "ntp_monitor.exe is not recognized"
**Cause**: Executable not in PATH or wrong directory
**Solution**:
```cmd
# Use full path
C:\Tools\ntp_monitor.exe --help

# Or add to PATH
setx PATH "%PATH%;C:\Tools"
```

#### "MSVCP140.dll was not found"
**Cause**: Missing Visual C++ Redistributable
**Solution**:
- Download and install Microsoft Visual C++ Redistributable
- Or use the standalone executable which includes all dependencies

#### "Access is denied"
**Cause**: Insufficient permissions
**Solution**:
```cmd
# Run as administrator
runas /user:Administrator "cmd /c ntp_monitor.exe --help"

# Or install in user directory instead of Program Files
```

#### Python Installation Issues

**"python is not recognized"**:
- Install Python from python.org
- Ensure "Add to PATH" is checked during installation

**"pip is not recognized"**:
```cmd
python -m pip --version
# Use python -m pip instead of pip
```

**SSL Certificate errors during pip install**:
```cmd
pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org ntplib dnspython
```

### Network Requirements

Ensure the following network access:

- **Outbound UDP port 123**: For NTP queries
- **Outbound UDP port 53**: For DNS resolution
- **Internet access**: For external NTP servers

### Corporate Environment Setup

#### Firewall Configuration
```cmd
# Windows Firewall rules (run as administrator)
netsh advfirewall firewall add rule name="NTP Monitor Outbound" dir=out action=allow protocol=UDP localport=any remoteport=123
```

#### Proxy Considerations
- NTP uses UDP, which typically bypasses HTTP proxies
- DNS resolution may be affected by proxy settings
- Consider using IP addresses instead of hostnames if DNS issues occur

## Uninstallation

### Standalone Executable
```cmd
# Simply delete the executable and any created files
del ntp_monitor.exe
del ntp_monitor_report_*.csv
```

### Python Installation
```cmd
# Deactivate virtual environment
deactivate

# Remove project directory
rmdir /s C:\NTPMonitor
```

### System PATH Cleanup
```cmd
# Remove from PATH if added
# Use System Properties → Environment Variables to edit PATH
```

## Configuration Setup (Optional)

After installation, you can customize the program's default behavior using a configuration file:

### Quick Configuration Setup

1. **Copy the sample configuration**:
   ```cmd
   copy ntp_monitor_sample.ini ntp_monitor.ini
   ```

2. **Edit `ntp_monitor.ini`** with your environment settings:
   ```ini
   [ntp_settings]
   default_reference_server = your.ntp.server.com
   default_discovery_domain = your.domain.com
   
   [report_settings]
   default_parallel_limit = 20
   default_timeout = 15
   ```

3. **Test with your configuration**:
   ```cmd
   ntp_monitor.exe --help
   # Should show your configured defaults
   ```

### Configuration Benefits

- **No command-line arguments needed** for common operations
- **Environment-specific defaults** (corporate vs. public NTP)
- **Consistent behavior** across multiple runs
- **Easy deployment** - just copy the INI file

## Next Steps

After installation:

1. **Read the README.md** for usage instructions
2. **Create your server list files** (TXT or CSV format)
3. **Test with a small server list** first
4. **Set up scheduled monitoring** if needed
5. **Configure appropriate timeout and concurrency** settings

For detailed usage instructions, see the main README.md file.