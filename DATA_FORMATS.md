# Data Formats Reference

Author: Mark Oldham

This document describes the CSV input formats and XLSX output layouts for all monitoring programs.

---

## NTP Delta Monitor

### Input: external_ntp_servers.csv

Additional NTP servers to monitor (excluded from error counts and alerts).

| Column | Required | Default | Description |
|--------|----------|---------|-------------|
| server | Yes | - | NTP server hostname or IP address |
| short_name | No | server value | Display name |
| failure_count | No | 0 | Consecutive failure count (resets on success) |
| missed | No | 0 | Total connection error count |
| failed | No | ok | Status: 'ok' or 'failed' (failed when missed >= 10) |
| dlist | No | none | Distribution list email address |
| time | No | 0 | Consecutive variance threshold violations |

Backward compatible with 2-column (server, short_name) format. Missing columns auto-default.

### Output: XLSX Report (24 columns)

| # | Column | Description |
|---|--------|-------------|
| 1 | Timestamp (UTC) | Query timestamp ISO 8601 |
| 2 | NTP Server | Hostname or IP queried |
| 3 | Server IP | Resolved IP address |
| 4 | Short Name | Display name (hostname without domain suffix) |
| 5 | NTP Time (UTC) | Server's reported time |
| 6 | RTT (ms) | Round-trip time in milliseconds |
| 7 | Stratum | NTP stratum level |
| 8 | Root Delay (ms) | Root delay |
| 9 | Root Dispersion (ms) | Root dispersion |
| 10 | Delta Value | Time difference from reference (ms or seconds) |
| 11 | Delta Format | 'seconds' or 'milliseconds' |
| 12 | Leap Indicator | Leap second warning (0=none, 1=+1s, 2=-1s, 3=unsync) |
| 13 | Precision | Clock precision as power of 2 |
| 14 | Reference ID | Upstream source (ASCII for stratum 1, IP for 2+) |
| 15 | Reference Time (UTC) | When clock was last corrected |
| 16 | Poll Interval (s) | Polling frequency in seconds |
| 17 | Kerberos KDC | OK, KRB_ONLY, NO_RESPONSE |
| 18 | DNS Service | OK, NO_RESPONSE, INVALID |
| 19 | LDAP | OK, NO_RESPONSE |
| 20 | LDAPS | OK, NO_RESPONSE |
| 21 | LDAPS Cert Expiry | Certificate expiration date (YYYY-MM-DD) |
| 22 | Failure Count | Consecutive failure count |
| 23 | Status | OK, TIMEOUT, ERROR, UNREACHABLE, UNSYNCHRONIZED |
| 24 | Error Message | Error details for failed queries |

**Formatting:**
- Status OK: green background
- Status ERROR/TIMEOUT/UNSYNCHRONIZED: red background
- Status UNREACHABLE: yellow background
- Delta exceeding variance threshold: red with white text
- Kerberos/DNS/LDAP/LDAPS OK: green; failures: red
- Non-OK rows sorted to top
- Top row frozen, auto-filter enabled

---

## Certificate Expiry Monitor

### Input: cert_servers.csv

| Column | Required | Default | Description |
|--------|----------|---------|-------------|
| server | Yes | - | Hostname or IP to check |
| port | No | 443 | HTTPS port number |
| short_name | No | server value | Display name |

### Output: XLSX Report (11 columns)

| # | Column | Description |
|---|--------|-------------|
| 1 | Timestamp (UTC) | Check timestamp ISO 8601 |
| 2 | Server | Hostname or IP checked |
| 3 | Port | Port number |
| 4 | Short Name | Display name |
| 5 | Server IP | Resolved IP address |
| 6 | Cert Expiry | Expiration date (YYYY-MM-DD) |
| 7 | Days Remaining | Days until expiration (negative = expired) |
| 8 | Subject | Certificate subject fields |
| 9 | Issuer | Certificate issuer fields |
| 10 | Status | OK, NO_RESPONSE, SSL_ERROR, ERROR |
| 11 | Error Message | Error details |

**Formatting:**
- Days Remaining <= critical_days (default 7): red with white text
- Days Remaining <= warning_days (default 30): yellow
- Days Remaining > warning_days: green
- Status OK: green; non-OK: red
- Top row frozen, auto-filter enabled
- Auto-filter preset: Days Remaining < filter_days, Issuer matches configured strings
- Non-matching rows hidden (user can modify filter)

**Fallback Port Scanning:**
- When port 443 fails, tries fallback_ports (default: 8080, 8443, 3389)
- Successful alternate port results added to report
- Source CSV auto-updated with new server+port entries

---

## DNS Response Monitor

### Input: dns_servers.csv

Additional DNS servers to test beyond auto-discovered domain controllers.

| Column | Required | Default | Description |
|--------|----------|---------|-------------|
| server | Yes | - | DNS server hostname or IP |
| short_name | No | server value | Display name |

### Output: XLSX Report (14 columns)

| # | Column | Description |
|---|--------|-------------|
| 1 | Server | DNS server hostname or IP |
| 2 | Server IP | IP address |
| 3 | Short Name | Display name |
| 4 | Total Queries | Number of queries sent |
| 5 | Successful | Queries that got valid responses |
| 6 | Failed | Queries that timed out or errored |
| 7 | Failure Rate % | Percentage of failed queries |
| 8 | Min (ms) | Fastest response time |
| 9 | Max (ms) | Slowest response time |
| 10 | Avg (ms) | Average response time |
| 11 | Median (ms) | Median response time |
| 12 | StdDev (ms) | Standard deviation |
| 13 | Status | OK, SLOW, DEGRADED, FAILED |
| 14 | Sample Errors | First 3 error messages |

**Status Classification:**
- OK: 0% failure rate and avg <= variance_threshold_ms
- SLOW: 0% failure rate but avg > variance_threshold_ms
- DEGRADED: Some failures but not 100%
- FAILED: 100% failure rate

**Formatting:**
- Status OK: green
- Status SLOW: yellow
- Status DEGRADED/FAILED: red
- Avg response > threshold: red with white text
- Failure Rate > 0: red background
- Sorted: FAILED, DEGRADED, SLOW, OK (alphabetical within each group)
- Top row frozen, auto-filter enabled

**Performance Features:**
- Parallel queries per iteration (ThreadPoolExecutor)
- Servers removed from rotation after skip_after_failures consecutive failures
- Parallel reverse DNS lookups during discovery

---

## INI Configuration Files

### ntp_monitor.ini

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| ntp_settings | default_reference_server | time.cloudflare.com | Primary reference NTP server |
| ntp_settings | default_discovery_domain | tgna.tegna.com | Domain for DC auto-discovery |
| ntp_settings | fallback_servers | time.google.com,... | Fallback NTP servers |
| report_settings | default_format | milliseconds | Delta format |
| report_settings | default_parallel_limit | 10 | Max concurrent queries |
| report_settings | default_timeout | 30 | NTP query timeout (seconds) |
| report_settings | output_directory | .\Reports | Report output directory |
| advanced_settings | sort_by_variance | true | Sort by variance from zero |
| advanced_settings | skip_threshold | 10 | Skip additional servers after N failures |
| email_settings | send_email | false | Enable email notifications |
| email_settings | variance_threshold_ms | 33 | Delta threshold for error flagging |

### cert_monitor.ini

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| monitor_settings | default_parallel_limit | 10 | Max concurrent checks |
| monitor_settings | default_timeout | 10 | Connection timeout (seconds) |
| monitor_settings | warning_days | 30 | Days before expiry for warning |
| monitor_settings | critical_days | 7 | Days before expiry for critical |
| monitor_settings | filter_days | 30 | Auto-filter threshold |
| monitor_settings | filter_issuers | Tegna... | Issuer filter substrings |
| monitor_settings | fallback_ports | 8080,8443,3389 | Ports to try when 443 fails |
| monitor_settings | output_directory | .\Reports | Report output directory |
| email_settings | send_email | false | Enable email notifications |

### dns_monitor.ini

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| dns_settings | default_discovery_domain | tgna.tegna.com | Domain for DC auto-discovery |
| dns_settings | fallback_servers | 8.8.8.8,... | Fallback DNS servers |
| dns_settings | query_domain | ntp1.tgna.tegna.com | Domain to query for testing |
| monitor_settings | default_iterations | 100 | Test iterations per server |
| monitor_settings | default_timeout | 2 | DNS query timeout (seconds) |
| monitor_settings | default_parallel_limit | 10 | Max concurrent workers |
| monitor_settings | variance_threshold_ms | 50 | Avg response threshold (ms) |
| monitor_settings | skip_after_failures | 5 | Remove server after N failures |
| monitor_settings | output_directory | .\Reports | Report output directory |
| email_settings | send_email | false | Enable email notifications |
