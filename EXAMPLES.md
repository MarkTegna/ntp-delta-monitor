# Usage Examples - NTP Delta Monitor

This document provides practical examples for using the NTP Delta Monitor in various scenarios.

## Default Usage (TEGNA Environment)

### Example 0: Zero-Configuration Monitoring

The simplest way to run NTP monitoring in the TEGNA environment:

```cmd
ntp_monitor.exe
```

**What happens**:
- Uses `ntp1.tgna.tegna.com` as reference server
- Queries all A records from `tgna.tegna.com` domain (typically 100+ IP addresses)
- Tests each IP address as a potential NTP server
- Reports which ones actually provide NTP service
- Generates timestamped CSV report
- Uses default settings (10 concurrent, 30s timeout, seconds format)

**Expected output**:
```
============================================================
NTP MONITORING SUMMARY
============================================================
Total servers processed: 109
Successful queries: 108
Failed queries: 1

Status breakdown:
  OK: 108
  ERROR: 1

Time delta statistics (successful measurements):
  Minimum delta: 0.062 seconds
  Maximum delta: 0.523 seconds
  Average delta: 0.277 seconds
============================================================
```

## Basic Examples

### Example 1: Simple NTP Monitoring

Monitor a few NTP servers against a reference:

**Create server list** (`servers.txt`):
```
pool.ntp.org
time.windows.com
time.google.com
time.cloudflare.com
```

**Run monitoring**:
```cmd
ntp_monitor.exe -r pool.ntp.org -s servers.txt
```

**Expected output**:
- XLSX file: `ntp_monitor_report_20240115_103000.xlsx` - Detailed spreadsheet report
- Summary file: `ntp_monitor_report_20240115_103000.txt` - Text summary with statistics
- Console summary showing 4 servers processed
- Delta statistics in seconds

### Example 2: Corporate Environment

Monitor internal NTP infrastructure:

**Create server list** (`corporate_ntp.csv`):
```csv
server,location,role
ntp1.company.com,datacenter1,primary
ntp2.company.com,datacenter2,secondary
ntp3.company.com,branch1,local
10.1.1.100,datacenter1,backup
10.2.1.100,datacenter2,backup
```

**Run with custom settings**:
```cmd
ntp_monitor.exe -r ntp1.company.com -s corporate_ntp.csv -o daily_ntp_report.csv -f milliseconds -v
```

**Features used**:
- CSV input with additional columns (ignored)
- Custom output filename
- Milliseconds format for precision
- Verbose logging for troubleshooting

**Output files generated**:
- `daily_ntp_report.xlsx` - Detailed XLSX report with all NTP metrics
- `daily_ntp_report.txt` - Summary file with statistics

**Sample summary file content** (`daily_ntp_report.txt`):
```
============================================================
NTP MONITORING SUMMARY
============================================================
Total servers processed: 5
Successful queries: 5
Failed queries: 0

Time delta statistics (successful measurements):
  Minimum delta: -12 milliseconds
  Maximum delta: 8 milliseconds
  Average delta: -2 milliseconds
============================================================
```

## Advanced Examples

### Example 3: High-Volume Monitoring

Monitor 100+ NTP servers efficiently:

**Create large server list** (`large_ntp_list.txt`):
```
# Public NTP pools
0.pool.ntp.org
1.pool.ntp.org
2.pool.ntp.org
3.pool.ntp.org
# Regional servers
time.nist.gov
time-a.nist.gov
time-b.nist.gov
# ... (100+ servers)
```

**Run with high concurrency**:
```cmd
ntp_monitor.exe -r time.nist.gov -s large_ntp_list.txt -p 50 -t 15 -o bulk_ntp_analysis.csv
```

**Configuration explanation**:
- `-p 50`: 50 concurrent queries for speed
- `-t 15`: 15-second timeout (faster than default)
- Processes 100+ servers in under 2 minutes

### Example 4: Network Troubleshooting

Diagnose NTP synchronization issues:

**Create problem server list** (`problem_servers.txt`):
```
unreachable.ntp.server
slow.ntp.server
192.168.1.999
timeout.example.com
```

**Run with verbose diagnostics**:
```cmd
ntp_monitor.exe -r time.windows.com -s problem_servers.txt -v -t 60 -o diagnostics.csv
```

**Diagnostic output includes**:
- DNS resolution attempts and failures
- Detailed error messages
- Network timing information
- Recovery actions taken

## Real-World Scenarios

### Scenario 1: Daily NTP Health Check

**Objective**: Monitor corporate NTP infrastructure daily

**Setup**:
1. Create comprehensive server list:
```csv
server,location,criticality,notes
ntp-primary.corp.com,hq-datacenter,critical,main reference
ntp-backup.corp.com,hq-datacenter,high,backup reference
ntp-branch1.corp.com,branch-office-1,medium,local time source
ntp-branch2.corp.com,branch-office-2,medium,local time source
ntp-dmz.corp.com,dmz,high,external facing
```

2. Create monitoring script (`daily_ntp_check.bat`):
```batch
@echo off
set REPORT_DATE=%date:~-4,4%%date:~-10,2%%date:~-7,2%
ntp_monitor.exe -r ntp-primary.corp.com -s corporate_ntp_servers.csv -o reports\ntp_health_%REPORT_DATE%.csv -f milliseconds
if %errorlevel% neq 0 (
    echo NTP monitoring detected issues - check report
    exit /b 1
)
echo NTP monitoring completed successfully
```

3. Schedule with Task Scheduler for daily execution

### Scenario 2: NTP Server Performance Analysis

**Objective**: Analyze NTP server performance over time

**Method**:
```cmd
# Run multiple times with different reference servers
ntp_monitor.exe -r time.nist.gov -s test_servers.txt -o analysis_nist.csv -f milliseconds
ntp_monitor.exe -r time.google.com -s test_servers.txt -o analysis_google.csv -f milliseconds
ntp_monitor.exe -r pool.ntp.org -s test_servers.txt -o analysis_pool.csv -f milliseconds
```

**Analysis**: Compare delta values across different reference sources to identify:
- Consistently accurate servers
- Servers with high variance
- Network path dependencies

### Scenario 3: Network Migration Validation

**Objective**: Validate NTP connectivity after network changes

**Pre-migration baseline**:
```cmd
ntp_monitor.exe -r current.ntp.server -s all_servers.txt -o pre_migration_baseline.csv -v
```

**Post-migration validation**:
```cmd
ntp_monitor.exe -r new.ntp.server -s all_servers.txt -o post_migration_validation.csv -v
```

**Compare results** to ensure:
- All servers remain reachable
- Delta values are within acceptable ranges
- No new timeout or error conditions

## Automation Examples

### Example 5: PowerShell Integration

**PowerShell script** (`Monitor-NTP.ps1`):
```powershell
param(
    [string]$ReferenceServer = "time.windows.com",
    [string]$ServerListFile = "servers.txt",
    [int]$ParallelLimit = 10,
    [switch]$Verbose
)

# Build command arguments
$args = @(
    "-r", $ReferenceServer,
    "-s", $ServerListFile,
    "-p", $ParallelLimit,
    "-f", "milliseconds"
)

if ($Verbose) { $args += "-v" }

# Run NTP monitor
$result = & "ntp_monitor.exe" @args

# Check exit code
if ($LASTEXITCODE -eq 0) {
    Write-Host "NTP monitoring completed successfully" -ForegroundColor Green
} else {
    Write-Host "NTP monitoring detected issues" -ForegroundColor Red
    exit $LASTEXITCODE
}
```

**Usage**:
```powershell
.\Monitor-NTP.ps1 -ReferenceServer "ntp.company.com" -ServerListFile "corporate_servers.csv" -Verbose
```

### Example 6: Batch Processing Multiple Lists

**Batch script** (`process_multiple_lists.bat`):
```batch
@echo off
setlocal enabledelayedexpansion

set REFERENCE_SERVER=time.nist.gov
set TIMESTAMP=%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=!TIMESTAMP: =0!

echo Processing multiple NTP server lists...

for %%f in (*.txt) do (
    echo Processing %%f...
    ntp_monitor.exe -r %REFERENCE_SERVER% -s "%%f" -o "results\%%~nf_%TIMESTAMP%.csv" -f milliseconds
    if !errorlevel! neq 0 (
        echo ERROR: Failed to process %%f
    ) else (
        echo SUCCESS: Processed %%f
    )
)

echo All lists processed. Results in results\ directory.
```

## Output Analysis Examples

### Example 7: CSV Analysis with Excel/PowerBI

**Sample CSV output**:
```csv
timestamp_utc,ntp_server,ntp_server_ip,ntp_time_utc,query_rtt_ms,stratum,root_delay_ms,root_dispersion_ms,delta_value,delta_format,status,error_message
2024-01-15T10:30:00.123Z,pool.ntp.org,162.159.200.1,2024-01-15T10:30:00.125Z,45.2,2,12.5,8.3,2,milliseconds,OK,
2024-01-15T10:30:00.156Z,time.google.com,216.239.35.0,2024-01-15T10:30:00.151Z,38.7,1,5.1,2.7,-5,milliseconds,OK,
2024-01-15T10:30:00.189Z,bad.server.com,,,,,,,,milliseconds,TIMEOUT,Query timeout after 30 seconds
```

**Excel analysis formulas**:
```excel
# Count successful queries
=COUNTIF(K:K,"OK")

# Average delta for successful queries
=AVERAGEIF(K:K,"OK",I:I)

# Maximum RTT
=MAX(E:E)

# Servers with high stratum (>3)
=COUNTIF(F:F,">3")
```

### Example 8: Log Analysis

**Extract errors from verbose logs**:
```cmd
ntp_monitor.exe -r time.nist.gov -s servers.txt -v > ntp_log.txt 2>&1
findstr /i "error\|timeout\|failed" ntp_log.txt > errors.txt
```

**PowerShell log analysis**:
```powershell
# Parse NTP monitor log for statistics
$log = Get-Content "ntp_log.txt"
$errors = $log | Where-Object { $_ -match "ERROR|TIMEOUT|FAILED" }
$successes = $log | Where-Object { $_ -match "Successfully processed" }

Write-Host "Total errors: $($errors.Count)"
Write-Host "Total successes: $($successes.Count)"
```

## Performance Optimization Examples

### Example 9: Tuning for Different Network Conditions

**Fast local network**:
```cmd
ntp_monitor.exe -r local.ntp.server -s local_servers.txt -p 30 -t 5
```

**Slow WAN connection**:
```cmd
ntp_monitor.exe -r remote.ntp.server -s remote_servers.txt -p 5 -t 120
```

**Mixed environment**:
```cmd
# Process local servers first (fast)
ntp_monitor.exe -r local.ntp.server -s local_servers.txt -p 20 -t 10 -o local_results.csv

# Process remote servers (slower)
ntp_monitor.exe -r remote.ntp.server -s remote_servers.txt -p 5 -t 60 -o remote_results.csv
```

### Example 10: Resource-Constrained Systems

**Low-resource system**:
```cmd
ntp_monitor.exe -r time.windows.com -s servers.txt -p 3 -t 45
```

**High-performance system**:
```cmd
ntp_monitor.exe -r time.nist.gov -s large_server_list.txt -p 100 -t 10
```

## Integration Examples

### Example 11: SIEM Integration

**Generate SIEM-friendly output**:
```cmd
ntp_monitor.exe -r siem.ntp.server -s monitored_servers.txt -o siem_ntp_data.csv -f milliseconds
```

**PowerShell SIEM forwarder**:
```powershell
# Convert CSV to JSON for SIEM ingestion
$csv = Import-Csv "siem_ntp_data.csv"
$json = $csv | ConvertTo-Json
$json | Out-File "ntp_events.json"

# Send to SIEM endpoint
Invoke-RestMethod -Uri "https://siem.company.com/api/events" -Method POST -Body $json -ContentType "application/json"
```

### Example 12: Monitoring System Integration

**Nagios/Icinga check script**:
```bash
#!/bin/bash
# NTP monitoring check for Nagios

REFERENCE_SERVER="ntp.company.com"
SERVER_LIST="/etc/nagios/ntp_servers.txt"
TEMP_OUTPUT="/tmp/ntp_check_$$.csv"

# Run NTP monitor
ntp_monitor.exe -r "$REFERENCE_SERVER" -s "$SERVER_LIST" -o "$TEMP_OUTPUT" -f milliseconds

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "OK - All NTP servers synchronized"
    exit 0
else
    echo "CRITICAL - NTP synchronization issues detected"
    exit 2
fi
```

## Troubleshooting Examples

### Example 13: Network Connectivity Issues

**Test basic connectivity**:
```cmd
# Test with single server and verbose output
ntp_monitor.exe -r time.windows.com -s single_server.txt -v -t 10

# Check DNS resolution
nslookup pool.ntp.org

# Test NTP port connectivity
telnet pool.ntp.org 123
```

### Example 14: Performance Issues

**Identify slow servers**:
```cmd
# Run with verbose timing
ntp_monitor.exe -r fast.ntp.server -s test_servers.txt -v -t 30 > timing_analysis.log

# Extract timing information
findstr /i "query completed\|timeout" timing_analysis.log
```

**Optimize based on results**:
```cmd
# Separate fast and slow servers
ntp_monitor.exe -r fast.server -s fast_servers.txt -p 20 -t 10
ntp_monitor.exe -r slow.server -s slow_servers.txt -p 5 -t 60
```

These examples demonstrate the flexibility and power of the NTP Delta Monitor for various monitoring scenarios, from simple health checks to complex enterprise monitoring solutions.