#!/usr/bin/env python3
"""
Certificate Expiry Monitor - A Windows-based HTTPS certificate monitoring program
Checks SSL/TLS certificate expiration dates for a list of servers

Author: Mark Oldham
"""

import argparse
import configparser
import csv
import logging
import os
import smtplib
import socket
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional, List

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

# Program version
VERSION = "0.3.0"
PROGRAM_NAME = "Certificate Expiry Monitor"
__author__ = "Mark Oldham"
__compile_date__ = "2026-09-29"


@dataclass
class CertResult:
    """Data model for certificate check result"""
    timestamp_utc: datetime
    server: str
    port: int
    short_name: str
    server_ip: Optional[str]
    status: str  # OK, NO_RESPONSE, SSL_ERROR, ERROR
    cert_expiry: Optional[str]  # YYYY-MM-DD
    days_remaining: Optional[int]
    cert_subject: Optional[str]
    cert_issuer: Optional[str]
    error_message: Optional[str] = None


@dataclass
class Config:
    """Configuration data model"""
    servers_file: Path
    output_file: Optional[Path]
    parallel_limit: int
    timeout: int
    warning_days: int  # Days before expiry to flag as warning
    critical_days: int  # Days before expiry to flag as critical
    verbose: bool
    filter_days: int = 30  # Default filter: show Days Remaining < this value
    filter_issuers: str = ''  # Comma-separated issuer substrings to filter on
    fallback_ports: List[int] = None  # Ports to try if 443 fails


def _parse_cert_expiry_from_der(der_bytes: bytes) -> Optional[str]:
    """
    Parse certificate expiry date from DER-encoded certificate bytes.
    Walks the ASN.1 structure to find the Validity sequence and extract notAfter.

    Returns expiry as 'YYYY-MM-DD' string, or None if parsing fails.
    """
    try:
        def _read_tag_len(data, offset):
            if offset >= len(data):
                return None, 0, 0
            tag = data[offset]
            if offset + 1 >= len(data):
                return tag, 0, 1
            length_byte = data[offset + 1]
            if length_byte < 0x80:
                return tag, length_byte, 2
            num_bytes = length_byte & 0x7f
            if offset + 2 + num_bytes > len(data):
                return tag, 0, 2
            length = int.from_bytes(data[offset + 2:offset + 2 + num_bytes], 'big')
            return tag, length, 2 + num_bytes

        def _parse_time(data, offset):
            tag, length, hdr = _read_tag_len(data, offset)
            if tag not in (0x17, 0x18) or length == 0:
                return None
            time_str = data[offset + hdr:offset + hdr + length].decode('ascii')
            if tag == 0x17:  # UTCTime
                year = int(time_str[:2])
                year += 2000 if year < 50 else 1900
                return f"{year:04d}-{int(time_str[2:4]):02d}-{int(time_str[4:6]):02d}"
            else:  # GeneralizedTime
                return f"{int(time_str[:4]):04d}-{int(time_str[4:6]):02d}-{int(time_str[6:8]):02d}"

        tag, _cert_len, hdr = _read_tag_len(der_bytes, 0)
        if tag != 0x30:
            return None
        tbs_offset = hdr
        tag, tbs_len, tbs_hdr = _read_tag_len(der_bytes, tbs_offset)
        if tag != 0x30:
            return None

        pos = tbs_offset + tbs_hdr
        tbs_end = tbs_offset + tbs_hdr + tbs_len
        fields_skipped = 0
        while pos < tbs_end and fields_skipped < 4:
            tag, length, field_hdr = _read_tag_len(der_bytes, pos)
            if tag is None:
                break
            pos += field_hdr + length
            fields_skipped += 1

        if pos >= tbs_end:
            return None
        tag, _val_len, val_hdr = _read_tag_len(der_bytes, pos)
        if tag != 0x30:
            return None

        nb_offset = pos + val_hdr
        _nb_tag, nb_len, nb_hdr = _read_tag_len(der_bytes, nb_offset)
        na_offset = nb_offset + nb_hdr + nb_len
        return _parse_time(der_bytes, na_offset)
    except Exception:
        return None


def _extract_cert_field(der_bytes: bytes, field_index: int) -> Optional[str]:
    """Extract subject (field_index=5) or issuer (field_index=3) CN from DER cert."""
    try:
        def _read_tag_len(data, offset):
            if offset >= len(data):
                return None, 0, 0
            tag = data[offset]
            if offset + 1 >= len(data):
                return tag, 0, 1
            length_byte = data[offset + 1]
            if length_byte < 0x80:
                return tag, length_byte, 2
            num_bytes = length_byte & 0x7f
            if offset + 2 + num_bytes > len(data):
                return tag, 0, 2
            length = int.from_bytes(data[offset + 2:offset + 2 + num_bytes], 'big')
            return tag, length, 2 + num_bytes

        tag, _cert_len, hdr = _read_tag_len(der_bytes, 0)
        if tag != 0x30:
            return None
        tbs_offset = hdr
        tag, tbs_len, tbs_hdr = _read_tag_len(der_bytes, tbs_offset)
        if tag != 0x30:
            return None

        pos = tbs_offset + tbs_hdr
        tbs_end = tbs_offset + tbs_hdr + tbs_len
        fields_skipped = 0
        while pos < tbs_end and fields_skipped < field_index:
            tag, length, field_hdr = _read_tag_len(der_bytes, pos)
            if tag is None:
                break
            pos += field_hdr + length
            fields_skipped += 1

        if pos >= tbs_end:
            return None

        # Now at the target field - try to extract readable strings
        tag, length, field_hdr = _read_tag_len(der_bytes, pos)
        field_data = der_bytes[pos + field_hdr:pos + field_hdr + length]

        # Find printable string fields (tags 0x0c=UTF8, 0x13=PrintableString, 0x16=IA5String)
        parts = []
        i = 0
        while i < len(field_data) - 2:
            t = field_data[i]
            if t in (0x0c, 0x13, 0x16):
                slen = field_data[i + 1]
                if slen < 0x80 and i + 2 + slen <= len(field_data):
                    try:
                        s = field_data[i + 2:i + 2 + slen].decode('utf-8')
                        if len(s) > 1:
                            parts.append(s)
                    except UnicodeDecodeError:
                        pass
                    i += 2 + slen
                    continue
            i += 1
        return ', '.join(parts) if parts else None
    except Exception:
        return None


def check_certificate(server: str, port: int = 443, timeout: int = 10,
                      short_name: str = '') -> CertResult:
    """
    Connect to server via HTTPS and extract certificate expiration info.

    Args:
        server: Hostname or IP address
        port: HTTPS port (default 443)
        timeout: Connection timeout in seconds
        short_name: Display name for the server

    Returns:
        CertResult with certificate details
    """
    logger = logging.getLogger(__name__)
    query_timestamp = datetime.now(timezone.utc)

    # Resolve IP
    resolved_ip = None
    try:
        resolved_ip = socket.gethostbyname(server)
    except socket.gaierror:
        pass

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        ssl_sock = ctx.wrap_socket(sock, server_hostname=server)
        ssl_sock.connect((server, port))

        cert_der = ssl_sock.getpeercert(binary_form=True)
        ssl_sock.close()

        if not cert_der:
            logger.debug(f"Cert check {server}:{port}: no certificate returned")
            return CertResult(
                timestamp_utc=query_timestamp, server=server, port=port,
                short_name=short_name or server, server_ip=resolved_ip,
                status='SSL_ERROR', cert_expiry=None, days_remaining=None,
                cert_subject=None, cert_issuer=None,
                error_message='No certificate returned')

        # Parse expiry
        cert_expiry = _parse_cert_expiry_from_der(cert_der)
        days_remaining = None
        if cert_expiry:
            try:
                expiry_date = datetime.strptime(cert_expiry, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                days_remaining = (expiry_date - datetime.now(timezone.utc)).days
            except ValueError:
                pass

        # Extract subject and issuer
        cert_subject = _extract_cert_field(cert_der, 5)
        cert_issuer = _extract_cert_field(cert_der, 3)

        logger.debug(f"Cert check {server}:{port}: expiry={cert_expiry}, days={days_remaining}")

        return CertResult(
            timestamp_utc=query_timestamp, server=server, port=port,
            short_name=short_name or server, server_ip=resolved_ip,
            status='OK', cert_expiry=cert_expiry, days_remaining=days_remaining,
            cert_subject=cert_subject, cert_issuer=cert_issuer)

    except socket.timeout:
        logger.debug(f"Cert check {server}:{port}: timed out")
        return CertResult(
            timestamp_utc=query_timestamp, server=server, port=port,
            short_name=short_name or server, server_ip=resolved_ip,
            status='NO_RESPONSE', cert_expiry=None, days_remaining=None,
            cert_subject=None, cert_issuer=None,
            error_message=f'Connection timed out after {timeout}s')

    except ConnectionRefusedError:
        logger.debug(f"Cert check {server}:{port}: connection refused")
        return CertResult(
            timestamp_utc=query_timestamp, server=server, port=port,
            short_name=short_name or server, server_ip=resolved_ip,
            status='NO_RESPONSE', cert_expiry=None, days_remaining=None,
            cert_subject=None, cert_issuer=None,
            error_message='Connection refused')

    except ssl.SSLError as e:
        logger.debug(f"Cert check {server}:{port}: SSL error: {e}")
        return CertResult(
            timestamp_utc=query_timestamp, server=server, port=port,
            short_name=short_name or server, server_ip=resolved_ip,
            status='SSL_ERROR', cert_expiry=None, days_remaining=None,
            cert_subject=None, cert_issuer=None,
            error_message=f'SSL error: {e}')

    except Exception as e:
        logger.debug(f"Cert check {server}:{port}: error: {e}")
        return CertResult(
            timestamp_utc=query_timestamp, server=server, port=port,
            short_name=short_name or server, server_ip=resolved_ip,
            status='ERROR', cert_expiry=None, days_remaining=None,
            cert_subject=None, cert_issuer=None,
            error_message=f'{e}')


def parse_servers_csv(file_path: Path) -> List[tuple[str, int, str, int, str]]:
    """
    Parse CSV file with server list. Expects 'server' column, optional 'port',
    'short_name', 'failure_count', and 'alt_port'.

    'failure_count' is a persistent consecutive-failure counter: it is
    incremented each run a server cannot be contacted / no cert retrieved,
    and reset to 0 on a successful cert retrieval. 'alt_port' records the
    alternate (fallback) port the server was actually reachable on when its
    primary port failed; blank when the primary port worked or nothing did.
    Missing/blank/invalid values default to 0 / '' (keeps older 1-3 column
    CSVs backward compatible).

    Returns list of (server, port, short_name, failure_count, alt_port) tuples.
    'alt_port' is a string ('' when none).
    """
    logger = logging.getLogger(__name__)
    servers = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or 'server' not in reader.fieldnames:
                logger.error(f"CSV missing 'server' column. Found: {reader.fieldnames}")
                sys.exit(1)

            has_port = 'port' in reader.fieldnames
            has_name = 'short_name' in reader.fieldnames
            has_fail = 'failure_count' in reader.fieldnames
            has_alt = 'alt_port' in reader.fieldnames

            for row_num, row in enumerate(reader, 2):
                server = row.get('server', '').strip()
                if not server:
                    continue

                port = 443
                if has_port:
                    port_str = row.get('port', '').strip()
                    if port_str:
                        try:
                            port = int(port_str)
                        except ValueError:
                            port = 443

                short_name = ''
                if has_name:
                    short_name = row.get('short_name', '').strip()
                if not short_name:
                    short_name = server

                failure_count = 0
                if has_fail:
                    fc_str = row.get('failure_count', '').strip()
                    if fc_str:
                        try:
                            failure_count = max(int(fc_str), 0)
                        except ValueError:
                            failure_count = 0

                alt_port = ''
                if has_alt:
                    alt_port = row.get('alt_port', '').strip()

                servers.append((server, port, short_name, failure_count, alt_port))
                logger.debug(f"Row {row_num}: {server}:{port} ({short_name}) "
                             f"fail={failure_count} alt={alt_port or '-'}")

        logger.info(f"Parsed {len(servers)} servers from {file_path}")
        return servers

    except Exception as e:
        logger.error(f"Error reading CSV {file_path}: {e}")
        sys.exit(1)


def write_servers_csv(file_path: Path, rows: List[tuple[str, int, str, int, str]]) -> None:
    """
    Atomically rewrite the servers CSV with the failure_count and alt_port
    columns.

    Writes to a temporary '.tmp' file then replaces the original, so a
    failure mid-write cannot corrupt the existing list. Non-fatal on error
    (failure tracking is supplementary) - logs and leaves the original file
    untouched.

    Args:
        file_path: Path to the servers CSV
        rows: list of (server, port, short_name, failure_count, alt_port) tuples
    """
    logger = logging.getLogger(__name__)
    temp_path = None
    try:
        temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
        with open(temp_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(['server', 'port', 'short_name', 'failure_count', 'alt_port'])
            for server, port, short_name, failure_count, alt_port in rows:
                writer.writerow([server, port, short_name, failure_count, alt_port])
        temp_path.replace(file_path)
        logger.info(f"Updated {file_path} with failure counts / alt ports ({len(rows)} rows)")
    except Exception as e:
        logger.error(f"Failed to write servers CSV {file_path}: {e}")
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass


def process_servers_parallel(servers: List[tuple[str, int, str, int, str]],
                             config: Config) -> tuple[List[CertResult], dict]:
    """
    Process all servers concurrently. When the primary port fails, try all
    fallback ports.

    Returns (results, alt_ports) where alt_ports maps
    (server, primary_port) -> working alternate port (int) for servers that
    were unreachable on their primary port but succeeded on a fallback port.
    """
    logger = logging.getLogger(__name__)
    results = []
    alt_ports = {}  # (server, primary_port) -> alternate port that worked

    if not servers:
        return results, alt_ports

    max_workers = config.parallel_limit if config.parallel_limit > 0 else 10
    fallback_ports = config.fallback_ports or []
    logger.info(f"Processing {len(servers)} servers with {max_workers} workers")
    if fallback_ports:
        logger.info(f"Fallback ports if 443 fails: {fallback_ports}")

    # Track which server+port combos are already in the CSV
    existing_entries = {(s, p) for s, p, _, _, _ in servers}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_server = {}
        for server, port, short_name, _failure_count, _alt in servers:
            future = executor.submit(check_certificate, server, port, config.timeout, short_name)
            future_to_server[future] = (server, port, short_name)

        for future in as_completed(future_to_server):
            server, port, short_name = future_to_server[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Unexpected error for {server}: {e}")
                result = CertResult(
                    timestamp_utc=datetime.now(timezone.utc), server=server, port=port,
                    short_name=short_name, server_ip=None, status='ERROR',
                    cert_expiry=None, days_remaining=None,
                    cert_subject=None, cert_issuer=None,
                    error_message=f'Unexpected: {e}')
                results.append(result)

    # For servers that failed on port 443, try fallback ports
    failed_443 = [r for r in results if r.port == 443 and r.status != 'OK']
    if failed_443 and fallback_ports:
        logger.info(f"Trying fallback ports for {len(failed_443)} failed servers...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            fallback_futures = {}
            for result in failed_443:
                for alt_port in fallback_ports:
                    if (result.server, alt_port) not in existing_entries:
                        future = executor.submit(check_certificate, result.server, alt_port,
                                                 config.timeout, result.short_name)
                        # remember the primary (failed) port so we can annotate
                        # the original CSV row with the working alternate port
                        fallback_futures[future] = (result.server, alt_port,
                                                     result.short_name, result.port)

            for future in as_completed(fallback_futures):
                server, alt_port, short_name, primary_port = fallback_futures[future]
                try:
                    alt_result = future.result()
                    if alt_result.status == 'OK':
                        results.append(alt_result)
                        # Record the working alternate port against the original
                        # row. Keep the lowest working port if several succeed.
                        key = (server, primary_port)
                        if key not in alt_ports or alt_port < alt_ports[key]:
                            alt_ports[key] = alt_port
                        logger.info(f"Found cert on {server}:{alt_port} "
                                    f"({short_name}) [primary {primary_port} failed]")
                except Exception:
                    pass

    # Sort: errors first, then by days_remaining ascending (soonest expiry first)
    def sort_key(r):
        if r.status != 'OK':
            return (0, 0)
        if r.days_remaining is not None:
            return (1, r.days_remaining)
        return (2, 0)

    results.sort(key=sort_key)
    return results, alt_ports


def _sanitize_xlsx(value: str) -> str:
    """Remove control characters that openpyxl rejects."""
    import re
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', value)


def write_xlsx_report(results: List[CertResult], output_path: Path, config: Config) -> None:
    """Write results to XLSX with formatting."""
    logger = logging.getLogger(__name__)

    try:
        workbook = openpyxl.Workbook()
        ws = workbook.active
        ws.title = "Certificate Expiry Report"

        headers = [
            'Timestamp (UTC)',
            'Server',
            'Port',
            'Short Name',
            'Server IP',
            'Cert Expiry',
            'Days Remaining',
            'Subject',
            'Issuer',
            'Status',
            'Error Message'
        ]

        # Header formatting
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_align = Alignment(horizontal="center", vertical="center")

        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align

        # Data rows
        for row_num, result in enumerate(results, 2):
            row_data = [
                result.timestamp_utc.isoformat(),
                result.server,
                result.port,
                result.short_name,
                result.server_ip or '',
                result.cert_expiry or '',
                result.days_remaining if result.days_remaining is not None else '',
                _sanitize_xlsx(result.cert_subject or ''),
                _sanitize_xlsx(result.cert_issuer or ''),
                result.status,
                result.error_message or ''
            ]

            for col, value in enumerate(row_data, 1):
                ws.cell(row=row_num, column=col, value=value)

            # Status cell formatting (column 10)
            status_cell = ws.cell(row=row_num, column=10)
            if result.status == 'OK':
                status_cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                status_cell.font = Font(bold=True)
            else:
                status_cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                status_cell.font = Font(bold=True)

            # Days remaining formatting (column 7)
            days_cell = ws.cell(row=row_num, column=7)
            if result.days_remaining is not None:
                if result.days_remaining <= config.critical_days:
                    # Critical - red
                    days_cell.fill = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
                    days_cell.font = Font(color="FFFFFF", bold=True)
                elif result.days_remaining <= config.warning_days:
                    # Warning - yellow
                    days_cell.fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
                    days_cell.font = Font(bold=True)
                else:
                    # OK - green
                    days_cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                    days_cell.font = Font(bold=True)

        # Auto-adjust column widths
        for column in ws.columns:
            max_length = 0
            try:
                col_letter = column[0].column_letter
            except AttributeError:
                continue
            for cell in column:
                try:
                    if hasattr(cell, 'column_letter') and len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except (TypeError, AttributeError):
                    pass
            ws.column_dimensions[col_letter].width = min(max_length + 2, 50)

        # Freeze top row and enable auto-filter on all columns
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions

        # Apply column filters using openpyxl's FilterColumn API
        # These are real Excel filters the user can see and modify
        from openpyxl.worksheet.filters import FilterColumn, CustomFilter, CustomFilters, Filters

        filter_days = config.filter_days
        filter_issuer_list = [s.strip() for s in config.filter_issuers.split(',') if s.strip()]

        # Days Remaining filter (column 7, index 6): custom filter < filter_days
        days_filter = CustomFilters(customFilter=[
            CustomFilter(operator='lessThan', val=str(filter_days))
        ])
        ws.auto_filter.filterColumn.append(
            FilterColumn(colId=6, customFilters=days_filter)
        )

        # Issuer filter (column 9, index 8): show only rows matching configured issuer substrings
        # Collect unique issuer values from data that match the configured substrings
        if filter_issuer_list:
            matching_issuers = set()
            for row_num in range(2, len(results) + 2):
                cell_val = ws.cell(row=row_num, column=9).value
                if cell_val:
                    cell_lower = str(cell_val).lower()
                    if any(f.lower() in cell_lower for f in filter_issuer_list):
                        matching_issuers.add(str(cell_val))

            if matching_issuers:
                issuer_filter = Filters(blank=False, filter=sorted(matching_issuers))
                ws.auto_filter.filterColumn.append(
                    FilterColumn(colId=8, filters=issuer_filter)
                )

        # Hide rows that don't match the filters (Excel auto-filter hides rows visually)
        for row_num in range(2, len(results) + 2):
            days_val = ws.cell(row=row_num, column=7).value
            issuer_val = ws.cell(row=row_num, column=9).value

            # Check days filter
            days_visible = True
            if days_val is None or days_val == '' or not isinstance(days_val, (int, float)):
                days_visible = False
            elif days_val >= filter_days:
                days_visible = False

            # Check issuer filter
            issuer_visible = True
            if filter_issuer_list:
                if not issuer_val or issuer_val == '':
                    issuer_visible = False
                else:
                    issuer_lower = str(issuer_val).lower()
                    issuer_visible = any(f.lower() in issuer_lower for f in filter_issuer_list)

            # Hide row if it doesn't match both filters
            if not (days_visible and issuer_visible):
                ws.row_dimensions[row_num].hidden = True

        logger.info(f"Applied filters: Days Remaining < {filter_days}, Issuers: {config.filter_issuers}")

        workbook.save(output_path)
        logger.info(f"Wrote {len(results)} results to {output_path}")

    except Exception as e:
        logger.error(f"Failed to write XLSX: {e}")
        raise


def format_summary(results: List[CertResult], config: Config) -> str:
    """Generate summary text."""
    total = len(results)
    ok = sum(1 for r in results if r.status == 'OK')
    failed = total - ok
    expired = sum(1 for r in results if r.days_remaining is not None and r.days_remaining <= 0)
    critical = sum(1 for r in results if r.days_remaining is not None and 0 < r.days_remaining <= config.critical_days)
    warning = sum(1 for r in results if r.days_remaining is not None
                  and config.critical_days < r.days_remaining <= config.warning_days)

    lines = [
        "=" * 60,
        "CERTIFICATE EXPIRY SUMMARY",
        "=" * 60,
        f"Hostname: {socket.gethostname()}",
        f"Execution path: {os.getcwd()}",
        f"Program: {PROGRAM_NAME} v{VERSION}",
        "",
        f"Total servers checked: {total}",
        f"Successful checks: {ok}",
        f"Failed checks: {failed}",
        "",
        f"Expired certificates: {expired}",
        f"Critical (< {config.critical_days} days): {critical}",
        f"Warning (< {config.warning_days} days): {warning}",
    ]

    # List problem certs
    problems = [r for r in results if r.days_remaining is not None and r.days_remaining <= config.warning_days]
    if problems:
        lines.append("")
        lines.append("Certificates requiring attention:")
        for r in sorted(problems, key=lambda x: x.days_remaining or 0):
            status = "EXPIRED" if r.days_remaining <= 0 else f"{r.days_remaining} days"
            lines.append(f"  {r.short_name} ({r.server}:{r.port}): {status} - expires {r.cert_expiry}")

    # List failed checks
    failures = [r for r in results if r.status != 'OK']
    if failures:
        lines.append("")
        lines.append("Failed checks:")
        for r in failures:
            lines.append(f"  {r.short_name} ({r.server}:{r.port}): {r.status} - {r.error_message}")

    lines.append("=" * 60)
    return "\n".join(lines)


def _html_escape(text: str) -> str:
    """Minimal HTML escaping for cell/text content."""
    if text is None:
        return ''
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def build_email_body(results: List[CertResult], config: Config,
                     ini_config: dict, source: str) -> tuple:
    """
    Build a structured summary email body grouped by severity.

    'source' is a short attribution string shown at the bottom of the body
    (e.g. the XLSX report filename).

    Returns a tuple (plain_text, html) matching a report layout:
      banner headline, source line, filter line, Summary block, and
      grouped tables for Expired and Expiring Soon certificates.
    """
    # Window bounds: certificates from -low_days through +high_days
    low_days = int(ini_config.get('email_low_days', 14))
    high_days = int(ini_config.get('email_high_days', 21))

    # Partition certs that have a known days_remaining within the window
    in_window = [
        r for r in results
        if r.days_remaining is not None and -low_days <= r.days_remaining <= high_days
    ]
    expired = sorted(
        [r for r in in_window if r.days_remaining <= 0],
        key=lambda x: x.days_remaining
    )
    expiring = sorted(
        [r for r in in_window if r.days_remaining > 0],
        key=lambda x: x.days_remaining
    )

    matched = len(in_window)
    n_expired = len(expired)
    n_expiring = len(expiring)

    # Headline banner reflects the most severe condition
    if n_expired > 0:
        banner_emoji = "🔴"
        banner = (f"{banner_emoji} CRITICAL — {n_expired} "
                  f"Certificate{'s' if n_expired != 1 else ''} Expired")
        banner_detail = (f"{n_expired} certificate{'s' if n_expired != 1 else ''} "
                         f"{'show' if n_expired != 1 else 'shows'} negative "
                         f"Days Remaining. Immediate renewal action required.")
    elif n_expiring > 0:
        banner_emoji = "🟠"
        banner = (f"{banner_emoji} WARNING — {n_expiring} "
                  f"Certificate{'s' if n_expiring != 1 else ''} Expiring Soon")
        banner_detail = (f"{n_expiring} certificate{'s' if n_expiring != 1 else ''} "
                         f"expiring within {high_days} days. Plan renewal.")
    else:
        banner_emoji = "🟢"
        banner = f"{banner_emoji} OK — No certificates in the alert window"
        banner_detail = (f"No certificates fall within the -{low_days} to "
                         f"+{high_days} day window.")

    title = f"Certificate Expiry Report — Certs Within -{low_days} to +{high_days} Days"
    source_line = f"Source: {source}"
    filter_line = (f"Filter: Days Remaining between -{low_days} and +{high_days} "
                   f"(inclusive)")

    def _fmt_days(d: int) -> str:
        return f"+{d}" if d > 0 else str(d)

    # ---- Plain text version ----
    pt = []
    pt.append(banner)
    pt.append(banner_detail)
    pt.append("")
    pt.append(title)
    pt.append(source_line)
    pt.append(filter_line)
    pt.append("")
    pt.append("Summary")
    pt.append(f"  - {matched} certificate{'s' if matched != 1 else ''} matched "
              f"the -{low_days} to +{high_days} day window")
    pt.append(f"  - {n_expired} expired (Days Remaining: negative)")
    pt.append(f"  - {n_expiring} expiring soon (Days Remaining: positive, "
              f"within {high_days} days)")

    if expired:
        pt.append("")
        pt.append(f"🔴 Expired Certificates ({n_expired})")
        pt.append(f"  {'Server':<40} {'Shortname':<25} {'Days Remaining':>14}")
        for r in expired:
            pt.append(f"  {r.server:<40} {r.short_name:<25} "
                      f"{_fmt_days(r.days_remaining):>14}")

    if expiring:
        pt.append("")
        pt.append(f"🟠 Expiring Soon ({n_expiring})")
        pt.append(f"  {'Server':<40} {'Shortname':<25} {'Days Remaining':>14}")
        for r in expiring:
            pt.append(f"  {r.server:<40} {r.short_name:<25} "
                      f"{_fmt_days(r.days_remaining):>14}")

    plain_text = "\n".join(pt)

    # ---- HTML version ----
    # Palette (per email format handoff):
    #   Expired  -> header #d32f2f, border #c62828, alt row #fce4ec, text #d32f2f
    #   Expiring -> header #e65100, border #bf360c, alt row #fff8e1, text #e65100
    #   Summary box -> #4472C4 accent on #e8f0fe
    #   Critical banner -> #d32f2f accent on #fdecea
    #   All-clear -> #2e7d32
    def _table(rows, header_bg, header_border, alt_row, cell_color):
        head = (
            '<table style="border-collapse:collapse;width:100%;margin-bottom:20px;">'
            f'<tr style="background:{header_bg};color:white;">'
            f'<th style="padding:8px 12px;text-align:left;border:1px solid {header_border};">Server</th>'
            f'<th style="padding:8px 12px;text-align:left;border:1px solid {header_border};">Shortname</th>'
            f'<th style="padding:8px 12px;text-align:center;border:1px solid {header_border};">Days Remaining</th>'
            '</tr>'
        )
        body = ''
        for i, r in enumerate(rows):
            # Alternating row colors: even rows tinted, odd rows white
            row_bg = alt_row if i % 2 == 0 else '#fff'
            body += (
                f'<tr style="background:{row_bg};">'
                f'<td style="padding:6px 12px;border:1px solid #ddd;">{_html_escape(r.server)}</td>'
                f'<td style="padding:6px 12px;border:1px solid #ddd;">{_html_escape(r.short_name)}</td>'
                f'<td style="padding:6px 12px;text-align:center;border:1px solid #ddd;'
                f'color:{cell_color};font-weight:bold;">{_fmt_days(r.days_remaining)}</td>'
                '</tr>'
            )
        return head + body + '</table>'

    html_parts = [
        '<html><body style="font-family:Calibri,sans-serif;font-size:11pt;color:#333;">',
    ]

    # [1] Critical alert banner — only when there are expired certs
    if n_expired > 0:
        html_parts.append(
            '<div style="border-left:4px solid #d32f2f;background:#fdecea;'
            'padding:12px 16px;margin-bottom:16px;border-radius:4px;">'
            '<strong style="color:#d32f2f;">&#9888;&#65039; CRITICAL:</strong> '
            f'{n_expired} certificate{"s" if n_expired != 1 else ""} currently '
            f'expired and {"require" if n_expired != 1 else "requires"} '
            'immediate attention.'
            '</div>'
        )

    # [2] Summary box — always present
    html_parts.append(
        '<div style="background:#e8f0fe;border-left:4px solid #4472C4;'
        'padding:12px 16px;margin-bottom:20px;border-radius:4px;">'
        f'<strong>Summary:</strong> {n_expired} expired, {n_expiring} expiring '
        f'within {high_days} days ({matched} total actionable)'
        '</div>'
    )

    # [3] Expired table — only if there are expired certs
    if expired:
        html_parts.append(
            '<h3 style="color:#d32f2f;margin-bottom:8px;">'
            '&#128308; Expired Certificates</h3>'
        )
        html_parts.append(_table(expired, '#d32f2f', '#c62828', '#fce4ec', '#d32f2f'))

    # [4] Expiring soon table — only if there are expiring certs
    if expiring:
        html_parts.append(
            '<h3 style="color:#e65100;margin-bottom:8px;">'
            '&#128992; Expiring Soon</h3>'
        )
        html_parts.append(_table(expiring, '#e65100', '#bf360c', '#fff8e1', '#e65100'))

    # [5] All-clear message — only if nothing is actionable
    if not expired and not expiring:
        html_parts.append(
            '<p style="color:#2e7d32;">&#9989; No certificates in the critical '
            f'window (-{low_days} to +{high_days} days).</p>'
        )

    # [6] Source attribution — always present
    html_parts.append(
        f'<p style="font-size:9pt;color:#888;">{_html_escape(source_line)}</p>'
    )

    html_parts.append('</body></html>')
    html = "\n".join(html_parts)

    return plain_text, html


def send_email_notification(summary_text: str, xlsx_path: Path, results: List[CertResult],
                            config: Config, ini_config: dict) -> None:
    """Send email notification with results."""
    logger = logging.getLogger(__name__)

    if not ini_config.get('send_email', False):
        return

    try:
        expired = sum(1 for r in results if r.days_remaining is not None and r.days_remaining <= 0)
        critical = sum(1 for r in results if r.days_remaining is not None
                       and 0 < r.days_remaining <= config.critical_days)
        failed = sum(1 for r in results if r.status != 'OK')

        has_error = expired > 0 or critical > 0 or failed > 0

        # Subject uses the audience-facing wording based on the filtered
        # -low..+high window counts (per email format handoff).
        low_days = int(ini_config.get('email_low_days', 14))
        high_days = int(ini_config.get('email_high_days', 21))
        win_expired = sum(
            1 for r in results
            if r.days_remaining is not None and -low_days <= r.days_remaining <= 0
        )
        win_expiring = sum(
            1 for r in results
            if r.days_remaining is not None and 0 < r.days_remaining <= high_days
        )
        subject = (f"Certificate Expiry Alert - {win_expired} "
                   f"Cert{'s' if win_expired != 1 else ''} Expired + "
                   f"{win_expiring} Expiring Soon")

        msg = MIMEMultipart('mixed')
        msg['From'] = ini_config.get('from_email', 'cert-monitor@tgna.tegna.com')
        msg['To'] = ini_config.get('to_email', 'moldham@tegna.com')
        msg['Subject'] = subject

        if has_error:
            msg['X-Priority'] = '1'
            msg['X-MSMail-Priority'] = 'High'
            msg['Importance'] = 'High'

        # Build structured summary body (plain text + HTML alternatives).
        # The alternative part is nested so attachments live at the
        # top-level 'mixed' container. Source attribution references the
        # XLSX report filename.
        source = xlsx_path.name if xlsx_path else "cert_monitor report"
        plain_body, html_body = build_email_body(results, config, ini_config, source)
        body = MIMEMultipart('alternative')
        body.attach(MIMEText(plain_body, 'plain', 'utf-8'))
        body.attach(MIMEText(html_body, 'html', 'utf-8'))
        msg.attach(body)

        if xlsx_path.exists():
            with open(xlsx_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename= {xlsx_path.name}')
                msg.attach(part)

        smtp_server = ini_config.get('smtp_server', 'relay.tgna.tegna.com')
        smtp_port = ini_config.get('smtp_port', 25)

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if ini_config.get('smtp_use_tls', False):
                server.starttls()
            username = ini_config.get('smtp_username', '')
            password = ini_config.get('smtp_password', '')
            if username and password:
                server.login(username, password)
            server.send_message(msg)
            logger.info(f"Email sent: {subject}")

    except Exception as e:
        logger.error(f"Failed to send email: {e}")


def load_configuration(config_file: str = "cert_monitor.ini") -> dict:
    """Load configuration from INI file with defaults."""
    logger = logging.getLogger(__name__)

    defaults = {
        'default_parallel_limit': 10,
        'default_timeout': 10,
        'warning_days': 30,
        'critical_days': 7,
        'filter_days': 30,
        'filter_issuers': 'Tegna SHA2 Issuing CA 01,Tegna Inc. Issuing',
        'fallback_ports': '8080,8443,3389',
        'output_directory': '.\\Reports',
        'send_email': False,
        'smtp_server': '',
        'smtp_port': 25,
        'smtp_use_tls': False,
        'smtp_username': '',
        'smtp_password': '',
        'from_email': '',
        'to_email': '',
        # Email summary window: certs with Days Remaining from
        # -email_low_days through +email_high_days are listed in the body
        'email_low_days': 14,
        'email_high_days': 21,
    }

    config = configparser.ConfigParser()
    try:
        if Path(config_file).exists():
            config.read(config_file)
            logger.debug(f"Loaded config from {config_file}")

            if 'monitor_settings' in config:
                s = config['monitor_settings']
                defaults['default_parallel_limit'] = s.getint(
                    'default_parallel_limit', defaults['default_parallel_limit'])
                defaults['default_timeout'] = s.getint('default_timeout', defaults['default_timeout'])
                defaults['warning_days'] = s.getint('warning_days', defaults['warning_days'])
                defaults['critical_days'] = s.getint('critical_days', defaults['critical_days'])
                defaults['filter_days'] = s.getint('filter_days', defaults['filter_days'])
                defaults['filter_issuers'] = s.get('filter_issuers', defaults['filter_issuers'])
                defaults['fallback_ports'] = s.get('fallback_ports', defaults['fallback_ports'])
                defaults['output_directory'] = s.get('output_directory', defaults['output_directory'])

            if 'email_settings' in config:
                s = config['email_settings']
                defaults['send_email'] = s.getboolean('send_email', defaults['send_email'])
                defaults['smtp_server'] = s.get('smtp_server', defaults['smtp_server'])
                defaults['smtp_port'] = s.getint('smtp_port', defaults['smtp_port'])
                defaults['smtp_use_tls'] = s.getboolean('smtp_use_tls', defaults['smtp_use_tls'])
                defaults['smtp_username'] = s.get('smtp_username', defaults['smtp_username'])
                defaults['smtp_password'] = s.get('smtp_password', defaults['smtp_password'])
                defaults['from_email'] = s.get('from_email', defaults['from_email'])
                defaults['to_email'] = s.get('to_email', defaults['to_email'])
                defaults['email_low_days'] = s.getint('email_low_days', defaults['email_low_days'])
                defaults['email_high_days'] = s.getint('email_high_days', defaults['email_high_days'])
        else:
            logger.debug(f"Config file {config_file} not found, using defaults")
    except Exception as e:
        logger.warning(f"Error reading config: {e}")

    return defaults


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler(sys.stdout)])


def parse_arguments() -> Config:
    """Parse CLI arguments."""
    ini_config = load_configuration()

    parser = argparse.ArgumentParser(
        description='Certificate Expiry Monitor - Check HTTPS certificate expiration dates',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Basic usage:
    %(prog)s -s servers.csv

  Custom output and timeout:
    %(prog)s -s servers.csv -o report.xlsx -t 5

  With warning/critical thresholds:
    %(prog)s -s servers.csv --warning-days 60 --critical-days 14

CSV Format:
  Required column: server
  Optional columns: port (default 443), short_name

  Example:
    server,port,short_name
    www.example.com,443,Example
    internal.corp.com,8443,Internal App
    10.0.0.1,,Web Server
        """)

    parser.add_argument('-s', '--servers-file', type=Path, metavar='FILE',
                        help='Path to CSV file with server list (default: cert_servers.csv in current directory)')
    parser.add_argument('-o', '--output-file', type=Path, metavar='FILE',
                        help='Output XLSX file path (default: auto-generated with timestamp)')
    parser.add_argument('-p', '--parallel-limit', type=int,
                        default=ini_config['default_parallel_limit'], metavar='N',
                        help=f'Max concurrent checks [default: {ini_config["default_parallel_limit"]}]')
    parser.add_argument('-t', '--timeout', type=int,
                        default=ini_config['default_timeout'], metavar='SECONDS',
                        help=f'Connection timeout [default: {ini_config["default_timeout"]}]')
    parser.add_argument('--warning-days', type=int,
                        default=ini_config['warning_days'], metavar='N',
                        help=f'Days before expiry to flag as warning (yellow) [default: {ini_config["warning_days"]}]')
    parser.add_argument('--critical-days', type=int,
                        default=ini_config['critical_days'], metavar='N',
                        help=f'Days before expiry to flag as critical (red) [default: {ini_config["critical_days"]}]')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging')
    parser.add_argument('--version', action='version',
                        version=f'{PROGRAM_NAME} {VERSION}')

    args = parser.parse_args()

    # Default to cert_servers.csv if not specified
    servers_file = args.servers_file
    if servers_file is None:
        servers_file = Path('cert_servers.csv')
        if not servers_file.exists():
            parser.error("No servers file specified and cert_servers.csv not found in current directory")

    if not servers_file.exists():
        parser.error(f"Servers file not found: {servers_file}")

    return Config(
        servers_file=servers_file,
        output_file=args.output_file,
        parallel_limit=args.parallel_limit,
        timeout=args.timeout,
        warning_days=args.warning_days,
        critical_days=args.critical_days,
        verbose=args.verbose,
        filter_days=ini_config['filter_days'],
        filter_issuers=ini_config['filter_issuers'],
        fallback_ports=[int(p.strip()) for p in ini_config['fallback_ports'].split(',') if p.strip()]
    )


def main():
    """Main entry point."""
    try:
        ini_config = load_configuration()
        config = parse_arguments()
        setup_logging(config.verbose)

        logger = logging.getLogger(__name__)
        logger.info(f"{PROGRAM_NAME} v{VERSION} starting...")
        logger.info(f"Servers file: {config.servers_file}")
        logger.info(f"Warning threshold: {config.warning_days} days")
        logger.info(f"Critical threshold: {config.critical_days} days")

        # Parse server list
        servers = parse_servers_csv(config.servers_file)
        if not servers:
            logger.error("No servers to check")
            return 1

        # Process servers
        results, alt_ports = process_servers_parallel(servers, config)

        # Update persistent failure_count / alt_port and rewrite the CSV.
        # Rules (correlate to CSV rows strictly by (server, port)):
        #   - Primary port returned a cert (OK): failure_count = 0, alt_port = ''
        #   - Primary failed but reachable on a fallback port: failure_count += 1
        #     (the primary port still failed) and alt_port = that working port
        #   - Unreachable on primary and all fallbacks: failure_count += 1,
        #     alt_port = ''
        #   - No result at all for the row (unexpected): leave values unchanged
        try:
            # Best status per (server, port): 'OK' wins over any failure
            status_by_key = {}
            for r in results:
                key = (r.server, r.port)
                if r.status == 'OK':
                    status_by_key[key] = 'OK'
                elif key not in status_by_key:
                    status_by_key[key] = r.status

            updated_rows = []
            for server, port, short_name, old_count, old_alt in servers:
                status = status_by_key.get((server, port))
                working_alt = alt_ports.get((server, port))

                if status == 'OK':
                    new_count = 0
                    new_alt = ''
                elif status is None:
                    # No result for this row (unexpected) - leave values as-is
                    new_count = old_count
                    new_alt = old_alt
                elif working_alt is not None:
                    # Primary port failed; still count it as a failure even
                    # though a cert was retrieved on a fallback port. Record
                    # the working alternate port for reference.
                    new_count = old_count + 1
                    new_alt = str(working_alt)
                    logger.info(f"{server}:{port} primary failed (reachable on "
                                f"alt port {working_alt}) - failure_count "
                                f"{old_count} -> {new_count}")
                else:
                    new_count = old_count + 1
                    new_alt = ''
                    logger.debug(f"{server}:{port} unreachable - failure_count "
                                 f"{old_count} -> {new_count}")

                updated_rows.append((server, port, short_name, new_count, new_alt))

            write_servers_csv(config.servers_file, updated_rows)
        except Exception as e:
            logger.error(f"Failed to update failure counts in CSV: {e}")

        # Determine output path
        if config.output_file:
            output_path = config.output_file
        else:
            output_dir = Path(ini_config.get('output_directory', '.\\Reports'))
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"cert_monitor_report_{timestamp}.xlsx"

        # Write report
        write_xlsx_report(results, output_path, config)

        # Generate and display summary
        summary = format_summary(results, config)
        print(summary)

        # Write summary file
        summary_path = output_path.with_suffix('.txt')
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary + '\n')
        logger.info(f"Summary written to {summary_path}")

        # Send email
        send_email_notification(summary, output_path, results, config, ini_config)

        # Exit code
        has_errors = any(r.status != 'OK' for r in results)
        has_expired = any(r.days_remaining is not None and r.days_remaining <= 0 for r in results)

        if has_errors or has_expired:
            logger.warning("Completed with issues")
            return 1

        logger.info("Completed successfully")
        return 0

    except KeyboardInterrupt:
        print("\nCancelled by user", file=sys.stderr)
        return 1
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
