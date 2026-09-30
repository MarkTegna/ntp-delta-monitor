# Changelog

All notable changes to the Certificate Expiry Monitor are documented here.

## [0.3.0] - 2026-09-29

### Added
- Structured HTML email body grouped by severity, matching the email-format
  handoff spec: Calibri/11pt, red critical alert banner, blue summary box,
  full-color Expired / Expiring Soon tables with alternating rows, green
  all-clear message, and a source-attribution line referencing the XLSX report.
- Audience-facing email subject: `Certificate Expiry Alert - X Certs Expired + Y Expiring Soon`.
- Configurable email summary window via `email_low_days` (default 14) and
  `email_high_days` (default 21) in `cert_monitor.ini`.
- Persistent `failure_count` column in the servers CSV. Increments each run a
  server's primary port cannot be contacted / no cert retrieved; resets to 0
  only on a successful primary-port cert retrieval.
- Persistent `alt_port` column in the servers CSV. Records the working fallback
  port when the primary port fails but a certificate is retrieved on an
  alternate port. The primary-port failure still increments `failure_count`.

### Changed
- Fallback-port discoveries now annotate the original server row's `alt_port`
  instead of appending new rows to the CSV.
- Servers CSV is rewritten atomically (temp file + replace) with the new
  columns; older 1-3 column CSVs upgrade automatically on first run.

### Quality
- Clean pylint run (10.00/10) with a project `.pylintrc`.
