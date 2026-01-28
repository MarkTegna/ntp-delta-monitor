#!/usr/bin/env python3
"""
NTP Delta Monitor - A Windows-based NTP monitoring program
Queries multiple NTP sources for time synchronization analysis
"""

import argparse
import configparser
import csv
import logging
import ntplib
import socket
import sys
import os
import dns.resolver
import dns.reversename
import smtplib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from enum import Enum
from pathlib import Path
from typing import Optional, List
import statistics
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# Program version
VERSION = "2.4.3"
PROGRAM_NAME = "NTP Delta Monitor"


class NTPStatus(Enum):
    """
    Status enumeration for NTP query results.
    
    Implements error classification system as required by:
    - Requirements 2.5, 8.1, 8.2, 8.3: Different types of NTP failures
    
    Values:
    - OK: Successful NTP query with synchronized server
    - UNREACHABLE: Server cannot be reached (DNS failure, connection refused)
    - TIMEOUT: Query exceeded specified timeout period
    - UNSYNCHRONIZED: Server responded but is not synchronized (stratum >= 16)
    - ERROR: NTP protocol errors or other unexpected failures
    """
    OK = "OK"
    UNREACHABLE = "UNREACHABLE"
    TIMEOUT = "TIMEOUT"
    UNSYNCHRONIZED = "UNSYNCHRONIZED"
    ERROR = "ERROR"


@dataclass
class NTPResponse:
    """Data model for NTP server response"""
    timestamp_utc: datetime
    query_rtt_ms: float
    stratum: int
    root_delay_ms: float
    root_dispersion_ms: float
    is_synchronized: bool
    offset_seconds: float  # NTP offset (time difference accounting for network delay)
    error_message: Optional[str] = None


def format_delta_value(delta_seconds: Optional[float], format_type: str) -> Optional[float]:
    """
    Convert delta value to specified format with appropriate precision.
    
    Args:
        delta_seconds: Delta value in seconds (None if calculation failed)
        format_type: 'seconds' for decimal seconds, 'milliseconds' for integer milliseconds
        
    Returns:
        Formatted delta value according to format_type, None if input is None
    """
    if delta_seconds is None:
        return None
    
    if format_type == 'seconds':
        # Return decimal seconds with millisecond precision (3 decimal places)
        return round(delta_seconds, 3)
    elif format_type == 'milliseconds':
        # Convert to integer milliseconds
        return int(round(delta_seconds * 1000))
    else:
        # Default to seconds format if unknown format specified
        return round(delta_seconds, 3)


@dataclass
class NTPResult:
    """Data model for complete NTP query result"""
    timestamp_utc: datetime
    ntp_server: str
    ntp_server_ip: Optional[str]
    hostname: Optional[str]  # Full hostname from reverse DNS
    short_name: Optional[str]  # Short name (hostname without tgna.tegna.com suffix)
    ntp_time_utc: Optional[datetime]
    query_rtt_ms: Optional[float]
    stratum: Optional[int]
    root_delay_ms: Optional[float]
    root_dispersion_ms: Optional[float]
    delta_seconds: Optional[float]  # vs reference NTP source (raw seconds)
    delta_formatted: Optional[float]  # formatted according to config (seconds/milliseconds)
    status: NTPStatus
    error_message: Optional[str] = None
    is_additional_server: bool = False  # True if from additional servers CSV (excluded from error counts)


@dataclass
class Config:
    """Configuration data model for NTP monitor"""
    reference_ntp: str  # Primary reference NTP source
    ntp_servers_file: Optional[Path]  # Path to NTP server list file (None for auto-discovery)
    additional_servers_file: Optional[Path]  # Path to additional servers CSV file (excluded from error counts)
    output_file: Optional[Path]
    format_type: str  # 'seconds' or 'milliseconds'
    parallel_limit: int
    ntp_timeout: int
    verbose: bool


@dataclass
class SummaryStats:
    """Data model for summary statistics"""
    total_servers: int
    successful_servers: int
    failed_servers: int
    min_delta: Optional[float]
    max_delta: Optional[float]
    avg_delta: Optional[float]
    status_counts: dict  # Count of each status type
    has_errors: bool  # True if any ERROR/TIMEOUT/UNSYNCHRONIZED status


def query_ntp_server(hostname: str, timeout: int = 30) -> NTPResponse:
    """
    Query a single NTP server and return structured response data.
    
    Args:
        hostname: NTP server hostname or IP address
        timeout: Query timeout in seconds
        
    Returns:
        NTPResponse with timestamp, RTT, stratum, delays, and dispersion
        
    Raises:
        Exception: For NTP protocol errors, timeouts, or network issues
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Create NTP client and query server
        ntp_client = ntplib.NTPClient()
        logger.debug(f"Querying NTP server: {hostname} (timeout: {timeout}s)")
        
        # Log timing information for verbose mode
        start_time = datetime.now(timezone.utc)
        
        # Query using NTP version 4
        response = ntp_client.request(hostname, version=4, timeout=timeout)
        
        # Calculate and log timing information
        end_time = datetime.now(timezone.utc)
        query_duration = (end_time - start_time).total_seconds()
        logger.debug(f"NTP query completed in {query_duration:.3f} seconds")
        
        # Convert NTP timestamp to UTC datetime
        timestamp_utc = datetime.fromtimestamp(response.tx_time, tz=timezone.utc)
        
        # Validate timestamp format
        if not validate_timestamp_format(timestamp_utc):
            raise Exception(f"Invalid timestamp format from server: {timestamp_utc}")
        
        # Calculate RTT in milliseconds
        query_rtt_ms = response.delay * 1000.0
        
        # Convert delays and dispersion to milliseconds
        root_delay_ms = response.root_delay * 1000.0
        root_dispersion_ms = response.root_dispersion * 1000.0
        
        # Check if server is synchronized (stratum < 16)
        is_synchronized = response.stratum < 16
        
        # Log detailed NTP query information when verbose
        logger.debug(f"NTP response from {hostname}:")
        logger.debug(f"  Timestamp: {timestamp_utc.isoformat()}")
        logger.debug(f"  Stratum: {response.stratum}")
        logger.debug(f"  RTT: {query_rtt_ms:.2f}ms")
        logger.debug(f"  Root delay: {root_delay_ms:.2f}ms")
        logger.debug(f"  Root dispersion: {root_dispersion_ms:.2f}ms")
        logger.debug(f"  Synchronized: {is_synchronized}")
        logger.debug(f"  Query duration: {query_duration:.3f}s")
        
        ntp_response = NTPResponse(
            timestamp_utc=timestamp_utc,
            query_rtt_ms=query_rtt_ms,
            stratum=response.stratum,
            root_delay_ms=root_delay_ms,
            root_dispersion_ms=root_dispersion_ms,
            is_synchronized=is_synchronized,
            offset_seconds=response.offset,  # NTP offset (accounts for network delay)
            error_message=None
        )
        
        # Validate the response
        status, error_msg = validate_ntp_response(ntp_response)
        if status != NTPStatus.OK:
            ntp_response.error_message = error_msg
            logger.debug(f"NTP response validation failed: {error_msg}")
        else:
            logger.debug(f"NTP response validation successful")
        
        return ntp_response
        
    except ntplib.NTPException as e:
        logger.debug(f"NTP protocol error for {hostname}: {e}")
        raise Exception(f"NTP protocol error: {e}")
    
    except socket.timeout:
        logger.debug(f"Timeout querying NTP server: {hostname} (timeout: {timeout}s)")
        raise Exception(f"Timeout after {timeout} seconds")
    
    except socket.gaierror as e:
        logger.debug(f"DNS resolution failed for {hostname}: {e}")
        raise Exception(f"DNS resolution failed: {e}")
    
    except Exception as e:
        logger.debug(f"Unexpected error querying {hostname}: {e}")
        raise Exception(f"Network error: {e}")


def validate_ntp_response(response: NTPResponse) -> tuple[NTPStatus, Optional[str]]:
    """
    Validate NTP response and determine status.
    
    Args:
        response: NTPResponse object to validate
        
    Returns:
        Tuple of (NTPStatus, error_message)
    """
    # Check for stratum 16+ (unsynchronized) condition
    if response.stratum >= 16:
        return NTPStatus.UNSYNCHRONIZED, f"Server unsynchronized (stratum {response.stratum})"
    
    # Check if response indicates synchronization
    if not response.is_synchronized:
        return NTPStatus.UNSYNCHRONIZED, "Server reports unsynchronized state"
    
    # Response is valid and synchronized
    return NTPStatus.OK, None


def validate_timestamp_format(timestamp: datetime) -> bool:
    """
    Validate that timestamp is properly formatted and in UTC.
    
    Args:
        timestamp: datetime object to validate
        
    Returns:
        True if timestamp is valid UTC datetime, False otherwise
    """
    try:
        # Check if timestamp has timezone info and is UTC
        if timestamp.tzinfo is None:
            return False
        
        if timestamp.tzinfo != timezone.utc:
            return False
        
        # Check if timestamp is reasonable (not too far in past/future)
        now = datetime.now(timezone.utc)
        time_diff = abs((timestamp - now).total_seconds())
        
        # Allow up to 24 hours difference (generous for NTP sync issues)
        if time_diff > 86400:  # 24 hours in seconds
            return False
        
        return True
        
    except (AttributeError, TypeError, ValueError):
        return False


def handle_ntp_query_error(hostname: str, error: Exception, timeout: int) -> tuple[NTPStatus, str]:
    """
    Classify NTP query errors and return appropriate status and message.
    
    This function implements comprehensive error classification as required by:
    - Requirements 2.5: Record appropriate error status and continue with remaining servers
    - Requirements 8.1: Record TIMEOUT status for network timeouts
    - Requirements 8.2: Record UNREACHABLE status for unreachable servers  
    - Requirements 8.3: Record ERROR status with specific error details
    
    Args:
        hostname: NTP server hostname that failed
        error: Exception that occurred during query
        timeout: Timeout value used for the query
        
    Returns:
        Tuple of (NTPStatus, error_message)
    """
    logger = logging.getLogger(__name__)
    error_str = str(error).lower()
    
    # Log error details and recovery actions when verbose
    logger.debug(f"Classifying error for {hostname}: {error}")
    
    # Classify different types of NTP failures with specific error messages
    if "timeout" in error_str:
        status = NTPStatus.TIMEOUT
        message = f"Query timeout after {timeout} seconds"
        logger.debug(f"Recovery action: Continuing with remaining servers after timeout")
        return status, message
    
    elif "dns resolution failed" in error_str or "name resolution" in error_str or "nodename nor servname provided" in error_str:
        status = NTPStatus.UNREACHABLE
        message = f"DNS resolution failed for {hostname}"
        logger.debug(f"Recovery action: Continuing with remaining servers after DNS failure")
        return status, message
    
    elif "connection refused" in error_str or "unreachable" in error_str or "no route to host" in error_str:
        status = NTPStatus.UNREACHABLE
        message = f"Server unreachable: {hostname}"
        logger.debug(f"Recovery action: Continuing with remaining servers after connection failure")
        return status, message
    
    elif "ntp protocol error" in error_str or "invalid ntp response" in error_str:
        status = NTPStatus.ERROR
        message = f"NTP protocol error: {error}"
        logger.debug(f"Recovery action: Continuing with remaining servers after protocol error")
        return status, message
    
    elif "network error" in error_str or "socket error" in error_str:
        status = NTPStatus.ERROR
        message = f"Network communication error: {error}"
        logger.debug(f"Recovery action: Continuing with remaining servers after network error")
        return status, message
    
    elif "invalid timestamp" in error_str or "malformed" in error_str:
        status = NTPStatus.ERROR
        message = f"Invalid NTP response format: {error}"
        logger.debug(f"Recovery action: Continuing with remaining servers after timestamp validation error")
        return status, message
    
    else:
        # Catch-all for any other unexpected errors
        status = NTPStatus.ERROR
        message = f"Unexpected error: {error}"
        logger.debug(f"Recovery action: Continuing with remaining servers after unexpected error")
        return status, message


def parse_server_file(file_path: Path) -> List[str]:
    """
    Auto-detect format and parse server list from TXT or CSV files.
    
    Implements server list parsing as required by:
    - Requirements 7.1: Parse TXT files with each line as NTP server hostname or IP address
    - Requirements 7.2: Parse CSV files expecting a "server" column header
    - Requirements 7.3: Ignore additional columns and process only server column values
    - Requirements 7.4: Terminate with error if file cannot be read
    - Requirements 7.5: Skip empty lines and whitespace-only entries
    
    Args:
        file_path: Path to server list file (.txt or .csv)
        
    Returns:
        List of NTP server hostnames/IPs from the file
        
    Raises:
        SystemExit: If file cannot be read (terminates with error message)
    """
    logger = logging.getLogger(__name__)
    
    try:
        if not file_path.exists():
            logger.error(f"Server list file not found: {file_path}")
            sys.exit(1)
        
        if not file_path.is_file():
            logger.error(f"Server list path is not a file: {file_path}")
            sys.exit(1)
        
        # Auto-detect format based on file extension
        if file_path.suffix.lower() == '.csv':
            logger.info(f"Parsing CSV server list: {file_path}")
            return parse_csv_file(file_path)
        elif file_path.suffix.lower() == '.txt':
            logger.info(f"Parsing TXT server list: {file_path}")
            return parse_txt_file(file_path)
        else:
            # Default to TXT format for unknown extensions
            logger.info(f"Unknown file extension, treating as TXT format: {file_path}")
            return parse_txt_file(file_path)
            
    except Exception as e:
        logger.error(f"Cannot read server list file {file_path}: {e}")
        sys.exit(1)


def parse_txt_file(file_path: Path) -> List[str]:
    """
    Parse line-delimited server list from TXT file.
    
    Args:
        file_path: Path to TXT file
        
    Returns:
        List of NTP server hostnames/IPs, with empty lines and whitespace skipped
    """
    logger = logging.getLogger(__name__)
    servers = []
    
    try:
        logger.debug(f"Opening TXT file for parsing: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Skip empty lines and whitespace-only entries
                server = line.strip()
                if server:
                    servers.append(server)
                    logger.debug(f"Line {line_num}: Added server '{server}'")
                else:
                    logger.debug(f"Line {line_num}: Skipped empty line")
        
        logger.info(f"Parsed {len(servers)} servers from TXT file")
        logger.debug(f"Server list: {', '.join(servers)}")
        return servers
        
    except Exception as e:
        logger.error(f"Error reading TXT file {file_path}: {e}")
        raise


def parse_csv_file(file_path: Path) -> List[str]:
    """
    Parse CSV file expecting a "server" column header.
    
    Args:
        file_path: Path to CSV file
        
    Returns:
        List of NTP server hostnames/IPs from server column, with empty entries skipped
    """
    logger = logging.getLogger(__name__)
    servers = []
    
    try:
        logger.debug(f"Opening CSV file for parsing: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Log available columns for debugging
            logger.debug(f"CSV columns found: {reader.fieldnames}")
            
            # Check if server column exists
            if 'server' not in reader.fieldnames:
                logger.error(f"CSV file missing required 'server' column. Found columns: {reader.fieldnames}")
                raise Exception("Missing 'server' column in CSV file")
            
            # Log additional columns that will be ignored
            additional_columns = [col for col in reader.fieldnames if col != 'server']
            if additional_columns:
                logger.debug(f"Ignoring additional CSV columns: {', '.join(additional_columns)}")
            
            for row_num, row in enumerate(reader, 2):  # Start at 2 since row 1 is header
                # Process only the server column values, ignore additional columns
                server = row.get('server', '').strip()
                if server:
                    servers.append(server)
                    logger.debug(f"Row {row_num}: Added server '{server}'")
                else:
                    logger.debug(f"Row {row_num}: Skipped empty server entry")
        
        logger.info(f"Parsed {len(servers)} servers from CSV file")
        logger.debug(f"Server list: {', '.join(servers)}")
        return servers
        
    except Exception as e:
        logger.error(f"Error reading CSV file {file_path}: {e}")
        raise


def parse_additional_servers_csv(file_path: Path) -> List[tuple]:
    """
    Parse additional servers CSV file with server and optional short_name/location columns.
    Automatically adds missing column headers and writes corrected file back to disk.
    
    Args:
        file_path: Path to CSV file with 'server' and optional 'short_name' or 'location' columns
        
    Returns:
        List of tuples (server, short_name) where short_name uses full server name if not provided
    """
    logger = logging.getLogger(__name__)
    servers = []
    file_needs_correction = False
    
    try:
        logger.debug(f"Opening additional servers CSV file for parsing: {file_path}")
        
        # First, read the file to check its format
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            f.seek(0)  # Reset to beginning
            all_lines = f.readlines()
        
        # Check if the first line looks like headers or data
        has_proper_headers = False
        if first_line and ('server' in first_line.lower() or 'short_name' in first_line.lower()):
            # Try to parse as CSV with headers
            try:
                reader = csv.DictReader(all_lines)
                fieldnames = reader.fieldnames
                if fieldnames and 'server' in fieldnames:
                    has_proper_headers = True
                    logger.debug(f"CSV has proper headers: {fieldnames}")
            except:
                has_proper_headers = False
        
        if not has_proper_headers:
            logger.info(f"CSV file missing proper headers, will add them and rewrite file")
            file_needs_correction = True
            
            # Parse as raw data (no headers)
            raw_servers = []
            for line_num, line in enumerate(all_lines, 1):
                line = line.strip()
                if not line:
                    continue
                
                # Split by comma to handle both single and multi-column formats
                parts = [part.strip() for part in line.split(',')]
                server = parts[0] if parts else ''
                short_name = parts[1] if len(parts) > 1 and parts[1] else ''
                
                if server:
                    raw_servers.append((server, short_name))
                    logger.debug(f"Line {line_num}: Parsed server '{server}' with short name '{short_name}'")
            
            # Write corrected CSV file with proper headers
            logger.info(f"Writing corrected CSV file with headers to: {file_path}")
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                # Write header row
                writer.writerow(['server', 'short_name'])
                # Write data rows
                for server, short_name in raw_servers:
                    writer.writerow([server, short_name])
            
            logger.info(f"Successfully rewrote CSV file with proper headers")
        
        # Now read the file with proper CSV parsing
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Log available columns for debugging
            logger.debug(f"CSV columns found: {reader.fieldnames}")
            
            # Check if server column exists (should exist now after correction)
            if 'server' not in reader.fieldnames:
                logger.error(f"CSV file still missing required 'server' column after correction. Found columns: {reader.fieldnames}")
                raise Exception("Missing 'server' column in CSV file")
            
            # Check if short_name or location column exists
            has_short_name_column = 'short_name' in reader.fieldnames
            has_location_column = 'location' in reader.fieldnames
            
            if has_short_name_column:
                logger.debug("Found 'short_name' column in CSV file")
                name_column = 'short_name'
            elif has_location_column:
                logger.debug("Found 'location' column in CSV file (using as short name)")
                name_column = 'location'
            else:
                logger.debug("No 'short_name' or 'location' column found, will use full server names")
                name_column = None
            
            for row_num, row in enumerate(reader, 2):  # Start at 2 since row 1 is header
                # Process server column
                server = row.get('server', '').strip()
                if not server:
                    logger.debug(f"Row {row_num}: Skipped empty server entry")
                    continue
                
                # Process short_name or location column (optional)
                short_name = None
                if name_column:
                    short_name = row.get(name_column, '').strip()
                
                # If no short_name provided, use the full server name
                # (Don't trim - additional servers should keep their full names)
                if not short_name:
                    short_name = server
                
                servers.append((server, short_name))
                logger.debug(f"Row {row_num}: Added server '{server}' with short name '{short_name}'")
        
        if file_needs_correction:
            logger.info(f"Successfully corrected and re-parsed CSV file with {len(servers)} servers")
        else:
            logger.info(f"Parsed {len(servers)} additional servers from CSV file")
            
        server_list = [f"{server} ({short_name})" for server, short_name in servers]
        logger.debug(f"Additional server list: {', '.join(server_list)}")
        return servers
        
    except Exception as e:
        logger.error(f"Error reading additional servers CSV file {file_path}: {e}")
        raise


def get_all_domain_ips(domain: str, timeout: int = 10) -> List[str]:
    """
    Get all A records (IP addresses) for the specified domain.
    
    Args:
        domain: Domain to query for A records (e.g., 'tgna.tegna.com')
        timeout: DNS query timeout in seconds
        
    Returns:
        List of IP addresses found for the domain
    """
    logger = logging.getLogger(__name__)
    ip_addresses = []
    
    try:
        # Configure DNS resolver with timeout
        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout
        
        logger.info(f"Querying all A records for domain: {domain}")
        
        # Get all A records for the domain
        try:
            answers = resolver.resolve(domain, 'A')
            
            for rdata in answers:
                ip = str(rdata)
                ip_addresses.append(ip)
                logger.debug(f"Found A record: {domain} -> {ip}")
                
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer) as e:
            logger.warning(f"No A records found for domain {domain}: {e}")
            return []
        except dns.resolver.Timeout:
            logger.warning(f"DNS query timeout for domain {domain}")
            return []
        except Exception as e:
            logger.error(f"DNS query error for domain {domain}: {e}")
            return []
        
        if ip_addresses:
            logger.info(f"Found {len(ip_addresses)} A records for {domain}: {', '.join(ip_addresses)}")
        else:
            logger.warning(f"No A records found for domain: {domain}")
            
        return ip_addresses
        
    except Exception as e:
        logger.error(f"Failed to query A records for domain {domain}: {e}")
        return []


def discover_ntp_servers_in_domain(domain: str, timeout: int = 10) -> List[str]:
    """
    Discover NTP servers in the specified domain by getting all A records and using them as potential NTP servers.
    
    Args:
        domain: Domain to search for NTP servers (e.g., 'tgna.tegna.com')
        timeout: DNS query timeout in seconds
        
    Returns:
        List of IP addresses from A records that can be used as NTP servers
    """
    logger = logging.getLogger(__name__)
    
    # Get all A records for the domain
    ip_addresses = get_all_domain_ips(domain, timeout)
    
    if not ip_addresses:
        logger.warning(f"No A records found for domain {domain}")
        return []
    
    logger.info(f"Using all {len(ip_addresses)} A records from {domain} as potential NTP servers")
    
    # Return all IP addresses as potential NTP servers
    # The NTP query process will determine which ones actually provide NTP service
    return ip_addresses


def perform_reverse_dns_lookup(ip_address: str, domain_suffix: str = "tgna.tegna.com", timeout: int = 10) -> tuple[Optional[str], Optional[str]]:
    """
    Perform reverse DNS lookup on an IP address and extract hostname information.
    
    Args:
        ip_address: IP address to perform reverse lookup on
        domain_suffix: Domain suffix to remove for short names (e.g., "tgna.tegna.com")
        timeout: DNS query timeout in seconds
        
    Returns:
        Tuple of (full_hostname, short_name)
        - full_hostname: Complete hostname from reverse DNS
        - short_name: Hostname with domain suffix removed (if applicable)
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Configure DNS resolver with timeout
        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout
        
        # Create reverse DNS query
        reverse_name = dns.reversename.from_address(ip_address)
        
        logger.debug(f"Performing reverse DNS lookup for: {ip_address}")
        
        # Perform reverse DNS lookup
        answers = resolver.resolve(reverse_name, 'PTR')
        
        if answers:
            full_hostname = str(answers[0]).rstrip('.')  # Remove trailing dot
            logger.debug(f"Reverse DNS successful: {ip_address} -> {full_hostname}")
            
            # Extract short name by removing configured domain suffix
            short_name = full_hostname
            domain_suffix_with_dot = f'.{domain_suffix}'
            if full_hostname.endswith(domain_suffix_with_dot):
                short_name = full_hostname[:-len(domain_suffix_with_dot)]
                logger.debug(f"Extracted short name: {short_name}")
            
            return full_hostname, short_name
        else:
            logger.debug(f"No PTR record found for: {ip_address}")
            return None, None
            
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        logger.debug(f"No reverse DNS record found for: {ip_address}")
        return None, None
    except dns.resolver.Timeout:
        logger.debug(f"Reverse DNS timeout for: {ip_address}")
        return None, None
    except Exception as e:
        logger.debug(f"Reverse DNS error for {ip_address}: {e}")
        return None, None


def resolve_hostname_with_fallback(hostname: str, timeout: int = 10) -> tuple[str, Optional[str]]:
    """
    Attempt DNS resolution for hostname with fallback to original hostname.
    
    Args:
        hostname: Hostname or IP address to resolve
        timeout: DNS resolution timeout in seconds
        
    Returns:
        Tuple of (hostname_to_use, resolved_ip_or_none)
    """
    logger = logging.getLogger(__name__)
    
    # If it's already an IP address, return as-is
    try:
        socket.inet_aton(hostname)
        logger.debug(f"Hostname {hostname} is already an IP address")
        return hostname, hostname
    except socket.error:
        pass  # Not an IP address, continue with DNS resolution
    
    try:
        # Configure DNS resolver with timeout
        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout
        
        logger.debug(f"Attempting DNS resolution for: {hostname}")
        answers = resolver.resolve(hostname, 'A')
        
        if answers:
            resolved_ip = str(answers[0])
            logger.debug(f"DNS resolution successful: {hostname} -> {resolved_ip}")
            return hostname, resolved_ip
        else:
            logger.debug(f"DNS resolution returned no answers for: {hostname}")
            return hostname, None
            
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout) as e:
        logger.debug(f"DNS resolution failed for {hostname}: {e}")
        return hostname, None
    except Exception as e:
        logger.debug(f"DNS resolution error for {hostname}: {e}")
        return hostname, None


def calculate_time_delta(target_time: Optional[datetime], reference_time: datetime) -> Optional[float]:
    """
    Calculate signed time delta between target NTP time and reference NTP time.
    
    Args:
        target_time: Target NTP server timestamp (None if query failed)
        reference_time: Reference NTP server timestamp
        
    Returns:
        Delta in seconds (target_time - reference_time), None if target_time is None
        Positive values indicate target is ahead of reference
        Negative values indicate target is behind reference
    """
    if target_time is None:
        return None
    
    # Calculate delta as target_time minus reference_time
    delta_seconds = (target_time - reference_time).total_seconds()
    
    return delta_seconds


def process_single_server(server: str, reference_offset: float, reference_query_time: datetime, config: Config, ini_config: dict, is_additional_server: bool = False, custom_short_name: str = None) -> NTPResult:
    """
    Process a single NTP server with DNS resolution, query, and delta calculation.
    
    Implements graceful failure handling as required by:
    - Requirements 3.5: Continue processing remaining servers on individual failures
    
    Args:
        server: NTP server hostname or IP address
        reference_offset: Reference NTP server offset (from batch query)
        reference_query_time: Wall clock time when reference was queried (unused, kept for compatibility)
        config: Configuration object with timeout and format settings
        
    Returns:
        NTPResult with complete query results and status.
        Always returns a result object, even for failed queries, to maintain processing continuity.
    """
    logger = logging.getLogger(__name__)
    query_timestamp = datetime.now(timezone.utc)
    
    # Attempt DNS resolution with fallback - graceful handling of DNS failures
    hostname_to_use, resolved_ip = resolve_hostname_with_fallback(server, config.ntp_timeout)
    
    # Perform reverse DNS lookup to get hostname information
    full_hostname = None
    short_name = None
    
    # Use custom short name if provided (for additional servers)
    if custom_short_name:
        short_name = custom_short_name
        logger.debug(f"Using custom short name: {custom_short_name}")
    
    if resolved_ip:
        full_hostname, dns_short_name = perform_reverse_dns_lookup(resolved_ip, ini_config['default_discovery_domain'], config.ntp_timeout)
        # Only use DNS-derived short name if no custom short name was provided
        if not custom_short_name:
            short_name = dns_short_name
    
    try:
        # Query the NTP server
        logger.debug(f"Querying NTP server: {server} (using {hostname_to_use})")
        ntp_response = query_ntp_server(hostname_to_use, config.ntp_timeout)
        
        # Calculate delta using NTP offsets
        # The offset from each server tells us how much that server differs from our local clock
        # To find the difference between two servers, we subtract their offsets
        # Delta = target_offset - reference_offset
        # This gives us the time difference between the two NTP servers
        delta_seconds = ntp_response.offset_seconds - reference_offset
        delta_formatted = format_delta_value(delta_seconds, config.format_type)
        logger.debug(f"Delta calculated: {delta_seconds:.6f}s (target offset: {ntp_response.offset_seconds:.6f}s, reference offset: {reference_offset:.6f}s)")
        
        # Determine final status based on validation
        status, error_message = validate_ntp_response(ntp_response)
        
        return NTPResult(
            timestamp_utc=query_timestamp,
            ntp_server=server,
            ntp_server_ip=resolved_ip,
            hostname=full_hostname,
            short_name=short_name,
            ntp_time_utc=ntp_response.timestamp_utc,
            query_rtt_ms=ntp_response.query_rtt_ms,
            stratum=ntp_response.stratum,
            root_delay_ms=ntp_response.root_delay_ms,
            root_dispersion_ms=ntp_response.root_dispersion_ms,
            delta_seconds=delta_seconds,
            delta_formatted=delta_formatted,
            status=status,
            error_message=error_message,
            is_additional_server=is_additional_server
        )
        
    except Exception as e:
        # Graceful failure handling - classify error and return result object
        # This ensures processing continues for remaining servers
        status, error_message = handle_ntp_query_error(server, e, config.ntp_timeout)
        
        logger.debug(f"Server {server} failed with status {status.value}: {error_message}")
        
        return NTPResult(
            timestamp_utc=query_timestamp,
            ntp_server=server,
            ntp_server_ip=resolved_ip,
            hostname=full_hostname,
            short_name=short_name,
            ntp_time_utc=None,
            query_rtt_ms=None,
            stratum=None,
            root_delay_ms=None,
            root_dispersion_ms=None,
            delta_seconds=None,  # No delta calculation for failed queries
            delta_formatted=None,  # No formatted delta for failed queries
            status=status,
            error_message=error_message,
            is_additional_server=is_additional_server
        )


def process_servers_parallel(server_list, reference_server: str, config: Config, ini_config: dict, is_additional_servers: bool = False) -> List[NTPResult]:
    """
    Process multiple NTP servers concurrently using thread pool.
    
    Implements graceful failure handling as required by:
    - Requirements 3.5: Continue processing remaining servers on individual failures
    
    Args:
        server_list: List of NTP server hostnames/IPs (strings) or tuples (server, short_name) for additional servers
        reference_server: Reference NTP server hostname for batch reference query
        config: Configuration object with parallel limits and timeout settings
        is_additional_servers: True if processing additional servers (excludes from error counts)
        
    Returns:
        List of NTPResult objects with query results for all servers.
        Results are collected regardless of individual server errors.
        Processing state is maintained across failures.
    """
    logger = logging.getLogger(__name__)
    results = []
    
    if not server_list:
        logger.warning("No servers to process")
        return results
    
    # Query reference server once at the start of batch processing
    logger.info(f"Querying reference server once for batch: {reference_server}")
    reference_query_time = datetime.now(timezone.utc)
    try:
        reference_response = query_ntp_server(reference_server, config.ntp_timeout)
        reference_offset = reference_response.offset_seconds
        logger.info(f"Reference offset captured: {reference_offset:.6f}s (stratum {reference_response.stratum})")
    except Exception as e:
        logger.error(f"Failed to query reference server {reference_server}: {e}")
        logger.error("Cannot proceed without reference time")
        return results
    
    # Use configured parallel limit, default to 10 if not specified
    max_workers = config.parallel_limit if config.parallel_limit > 0 else 10
    
    logger.info(f"Processing {len(server_list)} servers with {max_workers} concurrent workers")
    
    # Track processing statistics for graceful failure handling
    total_servers = len(server_list)
    completed_servers = 0
    successful_servers = 0
    failed_servers = 0
    
    # Create thread pool and submit all server processing tasks
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks - continue processing even if some fail
        future_to_server = {}
        
        for item in server_list:
            if is_additional_servers and isinstance(item, tuple):
                # Additional servers: (server, short_name)
                server, custom_short_name = item
                future = executor.submit(process_single_server, server, reference_offset, reference_query_time, config, ini_config, is_additional_servers, custom_short_name)
            else:
                # Regular servers: just server string
                server = item
                future = executor.submit(process_single_server, server, reference_offset, reference_query_time, config, ini_config, is_additional_servers)
            
            future_to_server[future] = server if isinstance(item, str) else item[0]
        
        # Collect results as they complete - maintain processing state across failures
        for future in as_completed(future_to_server):
            server = future_to_server[future]
            completed_servers += 1
            
            try:
                result = future.result()
                results.append(result)
                
                # Track success/failure statistics
                if result.status == NTPStatus.OK:
                    successful_servers += 1
                    logger.debug(f"Successfully processed server {completed_servers}/{total_servers}: {server}")
                else:
                    failed_servers += 1
                    logger.debug(f"Server {completed_servers}/{total_servers} failed with status {result.status.value}: {server}")
                    if config.verbose and result.error_message:
                        logger.debug(f"  Error details: {result.error_message}")
                    
            except Exception as e:
                # This should not happen since process_single_server handles all exceptions
                # But we implement graceful handling even for unexpected failures
                failed_servers += 1
                logger.error(f"Unexpected error processing server {completed_servers}/{total_servers} {server}: {e}")
                
                # Create error result for unexpected failures - collect all results regardless of errors
                error_result = NTPResult(
                    timestamp_utc=datetime.now(timezone.utc),
                    ntp_server=server,
                    ntp_server_ip=None,
                    hostname=None,
                    short_name=None,
                    ntp_time_utc=None,
                    query_rtt_ms=None,
                    stratum=None,
                    root_delay_ms=None,
                    root_dispersion_ms=None,
                    delta_seconds=None,
                    delta_formatted=None,
                    status=NTPStatus.ERROR,
                    error_message=f"Unexpected processing error: {e}",
                    is_additional_server=is_additional_servers
                )
                results.append(error_result)
    
    # Log final processing statistics - maintain processing state across failures
    logger.info(f"Completed processing {completed_servers}/{total_servers} servers")
    logger.info(f"Success: {successful_servers}, Failed: {failed_servers}")
    
    if failed_servers > 0:
        logger.info(f"Graceful failure handling: Collected results for all {total_servers} servers despite {failed_servers} failures")
    
    return results


def load_configuration(config_file: str = "ntp_monitor.ini") -> dict:
    """
    Load configuration from INI file with fallback defaults.
    
    Args:
        config_file: Path to configuration file
        
    Returns:
        Dictionary containing configuration values
    """
    logger = logging.getLogger(__name__)
    
    # Default configuration values (used when no INI file exists)
    defaults = {
        'default_reference_server': 'time.cloudflare.com',
        'default_discovery_domain': 'pool.ntp.org',
        'fallback_servers': ['time.google.com', 'time.cloudflare.com', 'time.aws.com', 'time.windows.com'],
        'default_format': 'milliseconds',
        'default_parallel_limit': 10,
        'default_timeout': 30,
        'output_directory': '.\\Reports',
        'sort_by_variance': True,
        'max_variance_display': 100,
        # Email settings
        'send_email': False,
        'smtp_server': '',
        'smtp_port': 25,
        'smtp_use_tls': False,
        'smtp_username': '',
        'smtp_password': '',
        'from_email': '',
        'to_email': '',
        'variance_threshold_ms': 33
    }
    
    config = configparser.ConfigParser()
    
    try:
        if Path(config_file).exists():
            config.read(config_file)
            logger.debug(f"Loaded configuration from {config_file}")
            
            # Extract values from INI file
            if 'ntp_settings' in config:
                ntp_section = config['ntp_settings']
                defaults['default_reference_server'] = ntp_section.get('default_reference_server', defaults['default_reference_server'])
                defaults['default_discovery_domain'] = ntp_section.get('default_discovery_domain', defaults['default_discovery_domain'])
                
                # Parse fallback servers list
                fallback_str = ntp_section.get('fallback_servers', '')
                if fallback_str:
                    defaults['fallback_servers'] = [s.strip() for s in fallback_str.split(',')]
            
            if 'report_settings' in config:
                report_section = config['report_settings']
                defaults['default_format'] = report_section.get('default_format', defaults['default_format'])
                defaults['default_parallel_limit'] = report_section.getint('default_parallel_limit', defaults['default_parallel_limit'])
                defaults['default_timeout'] = report_section.getint('default_timeout', defaults['default_timeout'])
                defaults['output_directory'] = report_section.get('output_directory', defaults['output_directory'])
            
            if 'advanced_settings' in config:
                advanced_section = config['advanced_settings']
                defaults['sort_by_variance'] = advanced_section.getboolean('sort_by_variance', defaults['sort_by_variance'])
                defaults['max_variance_display'] = advanced_section.getint('max_variance_display', defaults['max_variance_display'])
            
            if 'email_settings' in config:
                email_section = config['email_settings']
                defaults['send_email'] = email_section.getboolean('send_email', defaults['send_email'])
                defaults['smtp_server'] = email_section.get('smtp_server', defaults['smtp_server'])
                defaults['smtp_port'] = email_section.getint('smtp_port', defaults['smtp_port'])
                defaults['smtp_use_tls'] = email_section.getboolean('smtp_use_tls', defaults['smtp_use_tls'])
                defaults['smtp_username'] = email_section.get('smtp_username', defaults['smtp_username'])
                defaults['smtp_password'] = email_section.get('smtp_password', defaults['smtp_password'])
                defaults['from_email'] = email_section.get('from_email', defaults['from_email'])
                defaults['to_email'] = email_section.get('to_email', defaults['to_email'])
                defaults['variance_threshold_ms'] = email_section.getfloat('variance_threshold_ms', defaults['variance_threshold_ms'])
                
        else:
            logger.debug(f"Configuration file {config_file} not found, using defaults")
            
    except Exception as e:
        logger.warning(f"Error reading configuration file {config_file}: {e}")
        logger.debug("Using default configuration values")
    
    return defaults


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging system based on verbosity level.
    
    Implements detailed operation logging as required by:
    - Requirements 6.5: Output detailed operation information when verbose logging is enabled
    
    Args:
        verbose: Enable detailed DEBUG level logging if True, INFO level if False
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set specific loggers to appropriate levels
    logger = logging.getLogger(__name__)
    
    if verbose:
        logger.info("Verbose logging enabled - detailed operation information will be displayed")
        logger.debug("Debug logging level activated")
        
        # Enable detailed logging for DNS operations
        dns_logger = logging.getLogger('dns')
        dns_logger.setLevel(logging.WARNING)  # Reduce DNS library noise
        
        # Log configuration details when verbose
        logger.debug("Logging configuration completed")
    else:
        # In non-verbose mode, reduce noise from external libraries
        logging.getLogger('dns').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)


def parse_arguments() -> Config:
    """
    Parse command line arguments and return configuration.
    
    Implements comprehensive CLI argument handling as required by:
    - Requirements 1.1: Support reference NTP parameter
    - Requirements 3.2: Support parallel limit specification (default 10)
    - Requirements 3.4: Support timeout specification (default 30 seconds)
    - Requirements 4.2: Support seconds format for delta values
    - Requirements 4.3: Support milliseconds format for delta values
    
    Returns:
        Config object with validated command line arguments
        
    Raises:
        SystemExit: If argument validation fails or help is requested
    """
    # Load configuration from INI file
    ini_config = load_configuration()
    
    parser = argparse.ArgumentParser(
        description='NTP Delta Monitor - Query multiple NTP servers for time synchronization analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  Default usage (auto-discover NTP servers from {ini_config['default_discovery_domain']}):
    %(prog)s
    
  Basic usage with TXT server list:
    %(prog)s -r ntp1.example.com -s servers.txt
    
  CSV server list with custom output and milliseconds format:
    %(prog)s -r ntp2.example.com -s servers.csv -o report.xlsx -f milliseconds
    
  High concurrency with custom timeout and verbose logging:
    %(prog)s -r 10.43.9.64 -s ntp_list.txt -p 20 -t 10 -v
    
  Milliseconds format with custom output file:
    %(prog)s -r 10.176.127.84 -s servers.csv -f milliseconds -o sync_report.xlsx
    
  Include additional servers for monitoring (excluded from error counts):
    %(prog)s -r ntp1.example.com -s primary_servers.txt --additional-servers monitoring_servers.csv
    
  Auto-detect external_ntp_servers.csv in current directory:
    %(prog)s
    (Will automatically use external_ntp_servers.csv if present)

Server List File Formats:
  TXT format: One NTP server hostname or IP per line
    Example:
      ntp1.example.com
      ntp2.example.com
      192.168.1.100
      
  CSV format: Must have 'server' column header
    Example:
      server,location,notes
      ntp1.example.com,datacenter1,primary
      ntp2.example.com,datacenter2,backup

Additional Servers CSV Format:
  CSV format with 'server' and optional 'short_name' or 'location' columns:
    Example with short_name:
      server,short_name
      10.43.9.64,GPS-KING
      10.176.127.84,GPS-KGW
      pool.ntp.org,
      time.google.com,
    
    Example with location:
      server,location,notes
      pool.ntp.org,NTP Pool,Public NTP server
      10.43.9.64,GPS-KING,TEGNA Real GPS at KING
      time.google.com,time.google.com,GOOGLE domain time default
  
  - First column 'server': NTP server hostname or IP address (required)
  - Second column 'short_name' or 'location': Custom display name (optional)
  - If no display name provided, uses full server name (not trimmed)
  - Additional columns (like 'notes') are ignored
  
  Additional servers are included in reports and statistics but excluded from:
  - Error counts and failure statistics
  - Email alert triggers (NTP ERROR conditions)
  - Exit code determination
  
  Use for monitoring servers that should not trigger alerts when failing.

Default Behavior:
  When no arguments are provided, the program will:
  - Use {ini_config['default_reference_server']} as the reference server
  - Query all A records from the {ini_config['default_discovery_domain']} domain and use them as NTP servers
  - Generate a timestamped XLSX report sorted by variance from zero
        """
    )
    
    # Optional arguments (made reference and servers optional for default behavior)
    parser.add_argument(
        '-r', '--reference-ntp',
        metavar='SERVER',
        help=f'Reference NTP server hostname or IP address for baseline time comparison (default: {ini_config["default_reference_server"]})'
    )
    
    parser.add_argument(
        '-s', '--servers-file',
        type=Path,
        metavar='FILE',
        help=f'Path to NTP server list file (.txt or .csv format) (default: query all A records from {ini_config["default_discovery_domain"]} domain)'
    )
    
    parser.add_argument(
        '--additional-servers',
        type=Path,
        metavar='FILE',
        help='Path to CSV file with additional NTP servers to monitor (included in report but excluded from error counts and alerts). Auto-detects "external_ntp_servers.csv" in current directory if present.'
    )
    
    # Optional arguments with detailed help
    parser.add_argument(
        '-o', '--output-file',
        type=Path,
        metavar='FILE',
        help='Output XLSX file path (default: auto-generated with timestamp pattern "ntp_monitor_report_YYYYMMDD_HHMMSS.xlsx")'
    )
    
    parser.add_argument(
        '-f', '--format',
        choices=['seconds', 'milliseconds'],
        default=ini_config['default_format'],
        metavar='FORMAT',
        help=f'Delta value format: "seconds" for decimal seconds with millisecond precision, "milliseconds" for integer milliseconds [default: {ini_config["default_format"]}]'
    )
    
    parser.add_argument(
        '-p', '--parallel-limit',
        type=int,
        default=ini_config['default_parallel_limit'],
        metavar='N',
        help=f'Maximum number of concurrent NTP queries (1-100) [default: {ini_config["default_parallel_limit"]}]'
    )
    
    parser.add_argument(
        '-t', '--timeout',
        type=int,
        default=ini_config['default_timeout'],
        metavar='SECONDS',
        help=f'NTP query timeout in seconds (1-300) [default: {ini_config["default_timeout"]}]'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging with detailed operation information, timing data, and error details'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'{PROGRAM_NAME} {VERSION}'
    )
    
    args = parser.parse_args()
    
    # Set default values if not provided
    reference_ntp = args.reference_ntp or ini_config['default_reference_server']
    servers_file = args.servers_file
    
    # Auto-detect external_ntp_servers.csv if not specified via CLI
    additional_servers_file = args.additional_servers
    if additional_servers_file is None:
        # Look for external_ntp_servers.csv in current directory
        default_additional_file = Path('external_ntp_servers.csv')
        if default_additional_file.exists() and default_additional_file.is_file():
            additional_servers_file = default_additional_file
            logger = logging.getLogger(__name__)
            logger.debug(f"Auto-detected additional servers file: {default_additional_file}")
    
    # Comprehensive argument validation with detailed error messages
    validation_errors = []
    
    # Validate parallel limit range
    if args.parallel_limit < 1:
        validation_errors.append("Parallel limit must be at least 1")
    elif args.parallel_limit > 100:
        validation_errors.append("Parallel limit cannot exceed 100 (to prevent resource exhaustion)")
    
    # Validate timeout range
    if args.timeout < 1:
        validation_errors.append("Timeout must be at least 1 second")
    elif args.timeout > 300:
        validation_errors.append("Timeout cannot exceed 300 seconds (5 minutes)")
    
    # Validate server list file exists and is readable (only if provided)
    if servers_file:
        if not servers_file.exists():
            validation_errors.append(f"Server list file not found: {servers_file}")
        elif not servers_file.is_file():
            validation_errors.append(f"Server list path is not a file: {servers_file}")
        else:
            try:
                # Test file readability
                with open(servers_file, 'r', encoding='utf-8') as f:
                    f.read(1)  # Try to read first character
            except PermissionError:
                validation_errors.append(f"Permission denied reading server list file: {servers_file}")
            except Exception as e:
                validation_errors.append(f"Cannot read server list file {servers_file}: {e}")
    
    # Validate output file directory exists if specified
    if args.output_file:
        output_dir = args.output_file.parent
        if not output_dir.exists():
            validation_errors.append(f"Output directory does not exist: {output_dir}")
        elif not output_dir.is_dir():
            validation_errors.append(f"Output path parent is not a directory: {output_dir}")
    
    # Validate argument combinations and dependencies
    if args.format not in ['seconds', 'milliseconds']:
        validation_errors.append(f"Invalid format '{args.format}'. Must be 'seconds' or 'milliseconds'")
    
    # Report all validation errors at once
    if validation_errors:
        error_message = "Argument validation failed:\n" + "\n".join(f"  - {error}" for error in validation_errors)
        parser.error(error_message)
    
    return Config(
        reference_ntp=reference_ntp,
        ntp_servers_file=servers_file,
        additional_servers_file=additional_servers_file,
        output_file=args.output_file,
        format_type=args.format,
        parallel_limit=args.parallel_limit,
        ntp_timeout=args.timeout,
        verbose=args.verbose
    )


def query_reference_ntp(reference_server: str, config: Config) -> datetime:
    """
    Query primary reference NTP source at startup and return reference timestamp.
    
    Args:
        reference_server: Reference NTP server hostname or IP address
        config: Configuration object with timeout settings
        
    Returns:
        Reference timestamp in UTC for delta calculations
        
    Raises:
        SystemExit: If reference query fails (terminates program with error)
    """
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Querying reference NTP server: {reference_server}")
        
        # Query the reference NTP server
        ntp_response = query_ntp_server(reference_server, config.ntp_timeout)
        
        # Validate the reference response
        status, error_message = validate_ntp_response(ntp_response)
        
        if status != NTPStatus.OK:
            logger.error(f"Reference NTP server failed validation: {error_message}")
            logger.error("Cannot proceed without valid reference time")
            sys.exit(1)
        
        logger.info(f"Reference NTP query successful: {ntp_response.timestamp_utc.isoformat()}")
        logger.info(f"Reference server stratum: {ntp_response.stratum}, RTT: {ntp_response.query_rtt_ms:.2f}ms")
        
        return ntp_response.timestamp_utc
        
    except Exception as e:
        logger.error(f"Failed to query reference NTP server {reference_server}: {e}")
        logger.error("Cannot proceed without reference time - terminating")
        sys.exit(1)


def generate_default_filename() -> str:
    """
    Generate default filename with UTC timestamp pattern.
    
    Implements filename generation as required by:
    - Requirements 5.2: Generate filename using pattern "ntp_monitor_report_<UTCtimestamp>.xlsx"
    
    Returns:
        Default filename string with UTC timestamp
    """
    # Get current UTC timestamp and format for filename
    utc_now = datetime.now(timezone.utc)
    timestamp_str = utc_now.strftime("%Y%m%d_%H%M%S")
    
    return f"ntp_monitor_report_{timestamp_str}.xlsx"


def sort_results_by_variance(results: List[NTPResult], sort_by_variance: bool = True) -> List[NTPResult]:
    """
    Sort NTP results by variance from zero (highest to lowest absolute delta values).
    Error servers are placed at the top of the list for immediate attention.
    Additional servers are placed at the bottom as a separate section.
    
    Args:
        results: List of NTPResult objects to sort
        sort_by_variance: Whether to sort by variance (True) or keep original order (False)
        
    Returns:
        Sorted list of NTPResult objects with error servers first, then primary servers by variance, then additional servers
    """
    if not sort_by_variance:
        return results
    
    logger = logging.getLogger(__name__)
    logger.debug("Sorting results with error servers first, primary servers by variance, additional servers at bottom")
    
    # Separate primary and additional servers
    primary_results = [r for r in results if not r.is_additional_server]
    additional_results = [r for r in results if r.is_additional_server]
    
    # Sort primary servers: errors first, then by variance
    primary_error_results = []
    primary_results_with_delta = []
    primary_results_without_delta = []
    
    for result in primary_results:
        # Put error servers at the top of the list
        if result.status in [NTPStatus.ERROR, NTPStatus.TIMEOUT, NTPStatus.UNSYNCHRONIZED, NTPStatus.UNREACHABLE]:
            primary_error_results.append(result)
        elif result.delta_seconds is not None:
            primary_results_with_delta.append(result)
        else:
            primary_results_without_delta.append(result)
    
    # Sort primary error results by status severity (ERROR > TIMEOUT > UNSYNCHRONIZED > UNREACHABLE)
    status_priority = {
        NTPStatus.ERROR: 1,
        NTPStatus.TIMEOUT: 2, 
        NTPStatus.UNSYNCHRONIZED: 3,
        NTPStatus.UNREACHABLE: 4
    }
    primary_error_results.sort(key=lambda x: status_priority.get(x.status, 5))
    
    # Sort primary successful results with delta by absolute value (highest variance first)
    primary_results_with_delta.sort(key=lambda x: abs(x.delta_seconds), reverse=True)
    
    # Sort additional servers separately: errors first, then by variance
    additional_error_results = []
    additional_results_with_delta = []
    additional_results_without_delta = []
    
    for result in additional_results:
        if result.status in [NTPStatus.ERROR, NTPStatus.TIMEOUT, NTPStatus.UNSYNCHRONIZED, NTPStatus.UNREACHABLE]:
            additional_error_results.append(result)
        elif result.delta_seconds is not None:
            additional_results_with_delta.append(result)
        else:
            additional_results_without_delta.append(result)
    
    # Sort additional servers the same way as primary servers
    additional_error_results.sort(key=lambda x: status_priority.get(x.status, 5))
    additional_results_with_delta.sort(key=lambda x: abs(x.delta_seconds), reverse=True)
    
    # Combine: primary servers first (errors, then by variance), then additional servers at bottom
    sorted_results = (primary_error_results + primary_results_with_delta + primary_results_without_delta + 
                     additional_error_results + additional_results_with_delta + additional_results_without_delta)
    
    logger.debug(f"Sorted {len(primary_results)} primary servers (errors first, then by variance), {len(additional_results)} additional servers at bottom")
    
    return sorted_results


def write_xlsx_report(results: List[NTPResult], output_path: Path, config: Config, ini_config: dict, reference_server: str) -> None:
    """
    Write NTP monitoring results to XLSX file with all required columns.
    
    Implements XLSX report generation with:
    - Reference server row highlighted in bold blue
    - All required columns including hostname information
    - Formatted headers with styling
    - ISO 8601 UTC timestamp formatting
    - Error status and message recording
    - Overwrite existing files by default
    - Optional sorting by variance from zero
    
    Args:
        results: List of NTPResult objects to write to XLSX
        output_path: Path to output XLSX file
        config: Configuration object with format settings
        ini_config: INI configuration with sorting preferences
        reference_server: Reference NTP server used for delta calculations (for highlighting)
        
    Raises:
        Exception: If XLSX file cannot be written
    """
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Writing XLSX report to: {output_path}")
        
        # Sort results by variance if configured
        sorted_results = sort_results_by_variance(results, ini_config.get('sort_by_variance', True))
        
        # Create a new workbook and worksheet
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = "NTP Monitoring Results"
        
        # Define column headers with hostname information (Hostname column hidden per user request)
        headers = [
            'Timestamp (UTC)',         # Query timestamp in ISO 8601 UTC format
            'NTP Server',              # NTP server hostname/IP
            'Server IP',               # Resolved IP address
            'Short Name',              # Hostname without configured domain suffix
            'NTP Time (UTC)',          # NTP server time in ISO 8601 UTC format
            'RTT (ms)',                # Query round-trip time in milliseconds
            'Stratum',                 # NTP stratum level
            'Root Delay (ms)',         # Root delay in milliseconds
            'Root Dispersion (ms)',    # Root dispersion in milliseconds
            'Delta Value',             # Time delta in configured format
            'Delta Format',            # Format type ('seconds' or 'milliseconds')
            'Status',                  # Query status (OK, TIMEOUT, ERROR, etc.)
            'Error Message'            # Error details for failed queries
        ]
        
        # Write headers with formatting
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")
        
        for col_num, header in enumerate(headers, 1):
            cell = worksheet.cell(row=1, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
        
        # Write data rows (starting from row 2)
        for row_num, result in enumerate(sorted_results, 2):  # Start from row 2 (after headers)
            # Format timestamps in ISO 8601 UTC format
            timestamp_utc_str = result.timestamp_utc.isoformat() if result.timestamp_utc else ''
            ntp_time_utc_str = result.ntp_time_utc.isoformat() if result.ntp_time_utc else ''
            
            # Round RTT, Root Delay, and Root Dispersion to 2 decimal places
            query_rtt_rounded = round(result.query_rtt_ms, 2) if result.query_rtt_ms is not None else ''
            root_delay_rounded = round(result.root_delay_ms, 2) if result.root_delay_ms is not None else ''
            root_dispersion_rounded = round(result.root_dispersion_ms, 2) if result.root_dispersion_ms is not None else ''
            
            # Prepare row data (Hostname column removed per user request)
            row_data = [
                timestamp_utc_str,
                result.ntp_server or '',
                result.ntp_server_ip or '',
                result.short_name or '',
                ntp_time_utc_str,
                query_rtt_rounded,
                result.stratum if result.stratum is not None else '',
                root_delay_rounded,
                root_dispersion_rounded,
                result.delta_formatted if result.delta_formatted is not None else '',
                config.format_type,
                result.status.value,
                result.error_message or ''
            ]
            
            # Write row data
            for col_num, value in enumerate(row_data, 1):
                cell = worksheet.cell(row=row_num, column=col_num, value=value)
                
                # Highlight reference server row in bold blue
                if result.ntp_server == reference_server:
                    cell.font = Font(bold=True, color="0000FF")
                    logger.debug(f"Row {row_num}: Highlighted reference server '{reference_server}'")
        
        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            # Skip merged cells
            try:
                column_letter = column[0].column_letter
            except AttributeError:
                # Skip merged cells
                continue
            
            for cell in column:
                try:
                    # Skip merged cells
                    if hasattr(cell, 'column_letter') and len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            
            # Set column width with some padding
            adjusted_width = min(max_length + 2, 50)  # Cap at 50 characters
            worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # Apply status column and variance highlighting - DIRECT APPROACH ONLY
        status_col = 12  # Status column is now the 12th column (after removing Hostname)
        delta_col = 10   # Delta Value column
        variance_threshold_ms = ini_config.get('variance_threshold_ms', 33)
        
        logger.debug(f"Applying Excel DIRECT formatting with variance threshold: {variance_threshold_ms}ms")
        highlighted_count = 0
        
        # Apply DIRECT cell formatting only (most reliable approach)
        # Data rows start at row 2 (row 1 = headers)
        for row_num in range(2, len(sorted_results) + 2):
            # Status column direct formatting
            status_cell = worksheet.cell(row=row_num, column=status_col)
            if status_cell.value == 'OK':
                status_cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                status_cell.font = Font(bold=True)
            elif status_cell.value in ['ERROR', 'TIMEOUT', 'UNSYNCHRONIZED']:
                status_cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                status_cell.font = Font(bold=True)
            elif status_cell.value == 'UNREACHABLE':
                status_cell.fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
                status_cell.font = Font(bold=True)
            
            # Delta Value column variance highlighting - DIRECT FORMATTING ONLY
            delta_cell = worksheet.cell(row=row_num, column=delta_col)
            if delta_cell.value and isinstance(delta_cell.value, (int, float)):
                delta_value = abs(float(delta_cell.value))
                if delta_value > variance_threshold_ms:
                    try:
                        # Apply VERY STRONG direct formatting that should work everywhere
                        red_fill = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
                        white_font = Font(color="FFFFFF", bold=True, size=12)
                        delta_cell.fill = red_fill
                        delta_cell.font = white_font
                        
                        # Force the cell to be treated as formatted
                        delta_cell.number_format = '0'  # Ensure it's treated as a number
                        
                        highlighted_count += 1
                        logger.info(f"Row {row_num}: DIRECT formatting applied to {delta_value}ms (exceeds {variance_threshold_ms}ms) - Cell: {delta_cell.coordinate}")
                    except Exception as e:
                        logger.error(f"Failed to apply direct formatting to row {row_num}: {e}")
                else:
                    # Apply normal formatting to non-highlighted cells
                    delta_cell.font = Font(bold=False)
                    logger.debug(f"Row {row_num}: Normal formatting {delta_value}ms (within {variance_threshold_ms}ms)")
        
        logger.info(f"Applied DIRECT formatting to {highlighted_count} cells exceeding {variance_threshold_ms}ms threshold")
        
        # Force save with specific Excel format
        try:
            # Save as Excel 2010 format (.xlsx) with explicit formatting preservation
            workbook.save(output_path)
            logger.info(f"Saved Excel file with direct formatting: {output_path}")
            
            # Verify the file was saved correctly by reopening it
            from openpyxl import load_workbook
            test_wb = load_workbook(output_path)
            test_ws = test_wb.active
            
            # Check a few cells to verify formatting was preserved
            verification_count = 0
            for row_num in range(2, min(10, len(sorted_results) + 2)):  # Check first 8 data rows (starting from row 2)
                delta_cell = test_ws.cell(row=row_num, column=delta_col)
                if delta_cell.fill and delta_cell.fill.start_color:
                    color = delta_cell.fill.start_color.rgb if hasattr(delta_cell.fill.start_color, 'rgb') else str(delta_cell.fill.start_color)
                    logger.debug(f"Row {row_num}: Cell color = {color}")
                    # Check for red color in various formats
                    if 'FF0000' in str(color) or 'ff0000' in str(color).lower():
                        verification_count += 1
                        logger.info(f"Row {row_num}: Verified red formatting - color = {color}")
            
            logger.info(f"Verification: Found {verification_count} cells with red formatting in saved file")
            test_wb.close()
            
        except Exception as e:
            logger.error(f"Error during save/verification: {e}")
            # Still try to save the file even if verification fails
            workbook.save(output_path)
        
        # Save the workbook
        workbook.save(output_path)
        
        logger.info(f"Successfully wrote {len(sorted_results)} results to XLSX file: {output_path}")
        
    except Exception as e:
        logger.error(f"Failed to write XLSX report to {output_path}: {e}")
        raise Exception(f"XLSX write error: {e}")


def get_output_file_path(config: Config, ini_config: dict) -> Path:
    """
    Determine output file path based on configuration.
    
    Implements filename generation as required by:
    - Requirements 5.2: Generate default filename with UTC timestamp pattern when not specified
    - Requirements 5.5: Handle custom output path specification
    - Uses configurable output directory from INI settings
    
    Args:
        config: Configuration object with output_file setting
        ini_config: INI configuration with output_directory setting
        
    Returns:
        Path object for output XLSX file
    """
    if config.output_file:
        # Use custom output path specification
        return config.output_file
    else:
        # Get output directory from configuration
        output_dir = Path(ini_config.get('output_directory', '.\\Reports'))
        
        # Create output directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate default filename with UTC timestamp pattern (XLSX format)
        default_filename = generate_default_filename().replace('.csv', '.xlsx')
        
        # Combine directory and filename
        return output_dir / default_filename


def calculate_statistics(results: List[NTPResult]) -> SummaryStats:
    """
    Calculate min/max/avg delta values for successful measurements and count success/failure rates.
    Additional servers (is_additional_server=True) are excluded from error counts but included in delta statistics.
    
    Implements statistical calculation as required by:
    - Requirements 6.1: Display summary showing total servers processed and success/failure counts
    - Requirements 6.2: Calculate and display minimum, maximum, and average Delta_Value statistics
    
    Args:
        results: List of NTPResult objects from server processing
        
    Returns:
        SummaryStats object with calculated statistics (excluding additional servers from error counts)
    """
    logger = logging.getLogger(__name__)
    
    # Separate primary servers from additional servers for error counting
    primary_results = [r for r in results if not r.is_additional_server]
    
    total_servers = len(primary_results)  # Only count primary servers
    successful_servers = 0
    failed_servers = 0
    
    # Count servers by status type (primary servers only for error counts)
    status_counts = {}
    for status in NTPStatus:
        status_counts[status.value] = 0
    
    # Track if we have any error conditions for exit code determination (primary servers only)
    has_errors = False
    
    # Process primary servers for error counts and status tracking
    for result in primary_results:
        # Count by status
        status_counts[result.status.value] += 1
        
        if result.status == NTPStatus.OK:
            successful_servers += 1
        else:
            failed_servers += 1
            # Check for error conditions that should cause non-zero exit code
            if result.status in [NTPStatus.ERROR, NTPStatus.TIMEOUT, NTPStatus.UNSYNCHRONIZED]:
                has_errors = True
    
    # Collect delta values from ALL servers (including additional) for statistical calculations
    successful_deltas = []
    for result in results:
        if result.status == NTPStatus.OK and result.delta_seconds is not None:
            successful_deltas.append(result.delta_seconds)
    
    # Calculate min/max/avg delta values for successful measurements using absolute values
    min_delta = None
    max_delta = None
    avg_delta = None
    
    if successful_deltas:
        # Use absolute values for min/max/avg calculations
        abs_deltas = [abs(delta) for delta in successful_deltas]
        min_delta = min(abs_deltas)
        max_delta = max(abs_deltas)
        avg_delta = statistics.mean(abs_deltas)
        
        logger.debug(f"Delta statistics calculated from {len(successful_deltas)} successful measurements using absolute values")
        logger.debug(f"Statistics include {len([r for r in results if r.is_additional_server and r.status == NTPStatus.OK])} additional servers")
    else:
        logger.debug("No successful measurements available for delta statistics")
    
    return SummaryStats(
        total_servers=total_servers,
        successful_servers=successful_servers,
        failed_servers=failed_servers,
        min_delta=min_delta,
        max_delta=max_delta,
        avg_delta=avg_delta,
        status_counts=status_counts,
        has_errors=has_errors
    )


def format_summary(stats: SummaryStats, config: Config, ini_config: dict, results: List[NTPResult]) -> str:
    """
    Generate end-of-run summary text with statistics.
    
    Args:
        stats: SummaryStats object with calculated statistics
        config: Configuration object with format settings
        ini_config: INI configuration with threshold settings
        results: List of NTPResult objects for threshold analysis
        
    Returns:
        Formatted summary string for display
    """
    summary_lines = []
    
    # Overall processing summary
    summary_lines.append("=" * 60)
    summary_lines.append("NTP MONITORING SUMMARY")
    summary_lines.append("=" * 60)
    
    # Add execution environment information
    summary_lines.append(f"Hostname: {socket.gethostname()}")
    summary_lines.append(f"Execution path: {os.getcwd()}")
    summary_lines.append(f"Program: {PROGRAM_NAME} v{VERSION}")
    summary_lines.append("")
    
    summary_lines.append(f"Total servers processed: {stats.total_servers}")
    summary_lines.append(f"Successful queries: {stats.successful_servers}")
    summary_lines.append(f"Failed queries: {stats.failed_servers}")
    
    # Status breakdown
    if stats.failed_servers > 0:
        summary_lines.append("")
        summary_lines.append("Status breakdown:")
        for status_name, count in stats.status_counts.items():
            if count > 0:
                summary_lines.append(f"  {status_name}: {count}")
    
    # Variance threshold analysis
    variance_threshold_ms = ini_config.get('variance_threshold_ms', 33)
    exceeding_count = 0
    
    # Count servers exceeding variance threshold (exclude reference server and additional servers)
    reference_server = config.reference_ntp
    for result in results:
        # Exclude reference server and additional servers from threshold counting
        if (result.status == NTPStatus.OK and 
            result.delta_seconds is not None and 
            result.ntp_server != reference_server and
            not result.is_additional_server):
            # Use same rounding logic as Excel formatting for consistency
            delta_ms = int(round(abs(result.delta_seconds) * 1000))  # Convert to integer milliseconds like Excel
            if delta_ms > variance_threshold_ms:
                exceeding_count += 1
    
    summary_lines.append("")
    summary_lines.append("Variance threshold analysis:")
    summary_lines.append(f"  Threshold: {variance_threshold_ms} milliseconds")
    summary_lines.append(f"  Servers exceeding threshold: {exceeding_count}")
    if stats.successful_servers > 0:
        percentage = (exceeding_count / stats.successful_servers) * 100
        summary_lines.append(f"  Percentage exceeding: {percentage:.1f}%")
    
    # Delta statistics for successful measurements
    if stats.min_delta is not None and stats.max_delta is not None and stats.avg_delta is not None:
        summary_lines.append("")
        summary_lines.append("Time delta statistics (successful measurements):")
        
        if config.format_type == 'seconds':
            summary_lines.append(f"  Minimum delta: {stats.min_delta:.3f} seconds")
            summary_lines.append(f"  Maximum delta: {stats.max_delta:.3f} seconds")
            summary_lines.append(f"  Average delta: {stats.avg_delta:.3f} seconds")
        else:  # milliseconds
            min_ms = stats.min_delta * 1000
            max_ms = stats.max_delta * 1000
            avg_ms = stats.avg_delta * 1000
            summary_lines.append(f"  Minimum delta: {min_ms:.0f} milliseconds")
            summary_lines.append(f"  Maximum delta: {max_ms:.0f} milliseconds")
            summary_lines.append(f"  Average delta: {avg_ms:.0f} milliseconds")
    else:
        summary_lines.append("")
        summary_lines.append("No successful measurements available for delta statistics")
    
    summary_lines.append("=" * 60)
    
    return "\n".join(summary_lines)


def write_summary_file(summary_text: str, output_path: Path) -> None:
    """
    Write NTP monitoring summary to a text file.
    
    Args:
        summary_text: Formatted summary text to write
        output_path: Path to the XLSX output file (used to generate summary filename)
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Generate summary filename based on XLSX filename
        summary_path = output_path.with_suffix('.txt')
        
        logger.info(f"Writing summary to: {summary_path}")
        
        # Write summary text to file
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary_text)
            f.write('\n')  # Ensure file ends with newline
        
        logger.info(f"Successfully wrote summary to: {summary_path}")
        
    except Exception as e:
        logger.error(f"Failed to write summary file {summary_path}: {e}")
        # Don't raise exception - summary file is not critical


def send_email_notification(summary_text: str, xlsx_path: Path, txt_path: Path, stats: SummaryStats, ini_config: dict, results: List[NTPResult], reference_server: str) -> None:
    """
    Send email notification with NTP monitoring results.
    
    Args:
        summary_text: Formatted summary text for email body
        xlsx_path: Path to XLSX report file for attachment
        txt_path: Path to summary text file
        stats: Summary statistics for subject line generation
        ini_config: INI configuration with email settings
        results: List of NTPResult objects for threshold analysis
        reference_server: Reference NTP server hostname for exclusion from counts
    """
    logger = logging.getLogger(__name__)
    
    # Check if email is enabled
    if not ini_config.get('send_email', False):
        logger.debug("Email notifications disabled in configuration")
        return
    
    try:
        # Determine if this is an error condition based on variance threshold
        variance_threshold_ms = ini_config.get('variance_threshold_ms', 33)
        has_error = False
        max_delta_abs = 0.0
        exceeding_count = 0
        
        # Count servers exceeding variance threshold (exclude reference server and additional servers)
        for result in results:
            # Exclude reference server and additional servers from threshold counting
            if (result.status == NTPStatus.OK and 
                result.delta_seconds is not None and 
                result.ntp_server != reference_server and
                not result.is_additional_server):
                # Use same rounding logic as Excel formatting for consistency
                delta_ms = int(round(abs(result.delta_seconds) * 1000))  # Convert to integer milliseconds like Excel
                if delta_ms > variance_threshold_ms:
                    exceeding_count += 1
        
        if stats.max_delta is not None:
            # stats.max_delta is already the maximum absolute value from calculate_statistics
            max_delta_abs = stats.max_delta
            # Convert to milliseconds for comparison with threshold
            max_delta_ms = max_delta_abs * 1000
            has_error = max_delta_ms > variance_threshold_ms
        
        # Also set error flag if any servers are not responding
        if stats.failed_servers > 0:
            has_error = True
        
        # Generate subject line
        domain_name = ini_config.get('default_discovery_domain', 'unknown')
        failed_count = stats.failed_servers
        
        if has_error:
            subject_prefix = "NTP ERROR"
        else:
            subject_prefix = "NTP REPORT"
        
        # Format delta section for subject - enhanced logic for threshold exceeded
        if exceeding_count > 0:
            # When servers exceed threshold, show "MAX DELTA EXCEEDED" with count
            delta_section = f"MAX DELTA EXCEEDED ({exceeding_count} servers)"
        else:
            # When no servers exceed threshold, show traditional "Max Delta" format
            if stats.max_delta is not None:
                if ini_config.get('default_format', 'seconds') == 'milliseconds':
                    max_delta_str = f"{max_delta_abs * 1000:.0f}ms"
                else:
                    max_delta_str = f"{max_delta_abs:.3f}s"
            else:
                max_delta_str = "N/A"
            delta_section = f"Max Delta: {max_delta_str}"
        
        # Format server status for subject
        if failed_count == 0:
            server_status = "all servers responding"
        else:
            server_status = f"{failed_count} servers not responding"
        
        subject = f"{subject_prefix} {domain_name} - {delta_section} - {server_status}"
        
        logger.info(f"Sending email notification: {subject}")
        
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = ini_config.get('from_email', 'ntp-monitor@tgna.tegna.com')
        msg['To'] = ini_config.get('to_email', 'moldham@tegna.com')
        msg['Subject'] = subject
        
        # Set high importance for error conditions
        if has_error:
            msg['X-Priority'] = '1'  # High priority (1=High, 3=Normal, 5=Low)
            msg['X-MSMail-Priority'] = 'High'  # Microsoft Outlook priority
            msg['Importance'] = 'High'  # Standard importance header
        
        # Use summary text as email body
        msg.attach(MIMEText(summary_text, 'plain'))
        
        # Attach XLSX file
        if xlsx_path.exists():
            with open(xlsx_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {xlsx_path.name}'
                )
                msg.attach(part)
            logger.debug(f"Attached XLSX file: {xlsx_path.name}")
        else:
            logger.warning(f"XLSX file not found for attachment: {xlsx_path}")
        
        # Send email
        smtp_server = ini_config.get('smtp_server', 'relay.tgna.tegna.com')
        smtp_port = ini_config.get('smtp_port', 25)
        smtp_use_tls = ini_config.get('smtp_use_tls', False)
        smtp_username = ini_config.get('smtp_username', '')
        smtp_password = ini_config.get('smtp_password', '')
        
        logger.debug(f"Connecting to SMTP server: {smtp_server}:{smtp_port}")
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if smtp_use_tls:
                server.starttls()
                logger.debug("Started TLS encryption")
            
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
                logger.debug("Authenticated with SMTP server")
            
            server.send_message(msg)
            logger.info(f"Email sent successfully to {msg['To']}")
        
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")
        # Don't raise exception - email failure shouldn't crash the program


def determine_exit_code(stats: SummaryStats) -> int:
    """
    Determine appropriate exit code based on processing results.
    
    Implements exit code logic as required by:
    - Requirements 6.3: Return 0 for all-success scenarios
    - Requirements 6.4: Return non-zero for any ERROR/TIMEOUT/UNSYNCHRONIZED status
    
    Args:
        stats: SummaryStats object with processing results
        
    Returns:
        Exit code: 0 for success, non-zero for failures
    """
    logger = logging.getLogger(__name__)
    
    if stats.has_errors:
        # Non-zero exit code for any ERROR/TIMEOUT/UNSYNCHRONIZED status
        logger.debug("Exit code: 1 (errors detected)")
        return 1
    elif stats.successful_servers == stats.total_servers:
        # All servers processed successfully
        logger.debug("Exit code: 0 (all servers successful)")
        return 0
    else:
        # Some servers failed but no critical errors
        # This handles UNREACHABLE status which is not considered a critical error
        logger.debug("Exit code: 0 (no critical errors)")
        return 0


def main():
    """
    Main entry point for NTP Delta Monitor.
    
    Implements main execution flow as required by:
    - Requirements 1.1, 3.1, 5.1, 6.1: Parse arguments, initialize config, execute reference query,
      process target servers concurrently, generate CSV report and summary statistics
    """
    try:
        # Load INI configuration
        ini_config = load_configuration()
        
        # Parse command line arguments
        config = parse_arguments()
        
        # Setup logging
        setup_logging(config.verbose)
        
        logger = logging.getLogger(__name__)
        logger.info("NTP Delta Monitor starting...")
        logger.info(f"Reference NTP: {config.reference_ntp}")
        
        if config.ntp_servers_file:
            logger.info(f"Server list file: {config.ntp_servers_file}")
        else:
            logger.info(f"Server discovery: Querying all A records from {ini_config['default_discovery_domain']} domain")
            
        logger.info(f"Parallel limit: {config.parallel_limit}")
        logger.info(f"Timeout: {config.ntp_timeout}s")
        logger.info(f"Format: {config.format_type}")
        
        # Initialize configuration and validate inputs
        if config.verbose:
            logger.info("Configuration validation completed successfully")
        
        # Validate reference server is accessible (but don't store time to avoid drift)
        logger.info(f"Validating reference NTP server: {config.reference_ntp}")
        try:
            test_response = query_ntp_server(config.reference_ntp, config.ntp_timeout)
            status, error_message = validate_ntp_response(test_response)
            if status != NTPStatus.OK:
                logger.error(f"Reference NTP server failed validation: {error_message}")
                logger.error("Cannot proceed without valid reference server")
                sys.exit(1)
            logger.info(f"Reference server validation successful: stratum {test_response.stratum}")
        except Exception as e:
            logger.error(f"Failed to validate reference NTP server {config.reference_ntp}: {e}")
            logger.error("Cannot proceed without accessible reference server")
            sys.exit(1)
        
        # Parse NTP server list from file or auto-discover
        if config.ntp_servers_file:
            # Use provided server list file
            ntp_servers = parse_server_file(config.ntp_servers_file)
        else:
            # Auto-discover NTP servers by getting all A records from configured domain
            logger.info(f"No server list file provided - querying all A records from {ini_config['default_discovery_domain']} domain")
            ntp_servers = discover_ntp_servers_in_domain(ini_config['default_discovery_domain'], config.ntp_timeout)
            
            if not ntp_servers:
                logger.warning(f"No A records found for {ini_config['default_discovery_domain']} domain, using fallback servers")
                # Use fallback servers from INI configuration
                ntp_servers = ini_config['fallback_servers']
                logger.info(f"Using fallback server list: {', '.join(ntp_servers)}")
        
        if not ntp_servers:
            logger.error("No NTP servers available for monitoring")
            return 1
        
        logger.info(f"Loaded {len(ntp_servers)} NTP servers for monitoring")
        
        # Process target NTP servers concurrently
        logger.info("Processing target NTP servers...")
        results = process_servers_parallel(ntp_servers, config.reference_ntp, config, ini_config)
        
        # Process additional servers if specified (excluded from error counts)
        if config.additional_servers_file:
            logger.info(f"Processing additional NTP servers from: {config.additional_servers_file}")
            try:
                # Use specialized parser for additional servers CSV with short names
                additional_servers = parse_additional_servers_csv(config.additional_servers_file)
                if additional_servers:
                    logger.info(f"Loaded {len(additional_servers)} additional NTP servers for monitoring")
                    additional_results = process_servers_parallel(additional_servers, config.reference_ntp, config, ini_config, is_additional_servers=True)
                    results.extend(additional_results)
                    logger.info(f"Combined results: {len(results)} total servers ({len(ntp_servers)} primary + {len(additional_servers)} additional)")
                else:
                    logger.warning(f"No additional servers found in {config.additional_servers_file}")
            except Exception as e:
                logger.error(f"Failed to process additional servers file {config.additional_servers_file}: {e}")
                logger.info("Continuing with primary servers only")
        
        # Generate XLSX report
        output_path = get_output_file_path(config, ini_config)
        write_xlsx_report(results, output_path, config, ini_config, config.reference_ntp)
        
        # Generate summary statistics
        stats = calculate_statistics(results)
        summary_text = format_summary(stats, config, ini_config, results)
        
        # Write summary to text file
        write_summary_file(summary_text, output_path)
        
        # Send email notification if enabled
        txt_path = output_path.with_suffix('.txt')
        send_email_notification(summary_text, output_path, txt_path, stats, ini_config, results, config.reference_ntp)
        
        # Display end-of-run summary
        print(summary_text)
        
        # Determine appropriate exit code
        exit_code = determine_exit_code(stats)
        
        if exit_code == 0:
            logger.info("NTP monitoring completed successfully")
        else:
            logger.warning("NTP monitoring completed with errors")
        
        return exit_code
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 1
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())