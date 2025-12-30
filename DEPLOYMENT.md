# NTP Delta Monitor - Deployment Guide

This guide explains how to deploy and configure the NTP Delta Monitor in different environments.

## Quick Deployment

### 1. Extract Files
When you download or extract the NTP Delta Monitor, you'll get these files:
- `ntp_monitor.exe` - Main executable
- `ntp_monitor.ini` - Current configuration file (if exists)
- `ntp_monitor_sample.ini` - Sample configuration with examples

### 2. Basic Setup (Use Defaults)
For immediate use with TEGNA defaults:
```cmd
ntp_monitor.exe
```
This will use built-in TEGNA settings and auto-discover servers.

### 3. Custom Configuration Setup
For custom environments:

1. **Copy the sample configuration**:
   ```cmd
   copy ntp_monitor_sample.ini ntp_monitor.ini
   ```

2. **Edit `ntp_monitor.ini`** with your settings:
   ```ini
   [ntp_settings]
   default_reference_server = your.ntp.server.com
   default_discovery_domain = your.domain.com
   ```

3. **Test the configuration**:
   ```cmd
   ntp_monitor.exe --help
   ```
   The help output will show your configured defaults.

## Environment-Specific Deployments

### Corporate Environment

**Configuration** (`ntp_monitor.ini`):
```ini
[ntp_settings]
default_reference_server = ntp.company.com
default_discovery_domain = company.com
fallback_servers = ntp1.company.com,ntp2.company.com,ntp3.company.com

[report_settings]
default_format = seconds
default_parallel_limit = 20
default_timeout = 15

[advanced_settings]
sort_by_variance = true
```

**Usage**:
```cmd
# Monitor all company NTP servers
ntp_monitor.exe

# Monitor specific servers with custom output
ntp_monitor.exe -s company_servers.txt -o daily_report.xlsx
```

### Multi-Site Deployment

**Site A Configuration** (`ntp_monitor.ini`):
```ini
[ntp_settings]
default_reference_server = ntp.sitea.company.com
default_discovery_domain = sitea.company.com
fallback_servers = ntp1.sitea.company.com,ntp2.sitea.company.com

[report_settings]
default_parallel_limit = 10
default_timeout = 30
```

**Site B Configuration** (`ntp_monitor.ini`):
```ini
[ntp_settings]
default_reference_server = ntp.siteb.company.com
default_discovery_domain = siteb.company.com
fallback_servers = ntp1.siteb.company.com,ntp2.siteb.company.com

[report_settings]
default_parallel_limit = 15
default_timeout = 20
```

### Public NTP Monitoring

**Configuration** (`ntp_monitor.ini`):
```ini
[ntp_settings]
default_reference_server = time.nist.gov
fallback_servers = time.windows.com,time.google.com,pool.ntp.org,time.cloudflare.com

[report_settings]
default_format = milliseconds
default_parallel_limit = 50
default_timeout = 10

[advanced_settings]
sort_by_variance = true
```

**Server List** (`public_ntp.txt`):
```
pool.ntp.org
time.windows.com
time.google.com
time.cloudflare.com
time.apple.com
time.facebook.com
ntp.ubuntu.com
```

**Usage**:
```cmd
ntp_monitor.exe -s public_ntp.txt -o public_ntp_analysis.xlsx
```

## Automated Deployment

### Batch Script Deployment
Create `deploy_ntp_monitor.bat`:
```batch
@echo off
echo Deploying NTP Delta Monitor...

REM Create directory
mkdir "C:\Tools\NTPMonitor" 2>nul

REM Copy files
copy ntp_monitor.exe "C:\Tools\NTPMonitor\"
copy ntp_monitor_sample.ini "C:\Tools\NTPMonitor\"

REM Create custom configuration
echo [ntp_settings] > "C:\Tools\NTPMonitor\ntp_monitor.ini"
echo default_reference_server = %1 >> "C:\Tools\NTPMonitor\ntp_monitor.ini"
echo default_discovery_domain = %2 >> "C:\Tools\NTPMonitor\ntp_monitor.ini"

echo Deployment complete!
echo Usage: C:\Tools\NTPMonitor\ntp_monitor.exe
```

**Usage**:
```cmd
deploy_ntp_monitor.bat ntp.company.com company.com
```

### PowerShell Deployment
Create `Deploy-NTPMonitor.ps1`:
```powershell
param(
    [string]$InstallPath = "C:\Tools\NTPMonitor",
    [string]$ReferenceServer = "time.windows.com",
    [string]$DiscoveryDomain = "company.com"
)

# Create installation directory
New-Item -ItemType Directory -Path $InstallPath -Force

# Copy executable
Copy-Item "ntp_monitor.exe" -Destination $InstallPath
Copy-Item "ntp_monitor_sample.ini" -Destination $InstallPath

# Create configuration
$config = @"
[ntp_settings]
default_reference_server = $ReferenceServer
default_discovery_domain = $DiscoveryDomain

[report_settings]
default_format = seconds
default_parallel_limit = 10
default_timeout = 30

[advanced_settings]
sort_by_variance = true
"@

$config | Out-File -FilePath "$InstallPath\ntp_monitor.ini" -Encoding UTF8

Write-Host "NTP Delta Monitor deployed to: $InstallPath"
Write-Host "Test with: $InstallPath\ntp_monitor.exe --help"
```

## Scheduled Monitoring

### Windows Task Scheduler

1. **Create monitoring script** (`ntp_monitor_daily.bat`):
   ```batch
   @echo off
   cd /d "C:\Tools\NTPMonitor"
   
   REM Generate daily report (creates both XLSX and TXT files)
   set REPORT_DATE=%date:~-4,4%%date:~-10,2%%date:~-7,2%
   ntp_monitor.exe -o "reports\ntp_daily_%REPORT_DATE%.xlsx"
   
   REM This creates:
   REM   reports\ntp_daily_YYYYMMDD.xlsx - Detailed report
   REM   reports\ntp_daily_YYYYMMDD.txt  - Summary statistics
   
   REM Check exit code
   if %errorlevel% neq 0 (
       echo NTP monitoring failed - check logs
       exit /b 1
   )
   
   echo Daily NTP monitoring completed successfully
   ```

2. **Schedule with Task Scheduler**:
   - Open Task Scheduler
   - Create Basic Task
   - Set trigger: Daily at desired time
   - Set action: Start program `C:\Tools\NTPMonitor\ntp_monitor_daily.bat`

### PowerShell Scheduled Job
```powershell
# Create scheduled job for NTP monitoring
$trigger = New-JobTrigger -Daily -At "06:00"
$options = New-ScheduledJobOption -RunElevated

Register-ScheduledJob -Name "NTPMonitoring" -Trigger $trigger -ScheduledJobOption $options -ScriptBlock {
    Set-Location "C:\Tools\NTPMonitor"
    $date = Get-Date -Format "yyyyMMdd"
    & ".\ntp_monitor.exe" -o "reports\ntp_daily_$date.xlsx"
}
```

## Troubleshooting Deployment

### Configuration Issues

**Problem**: Program uses wrong defaults
**Solution**: Check `ntp_monitor.ini` exists and has correct format

**Problem**: Configuration file not found
**Solution**: Ensure `ntp_monitor.ini` is in same directory as executable

**Problem**: Invalid configuration values
**Solution**: Copy from `ntp_monitor_sample.ini` and modify carefully

### Network Issues

**Problem**: DNS resolution failures
**Solution**: Use IP addresses instead of hostnames in configuration

**Problem**: Firewall blocking NTP
**Solution**: Ensure UDP port 123 is open outbound

**Problem**: Slow performance
**Solution**: Reduce `default_parallel_limit` and increase `default_timeout`

### Permission Issues

**Problem**: Cannot write reports
**Solution**: Run from directory with write permissions or specify output path

**Problem**: Cannot read configuration
**Solution**: Check file permissions on `ntp_monitor.ini`

## Best Practices

1. **Test configuration** before deployment:
   ```cmd
   ntp_monitor.exe --help
   ntp_monitor.exe -v
   ```

2. **Use version control** for configuration files

3. **Monitor log output** in verbose mode during initial deployment

4. **Set appropriate timeouts** for your network environment

5. **Use fallback servers** for reliability

6. **Schedule regular monitoring** for proactive issue detection

7. **Archive reports** for historical analysis

8. **Document environment-specific settings** for team members