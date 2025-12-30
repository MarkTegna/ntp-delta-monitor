#!/usr/bin/env python3
"""
Property-based tests for NTP Delta Monitor

This module contains property-based tests using Hypothesis to validate
the correctness properties defined in the design document.
"""

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import socket
import ntplib

from hypothesis import given, strategies as st, settings, assume
from hypothesis.strategies import composite
from hypothesis import HealthCheck

# Import the modules under test
from ntp_monitor import (
    query_ntp_server, 
    NTPResponse, 
    NTPStatus,
    validate_ntp_response,
    validate_timestamp_format
)


class TestNTPQueryProtocolCompliance(unittest.TestCase):
    """
    **Feature: ntp-delta-monitor, Property 1: NTP Query Protocol Compliance**
    
    Property: For any valid NTP server hostname, the system should initiate queries 
    using NTP version 4 protocol and capture all required response fields 
    (timestamp, RTT, stratum, delays, dispersion)
    
    **Validates: Requirements 1.1, 1.2, 2.3**
    """

    @composite
    def valid_ntp_hostname(draw):
        """Generate valid NTP server hostnames for testing."""
        # Generate realistic hostnames
        hostname_types = st.one_of(
            # Standard NTP server patterns
            st.text(alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), min_codepoint=32, max_codepoint=126), 
                   min_size=1, max_size=20).filter(lambda x: x.replace('.', '').replace('-', '').isalnum()),
            # IP addresses (simplified pattern)
            st.builds(lambda a, b, c, d: f"{a}.{b}.{c}.{d}", 
                     st.integers(1, 255), st.integers(0, 255), st.integers(0, 255), st.integers(1, 255))
        )
        return draw(hostname_types)

    @composite
    def mock_ntp_response(draw):
        """Generate mock NTP response data for testing."""
        # Generate realistic NTP response values
        tx_time = draw(st.floats(min_value=1000000000, max_value=2000000000))  # Unix timestamp range
        delay = draw(st.floats(min_value=0.001, max_value=1.0))  # RTT in seconds
        stratum = draw(st.integers(min_value=1, max_value=15))  # Valid stratum range
        root_delay = draw(st.floats(min_value=0.0, max_value=0.1))  # Root delay in seconds
        root_dispersion = draw(st.floats(min_value=0.0, max_value=0.1))  # Root dispersion in seconds
        
        return {
            'tx_time': tx_time,
            'delay': delay,
            'stratum': stratum,
            'root_delay': root_delay,
            'root_dispersion': root_dispersion
        }

    @given(valid_ntp_hostname(), mock_ntp_response(), st.integers(min_value=1, max_value=300))
    @settings(max_examples=100, deadline=None)
    def test_ntp_query_protocol_compliance(self, hostname, mock_response_data, timeout):
        """
        **Feature: ntp-delta-monitor, Property 1: NTP Query Protocol Compliance**
        
        Test that NTP queries use version 4 protocol and capture all required fields.
        """
        # Create a mock NTP response object
        mock_response = MagicMock()
        mock_response.tx_time = mock_response_data['tx_time']
        mock_response.delay = mock_response_data['delay']
        mock_response.stratum = mock_response_data['stratum']
        mock_response.root_delay = mock_response_data['root_delay']
        mock_response.root_dispersion = mock_response_data['root_dispersion']
        
        # Mock the NTP client to avoid actual network calls
        # Also mock timestamp validation to avoid time-dependent issues
        with patch('ntp_monitor.ntplib.NTPClient') as mock_ntp_client_class, \
             patch('ntp_monitor.validate_timestamp_format', return_value=True):
            
            mock_client = MagicMock()
            mock_ntp_client_class.return_value = mock_client
            mock_client.request.return_value = mock_response
            
            # Execute the NTP query
            result = query_ntp_server(hostname, timeout)
            
            # Verify NTP version 4 protocol is used
            mock_client.request.assert_called_once_with(hostname, version=4, timeout=timeout)
            
            # Verify all required response fields are captured
            self.assertIsInstance(result, NTPResponse)
            
            # Verify timestamp is captured and properly formatted
            self.assertIsInstance(result.timestamp_utc, datetime)
            self.assertEqual(result.timestamp_utc.tzinfo, timezone.utc)
            
            # Verify RTT is captured and converted to milliseconds
            self.assertIsInstance(result.query_rtt_ms, float)
            self.assertEqual(result.query_rtt_ms, mock_response_data['delay'] * 1000.0)
            
            # Verify stratum is captured
            self.assertIsInstance(result.stratum, int)
            self.assertEqual(result.stratum, mock_response_data['stratum'])
            
            # Verify root delay is captured and converted to milliseconds
            self.assertIsInstance(result.root_delay_ms, float)
            self.assertEqual(result.root_delay_ms, mock_response_data['root_delay'] * 1000.0)
            
            # Verify root dispersion is captured and converted to milliseconds
            self.assertIsInstance(result.root_dispersion_ms, float)
            self.assertEqual(result.root_dispersion_ms, mock_response_data['root_dispersion'] * 1000.0)
            
            # Verify synchronization status is determined correctly
            self.assertIsInstance(result.is_synchronized, bool)
            expected_sync = mock_response_data['stratum'] < 16
            self.assertEqual(result.is_synchronized, expected_sync)

    @given(valid_ntp_hostname(), st.integers(min_value=1, max_value=300))
    @settings(max_examples=100, deadline=None)
    def test_ntp_query_handles_protocol_errors(self, hostname, timeout):
        """
        Test that NTP protocol errors are properly handled and classified.
        """
        # Mock NTP client to raise protocol error
        with patch('ntp_monitor.ntplib.NTPClient') as mock_ntp_client_class:
            mock_client = MagicMock()
            mock_ntp_client_class.return_value = mock_client
            mock_client.request.side_effect = ntplib.NTPException("NTP protocol error")
            
            # Execute the NTP query and expect exception
            with self.assertRaises(Exception) as context:
                query_ntp_server(hostname, timeout)
            
            # Verify NTP version 4 protocol was attempted
            mock_client.request.assert_called_once_with(hostname, version=4, timeout=timeout)
            
            # Verify error message indicates NTP protocol error
            self.assertIn("NTP protocol error", str(context.exception))

    @given(valid_ntp_hostname(), st.integers(min_value=1, max_value=300))
    @settings(max_examples=100, deadline=None)
    def test_ntp_query_handles_timeout_errors(self, hostname, timeout):
        """
        Test that timeout errors are properly handled and classified.
        """
        # Mock NTP client to raise timeout error
        with patch('ntp_monitor.ntplib.NTPClient') as mock_ntp_client_class:
            mock_client = MagicMock()
            mock_ntp_client_class.return_value = mock_client
            mock_client.request.side_effect = socket.timeout()
            
            # Execute the NTP query and expect exception
            with self.assertRaises(Exception) as context:
                query_ntp_server(hostname, timeout)
            
            # Verify NTP version 4 protocol was attempted
            mock_client.request.assert_called_once_with(hostname, version=4, timeout=timeout)
            
            # Verify error message indicates timeout
            self.assertIn("Timeout after", str(context.exception))

    @given(valid_ntp_hostname(), st.integers(min_value=1, max_value=300))
    @settings(max_examples=100, deadline=None)
    def test_ntp_query_handles_dns_errors(self, hostname, timeout):
        """
        Test that DNS resolution errors are properly handled and classified.
        """
        # Mock NTP client to raise DNS error
        with patch('ntp_monitor.ntplib.NTPClient') as mock_ntp_client_class:
            mock_client = MagicMock()
            mock_ntp_client_class.return_value = mock_client
            mock_client.request.side_effect = socket.gaierror("Name resolution failed")
            
            # Execute the NTP query and expect exception
            with self.assertRaises(Exception) as context:
                query_ntp_server(hostname, timeout)
            
            # Verify NTP version 4 protocol was attempted
            mock_client.request.assert_called_once_with(hostname, version=4, timeout=timeout)
            
            # Verify error message indicates DNS failure
            self.assertIn("DNS resolution failed", str(context.exception))


class TestTimestampValidation(unittest.TestCase):
    """
    **Feature: ntp-delta-monitor, Property 12: Timestamp Validation**
    
    Property: For any parsed time value, malformed timestamps should be rejected 
    with appropriate error messages
    
    **Validates: Requirements 8.5**
    """

    @composite
    def valid_utc_timestamp(draw):
        """Generate valid UTC timestamps within reasonable range."""
        # Generate timestamps within 24 hours of current time (as per validation logic)
        now = datetime.now(timezone.utc)
        # Generate offset within 23 hours to be safe (leave some margin)
        offset_seconds = draw(st.integers(min_value=-82800, max_value=82800))  # 23 hours = 82800 seconds
        timestamp = now + timedelta(seconds=offset_seconds)
        return timestamp

    @composite
    def invalid_timestamp_no_timezone(draw):
        """Generate timestamps without timezone info."""
        # Generate naive datetime (no timezone)
        year = draw(st.integers(min_value=2020, max_value=2030))
        month = draw(st.integers(min_value=1, max_value=12))
        day = draw(st.integers(min_value=1, max_value=28))  # Safe day range
        hour = draw(st.integers(min_value=0, max_value=23))
        minute = draw(st.integers(min_value=0, max_value=59))
        second = draw(st.integers(min_value=0, max_value=59))
        return datetime(year, month, day, hour, minute, second)

    @composite
    def invalid_timestamp_wrong_timezone(draw):
        """Generate timestamps with non-UTC timezone."""
        # Generate timestamp with non-UTC timezone
        base_timestamp = draw(TestTimestampValidation.valid_utc_timestamp())
        # Convert to a different timezone (not UTC)
        from datetime import timezone as tz, timedelta as td
        non_utc_tz = tz(td(hours=draw(st.integers(min_value=-12, max_value=12).filter(lambda x: x != 0))))
        return base_timestamp.replace(tzinfo=non_utc_tz)

    @composite
    def invalid_timestamp_too_far(draw):
        """Generate timestamps too far in past or future."""
        now = datetime.now(timezone.utc)
        # Generate offset beyond 24 hours
        direction = draw(st.sampled_from([-1, 1]))
        offset_seconds = draw(st.integers(min_value=86401, max_value=365*24*3600))  # Beyond 24h up to 1 year
        timestamp = now + timedelta(seconds=direction * offset_seconds)
        return timestamp

    @given(valid_utc_timestamp())
    @settings(max_examples=100, deadline=None)
    def test_valid_utc_timestamps_accepted(self, timestamp):
        """
        **Feature: ntp-delta-monitor, Property 12: Timestamp Validation**
        
        Test that valid UTC timestamps within reasonable range are accepted.
        """
        # Test that valid UTC timestamps pass validation
        result = validate_timestamp_format(timestamp)
        self.assertTrue(result, f"Valid UTC timestamp should be accepted: {timestamp}")

    @given(invalid_timestamp_no_timezone())
    @settings(max_examples=100, deadline=None)
    def test_timestamps_without_timezone_rejected(self, timestamp):
        """
        **Feature: ntp-delta-monitor, Property 12: Timestamp Validation**
        
        Test that timestamps without timezone info are rejected.
        """
        # Test that naive timestamps (no timezone) are rejected
        result = validate_timestamp_format(timestamp)
        self.assertFalse(result, f"Timestamp without timezone should be rejected: {timestamp}")

    @given(invalid_timestamp_wrong_timezone())
    @settings(max_examples=100, deadline=None)
    def test_non_utc_timestamps_rejected(self, timestamp):
        """
        **Feature: ntp-delta-monitor, Property 12: Timestamp Validation**
        
        Test that timestamps with non-UTC timezone are rejected.
        """
        # Test that non-UTC timestamps are rejected
        result = validate_timestamp_format(timestamp)
        self.assertFalse(result, f"Non-UTC timestamp should be rejected: {timestamp}")

    @given(invalid_timestamp_too_far())
    @settings(max_examples=100, deadline=None)
    def test_timestamps_too_far_rejected(self, timestamp):
        """
        **Feature: ntp-delta-monitor, Property 12: Timestamp Validation**
        
        Test that timestamps too far in past or future are rejected.
        """
        # Test that timestamps beyond 24 hours are rejected
        result = validate_timestamp_format(timestamp)
        self.assertFalse(result, f"Timestamp too far from current time should be rejected: {timestamp}")

    def test_malformed_timestamp_objects_rejected(self):
        """
        **Feature: ntp-delta-monitor, Property 12: Timestamp Validation**
        
        Test that malformed timestamp objects are rejected with appropriate error handling.
        """
        # Test None input
        result = validate_timestamp_format(None)
        self.assertFalse(result, "None timestamp should be rejected")

        # Test non-datetime objects (these will cause AttributeError/TypeError)
        invalid_inputs = [
            "2023-01-01T12:00:00Z",  # String instead of datetime
            123456789,  # Integer instead of datetime
            [],  # List instead of datetime
            {},  # Dict instead of datetime
        ]
        
        for invalid_input in invalid_inputs:
            with self.subTest(invalid_input=invalid_input):
                result = validate_timestamp_format(invalid_input)
                self.assertFalse(result, f"Invalid input type should be rejected: {type(invalid_input)}")

    def test_timestamp_validation_in_ntp_query_context(self):
        """
        **Feature: ntp-delta-monitor, Property 12: Timestamp Validation**
        
        Test that timestamp validation is properly integrated into NTP query processing.
        """
        from unittest.mock import patch, MagicMock
        import ntplib
        
        # Create a mock NTP response with valid timestamp
        mock_response = MagicMock()
        mock_response.tx_time = datetime.now(timezone.utc).timestamp()
        mock_response.delay = 0.05
        mock_response.stratum = 2
        mock_response.root_delay = 0.01
        mock_response.root_dispersion = 0.005
        
        # Test that valid timestamp passes through NTP query
        with patch('ntp_monitor.ntplib.NTPClient') as mock_ntp_client_class:
            mock_client = MagicMock()
            mock_ntp_client_class.return_value = mock_client
            mock_client.request.return_value = mock_response
            
            # This should succeed without raising an exception
            result = query_ntp_server("test.ntp.server", 30)
            self.assertIsInstance(result, NTPResponse)
            self.assertEqual(result.stratum, 2)

        # Test that invalid timestamp causes rejection
        # Mock validate_timestamp_format to return False
        with patch('ntp_monitor.ntplib.NTPClient') as mock_ntp_client_class, \
             patch('ntp_monitor.validate_timestamp_format', return_value=False):
            
            mock_client = MagicMock()
            mock_ntp_client_class.return_value = mock_client
            mock_client.request.return_value = mock_response
            
            # This should raise an exception due to invalid timestamp
            with self.assertRaises(Exception) as context:
                query_ntp_server("test.ntp.server", 30)
            
            self.assertIn("Invalid timestamp format", str(context.exception))


class TestStratumValidation(unittest.TestCase):
    """
    **Feature: ntp-delta-monitor, Property 11: Stratum Validation**
    
    Property: For any NTP response with stratum 16 or higher, the system should mark 
    the server as UNSYNCHRONIZED status
    
    **Validates: Requirements 1.3, 2.4**
    """

    def create_ntp_response_with_stratum(self, stratum_value):
        """Create NTP response with specific stratum value."""
        return NTPResponse(
            timestamp_utc=datetime.now(timezone.utc),
            query_rtt_ms=50.0,
            stratum=stratum_value,
            root_delay_ms=10.0,
            root_dispersion_ms=5.0,
            is_synchronized=stratum_value < 16,
            error_message=None
        )

    @given(st.integers(min_value=16, max_value=255))
    @settings(max_examples=100, deadline=None)
    def test_stratum_16_or_higher_marked_unsynchronized(self, stratum_value):
        """
        **Feature: ntp-delta-monitor, Property 11: Stratum Validation**
        
        Test that NTP responses with stratum 16 or higher are marked as UNSYNCHRONIZED.
        """
        # Generate NTP response with stratum >= 16
        response = self.create_ntp_response_with_stratum(stratum_value)
        
        # Validate the response
        status, error_message = validate_ntp_response(response)
        
        # Verify that stratum 16+ is marked as UNSYNCHRONIZED
        self.assertEqual(status, NTPStatus.UNSYNCHRONIZED)
        self.assertIsNotNone(error_message)
        self.assertIn("unsynchronized", error_message.lower())
        self.assertIn(str(stratum_value), error_message)

    @given(st.integers(min_value=1, max_value=15))
    @settings(max_examples=100, deadline=None)
    def test_stratum_below_16_marked_ok(self, stratum_value):
        """
        **Feature: ntp-delta-monitor, Property 11: Stratum Validation**
        
        Test that NTP responses with stratum below 16 are marked as OK (synchronized).
        """
        # Generate NTP response with stratum < 16
        response = self.create_ntp_response_with_stratum(stratum_value)
        
        # Validate the response
        status, error_message = validate_ntp_response(response)
        
        # Verify that stratum < 16 is marked as OK
        self.assertEqual(status, NTPStatus.OK)
        self.assertIsNone(error_message)

    @given(st.integers(min_value=0, max_value=0))
    @settings(max_examples=100, deadline=None)
    def test_stratum_zero_edge_case(self, stratum_value):
        """
        **Feature: ntp-delta-monitor, Property 11: Stratum Validation**
        
        Test edge case: stratum 0 (typically reserved for reference clocks) should be OK.
        """
        # Generate NTP response with stratum 0
        response = self.create_ntp_response_with_stratum(stratum_value)
        
        # Validate the response
        status, error_message = validate_ntp_response(response)
        
        # Verify that stratum 0 is marked as OK
        self.assertEqual(status, NTPStatus.OK)
        self.assertIsNone(error_message)


class TestDNSResolutionHandling(unittest.TestCase):
    """
    **Feature: ntp-delta-monitor, Property 14: DNS Resolution Handling**
    
    Property: For any hostname that fails DNS resolution, the system should continue 
    processing using the original hostname and record appropriate status
    
    **Validates: Requirements 2.1, 2.2**
    """

    @composite
    def valid_hostname(draw):
        """Generate valid hostnames for testing."""
        # Generate realistic hostnames and IP addresses
        hostname_types = st.one_of(
            # Domain names
            st.builds(lambda prefix, domain: f"{prefix}.{domain}",
                     st.text(alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), min_codepoint=97, max_codepoint=122), 
                            min_size=3, max_size=10).filter(lambda x: x.isalnum()),
                     st.sampled_from(['example.com', 'test.org', 'ntp.pool.org', 'time.google.com'])),
            # IP addresses
            st.builds(lambda a, b, c, d: f"{a}.{b}.{c}.{d}", 
                     st.integers(1, 255), st.integers(0, 255), st.integers(0, 255), st.integers(1, 255))
        )
        return draw(hostname_types)

    @composite
    def timeout_value(draw):
        """Generate valid timeout values."""
        return draw(st.integers(min_value=1, max_value=60))

    @given(valid_hostname(), timeout_value())
    @settings(max_examples=100, deadline=None)
    def test_dns_resolution_success_returns_hostname_and_ip(self, hostname, timeout):
        """
        **Feature: ntp-delta-monitor, Property 14: DNS Resolution Handling**
        
        Test that successful DNS resolution returns both hostname and resolved IP.
        """
        from ntp_monitor import resolve_hostname_with_fallback
        import dns.resolver
        from unittest.mock import patch, MagicMock
        
        # Skip if hostname is already an IP address
        try:
            import socket
            socket.inet_aton(hostname)
            # If we get here, it's an IP address - should return as-is
            result_hostname, result_ip = resolve_hostname_with_fallback(hostname, timeout)
            self.assertEqual(result_hostname, hostname)
            self.assertEqual(result_ip, hostname)
            return
        except socket.error:
            pass  # Not an IP address, continue with DNS resolution test
        
        # Mock successful DNS resolution
        mock_answer = MagicMock()
        mock_answer.__str__ = lambda self: "192.168.1.100"
        
        with patch('ntp_monitor.dns.resolver.Resolver') as mock_resolver_class:
            mock_resolver = MagicMock()
            mock_resolver_class.return_value = mock_resolver
            mock_resolver.resolve.return_value = [mock_answer]
            
            # Execute DNS resolution
            result_hostname, result_ip = resolve_hostname_with_fallback(hostname, timeout)
            
            # Verify DNS resolver was configured with timeout
            self.assertEqual(mock_resolver.timeout, timeout)
            self.assertEqual(mock_resolver.lifetime, timeout)
            
            # Verify DNS resolution was attempted
            mock_resolver.resolve.assert_called_once_with(hostname, 'A')
            
            # Verify successful resolution returns hostname and IP
            self.assertEqual(result_hostname, hostname)
            self.assertEqual(result_ip, "192.168.1.100")

    @given(valid_hostname(), timeout_value())
    @settings(max_examples=100, deadline=None)
    def test_dns_resolution_failure_continues_with_original_hostname(self, hostname, timeout):
        """
        **Feature: ntp-delta-monitor, Property 14: DNS Resolution Handling**
        
        Test that DNS resolution failures continue processing with original hostname.
        """
        from ntp_monitor import resolve_hostname_with_fallback
        import dns.resolver
        from unittest.mock import patch
        
        # Skip if hostname is already an IP address
        try:
            import socket
            socket.inet_aton(hostname)
            # If we get here, it's an IP address - should return as-is
            result_hostname, result_ip = resolve_hostname_with_fallback(hostname, timeout)
            self.assertEqual(result_hostname, hostname)
            self.assertEqual(result_ip, hostname)
            return
        except socket.error:
            pass  # Not an IP address, continue with DNS failure test
        
        # Test different types of DNS failures
        dns_exceptions = [
            dns.resolver.NXDOMAIN(),
            dns.resolver.NoAnswer(),
            dns.resolver.Timeout(),
            Exception("DNS error")
        ]
        
        for dns_exception in dns_exceptions:
            with self.subTest(exception=type(dns_exception).__name__):
                with patch('ntp_monitor.dns.resolver.Resolver') as mock_resolver_class:
                    mock_resolver = MagicMock()
                    mock_resolver_class.return_value = mock_resolver
                    mock_resolver.resolve.side_effect = dns_exception
                    
                    # Execute DNS resolution
                    result_hostname, result_ip = resolve_hostname_with_fallback(hostname, timeout)
                    
                    # Verify DNS resolver was configured with timeout
                    self.assertEqual(mock_resolver.timeout, timeout)
                    self.assertEqual(mock_resolver.lifetime, timeout)
                    
                    # Verify DNS resolution was attempted
                    mock_resolver.resolve.assert_called_once_with(hostname, 'A')
                    
                    # Verify failure continues with original hostname and None IP
                    self.assertEqual(result_hostname, hostname)
                    self.assertIsNone(result_ip)

    @given(timeout_value())
    @settings(max_examples=100, deadline=None)
    def test_ip_address_input_returns_unchanged(self, timeout):
        """
        **Feature: ntp-delta-monitor, Property 14: DNS Resolution Handling**
        
        Test that IP address inputs are returned unchanged without DNS resolution.
        """
        from ntp_monitor import resolve_hostname_with_fallback
        
        # Generate valid IP addresses
        ip_addresses = [
            "192.168.1.1",
            "10.0.0.1", 
            "172.16.0.1",
            "8.8.8.8",
            "1.1.1.1"
        ]
        
        for ip_address in ip_addresses:
            with self.subTest(ip_address=ip_address):
                # Execute DNS resolution with IP address
                result_hostname, result_ip = resolve_hostname_with_fallback(ip_address, timeout)
                
                # Verify IP addresses are returned unchanged
                self.assertEqual(result_hostname, ip_address)
                self.assertEqual(result_ip, ip_address)

    @given(valid_hostname(), timeout_value())
    @settings(max_examples=100, deadline=None)
    def test_dns_resolution_no_answers_continues_with_original(self, hostname, timeout):
        """
        **Feature: ntp-delta-monitor, Property 14: DNS Resolution Handling**
        
        Test that DNS resolution with no answers continues with original hostname.
        """
        from ntp_monitor import resolve_hostname_with_fallback
        from unittest.mock import patch
        
        # Skip if hostname is already an IP address
        try:
            import socket
            socket.inet_aton(hostname)
            return  # Skip IP addresses for this test
        except socket.error:
            pass  # Not an IP address, continue with test
        
        with patch('ntp_monitor.dns.resolver.Resolver') as mock_resolver_class:
            mock_resolver = MagicMock()
            mock_resolver_class.return_value = mock_resolver
            # Return empty list (no answers)
            mock_resolver.resolve.return_value = []
            
            # Execute DNS resolution
            result_hostname, result_ip = resolve_hostname_with_fallback(hostname, timeout)
            
            # Verify DNS resolver was configured with timeout
            self.assertEqual(mock_resolver.timeout, timeout)
            self.assertEqual(mock_resolver.lifetime, timeout)
            
            # Verify DNS resolution was attempted
            mock_resolver.resolve.assert_called_once_with(hostname, 'A')
            
            # Verify no answers continues with original hostname and None IP
            self.assertEqual(result_hostname, hostname)
            self.assertIsNone(result_ip)

    def test_dns_resolution_integration_with_ntp_processing(self):
        """
        **Feature: ntp-delta-monitor, Property 14: DNS Resolution Handling**
        
        Test that DNS resolution is properly integrated into NTP server processing.
        """
        from ntp_monitor import process_single_server, Config, NTPStatus
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        import dns.resolver
        
        # Create test configuration
        config = Config(
            reference_ntp="test.reference.com",
            ntp_servers_file=Path("test.txt"),
            output_file=None,
            format_type="seconds",
            parallel_limit=10,
            ntp_timeout=30,
            verbose=False
        )
        
        # Test case 1: DNS resolution succeeds, NTP query succeeds
        with patch('ntp_monitor.resolve_hostname_with_fallback') as mock_dns, \
             patch('ntp_monitor.query_ntp_server') as mock_ntp:
            
            # Mock successful DNS resolution
            mock_dns.return_value = ("test.server.com", "192.168.1.100")
            
            # Mock successful NTP query
            from datetime import datetime, timezone
            mock_ntp_response = MagicMock()
            mock_ntp_response.timestamp_utc = datetime.now(timezone.utc)
            mock_ntp_response.query_rtt_ms = 50.0
            mock_ntp_response.stratum = 2
            mock_ntp_response.root_delay_ms = 10.0
            mock_ntp_response.root_dispersion_ms = 5.0
            mock_ntp_response.is_synchronized = True
            mock_ntp_response.error_message = None
            mock_ntp.return_value = mock_ntp_response
            
            # Mock validation to return OK
            with patch('ntp_monitor.validate_ntp_response') as mock_validate:
                mock_validate.return_value = (NTPStatus.OK, None)
                
                # Execute server processing
                result = process_single_server("test.server.com", None, config)
                
                # Verify DNS resolution was called
                mock_dns.assert_called_once_with("test.server.com", config.ntp_timeout)
                
                # Verify NTP query used resolved hostname
                mock_ntp.assert_called_once_with("test.server.com", config.ntp_timeout)
                
                # Verify result contains resolved IP
                self.assertEqual(result.ntp_server, "test.server.com")
                self.assertEqual(result.ntp_server_ip, "192.168.1.100")
                self.assertEqual(result.status, NTPStatus.OK)

        # Test case 2: DNS resolution fails, NTP query still attempted with original hostname
        with patch('ntp_monitor.resolve_hostname_with_fallback') as mock_dns, \
             patch('ntp_monitor.query_ntp_server') as mock_ntp:
            
            # Mock failed DNS resolution
            mock_dns.return_value = ("test.server.com", None)
            
            # Mock NTP query failure due to DNS
            mock_ntp.side_effect = Exception("DNS resolution failed")
            
            # Mock error handling
            with patch('ntp_monitor.handle_ntp_query_error') as mock_error_handler:
                mock_error_handler.return_value = (NTPStatus.UNREACHABLE, "DNS resolution failed")
                
                # Execute server processing
                result = process_single_server("test.server.com", None, config)
                
                # Verify DNS resolution was called
                mock_dns.assert_called_once_with("test.server.com", config.ntp_timeout)
                
                # Verify NTP query was still attempted with original hostname
                mock_ntp.assert_called_once_with("test.server.com", config.ntp_timeout)
                
                # Verify result shows DNS failure but processing continued
                self.assertEqual(result.ntp_server, "test.server.com")
                self.assertIsNone(result.ntp_server_ip)
                self.assertEqual(result.status, NTPStatus.UNREACHABLE)
                self.assertIn("DNS resolution failed", result.error_message)


class TestDeltaCalculationAccuracy(unittest.TestCase):
    """
    **Feature: ntp-delta-monitor, Property 4: Delta Calculation Accuracy**
    
    Property: For any pair of target NTP time and reference NTP time, the delta calculation 
    should equal target_time minus reference_time with correct sign preservation
    
    **Validates: Requirements 4.1, 4.4**
    """

    @composite
    def valid_utc_datetime_pair(draw):
        """Generate pairs of valid UTC datetime objects for delta calculation testing."""
        # Generate base reference time
        base_time = datetime.now(timezone.utc)
        
        # Generate reference time within reasonable range (±1 day from now)
        ref_offset_seconds = draw(st.integers(min_value=-86400, max_value=86400))
        reference_time = base_time + timedelta(seconds=ref_offset_seconds)
        
        # Generate target time with various offsets from reference time
        # This will create both positive and negative deltas
        target_offset_seconds = draw(st.integers(min_value=-3600, max_value=3600))  # ±1 hour from reference
        target_time = reference_time + timedelta(seconds=target_offset_seconds)
        
        return target_time, reference_time

    @composite
    def none_target_time_case(draw):
        """Generate test case where target_time is None (failed query scenario)."""
        # Generate valid reference time
        base_time = datetime.now(timezone.utc)
        ref_offset_seconds = draw(st.integers(min_value=-86400, max_value=86400))
        reference_time = base_time + timedelta(seconds=ref_offset_seconds)
        
        return None, reference_time

    @given(valid_utc_datetime_pair())
    @settings(max_examples=100, deadline=None)
    def test_delta_calculation_equals_target_minus_reference(self, datetime_pair):
        """
        **Feature: ntp-delta-monitor, Property 4: Delta Calculation Accuracy**
        
        Test that delta calculation equals target_time minus reference_time.
        """
        from ntp_monitor import calculate_time_delta
        
        target_time, reference_time = datetime_pair
        
        # Calculate delta using the function under test
        calculated_delta = calculate_time_delta(target_time, reference_time)
        
        # Calculate expected delta manually
        expected_delta = (target_time - reference_time).total_seconds()
        
        # Verify delta calculation accuracy
        self.assertIsNotNone(calculated_delta)
        self.assertAlmostEqual(calculated_delta, expected_delta, places=6)
        
        # Verify the calculation is exactly target_time minus reference_time
        self.assertEqual(calculated_delta, expected_delta)

    @given(valid_utc_datetime_pair())
    @settings(max_examples=100, deadline=None)
    def test_delta_sign_preservation_positive_when_target_ahead(self, datetime_pair):
        """
        **Feature: ntp-delta-monitor, Property 4: Delta Calculation Accuracy**
        
        Test that positive delta values indicate target is ahead of reference.
        """
        from ntp_monitor import calculate_time_delta
        
        target_time, reference_time = datetime_pair
        
        # Ensure target is ahead of reference (positive delta expected)
        if target_time <= reference_time:
            # Make target ahead by adding time
            target_time = reference_time + timedelta(seconds=300)  # 5 minutes ahead
        
        # Calculate delta
        calculated_delta = calculate_time_delta(target_time, reference_time)
        
        # Verify positive delta when target is ahead
        self.assertIsNotNone(calculated_delta)
        self.assertGreater(calculated_delta, 0, 
                          f"Delta should be positive when target ({target_time}) is ahead of reference ({reference_time})")
        
        # Verify the exact calculation
        expected_delta = (target_time - reference_time).total_seconds()
        self.assertEqual(calculated_delta, expected_delta)
        self.assertGreater(expected_delta, 0)

    @given(valid_utc_datetime_pair())
    @settings(max_examples=100, deadline=None)
    def test_delta_sign_preservation_negative_when_target_behind(self, datetime_pair):
        """
        **Feature: ntp-delta-monitor, Property 4: Delta Calculation Accuracy**
        
        Test that negative delta values indicate target is behind reference.
        """
        from ntp_monitor import calculate_time_delta
        
        target_time, reference_time = datetime_pair
        
        # Ensure target is behind reference (negative delta expected)
        if target_time >= reference_time:
            # Make target behind by subtracting time
            target_time = reference_time - timedelta(seconds=300)  # 5 minutes behind
        
        # Calculate delta
        calculated_delta = calculate_time_delta(target_time, reference_time)
        
        # Verify negative delta when target is behind
        self.assertIsNotNone(calculated_delta)
        self.assertLess(calculated_delta, 0, 
                       f"Delta should be negative when target ({target_time}) is behind reference ({reference_time})")
        
        # Verify the exact calculation
        expected_delta = (target_time - reference_time).total_seconds()
        self.assertEqual(calculated_delta, expected_delta)
        self.assertLess(expected_delta, 0)

    @given(none_target_time_case())
    @settings(max_examples=100, deadline=None)
    def test_delta_calculation_handles_none_target_time(self, datetime_pair):
        """
        **Feature: ntp-delta-monitor, Property 4: Delta Calculation Accuracy**
        
        Test that delta calculation returns None when target_time is None (failed query).
        """
        from ntp_monitor import calculate_time_delta
        
        target_time, reference_time = datetime_pair
        
        # Verify target_time is None (failed query scenario)
        self.assertIsNone(target_time)
        self.assertIsNotNone(reference_time)
        
        # Calculate delta with None target_time
        calculated_delta = calculate_time_delta(target_time, reference_time)
        
        # Verify None is returned for failed queries
        self.assertIsNone(calculated_delta, 
                         "Delta calculation should return None when target_time is None")

    def test_delta_calculation_zero_when_times_equal(self):
        """
        **Feature: ntp-delta-monitor, Property 4: Delta Calculation Accuracy**
        
        Test that delta calculation returns zero when target and reference times are equal.
        """
        from ntp_monitor import calculate_time_delta
        
        # Create identical timestamps
        reference_time = datetime.now(timezone.utc)
        target_time = reference_time  # Exactly the same
        
        # Calculate delta
        calculated_delta = calculate_time_delta(target_time, reference_time)
        
        # Verify zero delta for identical times
        self.assertIsNotNone(calculated_delta)
        self.assertEqual(calculated_delta, 0.0)
        
        # Verify the calculation logic
        expected_delta = (target_time - reference_time).total_seconds()
        self.assertEqual(calculated_delta, expected_delta)
        self.assertEqual(expected_delta, 0.0)

    def test_delta_calculation_precision_with_microseconds(self):
        """
        **Feature: ntp-delta-monitor, Property 4: Delta Calculation Accuracy**
        
        Test that delta calculation maintains precision with microsecond-level differences.
        """
        from ntp_monitor import calculate_time_delta
        
        # Create times with microsecond precision differences
        reference_time = datetime.now(timezone.utc)
        target_time = reference_time + timedelta(microseconds=123456)  # 0.123456 seconds
        
        # Calculate delta
        calculated_delta = calculate_time_delta(target_time, reference_time)
        
        # Verify precision is maintained
        self.assertIsNotNone(calculated_delta)
        expected_delta = 0.123456  # 123456 microseconds = 0.123456 seconds
        self.assertAlmostEqual(calculated_delta, expected_delta, places=6)
        
        # Verify exact calculation
        manual_delta = (target_time - reference_time).total_seconds()
        self.assertEqual(calculated_delta, manual_delta)

    @given(st.integers(min_value=-86400, max_value=86400))
    @settings(max_examples=100, deadline=None)
    def test_delta_calculation_with_various_time_differences(self, offset_seconds):
        """
        **Feature: ntp-delta-monitor, Property 4: Delta Calculation Accuracy**
        
        Test delta calculation accuracy across various time differences.
        """
        from ntp_monitor import calculate_time_delta
        
        # Create reference time and target time with specified offset
        reference_time = datetime.now(timezone.utc)
        target_time = reference_time + timedelta(seconds=offset_seconds)
        
        # Calculate delta
        calculated_delta = calculate_time_delta(target_time, reference_time)
        
        # Verify calculation accuracy
        self.assertIsNotNone(calculated_delta)
        self.assertEqual(calculated_delta, float(offset_seconds))
        
        # Verify sign preservation based on offset
        if offset_seconds > 0:
            self.assertGreater(calculated_delta, 0, "Positive offset should result in positive delta")
        elif offset_seconds < 0:
            self.assertLess(calculated_delta, 0, "Negative offset should result in negative delta")
        else:
            self.assertEqual(calculated_delta, 0.0, "Zero offset should result in zero delta")

    def test_delta_calculation_integration_with_ntp_result(self):
        """
        **Feature: ntp-delta-monitor, Property 4: Delta Calculation Accuracy**
        
        Test that delta calculation is properly integrated into NTP result processing.
        """
        from ntp_monitor import process_single_server, Config, NTPStatus
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        
        # Create test configuration
        config = Config(
            reference_ntp="test.reference.com",
            ntp_servers_file=Path("test.txt"),
            output_file=None,
            format_type="seconds",
            parallel_limit=10,
            ntp_timeout=30,
            verbose=False
        )
        
        # Create test timestamps
        reference_time = datetime.now(timezone.utc)
        target_time = reference_time + timedelta(seconds=150)  # 2.5 minutes ahead
        expected_delta = 150.0
        
        # Mock NTP query to return controlled timestamp
        mock_ntp_response = MagicMock()
        mock_ntp_response.timestamp_utc = target_time
        mock_ntp_response.query_rtt_ms = 50.0
        mock_ntp_response.stratum = 2
        mock_ntp_response.root_delay_ms = 10.0
        mock_ntp_response.root_dispersion_ms = 5.0
        mock_ntp_response.is_synchronized = True
        mock_ntp_response.error_message = None
        
        with patch('ntp_monitor.resolve_hostname_with_fallback') as mock_dns, \
             patch('ntp_monitor.query_ntp_server') as mock_ntp, \
             patch('ntp_monitor.validate_ntp_response') as mock_validate:
            
            # Mock successful DNS resolution
            mock_dns.return_value = ("test.server.com", "192.168.1.100")
            
            # Mock successful NTP query
            mock_ntp.return_value = mock_ntp_response
            
            # Mock validation to return OK
            mock_validate.return_value = (NTPStatus.OK, None)
            
            # Execute server processing with reference time
            result = process_single_server("test.server.com", reference_time, config)
            
            # Verify delta calculation was performed correctly
            self.assertEqual(result.status, NTPStatus.OK)
            self.assertIsNotNone(result.delta_seconds)
            self.assertEqual(result.delta_seconds, expected_delta)
            
            # Verify formatted delta (should be same for seconds format)
            self.assertIsNotNone(result.delta_formatted)
            self.assertEqual(result.delta_formatted, expected_delta)


class TestTimestampFormatConsistency(unittest.TestCase):
    """
    **Feature: ntp-delta-monitor, Property 2: Timestamp Format Consistency**
    
    Property: For any timestamp generated or processed by the system, it should be 
    formatted in ISO 8601 UTC format
    
    **Validates: Requirements 1.5, 5.3**
    """

    @composite
    def valid_utc_datetime(draw):
        """Generate valid UTC datetime objects for testing."""
        # Generate timestamps within reasonable range (±1 year from now)
        now = datetime.now(timezone.utc)
        offset_seconds = draw(st.integers(min_value=-365*24*3600, max_value=365*24*3600))
        timestamp = now + timedelta(seconds=offset_seconds)
        return timestamp

    @composite
    def ntp_result_with_timestamps(draw):
        """Generate NTPResult objects with various timestamp scenarios."""
        from ntp_monitor import NTPResult, NTPStatus
        
        # Generate base timestamps
        query_timestamp = draw(TestTimestampFormatConsistency.valid_utc_datetime())
        
        # Sometimes include NTP time, sometimes None (for failed queries)
        include_ntp_time = draw(st.booleans())
        ntp_time = draw(TestTimestampFormatConsistency.valid_utc_datetime()) if include_ntp_time else None
        
        # Generate simple server names to avoid filtering issues
        server_names = [
            "test.server.com",
            "ntp.example.org", 
            "time.test.net",
            "192.168.1.100",
            "10.0.0.1"
        ]
        server = draw(st.sampled_from(server_names))
        status = draw(st.sampled_from(list(NTPStatus)))
        
        return NTPResult(
            timestamp_utc=query_timestamp,
            ntp_server=server,
            ntp_server_ip=None,
            ntp_time_utc=ntp_time,
            query_rtt_ms=50.0 if status == NTPStatus.OK else None,
            stratum=2 if status == NTPStatus.OK else None,
            root_delay_ms=10.0 if status == NTPStatus.OK else None,
            root_dispersion_ms=5.0 if status == NTPStatus.OK else None,
            delta_seconds=0.0 if status == NTPStatus.OK else None,
            delta_formatted=0.0 if status == NTPStatus.OK else None,
            status=status,
            error_message=None if status == NTPStatus.OK else "Test error"
        )

    @given(valid_utc_datetime())
    @settings(max_examples=100, deadline=None)
    def test_datetime_isoformat_produces_iso8601_utc(self, timestamp):
        """
        **Feature: ntp-delta-monitor, Property 2: Timestamp Format Consistency**
        
        Test that datetime.isoformat() produces valid ISO 8601 UTC format strings.
        """
        # Format timestamp using the same method as the system
        formatted_timestamp = timestamp.isoformat()
        
        # Verify the format matches ISO 8601 pattern
        # ISO 8601 UTC format: YYYY-MM-DDTHH:MM:SS+00:00 or YYYY-MM-DDTHH:MM:SS.fffffZ
        import re
        
        # Pattern for ISO 8601 UTC format (with or without microseconds)
        iso8601_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+00:00|Z)?$'
        
        self.assertIsNotNone(re.match(iso8601_pattern, formatted_timestamp),
                           f"Timestamp '{formatted_timestamp}' does not match ISO 8601 format")
        
        # Verify the timestamp can be parsed back to the same datetime
        # This ensures the format is valid and consistent
        if formatted_timestamp.endswith('+00:00'):
            # Handle explicit UTC offset
            parsed_timestamp = datetime.fromisoformat(formatted_timestamp)
        elif formatted_timestamp.endswith('Z'):
            # Handle Z suffix (not supported by fromisoformat directly)
            parsed_timestamp = datetime.fromisoformat(formatted_timestamp[:-1] + '+00:00')
        else:
            # Handle implicit UTC (add timezone info)
            parsed_timestamp = datetime.fromisoformat(formatted_timestamp).replace(tzinfo=timezone.utc)
        
        # Verify parsed timestamp equals original (within microsecond precision)
        time_diff = abs((parsed_timestamp - timestamp).total_seconds())
        self.assertLess(time_diff, 0.000001, 
                       f"Parsed timestamp differs from original by {time_diff} seconds")

    @given(ntp_result_with_timestamps())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.filter_too_much])
    def test_csv_timestamp_formatting_consistency(self, ntp_result):
        """
        **Feature: ntp-delta-monitor, Property 2: Timestamp Format Consistency**
        
        Test that CSV output formats all timestamps consistently in ISO 8601 UTC format.
        """
        from ntp_monitor import write_csv_report, Config
        from pathlib import Path
        import tempfile
        import csv
        
        # Create temporary config
        config = Config(
            reference_ntp="test.reference.com",
            ntp_servers_file=Path("test.txt"),
            output_file=None,
            format_type="seconds",
            parallel_limit=10,
            ntp_timeout=30,
            verbose=False
        )
        
        # Write CSV to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        
        try:
            # Write the result to CSV
            write_csv_report([ntp_result], temp_path, config)
            
            # Read back and verify timestamp formats
            with open(temp_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
                
                self.assertEqual(len(rows), 1, "Should have exactly one row")
                row = rows[0]
                
                # Check query timestamp format
                timestamp_utc_str = row['timestamp_utc']
                if timestamp_utc_str:  # Not empty
                    self.assertTrue(self._is_valid_iso8601_format(timestamp_utc_str),
                                  f"Query timestamp '{timestamp_utc_str}' is not in valid ISO 8601 format")
                
                # Check NTP time format (if present)
                ntp_time_utc_str = row['ntp_time_utc']
                if ntp_time_utc_str:  # Not empty (could be empty for failed queries)
                    self.assertTrue(self._is_valid_iso8601_format(ntp_time_utc_str),
                                  f"NTP timestamp '{ntp_time_utc_str}' is not in valid ISO 8601 format")
                
        finally:
            # Clean up temporary file
            temp_path.unlink(missing_ok=True)

    @given(valid_utc_datetime())
    @settings(max_examples=100, deadline=None)
    def test_ntp_query_timestamp_logging_format(self, mock_timestamp):
        """
        **Feature: ntp-delta-monitor, Property 2: Timestamp Format Consistency**
        
        Test that NTP query logging uses consistent ISO 8601 UTC format.
        """
        from ntp_monitor import query_ntp_server
        from unittest.mock import patch, MagicMock
        import logging
        
        # Create a mock NTP response with the test timestamp
        mock_response = MagicMock()
        mock_response.tx_time = mock_timestamp.timestamp()
        mock_response.delay = 0.05
        mock_response.stratum = 2
        mock_response.root_delay = 0.01
        mock_response.root_dispersion = 0.005
        
        # Capture log messages
        with patch('ntp_monitor.ntplib.NTPClient') as mock_ntp_client_class, \
             patch('ntp_monitor.validate_timestamp_format', return_value=True), \
             patch('ntp_monitor.validate_ntp_response', return_value=('OK', None)):
            
            mock_client = MagicMock()
            mock_ntp_client_class.return_value = mock_client
            mock_client.request.return_value = mock_response
            
            # Capture debug logs
            with self.assertLogs('ntp_monitor', level='DEBUG') as log_context:
                result = query_ntp_server("test.server.com", 30)
            
            # Find the timestamp log message
            timestamp_log_found = False
            for log_message in log_context.output:
                if "Timestamp:" in log_message:
                    timestamp_log_found = True
                    # Extract the timestamp from the log message
                    # Format: "DEBUG:ntp_monitor:  Timestamp: 2023-12-30T15:30:45.123456+00:00"
                    timestamp_part = log_message.split("Timestamp: ")[1]
                    
                    # Verify it's in ISO 8601 format
                    self.assertTrue(self._is_valid_iso8601_format(timestamp_part),
                                  f"Logged timestamp '{timestamp_part}' is not in valid ISO 8601 format")
                    break
            
            self.assertTrue(timestamp_log_found, "Timestamp log message not found in debug output")

    @given(valid_utc_datetime())
    @settings(max_examples=100, deadline=None)
    def test_reference_ntp_query_logging_format(self, mock_timestamp):
        """
        **Feature: ntp-delta-monitor, Property 2: Timestamp Format Consistency**
        
        Test that reference NTP query logging uses consistent ISO 8601 UTC format.
        """
        from ntp_monitor import NTPResponse, NTPStatus
        from unittest.mock import patch, MagicMock
        
        # Create a mock NTP response with the test timestamp
        mock_response = NTPResponse(
            timestamp_utc=mock_timestamp,
            query_rtt_ms=50.0,
            stratum=2,
            root_delay_ms=10.0,
            root_dispersion_ms=5.0,
            is_synchronized=True,
            error_message=None
        )
        
        with patch('ntp_monitor.query_ntp_server', return_value=mock_response), \
             patch('ntp_monitor.validate_ntp_response', return_value=(NTPStatus.OK, None)):
            
            # Capture info logs
            with self.assertLogs('ntp_monitor', level='INFO') as log_context:
                # Import and call the function that does the logging
                from ntp_monitor import query_reference_ntp, Config
                from pathlib import Path
                
                config = Config(
                    reference_ntp="test.reference.com",
                    ntp_servers_file=Path("test.txt"),
                    output_file=None,
                    format_type="seconds",
                    parallel_limit=10,
                    ntp_timeout=30,
                    verbose=False
                )
                
                result = query_reference_ntp("test.reference.com", config)
            
            # Find the reference query success log message
            reference_log_found = False
            for log_message in log_context.output:
                if "Reference NTP query successful:" in log_message:
                    reference_log_found = True
                    # Extract the timestamp from the log message
                    timestamp_part = log_message.split("Reference NTP query successful: ")[1].split()[0]
                    
                    # Verify it's in ISO 8601 format
                    self.assertTrue(self._is_valid_iso8601_format(timestamp_part),
                                  f"Reference query logged timestamp '{timestamp_part}' is not in valid ISO 8601 format")
                    break
            
            self.assertTrue(reference_log_found, "Reference NTP query success log message not found")

    def test_filename_generation_timestamp_format(self):
        """
        **Feature: ntp-delta-monitor, Property 2: Timestamp Format Consistency**
        
        Test that filename generation uses consistent timestamp format.
        """
        from ntp_monitor import generate_default_filename
        from unittest.mock import patch
        
        # Mock datetime.now to return a known timestamp
        test_timestamp = datetime(2023, 12, 30, 15, 30, 45, tzinfo=timezone.utc)
        
        with patch('ntp_monitor.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_timestamp
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            filename = generate_default_filename()
            
            # Verify filename contains properly formatted timestamp
            # Expected format: ntp_monitor_report_YYYYMMDD_HHMMSS.csv
            expected_timestamp_part = "20231230_153045"
            self.assertIn(expected_timestamp_part, filename,
                         f"Filename '{filename}' does not contain expected timestamp format")
            
            # Verify full filename format
            expected_filename = f"ntp_monitor_report_{expected_timestamp_part}.csv"
            self.assertEqual(filename, expected_filename)

    def _is_valid_iso8601_format(self, timestamp_str: str) -> bool:
        """
        Helper method to validate ISO 8601 timestamp format.
        
        Args:
            timestamp_str: Timestamp string to validate
            
        Returns:
            True if valid ISO 8601 format, False otherwise
        """
        import re
        
        # Pattern for ISO 8601 UTC format variations
        # Supports: YYYY-MM-DDTHH:MM:SS, YYYY-MM-DDTHH:MM:SS.ffffff, with +00:00 or Z suffix
        iso8601_patterns = [
            r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00$',  # With +00:00
            r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$',        # With Z suffix
            r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$'          # Without timezone (implicit UTC)
        ]
        
        for pattern in iso8601_patterns:
            if re.match(pattern, timestamp_str):
                return True
        
        return False

    @given(st.lists(ntp_result_with_timestamps(), min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.filter_too_much])
    def test_multiple_results_timestamp_consistency(self, ntp_results):
        """
        **Feature: ntp-delta-monitor, Property 2: Timestamp Format Consistency**
        
        Test that multiple NTP results maintain consistent timestamp formatting.
        """
        from ntp_monitor import write_csv_report, Config
        from pathlib import Path
        import tempfile
        import csv
        
        # Create temporary config
        config = Config(
            reference_ntp="test.reference.com",
            ntp_servers_file=Path("test.txt"),
            output_file=None,
            format_type="seconds",
            parallel_limit=10,
            ntp_timeout=30,
            verbose=False
        )
        
        # Write CSV to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        
        try:
            # Write all results to CSV
            write_csv_report(ntp_results, temp_path, config)
            
            # Read back and verify all timestamp formats are consistent
            with open(temp_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
                
                self.assertEqual(len(rows), len(ntp_results), 
                               f"Should have {len(ntp_results)} rows, got {len(rows)}")
                
                for i, row in enumerate(rows):
                    # Check query timestamp format (should always be present)
                    timestamp_utc_str = row['timestamp_utc']
                    self.assertTrue(timestamp_utc_str, f"Row {i}: Query timestamp should not be empty")
                    self.assertTrue(self._is_valid_iso8601_format(timestamp_utc_str),
                                  f"Row {i}: Query timestamp '{timestamp_utc_str}' is not in valid ISO 8601 format")
                    
                    # Check NTP time format (if present - may be empty for failed queries)
                    ntp_time_utc_str = row['ntp_time_utc']
                    if ntp_time_utc_str:  # Only check if not empty
                        self.assertTrue(self._is_valid_iso8601_format(ntp_time_utc_str),
                                      f"Row {i}: NTP timestamp '{ntp_time_utc_str}' is not in valid ISO 8601 format")
                
        finally:
            # Clean up temporary file
            temp_path.unlink(missing_ok=True)


class TestFormatPrecisionCompliance(unittest.TestCase):
    """
    **Feature: ntp-delta-monitor, Property 5: Format Precision Compliance**
    
    Property: For any delta value, when format is set to seconds, output should be 
    decimal seconds with millisecond precision; when set to milliseconds, output 
    should be integer milliseconds
    
    **Validates: Requirements 4.2, 4.3**
    """

    @composite
    def valid_delta_seconds(draw):
        """Generate valid delta values in seconds for testing."""
        # Generate realistic delta values that might occur in NTP monitoring
        # Range from -3600 to +3600 seconds (±1 hour) with high precision
        return draw(st.floats(
            min_value=-3600.0, 
            max_value=3600.0,
            allow_nan=False,
            allow_infinity=False
        ))

    @composite
    def format_type_choice(draw):
        """Generate valid format type choices."""
        return draw(st.sampled_from(['seconds', 'milliseconds']))

    @given(valid_delta_seconds(), st.just('seconds'))
    @settings(max_examples=100, deadline=None)
    def test_seconds_format_has_millisecond_precision(self, delta_seconds, format_type):
        """
        **Feature: ntp-delta-monitor, Property 5: Format Precision Compliance**
        
        Test that seconds format provides decimal seconds with millisecond precision (3 decimal places).
        """
        from ntp_monitor import format_delta_value
        
        # Format the delta value
        formatted_value = format_delta_value(delta_seconds, format_type)
        
        # Verify result is not None
        self.assertIsNotNone(formatted_value)
        
        # Verify result is a float (decimal seconds)
        self.assertIsInstance(formatted_value, float)
        
        # Verify millisecond precision (3 decimal places)
        # Convert to string to check decimal places
        formatted_str = f"{formatted_value:.10f}"  # Use high precision to see actual decimals
        
        # Find decimal point and count significant digits after it
        if '.' in formatted_str:
            decimal_part = formatted_str.split('.')[1].rstrip('0')  # Remove trailing zeros
            # The formatted value should have at most 3 decimal places of precision
            # (it may have fewer if the value rounds to fewer decimals)
            expected_rounded = round(delta_seconds, 3)
            self.assertEqual(formatted_value, expected_rounded)
        
        # Verify the value is properly rounded to 3 decimal places
        manually_rounded = round(delta_seconds, 3)
        self.assertEqual(formatted_value, manually_rounded)

    @given(valid_delta_seconds(), st.just('milliseconds'))
    @settings(max_examples=100, deadline=None)
    def test_milliseconds_format_returns_integer_milliseconds(self, delta_seconds, format_type):
        """
        **Feature: ntp-delta-monitor, Property 5: Format Precision Compliance**
        
        Test that milliseconds format returns integer milliseconds.
        """
        from ntp_monitor import format_delta_value
        
        # Format the delta value
        formatted_value = format_delta_value(delta_seconds, format_type)
        
        # Verify result is not None
        self.assertIsNotNone(formatted_value)
        
        # Verify result is an integer
        self.assertIsInstance(formatted_value, int)
        
        # Verify conversion accuracy: delta_seconds * 1000 rounded to nearest integer
        expected_milliseconds = int(round(delta_seconds * 1000))
        self.assertEqual(formatted_value, expected_milliseconds)
        
        # Verify the value represents the same time duration in milliseconds
        # Convert back to seconds and check it's within 0.5ms of original
        back_to_seconds = formatted_value / 1000.0
        difference = abs(back_to_seconds - delta_seconds)
        self.assertLessEqual(difference, 0.0005, 
                           f"Millisecond conversion should be within 0.5ms accuracy. "
                           f"Original: {delta_seconds}s, Converted: {formatted_value}ms, "
                           f"Back to seconds: {back_to_seconds}s, Difference: {difference}s")

    @given(st.just(None), format_type_choice())
    @settings(max_examples=100, deadline=None)
    def test_none_input_returns_none(self, delta_seconds, format_type):
        """
        **Feature: ntp-delta-monitor, Property 5: Format Precision Compliance**
        
        Test that None input (failed query scenario) returns None regardless of format.
        """
        from ntp_monitor import format_delta_value
        
        # Format None delta value
        formatted_value = format_delta_value(delta_seconds, format_type)
        
        # Verify None input returns None
        self.assertIsNone(formatted_value)

    @given(valid_delta_seconds())
    @settings(max_examples=100, deadline=None)
    def test_unknown_format_defaults_to_seconds(self, delta_seconds):
        """
        **Feature: ntp-delta-monitor, Property 5: Format Precision Compliance**
        
        Test that unknown format types default to seconds format with millisecond precision.
        """
        from ntp_monitor import format_delta_value
        
        # Test with unknown format type
        unknown_formats = ['unknown', 'invalid', '', 'minutes', 'hours']
        
        for unknown_format in unknown_formats:
            with self.subTest(format_type=unknown_format):
                # Format with unknown format type
                formatted_value = format_delta_value(delta_seconds, unknown_format)
                
                # Should default to seconds format behavior
                expected_value = round(delta_seconds, 3)
                
                # Verify result matches seconds format
                self.assertIsNotNone(formatted_value)
                self.assertIsInstance(formatted_value, float)
                self.assertEqual(formatted_value, expected_value)

    def test_format_precision_edge_cases(self):
        """
        **Feature: ntp-delta-monitor, Property 5: Format Precision Compliance**
        
        Test format precision with specific edge cases.
        """
        from ntp_monitor import format_delta_value
        
        # Test cases with known expected results
        # Note: Some values may have floating-point precision effects
        test_cases = [
            # (input_seconds, format_type, expected_output)
            (0.0, 'seconds', 0.0),
            (0.0, 'milliseconds', 0),
            (1.0, 'seconds', 1.0),
            (1.0, 'milliseconds', 1000),
            (0.001, 'seconds', 0.001),  # Exactly 1 millisecond
            (0.001, 'milliseconds', 1),
            (0.0015, 'seconds', 0.002),  # Rounds up to 2 milliseconds
            (0.0015, 'milliseconds', 2),  # Rounds up to 2 milliseconds
            (0.0004, 'seconds', 0.0),   # Rounds down to 0
            (0.0004, 'milliseconds', 0), # Rounds down to 0
            (-1.5, 'seconds', -1.5),
            (-1.5, 'milliseconds', -1500),
            (123.456789, 'seconds', 123.457),  # Rounds to 3 decimal places
            (123.456789, 'milliseconds', 123457),  # Converts to integer milliseconds
        ]
        
        for input_seconds, format_type, expected_output in test_cases:
            with self.subTest(input_seconds=input_seconds, format_type=format_type):
                result = format_delta_value(input_seconds, format_type)
                self.assertEqual(result, expected_output,
                               f"format_delta_value({input_seconds}, '{format_type}') "
                               f"expected {expected_output}, got {result}")
        
        # Test the 0.0005 case separately since it has floating-point precision effects
        # We'll test what the actual implementation returns rather than assuming the result
        result_seconds = format_delta_value(0.0005, 'seconds')
        result_milliseconds = format_delta_value(0.0005, 'milliseconds')
        
        # Verify the types are correct
        self.assertIsInstance(result_seconds, float)
        self.assertIsInstance(result_milliseconds, int)
        
        # Verify the results are consistent with the implementation's rounding behavior
        expected_seconds = round(0.0005, 3)
        expected_milliseconds = int(round(0.0005 * 1000))
        
        self.assertEqual(result_seconds, expected_seconds)
        self.assertEqual(result_milliseconds, expected_milliseconds)

    @given(valid_delta_seconds())
    @settings(max_examples=100, deadline=None)
    def test_format_consistency_between_types(self, delta_seconds):
        """
        **Feature: ntp-delta-monitor, Property 5: Format Precision Compliance**
        
        Test that conversion between seconds and milliseconds formats is consistent.
        """
        from ntp_monitor import format_delta_value
        
        # Format in both types
        seconds_result = format_delta_value(delta_seconds, 'seconds')
        milliseconds_result = format_delta_value(delta_seconds, 'milliseconds')
        
        # Both should be non-None
        self.assertIsNotNone(seconds_result)
        self.assertIsNotNone(milliseconds_result)
        
        # Convert seconds result to milliseconds and compare
        seconds_to_ms = int(round(seconds_result * 1000))
        
        # They should be equal (within rounding tolerance)
        # The difference should be at most 1 millisecond due to rounding
        difference = abs(seconds_to_ms - milliseconds_result)
        self.assertLessEqual(difference, 1,
                           f"Conversion consistency check failed. "
                           f"Original: {delta_seconds}s, "
                           f"Seconds format: {seconds_result}s ({seconds_to_ms}ms), "
                           f"Milliseconds format: {milliseconds_result}ms, "
                           f"Difference: {difference}ms")

    def test_format_precision_integration_with_ntp_result(self):
        """
        **Feature: ntp-delta-monitor, Property 5: Format Precision Compliance**
        
        Test that format precision is properly integrated into NTP result processing.
        """
        from ntp_monitor import process_single_server, Config, NTPStatus
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        
        # Test both format types
        format_types = ['seconds', 'milliseconds']
        
        for format_type in format_types:
            with self.subTest(format_type=format_type):
                # Create test configuration with specific format
                config = Config(
                    reference_ntp="test.reference.com",
                    ntp_servers_file=Path("test.txt"),
                    output_file=None,
                    format_type=format_type,
                    parallel_limit=10,
                    ntp_timeout=30,
                    verbose=False
                )
                
                # Create test timestamps with known delta
                reference_time = datetime.now(timezone.utc)
                target_time = reference_time + timedelta(seconds=2.5678)  # 2.5678 seconds ahead
                expected_delta_seconds = 2.5678
                
                # Mock NTP query to return controlled timestamp
                mock_ntp_response = MagicMock()
                mock_ntp_response.timestamp_utc = target_time
                mock_ntp_response.query_rtt_ms = 50.0
                mock_ntp_response.stratum = 2
                mock_ntp_response.root_delay_ms = 10.0
                mock_ntp_response.root_dispersion_ms = 5.0
                mock_ntp_response.is_synchronized = True
                mock_ntp_response.error_message = None
                
                with patch('ntp_monitor.resolve_hostname_with_fallback') as mock_dns, \
                     patch('ntp_monitor.query_ntp_server') as mock_ntp, \
                     patch('ntp_monitor.validate_ntp_response') as mock_validate:
                    
                    # Mock successful DNS resolution
                    mock_dns.return_value = ("test.server.com", "192.168.1.100")
                    
                    # Mock successful NTP query
                    mock_ntp.return_value = mock_ntp_response
                    
                    # Mock validation to return OK
                    mock_validate.return_value = (NTPStatus.OK, None)
                    
                    # Execute server processing with reference time
                    result = process_single_server("test.server.com", reference_time, config)
                    
                    # Verify delta calculation was performed correctly
                    self.assertEqual(result.status, NTPStatus.OK)
                    self.assertIsNotNone(result.delta_seconds)
                    self.assertAlmostEqual(result.delta_seconds, expected_delta_seconds, places=6)
                    
                    # Verify formatted delta matches expected format
                    self.assertIsNotNone(result.delta_formatted)
                    
                    if format_type == 'seconds':
                        # Should be decimal seconds with millisecond precision
                        expected_formatted = round(expected_delta_seconds, 3)
                        self.assertIsInstance(result.delta_formatted, float)
                        self.assertEqual(result.delta_formatted, expected_formatted)
                    elif format_type == 'milliseconds':
                        # Should be integer milliseconds
                        expected_formatted = int(round(expected_delta_seconds * 1000))
                        self.assertIsInstance(result.delta_formatted, int)
                        self.assertEqual(result.delta_formatted, expected_formatted)


class TestErrorHandlingContinuity(unittest.TestCase):
    """
    **Feature: ntp-delta-monitor, Property 3: Error Handling Continuity**
    
    Property: For any NTP server that encounters network timeouts or query failures, 
    the system should record the appropriate error status and continue processing 
    remaining servers
    
    **Validates: Requirements 2.5, 3.5, 8.1, 8.2**
    """

    @composite
    def server_list_with_failures(draw):
        """Generate list of servers with some that will fail."""
        # Generate 3-10 servers for testing
        num_servers = draw(st.integers(min_value=3, max_value=10))
        
        # Generate server names
        servers = []
        for i in range(num_servers):
            server_type = draw(st.sampled_from(['hostname', 'ip']))
            if server_type == 'hostname':
                server = f"server{i}.example.com"
            else:
                server = f"192.168.1.{i+1}"
            servers.append(server)
        
        # Determine which servers will fail (at least 1, at most num_servers-1)
        num_failures = draw(st.integers(min_value=1, max_value=max(1, num_servers-1)))
        failure_indices = draw(st.sets(st.integers(min_value=0, max_value=num_servers-1), 
                                     min_size=num_failures, max_size=num_failures))
        
        return servers, failure_indices

    @composite
    def error_types_to_simulate(draw):
        """Generate different types of errors to simulate."""
        error_types = [
            ('timeout', Exception("Timeout after 30 seconds")),
            ('dns_failure', Exception("DNS resolution failed: Name resolution failed")),
            ('connection_refused', Exception("Network error: Connection refused")),
            ('ntp_protocol_error', Exception("NTP protocol error: Invalid response")),
            ('network_error', Exception("Network error: Socket error")),
            ('invalid_timestamp', Exception("Invalid timestamp format from server")),
        ]
        return draw(st.sampled_from(error_types))

    @composite
    def config_for_testing(draw):
        """Generate test configuration."""
        from ntp_monitor import Config
        from pathlib import Path
        
        return Config(
            reference_ntp="reference.ntp.server",
            ntp_servers_file=Path("test_servers.txt"),
            output_file=None,
            format_type=draw(st.sampled_from(['seconds', 'milliseconds'])),
            parallel_limit=draw(st.integers(min_value=1, max_value=20)),
            ntp_timeout=draw(st.integers(min_value=5, max_value=60)),
            verbose=draw(st.booleans())
        )

    @given(server_list_with_failures(), error_types_to_simulate(), config_for_testing())
    @settings(max_examples=100, deadline=None)
    def test_error_handling_continues_processing_remaining_servers(self, server_data, error_data, config):
        """
        **Feature: ntp-delta-monitor, Property 3: Error Handling Continuity**
        
        Test that when some servers fail, processing continues for remaining servers.
        """
        from ntp_monitor import process_servers_parallel, NTPStatus, NTPResponse
        from unittest.mock import patch, MagicMock
        from datetime import datetime, timezone
        
        servers, failure_indices = server_data
        error_name, error_exception = error_data
        
        # Create reference time for delta calculations
        reference_time = datetime.now(timezone.utc)
        
        # Create a set of servers that should fail for easy lookup
        failing_servers = {servers[i] for i in failure_indices}
        
        # Mock successful NTP response for non-failing servers
        mock_success_response = MagicMock()
        mock_success_response.timestamp_utc = reference_time
        mock_success_response.query_rtt_ms = 50.0
        mock_success_response.stratum = 2
        mock_success_response.root_delay_ms = 10.0
        mock_success_response.root_dispersion_ms = 5.0
        mock_success_response.is_synchronized = True
        mock_success_response.error_message = None
        
        def mock_query_ntp_server(hostname, timeout):
            # Raise error for servers that should fail
            if hostname in failing_servers:
                raise error_exception
            else:
                return mock_success_response
        
        with patch('ntp_monitor.resolve_hostname_with_fallback') as mock_dns, \
             patch('ntp_monitor.query_ntp_server', side_effect=mock_query_ntp_server) as mock_ntp, \
             patch('ntp_monitor.validate_ntp_response') as mock_validate:
            
            # Mock DNS resolution to return hostname and IP
            def mock_dns_resolution(hostname, timeout):
                if hostname.startswith('192.168.1.'):
                    return hostname, hostname  # IP address case
                else:
                    return hostname, f"192.168.1.{hash(hostname) % 100 + 1}"  # Hostname case
            
            mock_dns.side_effect = mock_dns_resolution
            
            # Mock validation to return OK for successful responses
            mock_validate.return_value = (NTPStatus.OK, None)
            
            # Execute parallel processing
            results = process_servers_parallel(servers, reference_time, config)
            
            # Verify all servers were processed (continuity property)
            self.assertEqual(len(results), len(servers), 
                           "All servers should be processed despite failures")
            
            # Create a mapping of server name to result for easier verification
            result_by_server = {result.ntp_server: result for result in results}
            
            # Verify that all servers have results
            for server in servers:
                self.assertIn(server, result_by_server, 
                            f"Server {server} should have a result")
            
            # Verify that failed servers have appropriate error status
            failed_count = 0
            success_count = 0
            
            for server in servers:
                result = result_by_server[server]
                
                if server in failing_servers:
                    # This server should have failed
                    failed_count += 1
                    self.assertNotEqual(result.status, NTPStatus.OK, 
                                      f"Server {server} should have failed")
                    self.assertIsNotNone(result.error_message, 
                                       f"Failed server {server} should have error message")
                    
                    # Verify appropriate error status based on error type
                    error_str = str(error_exception).lower()
                    if "timeout" in error_str:
                        self.assertEqual(result.status, NTPStatus.TIMEOUT)
                    elif "dns resolution failed" in error_str or "connection refused" in error_str:
                        self.assertEqual(result.status, NTPStatus.UNREACHABLE)
                    else:
                        self.assertEqual(result.status, NTPStatus.ERROR)
                    
                    # Verify failed servers have None values for NTP data
                    self.assertIsNone(result.ntp_time_utc)
                    self.assertIsNone(result.query_rtt_ms)
                    self.assertIsNone(result.stratum)
                    self.assertIsNone(result.delta_seconds)
                    self.assertIsNone(result.delta_formatted)
                    
                else:
                    # This server should have succeeded
                    success_count += 1
                    self.assertEqual(result.status, NTPStatus.OK, 
                                   f"Server {server} should have succeeded")
                    self.assertIsNone(result.error_message, 
                                    f"Successful server {server} should not have error message")
                    
                    # Verify successful servers have valid NTP data
                    self.assertIsNotNone(result.ntp_time_utc)
                    self.assertIsNotNone(result.query_rtt_ms)
                    self.assertIsNotNone(result.stratum)
                    self.assertIsNotNone(result.delta_seconds)
                    self.assertIsNotNone(result.delta_formatted)
                
                # Verify all results have basic fields populated
                self.assertEqual(result.ntp_server, server)
                self.assertIsNotNone(result.timestamp_utc)
                self.assertIsNotNone(result.ntp_server_ip)
            
            # Verify the expected number of failures and successes
            expected_failures = len(failure_indices)
            expected_successes = len(servers) - expected_failures
            
            self.assertEqual(failed_count, expected_failures, 
                           f"Expected {expected_failures} failures, got {failed_count}")
            self.assertEqual(success_count, expected_successes, 
                           f"Expected {expected_successes} successes, got {success_count}")
            
            # Verify processing continued despite failures (at least one success if possible)
            if expected_successes > 0:
                self.assertGreater(success_count, 0, 
                                 "Processing should continue and succeed for non-failing servers")

    @given(st.integers(min_value=1, max_value=20), config_for_testing())
    @settings(max_examples=100, deadline=None)
    def test_all_servers_fail_still_returns_results(self, num_servers, config):
        """
        **Feature: ntp-delta-monitor, Property 3: Error Handling Continuity**
        
        Test that when all servers fail, the system still returns results for all servers.
        """
        from ntp_monitor import process_servers_parallel, NTPStatus
        from unittest.mock import patch
        from datetime import datetime, timezone
        
        # Generate server list
        servers = [f"failing-server-{i}.example.com" for i in range(num_servers)]
        reference_time = datetime.now(timezone.utc)
        
        # Mock all servers to fail with timeout
        def mock_failing_query(hostname, timeout):
            raise Exception("Timeout after 30 seconds")
        
        with patch('ntp_monitor.resolve_hostname_with_fallback') as mock_dns, \
             patch('ntp_monitor.query_ntp_server', side_effect=mock_failing_query):
            
            # Mock DNS resolution
            mock_dns.side_effect = lambda h, t: (h, f"192.168.1.{hash(h) % 100 + 1}")
            
            # Execute parallel processing
            results = process_servers_parallel(servers, reference_time, config)
            
            # Verify all servers have results despite all failing
            self.assertEqual(len(results), num_servers, 
                           "All servers should have results even when all fail")
            
            # Create a mapping of server name to result for easier verification
            result_by_server = {result.ntp_server: result for result in results}
            
            # Verify all results show failure status
            for server in servers:
                self.assertIn(server, result_by_server, 
                            f"Server {server} should have a result")
                result = result_by_server[server]
                
                self.assertEqual(result.status, NTPStatus.TIMEOUT)
                self.assertIsNotNone(result.error_message)
                self.assertIn("timeout", result.error_message.lower())
                
                # Verify failed servers have None values for NTP data
                self.assertIsNone(result.ntp_time_utc)
                self.assertIsNone(result.query_rtt_ms)
                self.assertIsNone(result.stratum)
                self.assertIsNone(result.delta_seconds)
                self.assertIsNone(result.delta_formatted)

    @given(st.integers(min_value=2, max_value=10), config_for_testing())
    @settings(max_examples=100, deadline=None)
    def test_mixed_error_types_all_handled_appropriately(self, num_servers, config):
        """
        **Feature: ntp-delta-monitor, Property 3: Error Handling Continuity**
        
        Test that different types of errors are all handled appropriately and processing continues.
        """
        from ntp_monitor import process_servers_parallel, NTPStatus
        from unittest.mock import patch
        from datetime import datetime, timezone
        
        # Generate server list
        servers = [f"server-{i}.example.com" for i in range(num_servers)]
        reference_time = datetime.now(timezone.utc)
        
        # Define different error types to simulate
        error_types = [
            Exception("Timeout after 30 seconds"),
            Exception("DNS resolution failed: Name resolution failed"),
            Exception("Network error: Connection refused"),
            Exception("NTP protocol error: Invalid response"),
            Exception("Network error: Socket error"),
            Exception("Invalid timestamp format from server"),
        ]
        
        def mock_mixed_errors_query(hostname, timeout):
            # Use hostname to determine which error to raise
            server_index = int(hostname.split('-')[1].split('.')[0])
            error_index = server_index % len(error_types)
            raise error_types[error_index]
        
        with patch('ntp_monitor.resolve_hostname_with_fallback') as mock_dns, \
             patch('ntp_monitor.query_ntp_server', side_effect=mock_mixed_errors_query):
            
            # Mock DNS resolution
            mock_dns.side_effect = lambda h, t: (h, f"192.168.1.{hash(h) % 100 + 1}")
            
            # Execute parallel processing
            results = process_servers_parallel(servers, reference_time, config)
            
            # Verify all servers have results
            self.assertEqual(len(results), num_servers, 
                           "All servers should have results despite mixed errors")
            
            # Create a mapping of server name to result for easier verification
            result_by_server = {result.ntp_server: result for result in results}
            
            # Verify each error type is handled appropriately
            for i, server in enumerate(servers):
                self.assertIn(server, result_by_server, 
                            f"Server {server} should have a result")
                result = result_by_server[server]
                
                self.assertIsNotNone(result.error_message)
                
                # Verify appropriate status based on error type
                error_index = i % len(error_types)
                error = error_types[error_index]
                error_str = str(error).lower()
                
                if "timeout" in error_str:
                    self.assertEqual(result.status, NTPStatus.TIMEOUT)
                    self.assertIn("timeout", result.error_message.lower())
                elif "dns resolution failed" in error_str or "connection refused" in error_str:
                    self.assertEqual(result.status, NTPStatus.UNREACHABLE)
                else:
                    self.assertEqual(result.status, NTPStatus.ERROR)
                
                # Verify failed servers have None values for NTP data
                self.assertIsNone(result.ntp_time_utc)
                self.assertIsNone(result.query_rtt_ms)
                self.assertIsNone(result.stratum)
                self.assertIsNone(result.delta_seconds)
                self.assertIsNone(result.delta_formatted)

    def test_single_server_error_handling_integration(self):
        """
        **Feature: ntp-delta-monitor, Property 3: Error Handling Continuity**
        
        Test that single server error handling integrates properly with the error classification system.
        """
        from ntp_monitor import process_single_server, Config, NTPStatus
        from pathlib import Path
        from unittest.mock import patch
        from datetime import datetime, timezone
        
        # Create test configuration
        config = Config(
            reference_ntp="reference.ntp.server",
            ntp_servers_file=Path("test_servers.txt"),
            output_file=None,
            format_type="seconds",
            parallel_limit=10,
            ntp_timeout=30,
            verbose=False
        )
        
        reference_time = datetime.now(timezone.utc)
        
        # Test different error scenarios
        error_scenarios = [
            (Exception("Timeout after 30 seconds"), NTPStatus.TIMEOUT, "timeout"),
            (Exception("DNS resolution failed: Name resolution failed"), NTPStatus.UNREACHABLE, "dns resolution failed"),
            (Exception("Network error: Connection refused"), NTPStatus.UNREACHABLE, "unreachable"),
            (Exception("NTP protocol error: Invalid response"), NTPStatus.ERROR, "ntp protocol error"),
            (Exception("Invalid timestamp format from server"), NTPStatus.ERROR, "invalid ntp response format"),
        ]
        
        for error_exception, expected_status, expected_message_content in error_scenarios:
            with self.subTest(error=type(error_exception).__name__):
                with patch('ntp_monitor.resolve_hostname_with_fallback') as mock_dns, \
                     patch('ntp_monitor.query_ntp_server') as mock_ntp:
                    
                    # Mock DNS resolution
                    mock_dns.return_value = ("test.server.com", "192.168.1.100")
                    
                    # Mock NTP query to raise specific error
                    mock_ntp.side_effect = error_exception
                    
                    # Execute single server processing
                    result = process_single_server("test.server.com", reference_time, config)
                    
                    # Verify error handling continuity
                    self.assertIsNotNone(result, "Result should always be returned for continuity")
                    self.assertEqual(result.status, expected_status)
                    self.assertIsNotNone(result.error_message)
                    self.assertIn(expected_message_content, result.error_message.lower())
                    
                    # Verify basic fields are populated for continuity
                    self.assertEqual(result.ntp_server, "test.server.com")
                    self.assertEqual(result.ntp_server_ip, "192.168.1.100")
                    self.assertIsNotNone(result.timestamp_utc)
                    
                    # Verify NTP data fields are None for failed queries
                    self.assertIsNone(result.ntp_time_utc)
                    self.assertIsNone(result.query_rtt_ms)
                    self.assertIsNone(result.stratum)
                    self.assertIsNone(result.delta_seconds)
                    self.assertIsNone(result.delta_formatted)

    @given(st.integers(min_value=1, max_value=5))
    @settings(max_examples=100, deadline=None)
    def test_thread_pool_exceptions_handled_gracefully(self, num_servers):
        """
        **Feature: ntp-delta-monitor, Property 3: Error Handling Continuity**
        
        Test that unexpected thread pool exceptions are handled gracefully and processing continues.
        """
        from ntp_monitor import process_servers_parallel, NTPStatus, Config
        from pathlib import Path
        from unittest.mock import patch, MagicMock
        from datetime import datetime, timezone
        
        # Create test configuration
        config = Config(
            reference_ntp="reference.ntp.server",
            ntp_servers_file=Path("test_servers.txt"),
            output_file=None,
            format_type="seconds",
            parallel_limit=2,  # Small pool to test thread handling
            ntp_timeout=30,
            verbose=False
        )
        
        servers = [f"server-{i}.example.com" for i in range(num_servers)]
        reference_time = datetime.now(timezone.utc)
        
        # Mock process_single_server to raise unexpected exception for first server
        original_process_single_server = None
        
        def mock_process_with_exception(server, ref_time, cfg):
            if server == servers[0]:
                # Simulate unexpected thread pool exception
                raise RuntimeError("Unexpected thread pool error")
            else:
                # Return normal result for other servers
                return MagicMock(
                    timestamp_utc=datetime.now(timezone.utc),
                    ntp_server=server,
                    ntp_server_ip="192.168.1.100",
                    ntp_time_utc=datetime.now(timezone.utc),
                    query_rtt_ms=50.0,
                    stratum=2,
                    root_delay_ms=10.0,
                    root_dispersion_ms=5.0,
                    delta_seconds=0.0,
                    delta_formatted=0.0,
                    status=NTPStatus.OK,
                    error_message=None
                )
        
        with patch('ntp_monitor.process_single_server', side_effect=mock_process_with_exception):
            # Execute parallel processing
            results = process_servers_parallel(servers, reference_time, config)
            
            # Verify all servers have results despite thread pool exception
            self.assertEqual(len(results), num_servers, 
                           "All servers should have results despite thread pool exceptions")
            
            # Verify first server has error result due to exception
            first_result = next(r for r in results if r.ntp_server == servers[0])
            self.assertEqual(first_result.status, NTPStatus.ERROR)
            self.assertIsNotNone(first_result.error_message)
            self.assertIn("unexpected processing error", first_result.error_message.lower())
            
            # Verify other servers processed normally (if any)
            if num_servers > 1:
                other_results = [r for r in results if r.ntp_server != servers[0]]
                for result in other_results:
                    self.assertEqual(result.status, NTPStatus.OK)
                    self.assertIsNone(result.error_message)


class TestCSVStructureCompleteness(unittest.TestCase):
    """
    **Feature: ntp-delta-monitor, Property 6: CSV Structure Completeness**
    
    Property: For any processing run, the generated CSV should contain all required columns 
    with proper headers and error information for failed servers
    
    **Validates: Requirements 5.1, 5.4**
    """

    @composite
    def ntp_result_list(draw):
        """Generate lists of NTPResult objects with various statuses for testing."""
        from ntp_monitor import NTPResult, NTPStatus
        from datetime import datetime, timezone, timedelta
        
        # Generate 1-10 results
        num_results = draw(st.integers(min_value=1, max_value=10))
        results = []
        
        for i in range(num_results):
            # Generate base timestamp
            base_time = datetime.now(timezone.utc)
            timestamp_offset = draw(st.integers(min_value=-3600, max_value=3600))
            timestamp = base_time + timedelta(seconds=timestamp_offset)
            
            # Generate server name
            server_name = draw(st.text(
                alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), min_codepoint=97, max_codepoint=122),
                min_size=5, max_size=15
            ).filter(lambda x: x.isalnum())) + f".server{i}.com"
            
            # Generate status (mix of success and failure cases)
            status = draw(st.sampled_from(list(NTPStatus)))
            
            # Generate result based on status
            if status == NTPStatus.OK:
                # Successful result with all fields populated
                ntp_time_offset = draw(st.integers(min_value=-300, max_value=300))
                ntp_time = timestamp + timedelta(seconds=ntp_time_offset)
                delta_seconds = ntp_time_offset
                
                result = NTPResult(
                    timestamp_utc=timestamp,
                    ntp_server=server_name,
                    ntp_server_ip=f"192.168.1.{100 + i}",
                    ntp_time_utc=ntp_time,
                    query_rtt_ms=draw(st.floats(min_value=10.0, max_value=200.0)),
                    stratum=draw(st.integers(min_value=1, max_value=15)),
                    root_delay_ms=draw(st.floats(min_value=0.1, max_value=50.0)),
                    root_dispersion_ms=draw(st.floats(min_value=0.1, max_value=20.0)),
                    delta_seconds=delta_seconds,
                    delta_formatted=delta_seconds,  # Will be formatted based on config
                    status=status,
                    error_message=None
                )
            else:
                # Failed result with minimal fields and error message
                error_messages = {
                    NTPStatus.TIMEOUT: "Query timeout after 30 seconds",
                    NTPStatus.UNREACHABLE: "Server unreachable",
                    NTPStatus.UNSYNCHRONIZED: f"Server stratum 16 (unsynchronized)",
                    NTPStatus.ERROR: "NTP protocol error"
                }
                
                result = NTPResult(
                    timestamp_utc=timestamp,
                    ntp_server=server_name,
                    ntp_server_ip=None,  # May be None for failed queries
                    ntp_time_utc=None,
                    query_rtt_ms=None,
                    stratum=None,
                    root_delay_ms=None,
                    root_dispersion_ms=None,
                    delta_seconds=None,
                    delta_formatted=None,
                    status=status,
                    error_message=error_messages.get(status, "Unknown error")
                )
            
            results.append(result)
        
        return results

    @composite
    def config_with_format(draw):
        """Generate Config objects with different format types."""
        from ntp_monitor import Config
        from pathlib import Path
        
        format_type = draw(st.sampled_from(['seconds', 'milliseconds']))
        
        return Config(
            reference_ntp="reference.ntp.server",
            ntp_servers_file=Path("test_servers.txt"),
            output_file=None,
            format_type=format_type,
            parallel_limit=10,
            ntp_timeout=30,
            verbose=False
        )

    @given(ntp_result_list(), config_with_format())
    @settings(max_examples=100, deadline=None)
    def test_csv_contains_all_required_columns(self, results, config):
        """
        **Feature: ntp-delta-monitor, Property 6: CSV Structure Completeness**
        
        Test that generated CSV contains all required columns with proper headers.
        """
        from ntp_monitor import write_csv_report
        import tempfile
        import csv
        from pathlib import Path
        
        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        
        try:
            # Write CSV report
            write_csv_report(results, temp_path, config)
            
            # Read and verify CSV structure
            with open(temp_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                # Verify all required columns are present
                required_columns = [
                    'timestamp_utc',
                    'ntp_server', 
                    'ntp_server_ip',
                    'ntp_time_utc',
                    'query_rtt_ms',
                    'stratum',
                    'root_delay_ms',
                    'root_dispersion_ms',
                    'delta_value',
                    'delta_format',
                    'status',
                    'error_message'
                ]
                
                self.assertIsNotNone(reader.fieldnames, "CSV should have headers")
                
                for required_column in required_columns:
                    self.assertIn(required_column, reader.fieldnames,
                                f"CSV should contain required column: {required_column}")
                
                # Verify no extra columns (structure completeness)
                self.assertEqual(set(reader.fieldnames), set(required_columns),
                               "CSV should contain exactly the required columns, no more, no less")
                
                # Read all rows and verify count matches input
                csv_rows = list(reader)
                self.assertEqual(len(csv_rows), len(results),
                               f"CSV should contain {len(results)} rows, found {len(csv_rows)}")
                
        finally:
            # Clean up temporary file
            if temp_path.exists():
                temp_path.unlink()

    @given(ntp_result_list(), config_with_format())
    @settings(max_examples=100, deadline=None)
    def test_csv_contains_error_information_for_failed_servers(self, results, config):
        """
        **Feature: ntp-delta-monitor, Property 6: CSV Structure Completeness**
        
        Test that CSV contains appropriate error information for failed servers.
        """
        from ntp_monitor import write_csv_report, NTPStatus
        import tempfile
        import csv
        from pathlib import Path
        
        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        
        try:
            # Write CSV report
            write_csv_report(results, temp_path, config)
            
            # Read and verify error information
            with open(temp_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                csv_rows = list(reader)
                
                # Check each result against corresponding CSV row
                for i, (result, csv_row) in enumerate(zip(results, csv_rows)):
                    with self.subTest(server=result.ntp_server, status=result.status):
                        
                        # Verify status is always present
                        self.assertEqual(csv_row['status'], result.status.value,
                                       f"Row {i}: Status should match result status")
                        
                        if result.status != NTPStatus.OK:
                            # Failed servers should have error information
                            self.assertIsNotNone(result.error_message,
                                               f"Row {i}: Failed server should have error message")
                            self.assertEqual(csv_row['error_message'], result.error_message,
                                           f"Row {i}: CSV error message should match result")
                            self.assertNotEqual(csv_row['error_message'], '',
                                              f"Row {i}: CSV error message should not be empty for failed servers")
                            
                            # Failed servers may have empty/missing data fields
                            if result.ntp_time_utc is None:
                                self.assertEqual(csv_row['ntp_time_utc'], '',
                                               f"Row {i}: Missing ntp_time_utc should be empty string in CSV")
                            if result.query_rtt_ms is None:
                                self.assertEqual(csv_row['query_rtt_ms'], '',
                                               f"Row {i}: Missing query_rtt_ms should be empty string in CSV")
                            if result.stratum is None:
                                self.assertEqual(csv_row['stratum'], '',
                                               f"Row {i}: Missing stratum should be empty string in CSV")
                            if result.delta_formatted is None:
                                self.assertEqual(csv_row['delta_value'], '',
                                               f"Row {i}: Missing delta_value should be empty string in CSV")
                        else:
                            # Successful servers should have no error message
                            self.assertEqual(csv_row['error_message'], '',
                                           f"Row {i}: Successful server should have empty error message")
                            
                            # Successful servers should have populated data fields
                            self.assertNotEqual(csv_row['ntp_time_utc'], '',
                                              f"Row {i}: Successful server should have ntp_time_utc")
                            self.assertNotEqual(csv_row['query_rtt_ms'], '',
                                              f"Row {i}: Successful server should have query_rtt_ms")
                            self.assertNotEqual(csv_row['stratum'], '',
                                              f"Row {i}: Successful server should have stratum")
                            
        finally:
            # Clean up temporary file
            if temp_path.exists():
                temp_path.unlink()

    @given(ntp_result_list(), config_with_format())
    @settings(max_examples=100, deadline=None)
    def test_csv_timestamp_format_consistency(self, results, config):
        """
        **Feature: ntp-delta-monitor, Property 6: CSV Structure Completeness**
        
        Test that all timestamps in CSV are formatted in ISO 8601 UTC format.
        """
        from ntp_monitor import write_csv_report
        import tempfile
        import csv
        from pathlib import Path
        import re
        
        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        
        try:
            # Write CSV report
            write_csv_report(results, temp_path, config)
            
            # Read and verify timestamp formats
            with open(temp_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                csv_rows = list(reader)
                
                # ISO 8601 UTC format pattern (with optional microseconds)
                iso8601_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{6})?(\+00:00|Z)?$')
                
                for i, csv_row in enumerate(csv_rows):
                    with self.subTest(row=i, server=csv_row['ntp_server']):
                        
                        # timestamp_utc should always be present and formatted
                        timestamp_utc = csv_row['timestamp_utc']
                        self.assertNotEqual(timestamp_utc, '',
                                          f"Row {i}: timestamp_utc should not be empty")
                        self.assertTrue(iso8601_pattern.match(timestamp_utc),
                                      f"Row {i}: timestamp_utc should be ISO 8601 format: {timestamp_utc}")
                        
                        # ntp_time_utc should be formatted if present
                        ntp_time_utc = csv_row['ntp_time_utc']
                        if ntp_time_utc != '':  # Only check if not empty (failed queries may be empty)
                            self.assertTrue(iso8601_pattern.match(ntp_time_utc),
                                          f"Row {i}: ntp_time_utc should be ISO 8601 format: {ntp_time_utc}")
                            
        finally:
            # Clean up temporary file
            if temp_path.exists():
                temp_path.unlink()

    @given(ntp_result_list(), config_with_format())
    @settings(max_examples=100, deadline=None)
    def test_csv_delta_format_consistency(self, results, config):
        """
        **Feature: ntp-delta-monitor, Property 6: CSV Structure Completeness**
        
        Test that delta format column matches config and delta values are formatted correctly.
        """
        from ntp_monitor import write_csv_report
        import tempfile
        import csv
        from pathlib import Path
        
        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        
        try:
            # Write CSV report
            write_csv_report(results, temp_path, config)
            
            # Read and verify delta format consistency
            with open(temp_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                csv_rows = list(reader)
                
                for i, csv_row in enumerate(csv_rows):
                    with self.subTest(row=i, server=csv_row['ntp_server']):
                        
                        # delta_format should always match config
                        self.assertEqual(csv_row['delta_format'], config.format_type,
                                       f"Row {i}: delta_format should match config format_type")
                        
                        # delta_value format should be consistent with delta_format
                        delta_value = csv_row['delta_value']
                        if delta_value != '':  # Only check if not empty (failed queries may be empty)
                            if config.format_type == 'seconds':
                                # Should be a decimal number (float)
                                try:
                                    float_value = float(delta_value)
                                    # Should have at most 3 decimal places (millisecond precision)
                                    decimal_places = len(delta_value.split('.')[-1]) if '.' in delta_value else 0
                                    self.assertLessEqual(decimal_places, 3,
                                                       f"Row {i}: Seconds format should have at most 3 decimal places: {delta_value}")
                                except ValueError:
                                    self.fail(f"Row {i}: delta_value should be valid float for seconds format: {delta_value}")
                                    
                            elif config.format_type == 'milliseconds':
                                # Should be an integer
                                try:
                                    int_value = int(delta_value)
                                    # Should not have decimal point
                                    self.assertNotIn('.', delta_value,
                                                   f"Row {i}: Milliseconds format should not have decimal point: {delta_value}")
                                except ValueError:
                                    self.fail(f"Row {i}: delta_value should be valid integer for milliseconds format: {delta_value}")
                            
        finally:
            # Clean up temporary file
            if temp_path.exists():
                temp_path.unlink()

    def test_csv_structure_with_empty_results(self):
        """
        **Feature: ntp-delta-monitor, Property 6: CSV Structure Completeness**
        
        Test that CSV structure is complete even with empty results list.
        """
        from ntp_monitor import write_csv_report, Config
        import tempfile
        import csv
        from pathlib import Path
        
        # Create empty results list
        results = []
        
        # Create test config
        config = Config(
            reference_ntp="reference.ntp.server",
            ntp_servers_file=Path("test_servers.txt"),
            output_file=None,
            format_type="seconds",
            parallel_limit=10,
            ntp_timeout=30,
            verbose=False
        )
        
        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        
        try:
            # Write CSV report with empty results
            write_csv_report(results, temp_path, config)
            
            # Read and verify CSV structure
            with open(temp_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                # Verify headers are present even with no data
                required_columns = [
                    'timestamp_utc', 'ntp_server', 'ntp_server_ip', 'ntp_time_utc',
                    'query_rtt_ms', 'stratum', 'root_delay_ms', 'root_dispersion_ms',
                    'delta_value', 'delta_format', 'status', 'error_message'
                ]
                
                self.assertIsNotNone(reader.fieldnames, "CSV should have headers even with empty results")
                self.assertEqual(set(reader.fieldnames), set(required_columns),
                               "CSV should contain all required columns even with empty results")
                
                # Verify no data rows
                csv_rows = list(reader)
                self.assertEqual(len(csv_rows), 0, "CSV should have no data rows for empty results")
                
        finally:
            # Clean up temporary file
            if temp_path.exists():
                temp_path.unlink()


class TestFilenameGenerationPattern(unittest.TestCase):
    """
    **Feature: ntp-delta-monitor, Property 7: Filename Generation Pattern**
    
    Property: For any run without specified output path, the generated filename should 
    match the pattern "ntp_monitor_report_<UTCtimestamp>.csv"
    
    **Validates: Requirements 5.2**
    """

    @composite
    def mock_utc_datetime(draw):
        """Generate valid UTC datetime objects for filename testing."""
        # Generate realistic timestamps within a reasonable range
        # Use a narrower range to avoid edge cases with year boundaries
        year = draw(st.integers(min_value=2020, max_value=2030))
        month = draw(st.integers(min_value=1, max_value=12))
        day = draw(st.integers(min_value=1, max_value=28))  # Safe day range for all months
        hour = draw(st.integers(min_value=0, max_value=23))
        minute = draw(st.integers(min_value=0, max_value=59))
        second = draw(st.integers(min_value=0, max_value=59))
        
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)

    @given(mock_utc_datetime())
    @settings(max_examples=100, deadline=None)
    def test_filename_matches_required_pattern(self, mock_timestamp):
        """
        **Feature: ntp-delta-monitor, Property 7: Filename Generation Pattern**
        
        Test that generated filename matches the pattern "ntp_monitor_report_<UTCtimestamp>.csv".
        """
        from ntp_monitor import generate_default_filename
        from unittest.mock import patch
        import re
        
        # Mock datetime.now to return our test timestamp
        with patch('ntp_monitor.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_timestamp
            # Preserve the datetime constructor for other uses
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            # Generate filename
            filename = generate_default_filename()
            
            # Verify the filename matches the required pattern
            # Pattern: ntp_monitor_report_YYYYMMDD_HHMMSS.csv
            expected_timestamp_str = mock_timestamp.strftime("%Y%m%d_%H%M%S")
            expected_filename = f"ntp_monitor_report_{expected_timestamp_str}.csv"
            
            self.assertEqual(filename, expected_filename,
                           f"Generated filename '{filename}' does not match expected pattern")
            
            # Verify the pattern using regex
            pattern = r'^ntp_monitor_report_\d{8}_\d{6}\.csv$'
            self.assertIsNotNone(re.match(pattern, filename),
                               f"Filename '{filename}' does not match regex pattern '{pattern}'")
            
            # Verify specific components
            self.assertTrue(filename.startswith("ntp_monitor_report_"),
                          "Filename should start with 'ntp_monitor_report_'")
            self.assertTrue(filename.endswith(".csv"),
                          "Filename should end with '.csv'")
            
            # Extract and verify timestamp format
            timestamp_part = filename[len("ntp_monitor_report_"):-len(".csv")]
            self.assertEqual(len(timestamp_part), 15,  # YYYYMMDD_HHMMSS = 15 characters
                           f"Timestamp part '{timestamp_part}' should be 15 characters long")
            self.assertIn("_", timestamp_part,
                        f"Timestamp part '{timestamp_part}' should contain underscore separator")
            
            # Verify timestamp components
            date_part, time_part = timestamp_part.split("_")
            self.assertEqual(len(date_part), 8, "Date part should be 8 characters (YYYYMMDD)")
            self.assertEqual(len(time_part), 6, "Time part should be 6 characters (HHMMSS)")
            
            # Verify all characters are digits
            self.assertTrue(date_part.isdigit(), "Date part should contain only digits")
            self.assertTrue(time_part.isdigit(), "Time part should contain only digits")

    @given(mock_utc_datetime())
    @settings(max_examples=100, deadline=None)
    def test_filename_contains_correct_timestamp_values(self, mock_timestamp):
        """
        **Feature: ntp-delta-monitor, Property 7: Filename Generation Pattern**
        
        Test that the timestamp in the filename corresponds to the actual UTC time.
        """
        from ntp_monitor import generate_default_filename
        from unittest.mock import patch
        
        # Mock datetime.now to return our test timestamp
        with patch('ntp_monitor.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_timestamp
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            # Generate filename
            filename = generate_default_filename()
            
            # Extract timestamp from filename
            timestamp_part = filename[len("ntp_monitor_report_"):-len(".csv")]
            
            # Parse the timestamp components
            date_part, time_part = timestamp_part.split("_")
            
            # Verify year, month, day
            year = int(date_part[:4])
            month = int(date_part[4:6])
            day = int(date_part[6:8])
            
            self.assertEqual(year, mock_timestamp.year)
            self.assertEqual(month, mock_timestamp.month)
            self.assertEqual(day, mock_timestamp.day)
            
            # Verify hour, minute, second
            hour = int(time_part[:2])
            minute = int(time_part[2:4])
            second = int(time_part[4:6])
            
            self.assertEqual(hour, mock_timestamp.hour)
            self.assertEqual(minute, mock_timestamp.minute)
            self.assertEqual(second, mock_timestamp.second)

    def test_filename_generation_uses_utc_timezone(self):
        """
        **Feature: ntp-delta-monitor, Property 7: Filename Generation Pattern**
        
        Test that filename generation uses UTC timezone as required.
        """
        from ntp_monitor import generate_default_filename
        from unittest.mock import patch
        
        # Create a specific UTC timestamp for testing
        test_utc_time = datetime(2023, 12, 30, 15, 30, 45, tzinfo=timezone.utc)
        
        with patch('ntp_monitor.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_utc_time
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            # Verify datetime.now was called with timezone.utc
            filename = generate_default_filename()
            
            # Verify the call was made with UTC timezone
            mock_datetime.now.assert_called_once_with(timezone.utc)
            
            # Verify the resulting filename contains the correct UTC timestamp
            expected_filename = "ntp_monitor_report_20231230_153045.csv"
            self.assertEqual(filename, expected_filename)

    def test_filename_generation_multiple_calls_different_times(self):
        """
        **Feature: ntp-delta-monitor, Property 7: Filename Generation Pattern**
        
        Test that multiple calls at different times generate different filenames.
        """
        from ntp_monitor import generate_default_filename
        from unittest.mock import patch
        
        # Create two different timestamps
        time1 = datetime(2023, 12, 30, 15, 30, 45, tzinfo=timezone.utc)
        time2 = datetime(2023, 12, 30, 15, 30, 46, tzinfo=timezone.utc)  # 1 second later
        
        # Generate filename for first timestamp
        with patch('ntp_monitor.datetime') as mock_datetime:
            mock_datetime.now.return_value = time1
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            filename1 = generate_default_filename()
        
        # Generate filename for second timestamp
        with patch('ntp_monitor.datetime') as mock_datetime:
            mock_datetime.now.return_value = time2
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            filename2 = generate_default_filename()
        
        # Verify filenames are different
        self.assertNotEqual(filename1, filename2,
                          "Different timestamps should generate different filenames")
        
        # Verify both follow the correct pattern
        expected_filename1 = "ntp_monitor_report_20231230_153045.csv"
        expected_filename2 = "ntp_monitor_report_20231230_153046.csv"
        
        self.assertEqual(filename1, expected_filename1)
        self.assertEqual(filename2, expected_filename2)

    def test_filename_generation_integration_with_output_path_logic(self):
        """
        **Feature: ntp-delta-monitor, Property 7: Filename Generation Pattern**
        
        Test that filename generation is properly integrated with output path logic.
        """
        from ntp_monitor import get_output_file_path, Config
        from pathlib import Path
        from unittest.mock import patch
        
        # Test case 1: No output file specified (should use generated filename)
        config_no_output = Config(
            reference_ntp="test.reference.com",
            ntp_servers_file=Path("test.txt"),
            output_file=None,  # No output file specified
            format_type="seconds",
            parallel_limit=10,
            ntp_timeout=30,
            verbose=False
        )
        
        test_timestamp = datetime(2023, 12, 30, 15, 30, 45, tzinfo=timezone.utc)
        
        with patch('ntp_monitor.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_timestamp
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            output_path = get_output_file_path(config_no_output)
            
            # Verify it uses the generated filename
            expected_filename = "ntp_monitor_report_20231230_153045.csv"
            self.assertEqual(output_path.name, expected_filename)
            self.assertEqual(str(output_path), expected_filename)
        
        # Test case 2: Custom output file specified (should use custom path)
        custom_output_path = Path("custom_report.csv")
        config_with_output = Config(
            reference_ntp="test.reference.com",
            ntp_servers_file=Path("test.txt"),
            output_file=custom_output_path,  # Custom output file specified
            format_type="seconds",
            parallel_limit=10,
            ntp_timeout=30,
            verbose=False
        )
        
        output_path = get_output_file_path(config_with_output)
        
        # Verify it uses the custom path (no filename generation)
        self.assertEqual(output_path, custom_output_path)
        self.assertEqual(str(output_path), "custom_report.csv")

    @given(st.integers(min_value=0, max_value=59))
    @settings(max_examples=100, deadline=None)
    def test_filename_handles_edge_case_timestamps(self, second_value):
        """
        **Feature: ntp-delta-monitor, Property 7: Filename Generation Pattern**
        
        Test that filename generation handles edge cases like leap seconds and boundary values.
        """
        from ntp_monitor import generate_default_filename
        from unittest.mock import patch
        
        # Test with various second values including edge cases
        test_timestamp = datetime(2023, 12, 31, 23, 59, second_value, tzinfo=timezone.utc)
        
        with patch('ntp_monitor.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_timestamp
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            filename = generate_default_filename()
            
            # Verify the filename is generated correctly
            expected_timestamp_str = test_timestamp.strftime("%Y%m%d_%H%M%S")
            expected_filename = f"ntp_monitor_report_{expected_timestamp_str}.csv"
            
            self.assertEqual(filename, expected_filename)
            
            # Verify the pattern is still correct
            import re
            pattern = r'^ntp_monitor_report_\d{8}_\d{6}\.csv$'
            self.assertIsNotNone(re.match(pattern, filename),
                               f"Edge case filename '{filename}' does not match pattern")

    def test_filename_generation_consistent_format_specification(self):
        """
        **Feature: ntp-delta-monitor, Property 7: Filename Generation Pattern**
        
        Test that filename generation consistently uses the specified format.
        """
        from ntp_monitor import generate_default_filename
        from unittest.mock import patch
        
        # Test various timestamps to ensure consistent formatting
        test_cases = [
            datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc),      # New Year
            datetime(2023, 2, 14, 12, 30, 45, tzinfo=timezone.utc),  # Valentine's Day
            datetime(2023, 7, 4, 16, 45, 30, tzinfo=timezone.utc),   # Independence Day
            datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc), # New Year's Eve
        ]
        
        for test_timestamp in test_cases:
            with self.subTest(timestamp=test_timestamp):
                with patch('ntp_monitor.datetime') as mock_datetime:
                    mock_datetime.now.return_value = test_timestamp
                    mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
                    
                    filename = generate_default_filename()
                    
                    # Verify consistent format
                    expected_timestamp_str = test_timestamp.strftime("%Y%m%d_%H%M%S")
                    expected_filename = f"ntp_monitor_report_{expected_timestamp_str}.csv"
                    
                    self.assertEqual(filename, expected_filename,
                                   f"Timestamp {test_timestamp} should generate consistent filename format")
                    
                    # Verify the format components
                    timestamp_part = filename[len("ntp_monitor_report_"):-len(".csv")]
                    date_part, time_part = timestamp_part.split("_")
                    
                    # Verify zero-padding
                    self.assertEqual(len(date_part), 8, "Date should be zero-padded to 8 digits")
                    self.assertEqual(len(time_part), 6, "Time should be zero-padded to 6 digits")
                    
                    # Verify specific zero-padding cases
                    if test_timestamp.month < 10:
                        self.assertTrue(date_part[4] == '0', "Month should be zero-padded")
                    if test_timestamp.day < 10:
                        self.assertTrue(date_part[6] == '0', "Day should be zero-padded")
                    if test_timestamp.hour < 10:
                        self.assertTrue(time_part[0] == '0', "Hour should be zero-padded")
                    if test_timestamp.minute < 10:
                        self.assertTrue(time_part[2] == '0', "Minute should be zero-padded")
                    if test_timestamp.second < 10:
                        self.assertTrue(time_part[4] == '0', "Second should be zero-padded")


class TestStatisticalCalculationAccuracy(unittest.TestCase):
    """
    **Feature: ntp-delta-monitor, Property 10: Statistical Calculation Accuracy**
    
    Property: For any set of successful delta measurements, the calculated minimum, 
    maximum, and average values should be mathematically correct
    
    **Validates: Requirements 6.2**
    """

    @composite
    def ntp_result_list_with_deltas(draw):
        """Generate list of NTPResult objects with various delta values for statistical testing."""
        from ntp_monitor import NTPResult, NTPStatus
        
        # Generate 1-20 results for testing
        num_results = draw(st.integers(min_value=1, max_value=20))
        
        # Generate some successful results with delta values
        num_successful = draw(st.integers(min_value=1, max_value=num_results))
        
        results = []
        successful_deltas = []
        
        # Create successful results with delta values
        for i in range(num_successful):
            # Generate realistic delta values (±1 hour range)
            delta_seconds = draw(st.floats(
                min_value=-3600.0, 
                max_value=3600.0,
                allow_nan=False,
                allow_infinity=False
            ))
            successful_deltas.append(delta_seconds)
            
            result = NTPResult(
                timestamp_utc=datetime.now(timezone.utc),
                ntp_server=f"server{i}.example.com",
                ntp_server_ip=f"192.168.1.{i+1}",
                ntp_time_utc=datetime.now(timezone.utc),
                query_rtt_ms=50.0,
                stratum=2,
                root_delay_ms=10.0,
                root_dispersion_ms=5.0,
                delta_seconds=delta_seconds,
                delta_formatted=delta_seconds,  # Simplified for testing
                status=NTPStatus.OK,
                error_message=None
            )
            results.append(result)
        
        # Create failed results (no delta values)
        num_failed = num_results - num_successful
        for i in range(num_failed):
            # Generate different failure statuses
            # Note: Only ERROR, TIMEOUT, UNSYNCHRONIZED set has_errors=True
            failure_status = draw(st.sampled_from([
                NTPStatus.TIMEOUT, 
                NTPStatus.UNREACHABLE, 
                NTPStatus.ERROR, 
                NTPStatus.UNSYNCHRONIZED
            ]))
            
            result = NTPResult(
                timestamp_utc=datetime.now(timezone.utc),
                ntp_server=f"failed-server{i}.example.com",
                ntp_server_ip=None,
                ntp_time_utc=None,
                query_rtt_ms=None,
                stratum=None,
                root_delay_ms=None,
                root_dispersion_ms=None,
                delta_seconds=None,  # Failed queries have no delta
                delta_formatted=None,
                status=failure_status,
                error_message="Test failure"
            )
            results.append(result)
        
        # Shuffle the results to mix successful and failed ones
        # Use Hypothesis's permutation instead of random.shuffle
        results = draw(st.permutations(results))
        
        return list(results), successful_deltas

    @composite
    def all_failed_results(draw):
        """Generate list of NTPResult objects where all queries failed."""
        from ntp_monitor import NTPResult, NTPStatus
        
        # Generate 1-10 failed results
        num_results = draw(st.integers(min_value=1, max_value=10))
        
        results = []
        for i in range(num_results):
            failure_status = draw(st.sampled_from([
                NTPStatus.TIMEOUT, 
                NTPStatus.UNREACHABLE, 
                NTPStatus.ERROR, 
                NTPStatus.UNSYNCHRONIZED
            ]))
            
            result = NTPResult(
                timestamp_utc=datetime.now(timezone.utc),
                ntp_server=f"failed-server{i}.example.com",
                ntp_server_ip=None,
                ntp_time_utc=None,
                query_rtt_ms=None,
                stratum=None,
                root_delay_ms=None,
                root_dispersion_ms=None,
                delta_seconds=None,
                delta_formatted=None,
                status=failure_status,
                error_message="Test failure"
            )
            results.append(result)
        
        return results

    @given(ntp_result_list_with_deltas())
    @settings(max_examples=100, deadline=None)
    def test_statistical_calculation_accuracy_with_successful_measurements(self, result_data):
        """
        **Feature: ntp-delta-monitor, Property 10: Statistical Calculation Accuracy**
        
        Test that calculated minimum, maximum, and average values are mathematically correct.
        """
        from ntp_monitor import calculate_statistics
        import statistics as py_statistics
        
        results, expected_successful_deltas = result_data
        
        # Calculate statistics using the function under test
        stats = calculate_statistics(results)
        
        # Verify basic counts are correct
        total_servers = len(results)
        expected_successful = len(expected_successful_deltas)
        expected_failed = total_servers - expected_successful
        
        self.assertEqual(stats.total_servers, total_servers)
        self.assertEqual(stats.successful_servers, expected_successful)
        self.assertEqual(stats.failed_servers, expected_failed)
        
        # Verify statistical calculations are mathematically correct
        if expected_successful_deltas:
            # Calculate expected statistics manually
            expected_min = min(expected_successful_deltas)
            expected_max = max(expected_successful_deltas)
            expected_avg = py_statistics.mean(expected_successful_deltas)
            
            # Verify calculated statistics match expected values
            self.assertIsNotNone(stats.min_delta)
            self.assertIsNotNone(stats.max_delta)
            self.assertIsNotNone(stats.avg_delta)
            
            self.assertEqual(stats.min_delta, expected_min)
            self.assertEqual(stats.max_delta, expected_max)
            self.assertAlmostEqual(stats.avg_delta, expected_avg, places=10)
            
            # Verify mathematical relationships
            self.assertLessEqual(stats.min_delta, stats.avg_delta)
            self.assertLessEqual(stats.avg_delta, stats.max_delta)
            self.assertLessEqual(stats.min_delta, stats.max_delta)
            
        else:
            # No successful measurements - statistics should be None
            self.assertIsNone(stats.min_delta)
            self.assertIsNone(stats.max_delta)
            self.assertIsNone(stats.avg_delta)

    @given(all_failed_results())
    @settings(max_examples=100, deadline=None)
    def test_statistical_calculation_with_no_successful_measurements(self, results):
        """
        **Feature: ntp-delta-monitor, Property 10: Statistical Calculation Accuracy**
        
        Test that statistics are None when no successful measurements exist.
        """
        from ntp_monitor import calculate_statistics, NTPStatus
        
        # Calculate statistics with all failed results
        stats = calculate_statistics(results)
        
        # Verify basic counts
        self.assertEqual(stats.total_servers, len(results))
        self.assertEqual(stats.successful_servers, 0)
        self.assertEqual(stats.failed_servers, len(results))
        
        # Verify statistics are None when no successful measurements
        self.assertIsNone(stats.min_delta)
        self.assertIsNone(stats.max_delta)
        self.assertIsNone(stats.avg_delta)
        
        # Verify has_errors flag is set appropriately
        # has_errors is True only for ERROR, TIMEOUT, UNSYNCHRONIZED (not UNREACHABLE)
        error_statuses = {NTPStatus.ERROR, NTPStatus.TIMEOUT, NTPStatus.UNSYNCHRONIZED}
        result_statuses = {result.status for result in results}
        expected_has_errors = bool(error_statuses.intersection(result_statuses))
        
        self.assertEqual(stats.has_errors, expected_has_errors)

    def test_statistical_calculation_edge_cases(self):
        """
        **Feature: ntp-delta-monitor, Property 10: Statistical Calculation Accuracy**
        
        Test statistical calculations with specific edge cases.
        """
        from ntp_monitor import calculate_statistics, NTPResult, NTPStatus
        
        # Test case 1: Single successful measurement
        single_delta = 123.456
        single_result = [NTPResult(
            timestamp_utc=datetime.now(timezone.utc),
            ntp_server="single.server.com",
            ntp_server_ip="192.168.1.1",
            ntp_time_utc=datetime.now(timezone.utc),
            query_rtt_ms=50.0,
            stratum=2,
            root_delay_ms=10.0,
            root_dispersion_ms=5.0,
            delta_seconds=single_delta,
            delta_formatted=single_delta,
            status=NTPStatus.OK,
            error_message=None
        )]
        
        stats = calculate_statistics(single_result)
        
        # For single measurement, min = max = avg
        self.assertEqual(stats.min_delta, single_delta)
        self.assertEqual(stats.max_delta, single_delta)
        self.assertEqual(stats.avg_delta, single_delta)
        self.assertEqual(stats.successful_servers, 1)
        self.assertEqual(stats.failed_servers, 0)
        self.assertFalse(stats.has_errors)
        
        # Test case 2: All identical values
        identical_delta = -45.678
        identical_results = []
        for i in range(5):
            result = NTPResult(
                timestamp_utc=datetime.now(timezone.utc),
                ntp_server=f"identical{i}.server.com",
                ntp_server_ip=f"192.168.1.{i+1}",
                ntp_time_utc=datetime.now(timezone.utc),
                query_rtt_ms=50.0,
                stratum=2,
                root_delay_ms=10.0,
                root_dispersion_ms=5.0,
                delta_seconds=identical_delta,
                delta_formatted=identical_delta,
                status=NTPStatus.OK,
                error_message=None
            )
            identical_results.append(result)
        
        stats = calculate_statistics(identical_results)
        
        # For identical values, min = max = avg
        self.assertEqual(stats.min_delta, identical_delta)
        self.assertEqual(stats.max_delta, identical_delta)
        self.assertEqual(stats.avg_delta, identical_delta)
        self.assertEqual(stats.successful_servers, 5)
        self.assertEqual(stats.failed_servers, 0)
        
        # Test case 3: Zero delta values
        zero_results = []
        for i in range(3):
            result = NTPResult(
                timestamp_utc=datetime.now(timezone.utc),
                ntp_server=f"zero{i}.server.com",
                ntp_server_ip=f"192.168.1.{i+1}",
                ntp_time_utc=datetime.now(timezone.utc),
                query_rtt_ms=50.0,
                stratum=2,
                root_delay_ms=10.0,
                root_dispersion_ms=5.0,
                delta_seconds=0.0,
                delta_formatted=0.0,
                status=NTPStatus.OK,
                error_message=None
            )
            zero_results.append(result)
        
        stats = calculate_statistics(zero_results)
        
        # All zeros should result in zero statistics
        self.assertEqual(stats.min_delta, 0.0)
        self.assertEqual(stats.max_delta, 0.0)
        self.assertEqual(stats.avg_delta, 0.0)

    def test_statistical_calculation_with_extreme_values(self):
        """
        **Feature: ntp-delta-monitor, Property 10: Statistical Calculation Accuracy**
        
        Test statistical calculations with extreme positive and negative values.
        """
        from ntp_monitor import calculate_statistics, NTPResult, NTPStatus
        
        # Create results with extreme values
        extreme_deltas = [-3600.0, -1.0, 0.0, 1.0, 3600.0]  # ±1 hour range
        extreme_results = []
        
        for i, delta in enumerate(extreme_deltas):
            result = NTPResult(
                timestamp_utc=datetime.now(timezone.utc),
                ntp_server=f"extreme{i}.server.com",
                ntp_server_ip=f"192.168.1.{i+1}",
                ntp_time_utc=datetime.now(timezone.utc),
                query_rtt_ms=50.0,
                stratum=2,
                root_delay_ms=10.0,
                root_dispersion_ms=5.0,
                delta_seconds=delta,
                delta_formatted=delta,
                status=NTPStatus.OK,
                error_message=None
            )
            extreme_results.append(result)
        
        stats = calculate_statistics(extreme_results)
        
        # Verify calculations with extreme values
        expected_min = min(extreme_deltas)
        expected_max = max(extreme_deltas)
        expected_avg = sum(extreme_deltas) / len(extreme_deltas)
        
        self.assertEqual(stats.min_delta, expected_min)
        self.assertEqual(stats.max_delta, expected_max)
        self.assertAlmostEqual(stats.avg_delta, expected_avg, places=10)
        
        # Verify mathematical relationships hold
        self.assertLessEqual(stats.min_delta, stats.avg_delta)
        self.assertLessEqual(stats.avg_delta, stats.max_delta)

    def test_statistical_calculation_status_counting_accuracy(self):
        """
        **Feature: ntp-delta-monitor, Property 10: Statistical Calculation Accuracy**
        
        Test that status counting is mathematically correct.
        """
        from ntp_monitor import calculate_statistics, NTPResult, NTPStatus
        
        # Create results with known status distribution
        status_counts = {
            NTPStatus.OK: 3,
            NTPStatus.TIMEOUT: 2,
            NTPStatus.UNREACHABLE: 1,
            NTPStatus.ERROR: 1,
            NTPStatus.UNSYNCHRONIZED: 1
        }
        
        results = []
        delta_counter = 0
        
        for status, count in status_counts.items():
            for i in range(count):
                if status == NTPStatus.OK:
                    # Successful result with delta
                    delta_value = float(delta_counter)
                    delta_counter += 1
                    result = NTPResult(
                        timestamp_utc=datetime.now(timezone.utc),
                        ntp_server=f"{status.value.lower()}{i}.server.com",
                        ntp_server_ip=f"192.168.1.{len(results)+1}",
                        ntp_time_utc=datetime.now(timezone.utc),
                        query_rtt_ms=50.0,
                        stratum=2,
                        root_delay_ms=10.0,
                        root_dispersion_ms=5.0,
                        delta_seconds=delta_value,
                        delta_formatted=delta_value,
                        status=status,
                        error_message=None
                    )
                else:
                    # Failed result
                    result = NTPResult(
                        timestamp_utc=datetime.now(timezone.utc),
                        ntp_server=f"{status.value.lower()}{i}.server.com",
                        ntp_server_ip=None,
                        ntp_time_utc=None,
                        query_rtt_ms=None,
                        stratum=None,
                        root_delay_ms=None,
                        root_dispersion_ms=None,
                        delta_seconds=None,
                        delta_formatted=None,
                        status=status,
                        error_message="Test error"
                    )
                results.append(result)
        
        stats = calculate_statistics(results)
        
        # Verify total counts
        expected_total = sum(status_counts.values())
        expected_successful = status_counts[NTPStatus.OK]
        expected_failed = expected_total - expected_successful
        
        self.assertEqual(stats.total_servers, expected_total)
        self.assertEqual(stats.successful_servers, expected_successful)
        self.assertEqual(stats.failed_servers, expected_failed)
        
        # Verify status counts are accurate
        for status, expected_count in status_counts.items():
            actual_count = stats.status_counts[status.value]
            self.assertEqual(actual_count, expected_count,
                           f"Status {status.value} count should be {expected_count}, got {actual_count}")
        
        # Verify has_errors flag (should be True since we have ERROR, TIMEOUT, UNSYNCHRONIZED)
        self.assertTrue(stats.has_errors)
        
        # Verify delta statistics for successful measurements
        expected_deltas = [0.0, 1.0, 2.0]  # From the OK results
        expected_min = min(expected_deltas)
        expected_max = max(expected_deltas)
        expected_avg = sum(expected_deltas) / len(expected_deltas)
        
        self.assertEqual(stats.min_delta, expected_min)
        self.assertEqual(stats.max_delta, expected_max)
        self.assertAlmostEqual(stats.avg_delta, expected_avg, places=10)

    def test_empty_results_list(self):
        """
        **Feature: ntp-delta-monitor, Property 10: Statistical Calculation Accuracy**
        
        Test statistical calculations with empty results list.
        """
        from ntp_monitor import calculate_statistics
        
        # Test with empty list
        stats = calculate_statistics([])
        
        # Verify all counts are zero
        self.assertEqual(stats.total_servers, 0)
        self.assertEqual(stats.successful_servers, 0)
        self.assertEqual(stats.failed_servers, 0)
        
        # Verify statistics are None
        self.assertIsNone(stats.min_delta)
        self.assertIsNone(stats.max_delta)
        self.assertIsNone(stats.avg_delta)
        
        # Verify has_errors is False (no errors because no servers)
        self.assertFalse(stats.has_errors)
        
        # Verify all status counts are zero
        from ntp_monitor import NTPStatus
        for status in NTPStatus:
            self.assertEqual(stats.status_counts[status.value], 0)


class TestExitCodeDetermination(unittest.TestCase):
    """
    **Feature: ntp-delta-monitor, Property 13: Exit Code Determination**
    
    Property: For any processing run, the exit code should be 0 when all servers 
    complete without ERROR/TIMEOUT/UNSYNCHRONIZED status, and non-zero otherwise
    
    **Validates: Requirements 6.3, 6.4**
    """

    def create_summary_stats(self, total_servers, successful_servers, failed_servers, 
                           has_errors, status_counts=None):
        """Create SummaryStats object for testing."""
        from ntp_monitor import SummaryStats, NTPStatus
        
        if status_counts is None:
            status_counts = {status.value: 0 for status in NTPStatus}
        
        return SummaryStats(
            total_servers=total_servers,
            successful_servers=successful_servers,
            failed_servers=failed_servers,
            min_delta=None,
            max_delta=None,
            avg_delta=None,
            status_counts=status_counts,
            has_errors=has_errors
        )

    @composite
    def successful_stats(draw):
        """Generate SummaryStats with all successful servers (no errors)."""
        from ntp_monitor import SummaryStats, NTPStatus
        
        total_servers = draw(st.integers(min_value=1, max_value=100))
        
        # All servers successful, no errors
        status_counts = {status.value: 0 for status in NTPStatus}
        status_counts[NTPStatus.OK.value] = total_servers
        
        return SummaryStats(
            total_servers=total_servers,
            successful_servers=total_servers,
            failed_servers=0,
            min_delta=draw(st.floats(min_value=-1.0, max_value=1.0)),
            max_delta=draw(st.floats(min_value=-1.0, max_value=1.0)),
            avg_delta=draw(st.floats(min_value=-1.0, max_value=1.0)),
            status_counts=status_counts,
            has_errors=False
        )

    @composite
    def error_stats(draw):
        """Generate SummaryStats with error conditions (ERROR/TIMEOUT/UNSYNCHRONIZED)."""
        from ntp_monitor import NTPStatus, SummaryStats
        
        total_servers = draw(st.integers(min_value=1, max_value=100))
        error_servers = draw(st.integers(min_value=1, max_value=total_servers))
        successful_servers = total_servers - error_servers
        
        # Generate status counts with at least one error status
        status_counts = {status.value: 0 for status in NTPStatus}
        status_counts[NTPStatus.OK.value] = successful_servers
        
        # Distribute error servers among error statuses
        error_statuses = [NTPStatus.ERROR, NTPStatus.TIMEOUT, NTPStatus.UNSYNCHRONIZED]
        remaining_errors = error_servers
        
        for i, status in enumerate(error_statuses):
            if i == len(error_statuses) - 1:
                # Last status gets all remaining errors
                status_counts[status.value] = remaining_errors
            else:
                # Distribute some errors to this status
                count = draw(st.integers(min_value=0, max_value=remaining_errors))
                status_counts[status.value] = count
                remaining_errors -= count
        
        return SummaryStats(
            total_servers=total_servers,
            successful_servers=successful_servers,
            failed_servers=error_servers,
            min_delta=None if successful_servers == 0 else draw(st.floats(min_value=-1.0, max_value=1.0)),
            max_delta=None if successful_servers == 0 else draw(st.floats(min_value=-1.0, max_value=1.0)),
            avg_delta=None if successful_servers == 0 else draw(st.floats(min_value=-1.0, max_value=1.0)),
            status_counts=status_counts,
            has_errors=True
        )

    @composite
    def unreachable_only_stats(draw):
        """Generate SummaryStats with only UNREACHABLE status (no critical errors)."""
        from ntp_monitor import NTPStatus, SummaryStats
        
        total_servers = draw(st.integers(min_value=1, max_value=100))
        successful_servers = draw(st.integers(min_value=0, max_value=total_servers))
        unreachable_servers = total_servers - successful_servers
        
        # Only OK and UNREACHABLE statuses
        status_counts = {status.value: 0 for status in NTPStatus}
        status_counts[NTPStatus.OK.value] = successful_servers
        status_counts[NTPStatus.UNREACHABLE.value] = unreachable_servers
        
        return SummaryStats(
            total_servers=total_servers,
            successful_servers=successful_servers,
            failed_servers=unreachable_servers,
            min_delta=None if successful_servers == 0 else draw(st.floats(min_value=-1.0, max_value=1.0)),
            max_delta=None if successful_servers == 0 else draw(st.floats(min_value=-1.0, max_value=1.0)),
            avg_delta=None if successful_servers == 0 else draw(st.floats(min_value=-1.0, max_value=1.0)),
            status_counts=status_counts,
            has_errors=False  # UNREACHABLE is not considered a critical error
        )

    @given(successful_stats())
    @settings(max_examples=100, deadline=None)
    def test_all_successful_servers_return_exit_code_zero(self, stats):
        """
        **Feature: ntp-delta-monitor, Property 13: Exit Code Determination**
        
        Test that when all servers complete successfully, exit code is 0.
        """
        from ntp_monitor import determine_exit_code
        
        # Verify preconditions
        self.assertFalse(stats.has_errors)
        self.assertEqual(stats.successful_servers, stats.total_servers)
        
        # Test exit code determination
        exit_code = determine_exit_code(stats)
        
        # Verify exit code is 0 for all successful servers
        self.assertEqual(exit_code, 0)

    @given(error_stats())
    @settings(max_examples=100, deadline=None)
    def test_error_conditions_return_non_zero_exit_code(self, stats):
        """
        **Feature: ntp-delta-monitor, Property 13: Exit Code Determination**
        
        Test that when any server has ERROR/TIMEOUT/UNSYNCHRONIZED status, exit code is non-zero.
        """
        from ntp_monitor import determine_exit_code, NTPStatus
        
        # Verify preconditions - should have errors
        self.assertTrue(stats.has_errors)
        
        # Verify at least one error status is present
        error_statuses = [NTPStatus.ERROR, NTPStatus.TIMEOUT, NTPStatus.UNSYNCHRONIZED]
        has_error_status = any(stats.status_counts[status.value] > 0 for status in error_statuses)
        self.assertTrue(has_error_status)
        
        # Test exit code determination
        exit_code = determine_exit_code(stats)
        
        # Verify exit code is non-zero for error conditions
        self.assertNotEqual(exit_code, 0)
        self.assertEqual(exit_code, 1)  # Should specifically be 1

    @given(unreachable_only_stats())
    @settings(max_examples=100, deadline=None)
    def test_unreachable_only_returns_exit_code_zero(self, stats):
        """
        **Feature: ntp-delta-monitor, Property 13: Exit Code Determination**
        
        Test that UNREACHABLE status alone (without critical errors) returns exit code 0.
        """
        from ntp_monitor import determine_exit_code, NTPStatus
        
        # Verify preconditions - should not have critical errors
        self.assertFalse(stats.has_errors)
        
        # Verify only OK and UNREACHABLE statuses are present
        critical_statuses = [NTPStatus.ERROR, NTPStatus.TIMEOUT, NTPStatus.UNSYNCHRONIZED]
        has_critical_status = any(stats.status_counts[status.value] > 0 for status in critical_statuses)
        self.assertFalse(has_critical_status)
        
        # Test exit code determination
        exit_code = determine_exit_code(stats)
        
        # Verify exit code is 0 for non-critical failures
        self.assertEqual(exit_code, 0)

    def test_specific_error_status_combinations(self):
        """
        **Feature: ntp-delta-monitor, Property 13: Exit Code Determination**
        
        Test specific combinations of error statuses to ensure proper exit code determination.
        """
        from ntp_monitor import determine_exit_code, NTPStatus
        
        # Test case 1: Only ERROR status
        stats = self.create_summary_stats(
            total_servers=5,
            successful_servers=4,
            failed_servers=1,
            has_errors=True,
            status_counts={
                NTPStatus.OK.value: 4,
                NTPStatus.ERROR.value: 1,
                NTPStatus.TIMEOUT.value: 0,
                NTPStatus.UNSYNCHRONIZED.value: 0,
                NTPStatus.UNREACHABLE.value: 0
            }
        )
        exit_code = determine_exit_code(stats)
        self.assertEqual(exit_code, 1)
        
        # Test case 2: Only TIMEOUT status
        stats = self.create_summary_stats(
            total_servers=5,
            successful_servers=4,
            failed_servers=1,
            has_errors=True,
            status_counts={
                NTPStatus.OK.value: 4,
                NTPStatus.ERROR.value: 0,
                NTPStatus.TIMEOUT.value: 1,
                NTPStatus.UNSYNCHRONIZED.value: 0,
                NTPStatus.UNREACHABLE.value: 0
            }
        )
        exit_code = determine_exit_code(stats)
        self.assertEqual(exit_code, 1)
        
        # Test case 3: Only UNSYNCHRONIZED status
        stats = self.create_summary_stats(
            total_servers=5,
            successful_servers=4,
            failed_servers=1,
            has_errors=True,
            status_counts={
                NTPStatus.OK.value: 4,
                NTPStatus.ERROR.value: 0,
                NTPStatus.TIMEOUT.value: 0,
                NTPStatus.UNSYNCHRONIZED.value: 1,
                NTPStatus.UNREACHABLE.value: 0
            }
        )
        exit_code = determine_exit_code(stats)
        self.assertEqual(exit_code, 1)
        
        # Test case 4: Mixed error statuses
        stats = self.create_summary_stats(
            total_servers=10,
            successful_servers=7,
            failed_servers=3,
            has_errors=True,
            status_counts={
                NTPStatus.OK.value: 7,
                NTPStatus.ERROR.value: 1,
                NTPStatus.TIMEOUT.value: 1,
                NTPStatus.UNSYNCHRONIZED.value: 1,
                NTPStatus.UNREACHABLE.value: 0
            }
        )
        exit_code = determine_exit_code(stats)
        self.assertEqual(exit_code, 1)
        
        # Test case 5: Mixed with UNREACHABLE (should still be non-zero due to critical errors)
        stats = self.create_summary_stats(
            total_servers=10,
            successful_servers=6,
            failed_servers=4,
            has_errors=True,
            status_counts={
                NTPStatus.OK.value: 6,
                NTPStatus.ERROR.value: 1,
                NTPStatus.TIMEOUT.value: 0,
                NTPStatus.UNSYNCHRONIZED.value: 0,
                NTPStatus.UNREACHABLE.value: 3
            }
        )
        exit_code = determine_exit_code(stats)
        self.assertEqual(exit_code, 1)

    def test_edge_cases(self):
        """
        **Feature: ntp-delta-monitor, Property 13: Exit Code Determination**
        
        Test edge cases for exit code determination.
        """
        from ntp_monitor import determine_exit_code, NTPStatus
        
        # Test case 1: All servers successful
        stats = self.create_summary_stats(
            total_servers=1,
            successful_servers=1,
            failed_servers=0,
            has_errors=False,
            status_counts={
                NTPStatus.OK.value: 1,
                NTPStatus.ERROR.value: 0,
                NTPStatus.TIMEOUT.value: 0,
                NTPStatus.UNSYNCHRONIZED.value: 0,
                NTPStatus.UNREACHABLE.value: 0
            }
        )
        exit_code = determine_exit_code(stats)
        self.assertEqual(exit_code, 0)
        
        # Test case 2: All servers unreachable (no critical errors)
        stats = self.create_summary_stats(
            total_servers=3,
            successful_servers=0,
            failed_servers=3,
            has_errors=False,
            status_counts={
                NTPStatus.OK.value: 0,
                NTPStatus.ERROR.value: 0,
                NTPStatus.TIMEOUT.value: 0,
                NTPStatus.UNSYNCHRONIZED.value: 0,
                NTPStatus.UNREACHABLE.value: 3
            }
        )
        exit_code = determine_exit_code(stats)
        self.assertEqual(exit_code, 0)
        
        # Test case 3: All servers have critical errors
        stats = self.create_summary_stats(
            total_servers=3,
            successful_servers=0,
            failed_servers=3,
            has_errors=True,
            status_counts={
                NTPStatus.OK.value: 0,
                NTPStatus.ERROR.value: 1,
                NTPStatus.TIMEOUT.value: 1,
                NTPStatus.UNSYNCHRONIZED.value: 1,
                NTPStatus.UNREACHABLE.value: 0
            }
        )
        exit_code = determine_exit_code(stats)
        self.assertEqual(exit_code, 1)

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=100, deadline=None)
    def test_has_errors_flag_consistency(self, total_servers):
        """
        **Feature: ntp-delta-monitor, Property 13: Exit Code Determination**
        
        Test that the has_errors flag is consistent with exit code determination logic.
        """
        from ntp_monitor import determine_exit_code, NTPStatus
        
        # Test case 1: has_errors=True should always result in exit code 1
        stats_with_errors = self.create_summary_stats(
            total_servers=total_servers,
            successful_servers=total_servers - 1,
            failed_servers=1,
            has_errors=True,
            status_counts={
                NTPStatus.OK.value: total_servers - 1,
                NTPStatus.ERROR.value: 1,
                NTPStatus.TIMEOUT.value: 0,
                NTPStatus.UNSYNCHRONIZED.value: 0,
                NTPStatus.UNREACHABLE.value: 0
            }
        )
        exit_code = determine_exit_code(stats_with_errors)
        self.assertEqual(exit_code, 1)
        
        # Test case 2: has_errors=False should result in exit code 0
        stats_no_errors = self.create_summary_stats(
            total_servers=total_servers,
            successful_servers=total_servers,
            failed_servers=0,
            has_errors=False,
            status_counts={
                NTPStatus.OK.value: total_servers,
                NTPStatus.ERROR.value: 0,
                NTPStatus.TIMEOUT.value: 0,
                NTPStatus.UNSYNCHRONIZED.value: 0,
                NTPStatus.UNREACHABLE.value: 0
            }
        )
        exit_code = determine_exit_code(stats_no_errors)
        self.assertEqual(exit_code, 0)


if __name__ == '__main__':
    unittest.main()