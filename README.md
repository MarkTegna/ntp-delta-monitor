# NTP Delta Monitor

A Windows-based NTP monitoring program that queries multiple NTP sources for time synchronization analysis. The system queries a list of NTP servers to measure their time accuracy against a reference NTP source, computing time deltas and outputting comprehensive CSV reports with concurrent processing capabilities.

## Features

- **Multi-server NTP monitoring**: Query multiple NTP servers concurrently
- **Time delta calculation**: Compare target servers against a reference NTP source
- **Flexible input formats**: Support for both TXT and CSV server list files
- **Comprehensive reporting**: Generate detailed XLSX reports with all NTP metrics
- **Summary text files**: Automatic generation of concise summary statistics
- **Email notifications**: Automatic email alerts with reports and intelligent error detection
- **Concurrent processing**: Configurable parallel processing for efficient monitoring
- **Error handling**: Graceful handling of network timeouts and server failures
- **Multiple output formats**: Support for seconds or milliseconds delta formats
- **Variance sorting**: Results sorted by time drift for easy problem identification
- **Verbose logging**: Detailed operation information for troubleshooting
- **Standalone executable**: Single executable file with no dependencies
- **INI configuration**: Flexible configuration for different environments

## Installation and Setup

### Option 1: Standalone Executable (Recommended)

1. Download the `ntp_monitor.exe` file from the releases
2. Place it in a directory of your choice
3. No additional installation required - all dependencies are included

### Option 2: Python Source

If you prefer to run from source:

1. **Prerequisites**:
   - Python 3.8 or higher
   - Windows operating system

2. **Install dependencies**:
   ```cmd
   pip install ntplib dnspython
   ```

3. **Run the script**:
   ```cmd
   python ntp_monitor.py [options]
   ```

## Usage

### Basic Command Syntax

```cmd
# Default usage (auto-discover TEGNA NTP servers)
ntp_monitor.exe

# Custom usage with specific servers
ntp_monitor.exe -r <reference_server> -s <server_list_file> [options]
```

### Default Behavior

When run without any arguments, the program will:
- Use `ntp1.tgna.tegna.com` as the reference NTP server
- Query all A records from the `tgna.tegna.com` domain and use those IP addresses as NTP servers
- Generate a timestamped CSV report with default settings

This approach discovers all hosts in the TEGNA domain and tests them for NTP service availability.

### Required Arguments (when not using defaults)

- `-r, --reference-ntp SERVER`: Reference NTP server hostname or IP address for baseline time comparison
- `-s, --servers-file FILE`: Path to NTP server list file (.txt or .csv format)

### Optional Arguments

- `-o, --output-file FILE`: Output CSV file path (default: auto-generated with timestamp)
- `-f, --format FORMAT`: Delta value format - "seconds" or "milliseconds" (default: seconds)
- `-p, --parallel-limit N`: Maximum concurrent NTP queries, 1-100 (default: 10)
- `-t, --timeout SECONDS`: NTP query timeout in seconds, 1-300 (default: 30)
- `-v, --verbose`: Enable verbose logging with detailed operation information
- `--version`: Show program version and exit

## Configuration

The NTP Delta Monitor can be configured using an optional `ntp_monitor.ini` configuration file. This allows you to customize default settings for your environment without modifying command-line arguments.

### Configuration File Setup

1. **Copy the sample configuration**:
   ```cmd
   copy ntp_monitor_sample.ini ntp_monitor.ini
   ```

2. **Edit the configuration file** with your preferred settings:
   ```ini
   [ntp_settings]
   default_reference_server = your.ntp.server.com
   default_discovery_domain = your.domain.com
   fallback_servers = ntp1.company.com,ntp2.company.com
   
   [report_settings]
   default_format = milliseconds
   default_parallel_limit = 10
   default_timeout = 30
   output_directory = .\Reports
   
   [advanced_settings]
   sort_by_variance = true
   ```

3. **Run the program** - it will automatically use your configuration:
   ```cmd
   ntp_monitor.exe
   ```

### Configuration Options

| Section | Setting | Description | Default |
|---------|---------|-------------|---------|
| `ntp_settings` | `default_reference_server` | Reference NTP server for baseline comparison | `ntp1.tgna.tegna.com` |
| `ntp_settings` | `default_discovery_domain` | Domain for auto-discovery of NTP servers | `tgna.tegna.com` |
| `ntp_settings` | `fallback_servers` | Comma-separated list of fallback servers | TEGNA servers |
| `report_settings` | `default_format` | Delta format: `seconds` or `milliseconds` | `milliseconds` |
| `report_settings` | `default_parallel_limit` | Concurrent queries (1-100) | `10` |
| `report_settings` | `default_timeout` | Query timeout in seconds (1-300) | `30` |
| `report_settings` | `output_directory` | Directory for reports and logs | `.\Reports` |
| `advanced_settings` | `sort_by_variance` | Sort results by time variance | `true` |

### Email Configuration

The program can automatically send email notifications after each monitoring run with the XLSX report attached and summary statistics in the email body.

| Section | Setting | Description | Default |
|---------|---------|-------------|---------|
| `email_settings` | `send_email` | Enable/disable email notifications | `true` |
| `email_settings` | `smtp_server` | SMTP server hostname | `relay.tgna.tegna.com` |
| `email_settings` | `smtp_port` | SMTP server port | `25` |
| `email_settings` | `smtp_use_tls` | Use TLS encryption | `false` |
| `email_settings` | `smtp_username` | SMTP authentication username | *(empty)* |
| `email_settings` | `smtp_password` | SMTP authentication password | *(empty)* |
| `email_settings` | `from_email` | Sender email address | `ntp-monitor@tgna.tegna.com` |
| `email_settings` | `to_email` | Recipient email address | `moldham@tegna.com` |
| `email_settings` | `error_threshold_seconds` | Delta threshold for error alerts | `0.2` |

### Email Subject Format

The email subject line is automatically generated based on monitoring results:

**Normal Report**: `NTP REPORT {domain} - Max Delta: {delta} - {server_status}`
**Error Alert**: `NTP ERROR {domain} - Max Delta: {delta} - {server_status}`

- **Error condition**: Triggered when any server has a time delta > 0.2 seconds (configurable)
- **Domain**: The discovery domain from configuration
- **Max Delta**: Highest absolute time variance found
- **Server Status**: Either "all servers responding" or "X servers not responding"

**Example subjects**:
- `NTP REPORT tgna.tegna.com - Max Delta: 0.045s - all servers responding`
- `NTP ERROR tgna.tegna.com - Max Delta: 0.312s - 2 servers not responding`

### Environment Examples

**Corporate Environment**:
```ini
[ntp_settings]
default_reference_server = ntp.company.com
default_discovery_domain = company.com
fallback_servers = ntp1.company.com,ntp2.company.com

[report_settings]
default_parallel_limit = 20
default_timeout = 15
```

**Public NTP Monitoring**:
```ini
[ntp_settings]
default_reference_server = time.nist.gov
fallback_servers = time.windows.com,time.google.com,pool.ntp.org

[report_settings]
default_format = milliseconds
default_parallel_limit = 50
```

**Slow Network Environment**:
```ini
[report_settings]
default_parallel_limit = 5
default_timeout = 60
```

**Email Notifications**:
```ini
[email_settings]
send_email = true
smtp_server = relay.company.com
smtp_port = 25
from_email = ntp-monitor@company.com
to_email = netops@company.com
error_threshold_seconds = 0.1
```

## Usage Examples

### Default Usage (TEGNA Environment)

Run with auto-discovery of TEGNA NTP servers:
```cmd
ntp_monitor.exe
```

This will:
- Use `ntp1.tgna.tegna.com` as the reference server
- Query all A records from the `tgna.tegna.com` domain and test them as NTP servers
- Generate a report like `ntp_monitor_report_20240115_103000.csv`
- Typically discovers 100+ potential NTP servers from the domain

### Basic Usage

Query NTP servers from a text file:
```cmd
ntp_monitor.exe -r ntp1.example.com -s servers.txt
```

### CSV Input with Custom Output

Use CSV server list with custom output file and milliseconds format:
```cmd
ntp_monitor.exe -r ntp2.example.com -s servers.csv -o report.csv -f milliseconds
```

### High Performance Monitoring

High concurrency with custom timeout and verbose logging:
```cmd
ntp_monitor.exe -r 10.43.9.64 -s ntp_list.txt -p 20 -t 10 -v
```

### Corporate Environment Example

Monitor internal NTP infrastructure:
```cmd
ntp_monitor.exe -r 10.176.127.84 -s corporate_ntp_servers.csv -f milliseconds -o daily_sync_report.csv
```

## Server List File Formats

### TXT Format

One NTP server hostname or IP address per line:

```
ntp1.example.com
ntp2.example.com
192.168.1.100
time.windows.com
pool.ntp.org
```

### CSV Format

Must include a 'server' column header. Additional columns are ignored:

```csv
server,location,notes,priority
ntp1.example.com,datacenter1,primary,1
ntp2.example.com,datacenter2,backup,2
192.168.1.100,local,internal,3
time.windows.com,external,microsoft,4
```

## Output Format

The program generates two output files for each monitoring run, saved to the configured output directory (default: `.\Reports`):

### 1. XLSX Report
A detailed spreadsheet with comprehensive NTP monitoring data. **Error servers are automatically placed at the top of the list** for immediate attention, followed by successful servers sorted by variance from zero (highest time drift first).

### 2. Summary Text File
A concise summary file with the same name as the XLSX file but with a `.txt` extension, containing:
- Total servers processed
- Success and failure counts
- Status breakdown
- Time delta statistics (min/max/average)

**Example output files**:
- `Reports\ntp_monitor_report_20241230_103000.xlsx` - Detailed XLSX report
- `Reports\ntp_monitor_report_20241230_103000.txt` - Summary text file

### Report Sorting Priority

The XLSX report uses intelligent sorting to prioritize problem servers:

1. **Error Servers First**: Servers with ERROR, TIMEOUT, UNSYNCHRONIZED, or UNREACHABLE status appear at the top
2. **Error Severity**: Error servers are sorted by severity (ERROR > TIMEOUT > UNSYNCHRONIZED > UNREACHABLE)  
3. **Variance Sorting**: Successful servers are sorted by highest absolute time variance
4. **No Delta Last**: Servers without delta calculations appear at the bottom

This ensures that problematic servers requiring immediate attention are always visible at the top of the report.

### XLSX Report Columns

The XLSX report contains the following columns:

| Column | Description |
|--------|-------------|
| `timestamp_utc` | Query timestamp in ISO 8601 UTC format |
| `ntp_server` | NTP server hostname or IP address |
| `ntp_server_ip` | Resolved IP address (if different from hostname) |
| `ntp_time_utc` | NTP server time in ISO 8601 UTC format |
| `query_rtt_ms` | Query round-trip time in milliseconds |
| `stratum` | NTP stratum level |
| `root_delay_ms` | Root delay in milliseconds |
| `root_dispersion_ms` | Root dispersion in milliseconds |
| `delta_value` | Time delta in configured format (seconds/milliseconds) |
| `delta_format` | Format type ('seconds' or 'milliseconds') |
| `status` | Query status (OK, TIMEOUT, ERROR, UNREACHABLE, UNSYNCHRONIZED) |
| `error_message` | Error details for failed queries |

### Sample Output

```csv
timestamp_utc,ntp_server,ntp_server_ip,ntp_time_utc,query_rtt_ms,stratum,root_delay_ms,root_dispersion_ms,delta_value,delta_format,status,error_message
2024-01-15T10:30:00.123Z,ntp1.example.com,192.168.1.10,2024-01-15T10:30:00.125Z,45.2,2,12.5,8.3,0.002,seconds,OK,
2024-01-15T10:30:00.156Z,ntp2.example.com,192.168.1.11,2024-01-15T10:30:00.151Z,38.7,3,15.1,6.7,-0.005,seconds,OK,
2024-01-15T10:30:00.189Z,bad.server.com,,,,,,,,seconds,TIMEOUT,Query timeout after 30 seconds
```

## Summary Statistics

After processing all servers, the program displays a summary including:

- Total servers processed
- Success and failure counts
- Status breakdown (OK, TIMEOUT, ERROR, etc.)
- Time delta statistics (min/max/average) for successful measurements

### Sample Summary

```
============================================================
NTP MONITORING SUMMARY
============================================================
Total servers processed: 25
Successful queries: 23
Failed queries: 2

Status breakdown:
  OK: 23
  TIMEOUT: 1
  UNREACHABLE: 1

Time delta statistics (successful measurements):
  Minimum delta: -0.012 seconds
  Maximum delta: 0.008 seconds
  Average delta: -0.002 seconds
============================================================
```

## Exit Codes

The program returns appropriate exit codes for automation:

- **0**: All servers processed successfully (or only UNREACHABLE failures)
- **Non-zero**: Any ERROR, TIMEOUT, or UNSYNCHRONIZED status encountered

## Troubleshooting

### Common Issues

#### 1. "Server list file not found"
**Problem**: The specified server list file doesn't exist.
**Solution**: 
- Verify the file path is correct
- Use absolute paths if relative paths don't work
- Check file permissions

#### 2. "DNS resolution failed"
**Problem**: Cannot resolve NTP server hostnames.
**Solution**:
- Check network connectivity
- Verify DNS server configuration
- Use IP addresses instead of hostnames
- Check corporate firewall settings

#### 3. "Query timeout after X seconds"
**Problem**: NTP servers are not responding within the timeout period.
**Solution**:
- Increase timeout with `-t` option (e.g., `-t 60`)
- Check network connectivity to NTP servers
- Verify NTP servers are running and accessible
- Check firewall rules for UDP port 123

#### 4. "Permission denied reading server list file"
**Problem**: Insufficient permissions to read the input file.
**Solution**:
- Run as administrator if necessary
- Check file permissions
- Move file to a location with appropriate permissions

#### 5. "Server unsynchronized (stratum 16)"
**Problem**: NTP server is not synchronized to a time source.
**Solution**:
- This is informational - the server is not providing reliable time
- Check NTP server configuration
- Use a different reference server if this is your reference

### Network Requirements

- **Outbound UDP port 123**: Required for NTP queries
- **DNS resolution**: Required for hostname lookups (unless using IP addresses)
- **Internet access**: Required for external NTP servers (pool.ntp.org, time.windows.com, etc.)

### Performance Tuning

#### For Large Server Lists (100+ servers):
```cmd
ntp_monitor.exe -r your.ref.server -s large_list.txt -p 50 -t 15
```

#### For Slow Networks:
```cmd
ntp_monitor.exe -r your.ref.server -s servers.txt -p 5 -t 60
```

#### For Fast Local Networks:
```cmd
ntp_monitor.exe -r your.ref.server -s servers.txt -p 20 -t 5
```

### Verbose Logging

Use the `-v` flag for detailed troubleshooting information:

```cmd
ntp_monitor.exe -r ntp.example.com -s servers.txt -v
```

This provides:
- Detailed NTP query information
- DNS resolution details
- Timing information
- Error details and recovery actions
- Processing statistics

### Corporate Environment Considerations

#### Proxy Servers
The program uses direct UDP connections for NTP queries, which typically bypass HTTP proxies. However, some corporate firewalls may block UDP port 123.

#### Internal NTP Servers
Many organizations run internal NTP servers. Use these as reference servers for better accuracy:
```cmd
ntp_monitor.exe -r internal.ntp.company.com -s server_list.txt
```

#### Firewall Configuration
Ensure the following ports are open:
- **Outbound UDP 123**: For NTP queries
- **Outbound UDP 53**: For DNS resolution (if using hostnames)

## Technical Details

### NTP Protocol
- Uses NTP version 4 protocol
- Queries UDP port 123
- Captures timestamp, RTT, stratum, delays, and dispersion
- Validates server synchronization status

### Time Calculations
- Delta = target_ntp_time - reference_ntp_time
- Positive values: target is ahead of reference
- Negative values: target is behind reference
- Precision: millisecond accuracy for seconds format

### Concurrent Processing
- Uses Python ThreadPoolExecutor for parallel queries
- Configurable worker pool size (1-100 workers)
- Graceful handling of individual server failures
- Maintains processing continuity across errors

## Version Information

**Version**: 1.0.0
**Platform**: Windows
**Python Version**: 3.8+
**Dependencies**: ntplib, dnspython (included in executable)

## Support

For issues, questions, or feature requests, please refer to the project documentation or contact your system administrator.